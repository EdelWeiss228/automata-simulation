//! Resumable single-scenario runner.
//!
//! One run owns a directory:
//!
//! ```text
//! run-dir/
//!   manifest.txt
//!   snapshot.bin
//!   interactions.csv
//!   agent_states.csv
//!   agent_relations.csv
//!   agent_registry.csv
//! ```
//!
//! The manifest is the commit record.  A day is appended to the CSV files and
//! inserted into ClickHouse before `days_completed` is advanced.  Checkpoints
//! are written every `checkpoint_every` days and carry the byte offsets and
//! counters of that day.  On resume, the runner rolls the manifest back to the
//! last checkpoint, truncates the CSVs to the checkpoint offsets and deletes
//! ClickHouse rows with `day_id >= checkpoint_days`, so a crash in the middle
//! of a checkpoint interval cannot leave duplicate rows.

use std::collections::BTreeSet;
use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::time::Instant;

use automata_core::{EmotionAxis, RelationAxis};
use automata_university::runtime::SnapshotError;
use automata_university::{University, UniversityConfig};

use crate::clickhouse::{ClickHouseClient, ClickHouseConfig, ClickHouseError};
use crate::csv::{CsvFile, CsvRow};
use crate::fsutil;
use crate::manifest::{DEFAULT_DAYS_TOTAL, Manifest, ManifestError, RunStatus};
use crate::run_id::{Scenario, V3_LAST_RUN_NUMBER};
use crate::sha1::sha1_hex;
use crate::time::{format_utc, format_utc_millis, now_unix, now_unix_millis};
use crate::uuid::Uuid;

pub const MANIFEST_FILE: &str = "manifest.txt";
pub const INTERACTIONS_FILE: &str = "interactions.csv";
pub const STATES_FILE: &str = "agent_states.csv";
pub const RELATIONS_FILE: &str = "agent_relations.csv";
pub const REGISTRY_FILE: &str = "agent_registry.csv";

const CLEANUP_SLOT_ID: u32 = automata_university::DAY_SLOTS.len() as u32;

const INTERACTION_COLUMNS: [&str; 6] = ["run_id", "day_id", "slot_id", "from_id", "to_id", "type"];
const STATE_COLUMNS_FULL: [&str; 11] = [
    "run_id",
    "day_id",
    "slot_id",
    "agent_id",
    "sadness_joy",
    "fear_calm",
    "anger_humility",
    "disgust_acceptance",
    "habit_surprise",
    "shame_confidence",
    "alienation_openness",
];
const RELATION_COLUMNS: [&str; 8] = [
    "run_id",
    "day_id",
    "slot_id",
    "subject_id",
    "object_id",
    "utility",
    "affinity",
    "trust",
];
const REGISTRY_COLUMNS: [&str; 6] = [
    "run_id",
    "agent_id",
    "string_id",
    "name",
    "group_id",
    "archetype",
];
const SIMULATION_RUN_COLUMNS: [&str; 5] = [
    "run_id",
    "start_time",
    "run_name",
    "description",
    "scenario_name",
];
const RUN_TIMINGS_COLUMNS: [&str; 24] = [
    "run_id",
    "scenario",
    "implementation",
    "engine",
    "version",
    "started_at",
    "finished_at",
    "wall_seconds",
    "cpu_user_seconds",
    "cpu_system_seconds",
    "max_rss_kb",
    "init_seconds",
    "simulation_seconds",
    "finalize_seconds",
    "agents",
    "days",
    "semesters",
    "interactions",
    "seed",
    "status",
    "platform",
    "python_version",
    "omp_threads",
    "workers",
];

#[derive(Clone, Debug)]
pub struct RunOptions {
    pub scenario: Scenario,
    pub output_dir: PathBuf,
    pub start_year: i32,
    pub parallelism: usize,
    pub master_chance: f32,
    pub days: u32,
    pub checkpoint_every: u32,
    pub log_interactions: bool,
    pub log_states: bool,
    pub log_relations: bool,
    /// Write the CSV mirror next to ClickHouse.  Disable for large batches
    /// where ClickHouse is the authoritative store.
    pub csv_enabled: bool,
    pub clickhouse: Option<ClickHouseConfig>,
    pub clickhouse_required: bool,
    pub verbose: bool,
}

impl RunOptions {
    pub fn new(scenario: Scenario, output_dir: impl Into<PathBuf>) -> Self {
        Self {
            scenario,
            output_dir: output_dir.into(),
            start_year: 2024,
            parallelism: 1,
            master_chance: 0.3,
            days: DEFAULT_DAYS_TOTAL,
            checkpoint_every: 30,
            log_interactions: true,
            log_states: true,
            log_relations: true,
            csv_enabled: true,
            clickhouse: None,
            clickhouse_required: false,
            verbose: true,
        }
    }

    pub fn with_clickhouse(mut self, config: ClickHouseConfig) -> Self {
        self.clickhouse = Some(config);
        self
    }
}

#[derive(Clone, Debug)]
pub struct RunOutcome {
    pub run_id: Uuid,
    pub scenario_name: String,
    pub days_completed: u32,
    pub interactions: u64,
    pub successes: u64,
    pub failures: u64,
    pub refusals: u64,
    pub rotations: u32,
    pub semesters: u32,
    pub final_hash: u64,
    pub wall_seconds: f64,
    pub resumed: bool,
    pub completed: bool,
}

#[derive(Debug)]
pub enum RunError {
    Io(io::Error),
    Manifest(ManifestError),
    Snapshot(SnapshotError),
    ClickHouse(ClickHouseError),
    InvalidState(String),
}

impl fmt::Display for RunError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "run I/O error: {error}"),
            Self::Manifest(error) => write!(formatter, "manifest error: {error}"),
            Self::Snapshot(error) => write!(formatter, "snapshot error: {error}"),
            Self::ClickHouse(error) => write!(formatter, "ClickHouse error: {error}"),
            Self::InvalidState(message) => write!(formatter, "invalid run state: {message}"),
        }
    }
}

impl std::error::Error for RunError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Manifest(error) => Some(error),
            Self::Snapshot(error) => Some(error),
            Self::ClickHouse(error) => Some(error),
            Self::InvalidState(_) => None,
        }
    }
}

impl From<io::Error> for RunError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

impl From<ManifestError> for RunError {
    fn from(error: ManifestError) -> Self {
        Self::Manifest(error)
    }
}

impl From<SnapshotError> for RunError {
    fn from(error: SnapshotError) -> Self {
        Self::Snapshot(error)
    }
}

impl From<ClickHouseError> for RunError {
    fn from(error: ClickHouseError) -> Self {
        Self::ClickHouse(error)
    }
}

/// Runs one scenario, resuming from its manifest and snapshot when present.
pub fn run(options: &RunOptions) -> Result<RunOutcome, RunError> {
    let started = Instant::now();
    fs::create_dir_all(&options.output_dir)?;
    let manifest_path = options.output_dir.join(MANIFEST_FILE);
    let existed = manifest_path.exists();

    let mut manifest = if existed {
        Manifest::load(&manifest_path)?
    } else {
        Manifest::new(
            &options.scenario,
            options.start_year,
            options.parallelism,
            options.master_chance,
            options.days.max(1),
        )
    };
    validate_manifest(&mut manifest, options)?;

    let requested_days = if options.days == 0 {
        manifest.days_total()?
    } else {
        options.days
    };
    if manifest.status()? == RunStatus::Completed && manifest.days_completed()? >= requested_days {
        let wall_seconds =
            manifest.f64_field("wall_seconds").unwrap_or(0.0) + started.elapsed().as_secs_f64();
        return Ok(outcome_from_manifest(&manifest, wall_seconds, true, true));
    }

    if !existed {
        ensure_clean_directory(&options.output_dir)?;
    }

    let mut session = Session::open(options.clone(), manifest, manifest_path, existed, started)?;

    match session.execute() {
        Ok(outcome) => Ok(outcome),
        Err(error) => {
            session.mark_failed(&error);
            Err(error)
        }
    }
}

fn validate_manifest(manifest: &mut Manifest, options: &RunOptions) -> Result<(), RunError> {
    if manifest.run_id()? != options.scenario.run_id() {
        return Err(RunError::InvalidState(format!(
            "manifest run_id does not match {}",
            options.scenario.scenario_name()
        )));
    }
    if manifest.run_number()? != options.scenario.number() {
        return Err(RunError::InvalidState(
            "manifest run_number does not match the scenario".to_string(),
        ));
    }
    if manifest.seed()? != options.scenario.seed() {
        return Err(RunError::InvalidState(
            "manifest seed does not match the scenario".to_string(),
        ));
    }
    if manifest.scenario_name()? != options.scenario.scenario_name() {
        return Err(RunError::InvalidState(
            "manifest scenario_name does not match the scenario".to_string(),
        ));
    }
    if manifest.i32_field("start_year")? != options.start_year {
        return Err(RunError::InvalidState(
            "manifest start_year does not match the requested start year".to_string(),
        ));
    }
    let master_chance = manifest.f32_field("master_chance")?;
    if (master_chance - options.master_chance).abs() > 1e-6 {
        return Err(RunError::InvalidState(
            "manifest master_chance does not match the requested value".to_string(),
        ));
    }

    let completed = manifest.days_completed()?;
    let requested = if options.days == 0 {
        manifest.days_total()?
    } else {
        options.days
    };
    if requested < completed {
        return Err(RunError::InvalidState(format!(
            "requested horizon {requested} is shorter than the {completed} days already completed"
        )));
    }
    if requested != manifest.days_total()? {
        manifest.set_u64("days_total", u64::from(requested));
    }
    Ok(())
}

fn ensure_clean_directory(directory: &Path) -> Result<(), RunError> {
    for file in [
        INTERACTIONS_FILE,
        STATES_FILE,
        RELATIONS_FILE,
        REGISTRY_FILE,
        MANIFEST_FILE,
    ] {
        if directory.join(file).exists() {
            return Err(RunError::InvalidState(format!(
                "{} already exists; use a new run directory",
                directory.join(file).display()
            )));
        }
    }
    for entry in fs::read_dir(directory)? {
        let entry = entry?;
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if name.starts_with("snapshot-") && name.ends_with(".bin") {
            return Err(RunError::InvalidState(format!(
                "{} already contains a snapshot; use a new run directory",
                directory.display()
            )));
        }
    }
    Ok(())
}

struct SessionParts {
    university: University,
    clickhouse: Option<ClickHouseClient>,
    interactions_csv: CsvFile,
    states_csv: CsvFile,
    relations_csv: CsvFile,
    registry_csv: CsvFile,
    logged_registry: BTreeSet<String>,
    init_seconds: f64,
    semesters: u32,
    last_semester_index: Option<u32>,
}

struct Session {
    options: RunOptions,
    manifest: Manifest,
    manifest_path: PathBuf,
    started: Instant,
    resumed: bool,
    run_id_text: String,
    university: University,
    clickhouse: Option<ClickHouseClient>,
    interactions_csv: CsvFile,
    states_csv: CsvFile,
    relations_csv: CsvFile,
    registry_csv: CsvFile,
    logged_registry: BTreeSet<String>,
    init_seconds: f64,
    semesters: u32,
    last_semester_index: Option<u32>,
}

impl Session {
    fn open(
        options: RunOptions,
        mut manifest: Manifest,
        manifest_path: PathBuf,
        existed: bool,
        started: Instant,
    ) -> Result<Self, RunError> {
        let parts = match open_inner(&options, &mut manifest, &manifest_path, existed) {
            Ok(parts) => parts,
            Err(error) => {
                manifest.set_status(RunStatus::Failed);
                manifest.set("error", error.to_string());
                manifest.touch();
                let _ = manifest.save(&manifest_path);
                return Err(error);
            }
        };

        let run_id_text = manifest.run_id()?.to_string();
        let mut session = Self {
            options,
            manifest,
            manifest_path,
            started,
            resumed: existed,
            run_id_text,
            university: parts.university,
            clickhouse: parts.clickhouse,
            interactions_csv: parts.interactions_csv,
            states_csv: parts.states_csv,
            relations_csv: parts.relations_csv,
            registry_csv: parts.registry_csv,
            logged_registry: parts.logged_registry,
            init_seconds: parts.init_seconds,
            semesters: parts.semesters,
            last_semester_index: parts.last_semester_index,
        };

        if let Err(error) = session.initialise_registry_and_state() {
            session.mark_failed(&error);
            return Err(error);
        }
        session.manifest.touch();
        session.manifest.save(&session.manifest_path)?;
        Ok(session)
    }

    /// Writes the registry and the pre-interaction state of day 0.
    ///
    /// v2 logs one state row per agent before the first step (slot 0) and then
    /// only at `CLEANUP` on non-Sunday days.  The first day is a Sunday, so
    /// this initial row is the only state row for day 0.
    fn initialise_registry_and_state(&mut self) -> Result<(), RunError> {
        self.log_registry()?;
        if self.manifest.days_completed()? == 0 && self.options.log_states {
            let mut buffer = String::new();
            append_states(&self.university, &self.run_id_text, 0, 0, &mut buffer);
            if self.options.csv_enabled {
                self.states_csv.write_raw(&buffer)?;
                self.states_csv.flush()?;
                self.manifest
                    .set_u64("csv_states_bytes", self.states_csv.len());
            }
            if let Some(client) = &self.clickhouse {
                client.insert("agent_states", &STATE_COLUMNS_FULL, &buffer)?;
            }
        }
        Ok(())
    }

    fn execute(&mut self) -> Result<RunOutcome, RunError> {
        let simulation_start = Instant::now();
        let days_total = self.manifest.days_total()?;
        let mut row = CsvRow::new();
        let mut interaction_buffer = String::new();
        let mut state_buffer = String::new();
        let mut relation_buffer = String::new();

        while self.manifest.days_completed()? < days_total {
            let Some(day) = self.university.step_day() else {
                break;
            };
            let day_id = day.day_id;

            interaction_buffer.clear();
            state_buffer.clear();
            relation_buffer.clear();

            if self.options.log_interactions {
                for event in &day.interactions {
                    row.clear();
                    row.field(&self.run_id_text)
                        .display(day_id)
                        .display(event.slot_id)
                        .display(event.from.index())
                        .display(event.to.index())
                        .display(event.outcome.as_i8());
                    interaction_buffer.push_str(row.finish());
                }
            }

            if !day.is_sunday && self.options.log_states {
                append_states(
                    &self.university,
                    &self.run_id_text,
                    day_id,
                    CLEANUP_SLOT_ID,
                    &mut state_buffer,
                );
            }

            if !day.is_sunday && self.options.log_relations {
                let n = self.university.world.len();
                for from in 0..n {
                    for to in 0..n {
                        if from == to {
                            continue;
                        }
                        let relation = self.university.world.relations[from * n + to];
                        if relation.is_zero() {
                            continue;
                        }
                        row.clear();
                        row.field(&self.run_id_text)
                            .display(day_id)
                            .display(CLEANUP_SLOT_ID)
                            .display(from)
                            .display(to);
                        for axis in RelationAxis::ALL {
                            row.display(relation.get(axis));
                        }
                        relation_buffer.push_str(row.finish());
                    }
                }
            }

            if self.options.csv_enabled {
                if self.options.log_interactions {
                    self.interactions_csv.write_raw(&interaction_buffer)?;
                }
                if self.options.log_states {
                    self.states_csv.write_raw(&state_buffer)?;
                }
                if self.options.log_relations {
                    self.relations_csv.write_raw(&relation_buffer)?;
                }
                self.interactions_csv.flush()?;
                self.states_csv.flush()?;
                self.relations_csv.flush()?;
            }

            if let Some(client) = &self.clickhouse {
                if self.options.log_interactions {
                    client.insert("interactions", &INTERACTION_COLUMNS, &interaction_buffer)?;
                }
                if self.options.log_states {
                    client.insert("agent_states", &STATE_COLUMNS_FULL, &state_buffer)?;
                }
                if self.options.log_relations {
                    client.insert("agent_relations", &RELATION_COLUMNS, &relation_buffer)?;
                }
            }

            let successes = day.successes() as u64;
            let failures = day.failures() as u64;
            let refusals = day.refusals() as u64;
            self.manifest
                .add_interactions(successes, failures, refusals);

            let rotations =
                self.manifest.u64_field("rotations")? + u64::from(day.rotation.is_some());
            self.manifest.set_u64("rotations", rotations);

            match self.last_semester_index {
                None => {
                    self.semesters = 1;
                    self.last_semester_index = Some(day.semester_index);
                }
                Some(previous) if previous != day.semester_index => {
                    self.semesters += 1;
                    self.last_semester_index = Some(day.semester_index);
                }
                _ => {}
            }
            self.manifest
                .set_u64("semesters", u64::from(self.semesters));
            self.manifest
                .set_u64("last_semester_index", u64::from(day.semester_index));

            let days_completed = self.manifest.days_completed()? + 1;
            self.manifest
                .set_u64("days_completed", u64::from(days_completed));
            self.manifest.set_state_hash(self.university.state_hash());
            self.manifest
                .set_u64("csv_interactions_bytes", self.interactions_csv.len());
            self.manifest
                .set_u64("csv_states_bytes", self.states_csv.len());
            self.manifest
                .set_u64("csv_relations_bytes", self.relations_csv.len());

            if day.rotation.is_some() {
                self.log_registry()?;
            }

            let should_checkpoint = self.options.checkpoint_every > 0
                && (days_completed % self.options.checkpoint_every == 0
                    || days_completed >= days_total);
            if should_checkpoint {
                self.write_checkpoint(days_completed)?;
            }

            self.manifest.touch();
            self.manifest.save(&self.manifest_path)?;

            if self.options.verbose && (days_completed % 25 == 0 || days_completed >= days_total) {
                println!(
                    "[{}] day {days_completed}/{days_total} interactions={} hash=0x{:016x}",
                    self.options.scenario.scenario_name(),
                    self.manifest.u64_field("interactions")?,
                    self.manifest.state_hash()?
                );
            }
        }

        let simulation_seconds = simulation_start.elapsed().as_secs_f64();
        self.finalize(simulation_seconds)
    }

    fn finalize(&mut self, simulation_seconds: f64) -> Result<RunOutcome, RunError> {
        let finalize_start = Instant::now();
        let days_completed = self.manifest.days_completed()?;
        if days_completed > 0 {
            self.write_checkpoint(days_completed)?;
        }

        let previous_wall = self.manifest.f64_field("wall_seconds").unwrap_or(0.0);
        let previous_init = self.manifest.f64_field("init_seconds").unwrap_or(0.0);
        let previous_simulation = self.manifest.f64_field("simulation_seconds").unwrap_or(0.0);
        let previous_finalize = self.manifest.f64_field("finalize_seconds").unwrap_or(0.0);

        self.manifest.set_status(RunStatus::Completed);
        self.manifest.set_u64("finished_unix", now_unix());
        self.manifest.set_f64(
            "wall_seconds",
            previous_wall + self.started.elapsed().as_secs_f64(),
        );
        self.manifest
            .set_f64("init_seconds", previous_init + self.init_seconds);
        self.manifest.set_f64(
            "simulation_seconds",
            previous_simulation + simulation_seconds,
        );
        self.manifest.set_f64(
            "finalize_seconds",
            previous_finalize + finalize_start.elapsed().as_secs_f64(),
        );
        self.manifest.touch();
        self.manifest.save(&self.manifest_path)?;

        if let Err(error) = self.write_timings(RunStatus::Completed) {
            eprintln!("warning: failed to write ClickHouse timings: {error}");
        }

        Ok(outcome_from_manifest(
            &self.manifest,
            self.started.elapsed().as_secs_f64(),
            self.resumed,
            true,
        ))
    }

    fn write_checkpoint(&mut self, days_completed: u32) -> Result<(), RunError> {
        let bytes = self.university.to_snapshot();
        let filename = "snapshot.bin";
        let path = self.options.output_dir.join(filename);
        fsutil::write_atomic(&path, &bytes)?;
        self.manifest.set("snapshot_file", filename);
        self.manifest.set("snapshot_sha1", sha1_hex(&bytes));
        self.manifest.set_u64("snapshot_bytes", bytes.len() as u64);

        self.manifest
            .set_u64("checkpoint_days", u64::from(days_completed));
        self.manifest.set(
            "checkpoint_state_hash",
            format!("0x{:016x}", self.university.state_hash()),
        );
        for (current, checkpoint) in [
            ("interactions", "checkpoint_interactions"),
            ("successes", "checkpoint_successes"),
            ("failures", "checkpoint_failures"),
            ("refusals", "checkpoint_refusals"),
            ("rotations", "checkpoint_rotations"),
            ("semesters", "checkpoint_semesters"),
        ] {
            let value = self.manifest.u64_field(current)?;
            self.manifest.set_u64(checkpoint, value);
        }
        self.manifest.set_u64(
            "checkpoint_last_semester_index",
            self.last_semester_index.map(u64::from).unwrap_or(u64::MAX),
        );
        self.manifest.set_u64(
            "checkpoint_csv_interactions_bytes",
            self.interactions_csv.len(),
        );
        self.manifest
            .set_u64("checkpoint_csv_states_bytes", self.states_csv.len());
        self.manifest
            .set_u64("checkpoint_csv_relations_bytes", self.relations_csv.len());
        self.manifest
            .set_u64("checkpoint_csv_registry_bytes", self.registry_csv.len());
        Ok(())
    }

    fn log_registry(&mut self) -> Result<(), RunError> {
        let mut buffer = String::new();
        let mut row = CsvRow::new();
        for (index, student) in self.university.population.students.iter().enumerate() {
            if !self.logged_registry.insert(student.string_id.clone()) {
                continue;
            }
            row.clear();
            row.field(&self.run_id_text)
                .display(index)
                .field(&student.string_id)
                .field(&student.name)
                .field(&student.group)
                .field(student.archetype.name());
            buffer.push_str(row.finish());
        }
        if buffer.is_empty() {
            return Ok(());
        }
        if self.options.csv_enabled {
            self.registry_csv.write_raw(&buffer)?;
            self.registry_csv.flush()?;
            self.manifest
                .set_u64("csv_registry_bytes", self.registry_csv.len());
        }
        if let Some(client) = &self.clickhouse {
            client.insert("agent_registry", &REGISTRY_COLUMNS, &buffer)?;
        }
        Ok(())
    }

    fn write_timings(&self, status: RunStatus) -> Result<(), RunError> {
        let Some(client) = &self.clickhouse else {
            return Ok(());
        };
        let run_id = self.manifest.run_id()?;
        let delete = format!(
            "ALTER TABLE {}.run_timings DELETE WHERE run_id = '{}' SETTINGS mutations_sync = 1",
            client.config().database,
            run_id
        );
        client.execute(&delete)?;

        let mut row = CsvRow::new();
        row.field(&run_id.to_string())
            .field(&self.options.scenario.scenario_name())
            .field("rust")
            .field("automata-university")
            .field(env!("CARGO_PKG_VERSION"))
            .field(&format_utc_millis(
                u128::from(self.manifest.u64_field("started_unix")?) * 1_000,
            ))
            .field(&format_utc_millis(now_unix_millis()))
            .display(
                self.manifest.f64_field("wall_seconds").unwrap_or(0.0)
                    + self.started.elapsed().as_secs_f64(),
            )
            .display(0.0)
            .display(0.0)
            .display(0u64)
            .display(self.manifest.f64_field("init_seconds").unwrap_or(0.0) + self.init_seconds)
            .display(self.manifest.f64_field("simulation_seconds").unwrap_or(0.0))
            .display(self.manifest.f64_field("finalize_seconds").unwrap_or(0.0))
            .display(self.university.len() as u32)
            .display(self.manifest.days_completed()?)
            .display(self.semesters as u8)
            .display(self.manifest.u64_field("interactions")?)
            .display(self.options.scenario.seed() as i64)
            .field(status.key())
            .field(&format!(
                "{}-{}",
                std::env::consts::OS,
                std::env::consts::ARCH
            ))
            .field("")
            .field(&self.options.parallelism.to_string())
            .field(&self.options.parallelism.to_string());

        client.insert("run_timings", &RUN_TIMINGS_COLUMNS, row.finish())?;
        Ok(())
    }

    fn mark_failed(&mut self, error: &RunError) {
        self.manifest.set_status(RunStatus::Failed);
        self.manifest.set("error", error.to_string());
        self.manifest.touch();
        if let Err(save_error) = self.manifest.save(&self.manifest_path) {
            eprintln!("warning: failed to save the failed manifest: {save_error}");
        }
        if let Err(timing_error) = self.write_timings(RunStatus::Failed) {
            eprintln!("warning: failed to write ClickHouse timings: {timing_error}");
        }
    }
}

fn open_inner(
    options: &RunOptions,
    manifest: &mut Manifest,
    manifest_path: &Path,
    existed: bool,
) -> Result<SessionParts, RunError> {
    manifest.set_status(RunStatus::Running);
    manifest.set("error", "");
    manifest.touch();
    manifest.save(manifest_path)?;

    let init_start = Instant::now();
    let days_completed = manifest.days_completed()?;
    let resume_days = if days_completed == 0 {
        0
    } else {
        manifest
            .u64_field("checkpoint_days")
            .unwrap_or(u64::from(days_completed))
            .min(u64::from(days_completed)) as u32
    };

    let mut university = if resume_days > 0 {
        let snapshot_file = manifest.snapshot_file().ok_or_else(|| {
            RunError::InvalidState("manifest has completed days but no snapshot_file".to_string())
        })?;
        let path = resolve_snapshot_path(&options.output_dir, snapshot_file);
        let bytes = fs::read(&path)?;
        if let Some(expected) = manifest.snapshot_sha1() {
            let actual = sha1_hex(&bytes);
            if actual != expected {
                return Err(RunError::InvalidState(format!(
                    "snapshot {} checksum mismatch: expected {expected}, got {actual}",
                    path.display()
                )));
            }
        }
        let university = University::from_snapshot(&bytes)?;
        if university.days_completed() != resume_days {
            return Err(RunError::InvalidState(format!(
                "snapshot contains {} days but the last checkpoint is at {resume_days}",
                university.days_completed()
            )));
        }
        let expected_hash = manifest
            .get("checkpoint_state_hash")
            .and_then(parse_hex_u64)
            .unwrap_or(manifest.state_hash()?);
        if university.state_hash() != expected_hash {
            return Err(RunError::InvalidState(
                "snapshot state hash does not match the last checkpoint".to_string(),
            ));
        }
        university
    } else {
        University::new(UniversityConfig {
            seed: options.scenario.seed(),
            start_year: options.start_year,
            parallelism: options.parallelism,
            init_mode: options.scenario.mode().init_mode(),
            master_chance: options.master_chance,
            bachelor_weights: options.scenario.bachelor_weights(),
            master_weights: options.scenario.master_weights(),
        })
    };
    university.world.config.parallelism = options.parallelism;
    let init_seconds = init_start.elapsed().as_secs_f64();

    if existed {
        restore_checkpoint(manifest, resume_days)?;
    }
    manifest.set_u64("parallelism", options.parallelism as u64);

    let clickhouse = connect_clickhouse(options)?;
    if let Some(client) = &clickhouse {
        let run_id = manifest.run_id()?;
        let already_exists = client.run_exists(run_id)?;
        if !existed && already_exists {
            return Err(RunError::InvalidState(format!(
                "ClickHouse already contains run_id {run_id}; refusing to overwrite it"
            )));
        }
        if !already_exists {
            insert_run_metadata(client, manifest)?;
        }
        // A previous attempt may have written rows without committing the
        // manifest (or without a simulation_runs row).  Clearing the tail and
        // the registry makes the fresh and resumed paths idempotent.
        client.delete_days(run_id, resume_days)?;
        client.delete_registry(run_id)?;
    }

    truncate_csvs(options, manifest)?;
    let interactions_csv = CsvFile::open(
        options.output_dir.join(INTERACTIONS_FILE),
        Some(&INTERACTION_COLUMNS[..]),
    )?;
    let states_csv = CsvFile::open(
        options.output_dir.join(STATES_FILE),
        Some(&STATE_COLUMNS_FULL[..]),
    )?;
    let relations_csv = CsvFile::open(
        options.output_dir.join(RELATIONS_FILE),
        Some(&RELATION_COLUMNS[..]),
    )?;
    let registry_csv = CsvFile::open(
        options.output_dir.join(REGISTRY_FILE),
        Some(&REGISTRY_COLUMNS[..]),
    )?;

    let semesters = manifest.u64_field("semesters").unwrap_or(0) as u32;
    let last_semester_index = manifest
        .get("last_semester_index")
        .and_then(|value| value.parse().ok());

    Ok(SessionParts {
        university,
        clickhouse,
        interactions_csv,
        states_csv,
        relations_csv,
        registry_csv,
        logged_registry: BTreeSet::new(),
        init_seconds,
        semesters,
        last_semester_index,
    })
}

fn connect_clickhouse(options: &RunOptions) -> Result<Option<ClickHouseClient>, RunError> {
    let Some(config) = options.clickhouse.clone() else {
        return Ok(None);
    };
    let client = ClickHouseClient::new(config);
    match client.ping() {
        Ok(()) => Ok(Some(client)),
        Err(error) if options.clickhouse_required => Err(error.into()),
        Err(error) => {
            eprintln!("warning: ClickHouse is unavailable ({error}); continuing with CSV only");
            Ok(None)
        }
    }
}

fn insert_run_metadata(client: &ClickHouseClient, manifest: &Manifest) -> Result<(), RunError> {
    let run_id = manifest.run_id()?;
    let mut row = CsvRow::new();
    row.field(&run_id.to_string())
        .field(&format_utc(manifest.u64_field("started_unix")?))
        .field(manifest.run_name()?)
        .field(manifest.require("description")?)
        .field(manifest.scenario_name()?);
    client.insert("simulation_runs", &SIMULATION_RUN_COLUMNS, row.finish())?;
    Ok(())
}

/// Rolls the manifest back to the last durable checkpoint.
///
/// The manifest is advanced after every day, while the snapshot is written
/// every `checkpoint_every` days.  A crash therefore leaves at most one
/// checkpoint interval of CSV/ClickHouse rows that have to be discarded.
fn restore_checkpoint(manifest: &mut Manifest, resume_days: u32) -> Result<(), RunError> {
    manifest.set_u64("days_completed", u64::from(resume_days));

    if manifest.get("checkpoint_days").is_some() {
        for (current, checkpoint) in [
            ("interactions", "checkpoint_interactions"),
            ("successes", "checkpoint_successes"),
            ("failures", "checkpoint_failures"),
            ("refusals", "checkpoint_refusals"),
            ("rotations", "checkpoint_rotations"),
            ("semesters", "checkpoint_semesters"),
        ] {
            let value = manifest
                .u64_field(checkpoint)
                .or_else(|_| manifest.u64_field(current))?;
            manifest.set_u64(current, value);
        }
        if let Some(hash) = manifest
            .get("checkpoint_state_hash")
            .and_then(parse_hex_u64)
        {
            manifest.set_state_hash(hash);
        }
        if let Ok(value) = manifest.u64_field("checkpoint_last_semester_index") {
            manifest.set_u64("last_semester_index", value);
        }
        for (current, checkpoint) in [
            (
                "csv_interactions_bytes",
                "checkpoint_csv_interactions_bytes",
            ),
            ("csv_states_bytes", "checkpoint_csv_states_bytes"),
            ("csv_relations_bytes", "checkpoint_csv_relations_bytes"),
            ("csv_registry_bytes", "checkpoint_csv_registry_bytes"),
        ] {
            let value = manifest
                .u64_field(checkpoint)
                .or_else(|_| manifest.u64_field(current))?;
            manifest.set_u64(current, value);
        }
    } else if resume_days == 0 {
        for key in [
            "interactions",
            "successes",
            "failures",
            "refusals",
            "rotations",
            "semesters",
            "csv_interactions_bytes",
            "csv_states_bytes",
            "csv_relations_bytes",
            "csv_registry_bytes",
        ] {
            manifest.set_u64(key, 0);
        }
        manifest.set_state_hash(0);
        manifest.set_u64("last_semester_index", u64::MAX);
    }

    // The registry is rebuilt from the restored roster, so its old byte
    // offset is never used after a resume.
    manifest.set_u64("csv_registry_bytes", 0);
    Ok(())
}

fn parse_hex_u64(value: &str) -> Option<u64> {
    let digits = value.strip_prefix("0x").unwrap_or(value);
    u64::from_str_radix(digits, 16).ok()
}

fn truncate_csvs(options: &RunOptions, manifest: &Manifest) -> Result<(), RunError> {
    for (file, key) in [
        (INTERACTIONS_FILE, "csv_interactions_bytes"),
        (STATES_FILE, "csv_states_bytes"),
        (RELATIONS_FILE, "csv_relations_bytes"),
        (REGISTRY_FILE, "csv_registry_bytes"),
    ] {
        fsutil::truncate_to(&options.output_dir.join(file), manifest.csv_offset(key)?)?;
    }
    Ok(())
}

fn resolve_snapshot_path(output_dir: &Path, file: &str) -> PathBuf {
    let path = Path::new(file);
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        output_dir.join(path)
    }
}

fn append_states(
    university: &University,
    run_id: &str,
    day_id: u32,
    slot_id: u32,
    buffer: &mut String,
) {
    let mut row = CsvRow::new();
    for (index, agent) in university.world.agents.iter().enumerate() {
        row.clear();
        row.field(run_id)
            .display(day_id)
            .display(slot_id)
            .display(index);
        for axis in EmotionAxis::ALL {
            row.display(agent.emotions.get(axis).get());
        }
        buffer.push_str(row.finish());
    }
}

fn outcome_from_manifest(
    manifest: &Manifest,
    wall_seconds: f64,
    resumed: bool,
    completed: bool,
) -> RunOutcome {
    RunOutcome {
        run_id: manifest.run_id().unwrap_or(Uuid::from_bytes([0; 16])),
        scenario_name: manifest.scenario_name().unwrap_or("").to_string(),
        days_completed: manifest.days_completed().unwrap_or(0),
        interactions: manifest.u64_field("interactions").unwrap_or(0),
        successes: manifest.u64_field("successes").unwrap_or(0),
        failures: manifest.u64_field("failures").unwrap_or(0),
        refusals: manifest.u64_field("refusals").unwrap_or(0),
        rotations: manifest.u64_field("rotations").unwrap_or(0) as u32,
        semesters: manifest.u64_field("semesters").unwrap_or(0) as u32,
        final_hash: manifest.state_hash().unwrap_or(0),
        wall_seconds,
        resumed,
        completed,
    }
}

/// Convenience for batch code: the highest reserved v3 run number.
pub const LAST_V3_RUN_NUMBER: u16 = V3_LAST_RUN_NUMBER;

#[cfg(test)]
mod tests {
    use super::*;

    fn temporary_directory(label: &str) -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "automata-runner-{}-{}-{label}",
            std::process::id(),
            now_unix()
        ));
        fs::create_dir_all(&path).expect("create test directory");
        path
    }

    fn short_options(directory: &Path, days: u32) -> RunOptions {
        let scenario = Scenario::from_number(55, 42).expect("scenario");
        let mut options = RunOptions::new(scenario, directory);
        options.days = days;
        options.checkpoint_every = 1;
        options.verbose = false;
        options
    }

    #[test]
    fn short_run_writes_csvs_and_a_completed_manifest() {
        let directory = temporary_directory("short");
        let outcome = run(&short_options(&directory, 3)).expect("run");
        assert!(outcome.completed);
        assert!(!outcome.resumed);
        assert_eq!(outcome.days_completed, 3);
        assert!(outcome.interactions > 0);

        let manifest = Manifest::load(&directory.join(MANIFEST_FILE)).expect("manifest");
        assert_eq!(manifest.status().unwrap(), RunStatus::Completed);
        assert_eq!(manifest.days_completed().unwrap(), 3);
        assert!(manifest.get("snapshot_file").is_some());

        let states = fs::read_to_string(directory.join(STATES_FILE)).expect("states");
        let mut lines = states.lines();
        assert_eq!(
            lines.next().unwrap(),
            STATE_COLUMNS_FULL.join(","),
            "state header"
        );
        let first = lines.next().expect("initial state row");
        assert!(first.contains(",0,0,"), "initial state is day 0 slot 0");
        assert_eq!(
            states.lines().count(),
            1 + 1_620 * 3,
            "initial state plus two non-Sunday days"
        );

        let registry = fs::read_to_string(directory.join(REGISTRY_FILE)).expect("registry");
        assert_eq!(registry.lines().count(), 1 + 1_620);

        let interactions =
            fs::read_to_string(directory.join(INTERACTIONS_FILE)).expect("interactions");
        assert!(interactions.lines().count() > 1);

        let relations = fs::read_to_string(directory.join(RELATIONS_FILE)).expect("relations");
        assert!(relations.lines().count() > 1);

        fs::remove_dir_all(&directory).unwrap();
    }

    #[test]
    fn resume_matches_a_continuous_run() {
        let continuous_directory = temporary_directory("continuous");
        let continuous = run(&short_options(&continuous_directory, 4)).expect("continuous run");

        let resumed_directory = temporary_directory("resumed");
        let first = run(&short_options(&resumed_directory, 2)).expect("first segment");
        assert!(first.completed);

        let manifest_path = resumed_directory.join(MANIFEST_FILE);
        let mut manifest = Manifest::load(&manifest_path).expect("manifest");
        manifest.set_status(RunStatus::Running);
        manifest
            .save(&manifest_path)
            .expect("save running manifest");

        let resumed = run(&short_options(&resumed_directory, 4)).expect("resumed run");
        assert!(resumed.completed);
        assert!(resumed.resumed);
        assert_eq!(resumed.days_completed, 4);
        assert_eq!(resumed.final_hash, continuous.final_hash);

        let registry = fs::read_to_string(resumed_directory.join(REGISTRY_FILE)).expect("registry");
        assert_eq!(
            registry.lines().count(),
            1 + 1_620,
            "registry is rebuilt, not duplicated"
        );

        fs::remove_dir_all(&continuous_directory).unwrap();
        fs::remove_dir_all(&resumed_directory).unwrap();
    }

    #[test]
    fn resume_rolls_back_to_the_last_checkpoint() {
        let baseline_directory = temporary_directory("rollback-baseline");
        let baseline = run(&short_options(&baseline_directory, 4)).expect("baseline");

        let directory = temporary_directory("rollback");
        let first = run(&short_options(&directory, 2)).expect("checkpoint segment");
        assert!(first.completed);

        let manifest_path = directory.join(MANIFEST_FILE);
        let snapshot_path = directory.join("snapshot.bin");
        let checkpoint_manifest = Manifest::load(&manifest_path).expect("checkpoint manifest");
        let checkpoint_snapshot = fs::read(&snapshot_path).expect("checkpoint snapshot");

        let mut manifest = Manifest::load(&manifest_path).expect("manifest");
        manifest.set_status(RunStatus::Running);
        manifest.set_u64("days_total", 3);
        manifest.save(&manifest_path).expect("save");
        let third = run(&short_options(&directory, 3)).expect("third day");
        assert_eq!(third.days_completed, 3);

        // Simulate a crash after day 3: the manifest advanced, but the last
        // durable snapshot is still the one from day 2.  The CSV tail is also
        // longer than the checkpoint offsets.
        let mut crashed = Manifest::load(&manifest_path).expect("crashed manifest");
        for key in [
            "checkpoint_days",
            "checkpoint_state_hash",
            "checkpoint_interactions",
            "checkpoint_successes",
            "checkpoint_failures",
            "checkpoint_refusals",
            "checkpoint_rotations",
            "checkpoint_semesters",
            "checkpoint_last_semester_index",
            "checkpoint_csv_interactions_bytes",
            "checkpoint_csv_states_bytes",
            "checkpoint_csv_relations_bytes",
            "checkpoint_csv_registry_bytes",
            "snapshot_file",
            "snapshot_sha1",
            "snapshot_bytes",
        ] {
            if let Some(value) = checkpoint_manifest.get(key) {
                crashed.set(key, value);
            }
        }
        crashed.set_status(RunStatus::Running);
        crashed.set_u64("days_total", 4);
        crashed.save(&manifest_path).expect("save crashed manifest");
        fs::write(&snapshot_path, &checkpoint_snapshot).expect("restore old snapshot");
        for file in [INTERACTIONS_FILE, STATES_FILE, RELATIONS_FILE] {
            let path = directory.join(file);
            let mut text = fs::read_to_string(&path).expect("csv");
            text.push_str("partial-row,after,checkpoint\n");
            fs::write(&path, text).expect("append junk");
        }

        let resumed = run(&short_options(&directory, 4)).expect("resumed run");
        assert!(resumed.completed);
        assert_eq!(resumed.final_hash, baseline.final_hash);

        for file in [INTERACTIONS_FILE, STATES_FILE, RELATIONS_FILE] {
            let baseline_text =
                fs::read_to_string(baseline_directory.join(file)).expect("baseline");
            let resumed_text = fs::read_to_string(directory.join(file)).expect("resumed");
            assert_eq!(baseline_text, resumed_text, "{file} differs");
        }

        fs::remove_dir_all(&baseline_directory).unwrap();
        fs::remove_dir_all(&directory).unwrap();
    }

    #[test]
    fn completed_run_can_be_extended_to_a_longer_horizon() {
        let baseline_directory = temporary_directory("extend-baseline");
        let baseline = run(&short_options(&baseline_directory, 4)).expect("baseline");

        let directory = temporary_directory("extend");
        let short = run(&short_options(&directory, 2)).expect("short run");
        assert!(short.completed);
        assert_eq!(short.days_completed, 2);

        let extended = run(&short_options(&directory, 4)).expect("extended run");
        assert!(extended.completed);
        assert_eq!(extended.days_completed, 4);
        assert_eq!(extended.final_hash, baseline.final_hash);

        for file in [
            INTERACTIONS_FILE,
            STATES_FILE,
            RELATIONS_FILE,
            REGISTRY_FILE,
        ] {
            let baseline_text =
                fs::read_to_string(baseline_directory.join(file)).expect("baseline");
            let extended_text = fs::read_to_string(directory.join(file)).expect("extended");
            assert_eq!(baseline_text, extended_text, "{file} differs");
        }

        fs::remove_dir_all(&baseline_directory).unwrap();
        fs::remove_dir_all(&directory).unwrap();
    }

    #[test]
    fn csv_can_be_disabled_for_clickhouse_only_runs() {
        let directory = temporary_directory("no-csv");
        let mut options = short_options(&directory, 2);
        options.csv_enabled = false;
        let outcome = run(&options).expect("run");
        assert!(outcome.completed);

        for file in [
            INTERACTIONS_FILE,
            STATES_FILE,
            RELATIONS_FILE,
            REGISTRY_FILE,
        ] {
            let text = fs::read_to_string(directory.join(file)).expect("csv");
            assert_eq!(
                text.lines().count(),
                1,
                "{file} should contain only the header"
            );
        }

        fs::remove_dir_all(&directory).unwrap();
    }

    #[test]
    fn checkpoint_restore_discards_uncommitted_counters() {
        let scenario = Scenario::from_number(55, 42).expect("scenario");
        let mut manifest = Manifest::new(&scenario, 2024, 1, 0.3, 100);
        manifest.set_u64("days_completed", 13);
        manifest.set_u64("checkpoint_days", 10);
        manifest.set_u64("checkpoint_interactions", 100);
        manifest.set_u64("checkpoint_successes", 60);
        manifest.set_u64("checkpoint_failures", 30);
        manifest.set_u64("checkpoint_refusals", 10);
        manifest.set_u64("checkpoint_rotations", 0);
        manifest.set_u64("checkpoint_semesters", 1);
        manifest.set_u64("checkpoint_last_semester_index", 0);
        manifest.set("checkpoint_state_hash", "0x00000000000000aa");
        manifest.set_u64("checkpoint_csv_interactions_bytes", 1_000);
        manifest.set_u64("checkpoint_csv_states_bytes", 2_000);
        manifest.set_u64("checkpoint_csv_relations_bytes", 3_000);
        manifest.set_u64("checkpoint_csv_registry_bytes", 4_000);
        manifest.set_u64("interactions", 130);
        manifest.set_u64("successes", 80);
        manifest.set_u64("failures", 40);
        manifest.set_u64("refusals", 10);
        manifest.set_u64("rotations", 1);
        manifest.set_u64("semesters", 2);
        manifest.set_u64("last_semester_index", 1);
        manifest.set_u64("csv_interactions_bytes", 1_300);
        manifest.set_u64("csv_states_bytes", 2_300);
        manifest.set_u64("csv_relations_bytes", 3_300);
        manifest.set_u64("csv_registry_bytes", 4_300);

        restore_checkpoint(&mut manifest, 10).expect("restore");
        assert_eq!(manifest.days_completed().unwrap(), 10);
        assert_eq!(manifest.u64_field("interactions").unwrap(), 100);
        assert_eq!(manifest.u64_field("successes").unwrap(), 60);
        assert_eq!(manifest.u64_field("failures").unwrap(), 30);
        assert_eq!(manifest.u64_field("refusals").unwrap(), 10);
        assert_eq!(manifest.u64_field("rotations").unwrap(), 0);
        assert_eq!(manifest.u64_field("semesters").unwrap(), 1);
        assert_eq!(manifest.state_hash().unwrap(), 0xaa);
        assert_eq!(manifest.u64_field("csv_interactions_bytes").unwrap(), 1_000);
        assert_eq!(manifest.u64_field("csv_states_bytes").unwrap(), 2_000);
        assert_eq!(manifest.u64_field("csv_relations_bytes").unwrap(), 3_000);
        assert_eq!(manifest.u64_field("csv_registry_bytes").unwrap(), 0);
    }
}
