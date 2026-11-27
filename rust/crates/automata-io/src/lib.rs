//! I/O layer for the v3 simulation.
//!
//! This crate is the only place that knows about files, ClickHouse and run
//! identities.  The simulation crates stay free of I/O.

pub mod batch;
pub mod clickhouse;
pub mod csv;
pub mod fsutil;
pub mod manifest;
pub mod run_id;
pub mod runner;
pub mod sha1;
pub mod time;
pub mod uuid;

pub use batch::{BATCH_SUMMARY_FILE, BatchError, BatchOptions, BatchOutcome, run_batch};
pub use clickhouse::{ClickHouseClient, ClickHouseConfig, ClickHouseError};
pub use csv::{CsvFile, CsvRow};
pub use manifest::{DEFAULT_DAYS_TOTAL, MANIFEST_FORMAT, Manifest, ManifestError, RunStatus};
pub use run_id::{
    RelationMode, SCENARIO_NAMES, Scenario, V2_LAST_RUN_NUMBER, V3_FIRST_RUN_NUMBER,
    V3_LAST_RUN_NUMBER, V3_RUN_COUNT,
};
pub use runner::{RunError, RunOptions, RunOutcome, run};
pub use sha1::{sha1, sha1_hex};
pub use time::{format_utc, format_utc_millis, now_unix, now_unix_millis};
pub use uuid::{Uuid, UuidError};
