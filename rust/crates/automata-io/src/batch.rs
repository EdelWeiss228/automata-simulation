//! Sequential batch runner for the 54-run v3 matrix.
//!
//! Each scenario owns a directory below the batch root.  A batch is resumable
//! by construction: completed runs are skipped, interrupted runs continue from
//! their manifest and snapshot, and a failed run does not stop the rest of the
//! matrix unless `fail_fast` is set.

use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::time::Instant;

use crate::clickhouse::ClickHouseConfig;
use crate::fsutil;
use crate::manifest::{MANIFEST_FORMAT, Manifest, RunStatus};
use crate::run_id::{Scenario, V3_FIRST_RUN_NUMBER, V3_LAST_RUN_NUMBER};
use crate::runner::{self, RunError, RunOptions, RunOutcome};
use crate::time::{format_utc_millis, now_unix, now_unix_millis};

pub const BATCH_SUMMARY_FILE: &str = "batch.txt";
pub const BATCH_FORMAT: &str = "automata-v3-batch/1";

#[derive(Clone, Debug)]
pub struct BatchOptions {
    pub output_root: PathBuf,
    pub seed: u64,
    pub days: u32,
    pub start_year: i32,
    pub parallelism: usize,
    pub master_chance: f32,
    pub checkpoint_every: u32,
    pub clickhouse: Option<ClickHouseConfig>,
    pub clickhouse_required: bool,
    pub verbose: bool,
    pub fail_fast: bool,
    pub log_interactions: bool,
    pub log_states: bool,
    pub log_relations: bool,
    /// Restrict the batch to these run numbers.  `None` means 55–108.
    pub run_numbers: Option<Vec<u16>>,
}

impl BatchOptions {
    pub fn new(output_root: impl Into<PathBuf>, seed: u64) -> Self {
        Self {
            output_root: output_root.into(),
            seed,
            days: crate::manifest::DEFAULT_DAYS_TOTAL,
            start_year: 2024,
            parallelism: 1,
            master_chance: 0.3,
            checkpoint_every: 30,
            clickhouse: None,
            clickhouse_required: false,
            verbose: true,
            fail_fast: false,
            log_interactions: true,
            log_states: true,
            log_relations: true,
            run_numbers: None,
        }
    }

    pub fn with_clickhouse(mut self, config: ClickHouseConfig) -> Self {
        self.clickhouse = Some(config);
        self
    }

    pub fn with_run_numbers(mut self, numbers: impl IntoIterator<Item = u16>) -> Self {
        self.run_numbers = Some(numbers.into_iter().collect());
        self
    }
}

#[derive(Clone, Debug)]
pub struct BatchOutcome {
    pub outcomes: Vec<RunOutcome>,
    pub skipped: Vec<u16>,
    pub failed: Vec<(u16, String)>,
    pub wall_seconds: f64,
}

impl BatchOutcome {
    /// Runs that finished during this invocation.
    pub fn completed_this_run(&self) -> usize {
        self.outcomes
            .iter()
            .filter(|outcome| outcome.completed)
            .count()
    }

    /// Runs that are completed in the batch root, including runs skipped
    /// because an earlier invocation had already finished them.
    pub fn completed_total(&self) -> usize {
        self.completed_this_run() + self.skipped.len()
    }

    pub fn total_interactions(&self) -> u64 {
        self.outcomes
            .iter()
            .map(|outcome| outcome.interactions)
            .sum()
    }
}

#[derive(Debug)]
pub enum BatchError {
    Io(io::Error),
    Invalid(String),
    Run { number: u16, source: RunError },
}

impl fmt::Display for BatchError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "batch I/O error: {error}"),
            Self::Invalid(message) => write!(formatter, "invalid batch: {message}"),
            Self::Run { number, source } => {
                write!(formatter, "run {number} failed: {source}")
            }
        }
    }
}

impl std::error::Error for BatchError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Invalid(_) => None,
            Self::Run { source, .. } => Some(source),
        }
    }
}

impl From<io::Error> for BatchError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

pub fn run_batch(options: &BatchOptions) -> Result<BatchOutcome, BatchError> {
    let started = Instant::now();
    fs::create_dir_all(&options.output_root)?;

    let scenarios = selected_scenarios(options)?;
    let mut outcomes = Vec::new();
    let mut skipped = Vec::new();
    let mut failed = Vec::new();

    for (position, scenario) in scenarios.iter().enumerate() {
        let directory = options.output_root.join(scenario.scenario_name());
        if let Some(status) = existing_status(&directory)?
            && status == RunStatus::Completed
        {
            if options.verbose {
                println!(
                    "[{}/{}] {} already completed; skipping",
                    position + 1,
                    scenarios.len(),
                    scenario.scenario_name()
                );
            }
            skipped.push(scenario.number());
            continue;
        }

        if options.verbose {
            println!(
                "[{}/{}] {} ({}, seed {})",
                position + 1,
                scenarios.len(),
                scenario.scenario_name(),
                scenario.mode().key(),
                scenario.seed()
            );
        }

        let mut run_options = RunOptions::new(scenario.clone(), &directory);
        run_options.days = options.days;
        run_options.start_year = options.start_year;
        run_options.parallelism = options.parallelism;
        run_options.master_chance = options.master_chance;
        run_options.checkpoint_every = options.checkpoint_every;
        run_options.clickhouse = options.clickhouse.clone();
        run_options.clickhouse_required = options.clickhouse_required;
        run_options.verbose = options.verbose;
        run_options.log_interactions = options.log_interactions;
        run_options.log_states = options.log_states;
        run_options.log_relations = options.log_relations;

        match runner::run(&run_options) {
            Ok(outcome) => outcomes.push(outcome),
            Err(error) => {
                let message = error.to_string();
                if options.fail_fast {
                    return Err(BatchError::Run {
                        number: scenario.number(),
                        source: error,
                    });
                }
                eprintln!(
                    "warning: {} failed and the batch continues: {message}",
                    scenario.scenario_name()
                );
                failed.push((scenario.number(), message));
            }
        }
    }

    let wall_seconds = started.elapsed().as_secs_f64();
    let outcome = BatchOutcome {
        outcomes,
        skipped,
        failed,
        wall_seconds,
    };
    write_summary(options, &outcome)?;
    Ok(outcome)
}

fn selected_scenarios(options: &BatchOptions) -> Result<Vec<Scenario>, BatchError> {
    let mut numbers = match &options.run_numbers {
        Some(numbers) => numbers.clone(),
        None => (V3_FIRST_RUN_NUMBER..=V3_LAST_RUN_NUMBER).collect(),
    };
    numbers.sort_unstable();
    numbers.dedup();

    let mut scenarios = Vec::with_capacity(numbers.len());
    for number in numbers {
        let scenario = Scenario::from_number(number, options.seed)
            .ok_or_else(|| BatchError::Invalid(format!("run number {number} is outside 55–108")))?;
        scenarios.push(scenario);
    }
    if scenarios.is_empty() {
        return Err(BatchError::Invalid("the batch is empty".to_string()));
    }
    Ok(scenarios)
}

fn existing_status(directory: &Path) -> Result<Option<RunStatus>, BatchError> {
    let path = directory.join(runner::MANIFEST_FILE);
    if !path.exists() {
        return Ok(None);
    }
    let manifest = Manifest::load(&path).map_err(|error| BatchError::Invalid(error.to_string()))?;
    manifest
        .status()
        .map(Some)
        .map_err(|error| BatchError::Invalid(error.to_string()))
}

fn write_summary(options: &BatchOptions, outcome: &BatchOutcome) -> Result<(), BatchError> {
    let mut text = String::new();
    text.push_str(&format!("format={BATCH_FORMAT}\n"));
    text.push_str(&format!("manifest_format={MANIFEST_FORMAT}\n"));
    text.push_str(&format!("seed={}\n", options.seed));
    text.push_str(&format!("days={}\n", options.days));
    text.push_str(&format!("start_year={}\n", options.start_year));
    text.push_str(&format!("parallelism={}\n", options.parallelism));
    text.push_str(&format!("checkpoint_every={}\n", options.checkpoint_every));
    let finished_millis = now_unix_millis();
    text.push_str(&format!("finished_unix={}\n", now_unix()));
    text.push_str(&format!(
        "finished_at={}\n",
        format_utc_millis(finished_millis)
    ));
    text.push_str(&format!("wall_seconds={:.3}\n", outcome.wall_seconds));
    text.push_str(&format!(
        "completed_this_run={}\n",
        outcome.completed_this_run()
    ));
    text.push_str(&format!("completed_total={}\n", outcome.completed_total()));
    text.push_str(&format!("skipped={}\n", outcome.skipped.len()));
    text.push_str(&format!("failed={}\n", outcome.failed.len()));
    text.push_str(&format!("interactions={}\n", outcome.total_interactions()));

    for number in &outcome.skipped {
        text.push_str(&format!("run.{number}.status=skipped-completed\n"));
    }
    for run in &outcome.outcomes {
        let number = scenario_number(&run.scenario_name);
        text.push_str(&format!(
            "run.{number}.status={}\n",
            if run.completed {
                "completed"
            } else {
                "partial"
            }
        ));
        text.push_str(&format!("run.{number}.days={}\n", run.days_completed));
        text.push_str(&format!("run.{number}.hash=0x{:016x}\n", run.final_hash));
        text.push_str(&format!("run.{number}.interactions={}\n", run.interactions));
    }
    for (number, message) in &outcome.failed {
        text.push_str(&format!("run.{number}.status=failed\n"));
        text.push_str(&format!(
            "run.{number}.error={}\n",
            message.replace('\n', " ")
        ));
    }

    fsutil::write_atomic(
        &options.output_root.join(BATCH_SUMMARY_FILE),
        text.as_bytes(),
    )?;
    Ok(())
}

fn scenario_number(scenario_name: &str) -> &str {
    scenario_name
        .strip_prefix("Run")
        .and_then(|rest| rest.split('_').next())
        .unwrap_or("unknown")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temporary_directory(label: &str) -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "automata-batch-{}-{}-{label}",
            std::process::id(),
            now_unix()
        ));
        fs::create_dir_all(&path).expect("create test directory");
        path
    }

    fn short_batch(directory: &Path) -> BatchOptions {
        let mut options = BatchOptions::new(directory, 42);
        options.days = 2;
        options.checkpoint_every = 1;
        options.verbose = false;
        options.run_numbers = Some(vec![55, 58]);
        options
    }

    #[test]
    fn batch_completes_selected_runs_and_skips_them_on_restart() {
        let directory = temporary_directory("selected");
        let first = run_batch(&short_batch(&directory)).expect("first batch");
        assert_eq!(first.completed_this_run(), 2);
        assert_eq!(first.completed_total(), 2);
        assert!(first.failed.is_empty());
        assert!(first.skipped.is_empty());

        let summary = fs::read_to_string(directory.join(BATCH_SUMMARY_FILE)).expect("summary");
        assert!(summary.contains("completed_this_run=2"));
        assert!(summary.contains("completed_total=2"));
        assert!(summary.contains("run.55.status=completed"));
        assert!(summary.contains("run.58.status=completed"));

        let second = run_batch(&short_batch(&directory)).expect("second batch");
        assert_eq!(second.completed_this_run(), 0);
        assert_eq!(second.completed_total(), 2);
        assert_eq!(second.skipped, vec![55, 58]);

        fs::remove_dir_all(&directory).unwrap();
    }

    #[test]
    fn batch_rejects_numbers_outside_the_reserved_range() {
        let directory = temporary_directory("range");
        let mut options = short_batch(&directory);
        options.run_numbers = Some(vec![54]);
        let error = run_batch(&options).expect_err("54 is frozen v2");
        assert!(error.to_string().contains("outside 55–108"));
        fs::remove_dir_all(&directory).unwrap();
    }
}
