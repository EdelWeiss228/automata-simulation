//! Stable identities for the v3 experiment matrix.
//!
//! v2 occupies scenario numbers 1–54 in `run_name`/`scenario_name` and uses
//! random UUIDs in the `run_id` column.  v3 reserves numbers **55–108** for
//! its 54-run matrix and derives the ClickHouse UUID deterministically from
//! the scenario name and seed.  Re-running a scenario therefore writes to the
//! same `run_id`, which makes resume and idempotent retries possible.

use automata_core::InitMode;

use crate::uuid::Uuid;

/// Last scenario number used by the frozen v2 matrix.
pub const V2_LAST_RUN_NUMBER: u16 = 54;
/// First scenario number reserved for v3.
pub const V3_FIRST_RUN_NUMBER: u16 = 55;
/// Last scenario number reserved for the 54-run v3 matrix.
pub const V3_LAST_RUN_NUMBER: u16 = 108;
/// Number of scenarios in the v3 matrix.
pub const V3_RUN_COUNT: u16 = V3_LAST_RUN_NUMBER - V3_FIRST_RUN_NUMBER + 1;

/// Scenario names in the v2 order (`Run01`–`Run18`).
pub const SCENARIO_NAMES: [&str; 18] = [
    "Erudition",
    "Enigmata",
    "Harmony",
    "Hunt",
    "Elation",
    "Preservation",
    "Nihility",
    "Uniform_Random",
    "Normal_Social",
    "Extremes",
    "Competitive",
    "Academic",
    "Chaotic",
    "Real_World_Approx",
    "Trailblaze",
    "Remembrance",
    "All_Nine_Uniform",
    "Weighted_Random",
];

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum RelationMode {
    Empty,
    Mixed,
    Random,
}

impl RelationMode {
    pub const ALL: [Self; 3] = [Self::Empty, Self::Mixed, Self::Random];

    pub const fn key(self) -> &'static str {
        match self {
            Self::Empty => "EMPTY",
            Self::Mixed => "MIXED",
            Self::Random => "RANDOM",
        }
    }

    pub const fn init_mode(self) -> InitMode {
        match self {
            Self::Empty => InitMode::Empty,
            Self::Mixed => InitMode::Mixed,
            Self::Random => InitMode::Random,
        }
    }

    pub const fn index(self) -> usize {
        match self {
            Self::Empty => 0,
            Self::Mixed => 1,
            Self::Random => 2,
        }
    }

    pub fn from_index(index: usize) -> Option<Self> {
        Self::ALL.get(index).copied()
    }

    pub fn from_key(key: &str) -> Option<Self> {
        Self::ALL
            .into_iter()
            .find(|mode| mode.key().eq_ignore_ascii_case(key))
    }
}

/// One concrete run of the 54-cell matrix.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Scenario {
    number: u16,
    scenario_index: usize,
    mode: RelationMode,
    seed: u64,
}

impl Scenario {
    /// Builds a scenario from its reserved number (`55..=108`).
    pub fn from_number(number: u16, seed: u64) -> Option<Self> {
        if !(V3_FIRST_RUN_NUMBER..=V3_LAST_RUN_NUMBER).contains(&number) {
            return None;
        }
        let offset = usize::from(number - V3_FIRST_RUN_NUMBER);
        let scenario_index = offset / RelationMode::ALL.len();
        let mode = RelationMode::from_index(offset % RelationMode::ALL.len())?;
        SCENARIO_NAMES.get(scenario_index)?;
        Some(Self {
            number,
            scenario_index,
            mode,
            seed,
        })
    }

    pub fn from_parts(scenario_index: usize, mode: RelationMode, seed: u64) -> Option<Self> {
        let number = V3_FIRST_RUN_NUMBER
            .checked_add((scenario_index * RelationMode::ALL.len() + mode.index()) as u16)?;
        Self::from_number(number, seed)
    }

    /// All 54 runs in numeric order.
    pub fn all(seed: u64) -> Vec<Self> {
        (V3_FIRST_RUN_NUMBER..=V3_LAST_RUN_NUMBER)
            .filter_map(|number| Self::from_number(number, seed))
            .collect()
    }

    pub const fn number(&self) -> u16 {
        self.number
    }

    pub const fn scenario_index(&self) -> usize {
        self.scenario_index
    }

    pub const fn mode(&self) -> RelationMode {
        self.mode
    }

    pub const fn seed(&self) -> u64 {
        self.seed
    }

    pub fn base_name(&self) -> &'static str {
        SCENARIO_NAMES[self.scenario_index]
    }

    /// Numeric scenario label, e.g. `Run55_Erudition`.
    pub fn run_name(&self) -> String {
        format!("Run{:02}_{}", self.number, self.base_name())
    }

    /// Full scenario label, e.g. `Run55_Erudition_EMPTY`.
    pub fn scenario_name(&self) -> String {
        format!("{}_{}", self.run_name(), self.mode.key())
    }

    /// Deterministic UUID written to the ClickHouse `run_id` column.
    pub fn run_id(&self) -> Uuid {
        let name = format!("automata-v3/{}:seed={}", self.scenario_name(), self.seed);
        Uuid::v5(Uuid::NAMESPACE_URL, name.as_bytes())
    }

    pub fn description(&self) -> String {
        format!(
            "v3 batch. Scenario {}, relations {}, seed {}",
            self.run_name(),
            self.mode.key(),
            self.seed
        )
    }

    /// Archetype weights for the initial 1500 bachelors.
    ///
    /// The numbers are the v2 scenario definitions after resolving the old
    /// aliases (`ANALYST` → `Erudition`, `MEDIATOR` → `Harmony`, ...).
    /// `Run08_Uniform_Random` uses `[1; 9]`, which is the weighted-random
    /// fallback of the v2 pool builder.
    pub fn bachelor_weights(&self) -> [u32; 9] {
        match self.scenario_index {
            0 => single(0, 1500),
            1 => single(1, 1500),
            2 => single(2, 1500),
            3 => single(3, 1500),
            4 => single(4, 1500),
            5 => single(5, 1500),
            6 => single(6, 1500),
            7 => [1; 9],
            8 => counts(&[(0, 200), (2, 600), (5, 400), (7, 300)]),
            9 => counts(&[(4, 500), (5, 500), (6, 500)]),
            10 => counts(&[(1, 500), (3, 1000)]),
            11 => counts(&[(0, 1200), (8, 300)]),
            12 => counts(&[(1, 500), (4, 500), (6, 500)]),
            13 => counts(&[(0, 500), (1, 50), (2, 400), (3, 200), (5, 300), (6, 50)]),
            14 => single(7, 1500),
            15 => single(8, 1500),
            16 => [167, 167, 167, 167, 166, 166, 167, 166, 167],
            17 => [260, 130, 210, 150, 120, 180, 100, 190, 160],
            _ => unreachable!("scenario index is validated"),
        }
    }

    /// Archetype weights for the initial 120 masters.
    ///
    /// v2 scaled the bachelor distribution to 120 places with the largest
    /// remainder method.  `Run08` keeps the uniform fallback.
    pub fn master_weights(&self) -> [u32; 9] {
        if self.scenario_index == 7 {
            return [1; 9];
        }
        scale_to_masters(self.bachelor_weights())
    }
}

fn single(index: usize, value: u32) -> [u32; 9] {
    let mut weights = [0u32; 9];
    weights[index] = value;
    weights
}

fn counts(entries: &[(usize, u32)]) -> [u32; 9] {
    let mut weights = [0u32; 9];
    for &(index, value) in entries {
        weights[index] += value;
    }
    weights
}

fn scale_to_masters(counts: [u32; 9]) -> [u32; 9] {
    const TOTAL: u32 = 120;
    let sum: u32 = counts.iter().sum();
    if sum == 0 {
        return [1; 9];
    }

    let mut result = [0u32; 9];
    let mut fractions = [0u64; 9];
    for (index, &count) in counts.iter().enumerate() {
        let scaled = u64::from(count) * u64::from(TOTAL);
        result[index] = (scaled / u64::from(sum)) as u32;
        fractions[index] = scaled % u64::from(sum);
    }

    let mut remainder = TOTAL.saturating_sub(result.iter().sum());
    let mut order: Vec<usize> = (0..9).filter(|&index| counts[index] > 0).collect();
    order.sort_by(|&left, &right| {
        fractions[right]
            .cmp(&fractions[left])
            .then_with(|| right.cmp(&left))
    });
    for &index in &order {
        if remainder == 0 {
            break;
        }
        result[index] += 1;
        remainder -= 1;
    }
    for weight in &mut result {
        if remainder == 0 {
            break;
        }
        *weight += 1;
        remainder -= 1;
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_matrix_has_exactly_the_reserved_numbers() {
        let scenarios = Scenario::all(42);
        assert_eq!(scenarios.len(), usize::from(V3_RUN_COUNT));
        assert_eq!(scenarios.len(), 54);
        assert_eq!(scenarios.first().map(Scenario::number), Some(55));
        assert_eq!(scenarios.last().map(Scenario::number), Some(108));

        let numbers: Vec<u16> = scenarios.iter().map(Scenario::number).collect();
        assert_eq!(numbers, (55..=108).collect::<Vec<_>>());
    }

    #[test]
    fn numbers_outside_the_v3_range_are_rejected() {
        assert!(Scenario::from_number(54, 42).is_none());
        assert!(Scenario::from_number(0, 42).is_none());
        assert!(Scenario::from_number(109, 42).is_none());
    }

    #[test]
    fn names_follow_the_v2_order() {
        let first = Scenario::from_number(55, 42).expect("Run55");
        assert_eq!(first.base_name(), "Erudition");
        assert_eq!(first.mode(), RelationMode::Empty);
        assert_eq!(first.run_name(), "Run55_Erudition");
        assert_eq!(first.scenario_name(), "Run55_Erudition_EMPTY");

        let last = Scenario::from_number(108, 42).expect("Run108");
        assert_eq!(last.base_name(), "Weighted_Random");
        assert_eq!(last.mode(), RelationMode::Random);
        assert_eq!(last.scenario_name(), "Run108_Weighted_Random_RANDOM");
    }

    #[test]
    fn every_run_gets_a_unique_stable_uuid() {
        let scenarios = Scenario::all(42);
        let mut ids: Vec<String> = scenarios
            .iter()
            .map(|run| run.run_id().to_string())
            .collect();
        ids.sort();
        ids.dedup();
        assert_eq!(ids.len(), 54);

        assert_eq!(
            Scenario::from_number(55, 42).unwrap().run_id().to_string(),
            "e1823e2e-b1a2-580a-853f-e69e314b438d"
        );
        assert_eq!(
            Scenario::from_number(108, 42).unwrap().run_id().to_string(),
            "8b8cd020-50f9-58d6-a14d-7a13a0d03ad4"
        );
    }

    #[test]
    fn changing_the_seed_changes_the_uuid() {
        let left = Scenario::from_number(55, 42).unwrap();
        let right = Scenario::from_number(55, 43).unwrap();
        assert_ne!(left.run_id(), right.run_id());
        assert_eq!(left.scenario_name(), right.scenario_name());
    }

    #[test]
    fn modes_map_to_core_init_modes() {
        assert_eq!(RelationMode::Empty.init_mode(), InitMode::Empty);
        assert_eq!(RelationMode::Mixed.init_mode(), InitMode::Mixed);
        assert_eq!(RelationMode::Random.init_mode(), InitMode::Random);
        assert_eq!(RelationMode::from_key("mixed"), Some(RelationMode::Mixed));
    }

    #[test]
    fn every_scenario_distribution_matches_the_v2_matrix() {
        // Bachelor weights after resolving the v2 aliases.  `Uniform_Random`
        // keeps the relative `[1; 9]` weights of the v2 fallback; all other
        // rows sum to 1500 and are used as sampling weights.
        let expected: [[u32; 9]; 18] = [
            [1500, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 1500, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1500, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 1500, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 1500, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 1500, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 1500, 0, 0],
            [1, 1, 1, 1, 1, 1, 1, 1, 1],
            [200, 0, 600, 0, 0, 400, 0, 300, 0],
            [0, 0, 0, 0, 500, 500, 500, 0, 0],
            [0, 500, 0, 1000, 0, 0, 0, 0, 0],
            [1200, 0, 0, 0, 0, 0, 0, 0, 300],
            [0, 500, 0, 0, 500, 0, 500, 0, 0],
            [500, 50, 400, 200, 0, 300, 50, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 1500, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 1500],
            [167, 167, 167, 167, 166, 166, 167, 166, 167],
            [260, 130, 210, 150, 120, 180, 100, 190, 160],
        ];

        let scenarios: Vec<_> = Scenario::all(42)
            .into_iter()
            .filter(|scenario| scenario.mode() == RelationMode::Empty)
            .collect();
        assert_eq!(scenarios.len(), expected.len());

        for (index, scenario) in scenarios.into_iter().enumerate() {
            assert_eq!(
                scenario.bachelor_weights(),
                expected[index],
                "{} bachelors",
                scenario.scenario_name()
            );
            let master_sum: u32 = scenario.master_weights().iter().sum();
            if scenario.bachelor_weights() == [1; 9] {
                assert_eq!(master_sum, 9, "{} masters", scenario.scenario_name());
            } else {
                assert_eq!(master_sum, 120, "{} masters", scenario.scenario_name());
            }
        }
    }

    #[test]
    fn uniform_random_keeps_uniform_master_weights() {
        let uniform = Scenario::from_number(76, 42).unwrap();
        assert_eq!(uniform.bachelor_weights(), [1; 9]);
        assert_eq!(uniform.master_weights(), [1; 9]);

        let erudition = Scenario::from_number(55, 42).unwrap();
        assert_eq!(erudition.master_weights()[0], 120);
    }
}
