//! University layer for the v3 simulation.
//!
//! This crate owns the academic calendar and the population structure:
//! faculties, streams, groups, master cohorts and the yearly rotation.  It
//! deliberately does not know about ClickHouse, CSV or the web API.

#![forbid(unsafe_code)]
#![deny(missing_debug_implementations)]

pub mod calendar;
pub mod population;

pub use calendar::{
    Calendar, CalendarDay, Date, Semester, TOTAL_DAYS, Weekday, days_in_month, is_leap_year,
};
pub use population::{
    BACHELOR_FACULTIES, BACHELOR_GROUP_SIZE, BACHELOR_GROUPS_PER_STREAM, BACHELOR_PER_YEAR,
    BACHELOR_STREAMS, GroupRegistry, INITIAL_BACHELORS, INITIAL_MASTERS, INITIAL_TOTAL,
    MASTER_DIRECTIONS, MASTER_GROUP_SIZE, MASTER_YEARS, Population, PopulationConfig,
    RotationReport, Student, all_group_ids, master_direction_for_faculty, master_group_id,
    parent_faculty_for_direction, year_suffix,
};
