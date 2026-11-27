//! Durable run manifest.
//!
//! The manifest is deliberately a line-oriented `key=value` file: it is easy
//! to inspect over SSH, has no dependency on a JSON crate, and can be extended
//! without breaking old readers.  Values are escaped for newlines and
//! backslashes.

use std::collections::BTreeMap;
use std::fmt;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use crate::run_id::{RelationMode, Scenario};
use crate::time::now_unix;
use crate::uuid::Uuid;

pub const MANIFEST_FORMAT: &str = "automata-v3-manifest/1";
pub const DEFAULT_DAYS_TOTAL: u32 = 1_213;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RunStatus {
    Pending,
    Running,
    Completed,
    Failed,
}

impl RunStatus {
    pub const fn key(self) -> &'static str {
        match self {
            Self::Pending => "pending",
            Self::Running => "running",
            Self::Completed => "completed",
            Self::Failed => "failed",
        }
    }

    pub fn from_key(value: &str) -> Option<Self> {
        match value.to_ascii_lowercase().as_str() {
            "pending" => Some(Self::Pending),
            "running" => Some(Self::Running),
            "completed" => Some(Self::Completed),
            "failed" => Some(Self::Failed),
            _ => None,
        }
    }
}

#[derive(Debug)]
pub enum ManifestError {
    Io(io::Error),
    InvalidFormat(String),
    MissingField(&'static str),
    InvalidValue { key: String, value: String },
}

impl fmt::Display for ManifestError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "manifest I/O error: {error}"),
            Self::InvalidFormat(format) => {
                write!(formatter, "unsupported manifest format: {format}")
            }
            Self::MissingField(key) => write!(formatter, "manifest is missing `{key}`"),
            Self::InvalidValue { key, value } => {
                write!(
                    formatter,
                    "manifest field `{key}` has invalid value `{value}`"
                )
            }
        }
    }
}

impl std::error::Error for ManifestError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            _ => None,
        }
    }
}

impl From<io::Error> for ManifestError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

#[derive(Clone, Debug)]
pub struct Manifest {
    fields: BTreeMap<String, String>,
}

impl Manifest {
    pub fn new(
        scenario: &Scenario,
        start_year: i32,
        parallelism: usize,
        master_chance: f32,
        days_total: u32,
    ) -> Self {
        let now = now_unix();
        let mut manifest = Self {
            fields: BTreeMap::new(),
        };
        manifest.set("format", MANIFEST_FORMAT);
        manifest.set("implementation", "rust");
        manifest.set("engine", "automata-university");
        manifest.set("version", env!("CARGO_PKG_VERSION"));
        manifest.set("run_id", scenario.run_id().to_string());
        manifest.set_u64("run_number", u64::from(scenario.number()));
        manifest.set("run_name", scenario.run_name());
        manifest.set("scenario_name", scenario.scenario_name());
        manifest.set("description", scenario.description());
        manifest.set("relation_mode", scenario.mode().key());
        manifest.set_u64("seed", scenario.seed());
        manifest.set_i32("start_year", start_year);
        manifest.set_u64("parallelism", parallelism as u64);
        manifest.set_f32("master_chance", master_chance);
        manifest.set_u64("days_total", u64::from(days_total));
        manifest.set_u64("days_completed", 0);
        manifest.set("status", RunStatus::Pending.key());
        manifest.set_u64("state_hash", 0);
        manifest.set_u64("snapshot_bytes", 0);
        manifest.set_u64("csv_interactions_bytes", 0);
        manifest.set_u64("csv_states_bytes", 0);
        manifest.set_u64("csv_relations_bytes", 0);
        manifest.set_u64("csv_registry_bytes", 0);
        manifest.set_u64("interactions", 0);
        manifest.set_u64("successes", 0);
        manifest.set_u64("failures", 0);
        manifest.set_u64("refusals", 0);
        manifest.set_u64("rotations", 0);
        manifest.set_u64("started_unix", now);
        manifest.set_u64("updated_unix", now);
        manifest.set_f64("wall_seconds", 0.0);
        manifest.set_f64("init_seconds", 0.0);
        manifest.set_f64("simulation_seconds", 0.0);
        manifest.set_f64("finalize_seconds", 0.0);
        manifest
    }

    pub fn load(path: &Path) -> Result<Self, ManifestError> {
        let text = fs::read_to_string(path)?;
        Self::parse(&text)
    }

    pub fn parse(text: &str) -> Result<Self, ManifestError> {
        let mut fields = BTreeMap::new();
        for line in text.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let (key, raw) = line
                .split_once('=')
                .ok_or_else(|| ManifestError::InvalidFormat(format!("line without `=`: {line}")))?;
            let key = key.trim();
            if key.is_empty() {
                return Err(ManifestError::InvalidFormat(
                    "empty manifest key".to_string(),
                ));
            }
            fields.insert(key.to_string(), decode_value(raw)?);
        }

        let format = fields
            .get("format")
            .ok_or(ManifestError::MissingField("format"))?;
        if format != MANIFEST_FORMAT {
            return Err(ManifestError::InvalidFormat(format.clone()));
        }

        Ok(Self { fields })
    }

    pub fn save(&self, path: &Path) -> Result<(), ManifestError> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let temporary = temporary_path(path);
        {
            let mut file = fs::File::create(&temporary)?;
            file.write_all(self.to_text().as_bytes())?;
            file.sync_all()?;
        }
        fs::rename(&temporary, path)?;
        Ok(())
    }

    pub fn to_text(&self) -> String {
        let mut text = String::new();
        for (key, value) in &self.fields {
            text.push_str(key);
            text.push('=');
            encode_value(value, &mut text);
            text.push('\n');
        }
        text
    }

    pub fn get(&self, key: &str) -> Option<&str> {
        self.fields.get(key).map(String::as_str)
    }

    pub fn set(&mut self, key: impl Into<String>, value: impl Into<String>) {
        self.fields.insert(key.into(), value.into());
    }

    pub fn set_u64(&mut self, key: impl Into<String>, value: u64) {
        self.set(key, value.to_string());
    }

    pub fn set_i32(&mut self, key: impl Into<String>, value: i32) {
        self.set(key, value.to_string());
    }

    pub fn set_f32(&mut self, key: impl Into<String>, value: f32) {
        self.set(key, value.to_string());
    }

    pub fn set_f64(&mut self, key: impl Into<String>, value: f64) {
        self.set(key, value.to_string());
    }

    pub fn set_bool(&mut self, key: impl Into<String>, value: bool) {
        self.set(key, if value { "true" } else { "false" });
    }

    pub fn set_status(&mut self, status: RunStatus) {
        self.set("status", status.key());
    }

    pub fn set_state_hash(&mut self, hash: u64) {
        self.set("state_hash", format!("0x{hash:016x}"));
    }

    pub fn touch(&mut self) {
        self.set_u64("updated_unix", now_unix());
    }

    pub fn require(&self, key: &'static str) -> Result<&str, ManifestError> {
        self.get(key).ok_or(ManifestError::MissingField(key))
    }

    pub fn u64_field(&self, key: &'static str) -> Result<u64, ManifestError> {
        let value = self.require(key)?;
        value.parse().map_err(|_| ManifestError::InvalidValue {
            key: key.to_string(),
            value: value.to_string(),
        })
    }

    pub fn u32_field(&self, key: &'static str) -> Result<u32, ManifestError> {
        let value = self.require(key)?;
        value.parse().map_err(|_| ManifestError::InvalidValue {
            key: key.to_string(),
            value: value.to_string(),
        })
    }

    pub fn u16_field(&self, key: &'static str) -> Result<u16, ManifestError> {
        let value = self.require(key)?;
        value.parse().map_err(|_| ManifestError::InvalidValue {
            key: key.to_string(),
            value: value.to_string(),
        })
    }

    pub fn i32_field(&self, key: &'static str) -> Result<i32, ManifestError> {
        let value = self.require(key)?;
        value.parse().map_err(|_| ManifestError::InvalidValue {
            key: key.to_string(),
            value: value.to_string(),
        })
    }

    pub fn f32_field(&self, key: &'static str) -> Result<f32, ManifestError> {
        let value = self.require(key)?;
        value.parse().map_err(|_| ManifestError::InvalidValue {
            key: key.to_string(),
            value: value.to_string(),
        })
    }

    pub fn f64_field(&self, key: &'static str) -> Result<f64, ManifestError> {
        let value = self.require(key)?;
        value.parse().map_err(|_| ManifestError::InvalidValue {
            key: key.to_string(),
            value: value.to_string(),
        })
    }

    pub fn bool_field(&self, key: &'static str) -> Result<bool, ManifestError> {
        match self.require(key)? {
            "true" | "1" | "yes" => Ok(true),
            "false" | "0" | "no" => Ok(false),
            value => Err(ManifestError::InvalidValue {
                key: key.to_string(),
                value: value.to_string(),
            }),
        }
    }

    pub fn run_id(&self) -> Result<Uuid, ManifestError> {
        let value = self.require("run_id")?;
        Uuid::parse(value).map_err(|_| ManifestError::InvalidValue {
            key: "run_id".to_string(),
            value: value.to_string(),
        })
    }

    pub fn run_number(&self) -> Result<u16, ManifestError> {
        self.u16_field("run_number")
    }

    pub fn run_name(&self) -> Result<&str, ManifestError> {
        self.require("run_name")
    }

    pub fn scenario_name(&self) -> Result<&str, ManifestError> {
        self.require("scenario_name")
    }

    pub fn relation_mode(&self) -> Result<RelationMode, ManifestError> {
        let value = self.require("relation_mode")?;
        RelationMode::from_key(value).ok_or_else(|| ManifestError::InvalidValue {
            key: "relation_mode".to_string(),
            value: value.to_string(),
        })
    }

    pub fn status(&self) -> Result<RunStatus, ManifestError> {
        let value = self.require("status")?;
        RunStatus::from_key(value).ok_or_else(|| ManifestError::InvalidValue {
            key: "status".to_string(),
            value: value.to_string(),
        })
    }

    pub fn days_completed(&self) -> Result<u32, ManifestError> {
        self.u32_field("days_completed")
    }

    pub fn days_total(&self) -> Result<u32, ManifestError> {
        self.u32_field("days_total")
    }

    pub fn seed(&self) -> Result<u64, ManifestError> {
        self.u64_field("seed")
    }

    pub fn state_hash(&self) -> Result<u64, ManifestError> {
        let value = self.require("state_hash")?;
        let digits = value.strip_prefix("0x").unwrap_or(value);
        u64::from_str_radix(digits, 16).map_err(|_| ManifestError::InvalidValue {
            key: "state_hash".to_string(),
            value: value.to_string(),
        })
    }

    pub fn snapshot_file(&self) -> Option<&str> {
        self.get("snapshot_file").filter(|value| !value.is_empty())
    }

    pub fn snapshot_sha1(&self) -> Option<&str> {
        self.get("snapshot_sha1").filter(|value| !value.is_empty())
    }

    pub fn csv_offset(&self, key: &'static str) -> Result<u64, ManifestError> {
        self.u64_field(key)
    }

    pub fn add_interactions(&mut self, success: u64, failure: u64, refusal: u64) {
        let interactions = success + failure + refusal;
        let current = self.u64_field("interactions").unwrap_or(0);
        let successes = self.u64_field("successes").unwrap_or(0);
        let failures = self.u64_field("failures").unwrap_or(0);
        let refusals = self.u64_field("refusals").unwrap_or(0);
        self.set_u64("interactions", current + interactions);
        self.set_u64("successes", successes + success);
        self.set_u64("failures", failures + failure);
        self.set_u64("refusals", refusals + refusal);
    }
}

fn temporary_path(path: &Path) -> PathBuf {
    let mut name = path.as_os_str().to_owned();
    name.push(format!(".tmp.{}", std::process::id()));
    PathBuf::from(name)
}

fn encode_value(value: &str, output: &mut String) {
    for character in value.chars() {
        match character {
            '\\' => output.push_str("\\\\"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            _ => output.push(character),
        }
    }
}

fn decode_value(raw: &str) -> Result<String, ManifestError> {
    let mut value = String::with_capacity(raw.len());
    let mut characters = raw.chars();
    while let Some(character) = characters.next() {
        if character != '\\' {
            value.push(character);
            continue;
        }
        match characters.next() {
            Some('\\') => value.push('\\'),
            Some('n') => value.push('\n'),
            Some('r') => value.push('\r'),
            Some(other) => {
                value.push('\\');
                value.push(other);
            }
            None => {
                return Err(ManifestError::InvalidFormat(
                    "dangling escape in manifest value".to_string(),
                ));
            }
        }
    }
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scenario() -> Scenario {
        Scenario::from_number(55, 42).expect("scenario")
    }

    fn manifest() -> Manifest {
        Manifest::new(&scenario(), 2024, 1, 0.3, DEFAULT_DAYS_TOTAL)
    }

    #[test]
    fn new_manifest_describes_the_run() {
        let manifest = manifest();
        assert_eq!(manifest.run_number().unwrap(), 55);
        assert_eq!(manifest.run_name().unwrap(), "Run55_Erudition");
        assert_eq!(manifest.scenario_name().unwrap(), "Run55_Erudition_EMPTY");
        assert_eq!(manifest.relation_mode().unwrap(), RelationMode::Empty);
        assert_eq!(manifest.status().unwrap(), RunStatus::Pending);
        assert_eq!(manifest.days_completed().unwrap(), 0);
        assert_eq!(manifest.days_total().unwrap(), DEFAULT_DAYS_TOTAL);
        assert_eq!(
            manifest.run_id().unwrap().to_string(),
            scenario().run_id().to_string()
        );
    }

    #[test]
    fn text_round_trip_preserves_all_fields() {
        let mut original = manifest();
        original.set("note", "a=b\nc\\d");
        original.set_state_hash(0x79f5_8093_8535_8043);
        original.set_status(RunStatus::Running);
        original.set_u64("days_completed", 17);

        let restored = Manifest::parse(&original.to_text()).expect("parse");
        assert_eq!(restored.get("note"), Some("a=b\nc\\d"));
        assert_eq!(restored.state_hash().unwrap(), 0x79f5_8093_8535_8043);
        assert_eq!(restored.status().unwrap(), RunStatus::Running);
        assert_eq!(restored.days_completed().unwrap(), 17);
    }

    #[test]
    fn save_and_load_are_atomic_and_lossless() {
        let directory = std::env::temp_dir().join(format!(
            "automata-manifest-{}-{}",
            std::process::id(),
            now_unix()
        ));
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join("manifest.txt");

        let mut original = manifest();
        original.set("note", "line one\nline two");
        original.save(&path).expect("save");
        let restored = Manifest::load(&path).expect("load");
        assert_eq!(restored.get("note"), Some("line one\nline two"));
        assert_eq!(restored.to_text(), original.to_text());

        fs::remove_dir_all(&directory).unwrap();
    }

    #[test]
    fn invalid_manifests_are_rejected() {
        assert!(matches!(
            Manifest::parse("run_id=x\n"),
            Err(ManifestError::MissingField("format"))
        ));
        assert!(matches!(
            Manifest::parse("format=other\n"),
            Err(ManifestError::InvalidFormat(_))
        ));
        let manifest = Manifest::parse("format=automata-v3-manifest/1\nrun_number=abc\n")
            .expect("format is valid");
        assert!(matches!(
            manifest.u16_field("run_number"),
            Err(ManifestError::InvalidValue { .. })
        ));
    }

    #[test]
    fn status_names_round_trip() {
        for status in [
            RunStatus::Pending,
            RunStatus::Running,
            RunStatus::Completed,
            RunStatus::Failed,
        ] {
            assert_eq!(RunStatus::from_key(status.key()), Some(status));
        }
        assert_eq!(RunStatus::from_key("unknown"), None);
    }
}
