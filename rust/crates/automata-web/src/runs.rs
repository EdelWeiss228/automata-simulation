//! Read-only access to run directories and their manifests.

use std::fs;
use std::path::{Path, PathBuf};

use automata_io::{Manifest, format_utc};

use crate::json;

#[derive(Clone, Debug)]
pub struct RunSummary {
    pub directory: String,
    pub run_id: String,
    pub run_number: u16,
    pub scenario_name: String,
    pub status: String,
    pub days_completed: u32,
    pub days_total: u32,
    pub interactions: u64,
    pub successes: u64,
    pub failures: u64,
    pub refusals: u64,
    pub rotations: u32,
    pub semesters: u32,
    pub final_hash: String,
    pub wall_seconds: f64,
    pub updated_unix: u64,
    pub updated_at: String,
}

impl RunSummary {
    pub fn from_manifest(directory: &Path, manifest: &Manifest) -> Option<Self> {
        let run_number = manifest.run_number().ok()?;
        let run_id = manifest.run_id().ok()?.to_string();
        let scenario_name = manifest.scenario_name().ok()?.to_string();
        let status = manifest
            .status()
            .map(|status| status.key().to_string())
            .unwrap_or_else(|_| "unknown".to_string());
        let days_completed = manifest.days_completed().unwrap_or(0);
        let days_total = manifest.days_total().unwrap_or(0);
        let updated_unix = manifest.u64_field("updated_unix").unwrap_or(0);
        let final_hash = manifest
            .state_hash()
            .map(|hash| format!("0x{hash:016x}"))
            .unwrap_or_else(|_| "0x0000000000000000".to_string());

        Some(Self {
            directory: directory
                .file_name()
                .map(|name| name.to_string_lossy().into_owned())
                .unwrap_or_default(),
            run_id,
            run_number,
            scenario_name,
            status,
            days_completed,
            days_total,
            interactions: manifest.u64_field("interactions").unwrap_or(0),
            successes: manifest.u64_field("successes").unwrap_or(0),
            failures: manifest.u64_field("failures").unwrap_or(0),
            refusals: manifest.u64_field("refusals").unwrap_or(0),
            rotations: manifest.u64_field("rotations").unwrap_or(0) as u32,
            semesters: manifest.u64_field("semesters").unwrap_or(0) as u32,
            final_hash,
            wall_seconds: manifest.f64_field("wall_seconds").unwrap_or(0.0),
            updated_unix,
            updated_at: if updated_unix > 0 {
                format_utc(updated_unix)
            } else {
                String::new()
            },
        })
    }

    pub fn progress(&self) -> f64 {
        if self.days_total == 0 {
            return 0.0;
        }
        (f64::from(self.days_completed) / f64::from(self.days_total)).clamp(0.0, 1.0)
    }

    pub fn to_json(&self) -> String {
        let fields = [
            json::field("directory", &json::string(&self.directory)),
            json::field("run_id", &json::string(&self.run_id)),
            json::field("run_number", &self.run_number.to_string()),
            json::field("scenario_name", &json::string(&self.scenario_name)),
            json::field("status", &json::string(&self.status)),
            json::field("days_completed", &self.days_completed.to_string()),
            json::field("days_total", &self.days_total.to_string()),
            json::field("progress", &json::number(self.progress())),
            json::field("interactions", &self.interactions.to_string()),
            json::field("successes", &self.successes.to_string()),
            json::field("failures", &self.failures.to_string()),
            json::field("refusals", &self.refusals.to_string()),
            json::field("rotations", &self.rotations.to_string()),
            json::field("semesters", &self.semesters.to_string()),
            json::field("final_hash", &json::string(&self.final_hash)),
            json::field("wall_seconds", &json::number(self.wall_seconds)),
            json::field("updated_unix", &self.updated_unix.to_string()),
            json::field("updated_at", &json::string(&self.updated_at)),
        ];
        format!("{{{}}}", fields.join(","))
    }
}

pub fn scan_runs(root: &Path) -> Vec<RunSummary> {
    let mut runs = Vec::new();
    let Ok(entries) = fs::read_dir(root) else {
        return runs;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let manifest_path = path.join("manifest.txt");
        if !manifest_path.is_file() {
            continue;
        }
        let Ok(manifest) = Manifest::load(&manifest_path) else {
            continue;
        };
        if let Some(summary) = RunSummary::from_manifest(&path, &manifest) {
            runs.push(summary);
        }
    }
    runs.sort_by(|left, right| {
        left.run_number
            .cmp(&right.run_number)
            .then_with(|| left.directory.cmp(&right.directory))
    });
    runs
}

pub fn runs_json(root: &Path) -> String {
    let runs = scan_runs(root);
    let body: Vec<String> = runs.iter().map(RunSummary::to_json).collect();
    format!("{{\"runs\":[{}]}}", body.join(","))
}

pub fn find_run(root: &Path, key: &str) -> Option<(PathBuf, RunSummary)> {
    let key = key.trim();
    if key.is_empty() || key.contains('/') || key.contains('\\') || key.contains("..") {
        return None;
    }
    for run in scan_runs(root) {
        let matches = run.directory == key
            || run.run_number.to_string() == key
            || run.run_id.eq_ignore_ascii_case(key)
            || run.scenario_name.eq_ignore_ascii_case(key);
        if matches {
            return Some((root.join(&run.directory), run));
        }
    }
    None
}

pub fn manifest_json(directory: &Path) -> String {
    let Ok(manifest) = Manifest::load(&directory.join("manifest.txt")) else {
        return "{}".to_string();
    };
    let fields: Vec<String> = manifest
        .iter()
        .map(|(key, value)| json::field(key, &json::string(value)))
        .collect();
    format!("{{{}}}", fields.join(","))
}

#[derive(Clone, Debug)]
pub struct ReportFile {
    pub name: String,
    pub bytes: u64,
}

pub const REPORT_EXTENSIONS: [&str; 6] = ["md", "json", "png", "svg", "html", "txt"];

pub fn list_reports(directory: &Path) -> Vec<ReportFile> {
    let mut reports = Vec::new();
    let Ok(entries) = fs::read_dir(directory) else {
        return reports;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let Some(extension) = path.extension().and_then(|extension| extension.to_str()) else {
            continue;
        };
        if !REPORT_EXTENSIONS
            .iter()
            .any(|allowed| extension.eq_ignore_ascii_case(allowed))
        {
            continue;
        }
        let Some(name) = path.file_name().and_then(|name| name.to_str()) else {
            continue;
        };
        let bytes = entry.metadata().map(|metadata| metadata.len()).unwrap_or(0);
        reports.push(ReportFile {
            name: name.to_string(),
            bytes,
        });
    }
    reports.sort_by(|left, right| left.name.cmp(&right.name));
    reports
}

pub fn reports_json(directory: &Path, summary: &RunSummary) -> String {
    let reports: Vec<String> = list_reports(directory)
        .iter()
        .map(|report| {
            format!(
                "{{{},{},{}}}",
                json::field("name", &json::string(&report.name)),
                json::field("bytes", &report.bytes.to_string()),
                json::field(
                    "url",
                    &json::string(&format!(
                        "/files/runs/{}/{}",
                        url_segment(&summary.directory),
                        url_segment(&report.name)
                    ))
                )
            )
        })
        .collect();
    format!("{{\"reports\":[{}]}}", reports.join(","))
}

/// Percent-encodes one URL path segment.
pub fn url_segment(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    for byte in value.bytes() {
        let unreserved = byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b'~');
        if unreserved {
            output.push(byte as char);
        } else {
            output.push_str(&format!("%{byte:02X}"));
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};

    static COUNTER: AtomicU64 = AtomicU64::new(0);

    fn temporary_directory(label: &str) -> PathBuf {
        let unique = COUNTER.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "automata-web-{}-{}-{label}-{unique}",
            std::process::id(),
            automata_io::now_unix()
        ));
        fs::create_dir_all(&path).expect("create test directory");
        path
    }

    #[test]
    fn scans_and_sorts_manifests() {
        let root = temporary_directory("scan");
        for (name, number) in [("Run56_x", 56), ("Run55_x", 55)] {
            let directory = root.join(name);
            fs::create_dir_all(&directory).unwrap();
            let scenario = automata_io::Scenario::from_number(number, 42).unwrap();
            let mut manifest = Manifest::new(&scenario, 2024, 1, 0.3, 10);
            manifest.set_u64("interactions", 100);
            manifest.save(&directory.join("manifest.txt")).unwrap();
        }
        let runs = scan_runs(&root);
        assert_eq!(runs.len(), 2);
        assert_eq!(runs[0].run_number, 55);
        assert_eq!(runs[1].run_number, 56);
        assert!(runs_json(&root).contains("\"runs\""));
        assert!(find_run(&root, "56").is_some());
        assert!(find_run(&root, "../etc").is_none());

        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn lists_reports_and_encodes_urls() {
        let root = temporary_directory("reports");
        fs::write(root.join("report.md"), "text").unwrap();
        fs::write(root.join("interactions.csv"), "ignored").unwrap();
        let reports = list_reports(&root);
        assert_eq!(reports.len(), 1);
        assert_eq!(reports[0].name, "report.md");
        assert_eq!(url_segment("a b.md"), "a%20b.md");

        fs::remove_dir_all(&root).unwrap();
    }
}
