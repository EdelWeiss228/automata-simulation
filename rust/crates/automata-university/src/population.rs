use std::collections::{BTreeMap, BTreeSet};

use automata_core::{AgentSpec, ArchetypeKind, Degree, DeterministicRng, EmotionVector};

pub const BACHELOR_FACULTIES: [&str; 5] = ["П", "Ф", "Р", "М", "Эк"];
pub const MASTER_DIRECTIONS: [&str; 6] = ["ММ", "ПМ", "ПО", "ЭкМ", "РМ", "ГП"];

pub const BACHELOR_STREAMS: u8 = 4;
pub const BACHELOR_GROUPS_PER_STREAM: u8 = 3;
pub const BACHELOR_GROUP_SIZE: u32 = 25;
pub const MASTER_YEARS: u8 = 2;
pub const MASTER_GROUP_SIZE: u32 = 10;

pub const BACHELOR_PER_YEAR: u32 =
    BACHELOR_FACULTIES.len() as u32 * BACHELOR_GROUPS_PER_STREAM as u32 * BACHELOR_GROUP_SIZE;
pub const INITIAL_BACHELORS: u32 = BACHELOR_PER_YEAR * BACHELOR_STREAMS as u32;
pub const INITIAL_MASTERS: u32 =
    MASTER_DIRECTIONS.len() as u32 * MASTER_YEARS as u32 * MASTER_GROUP_SIZE;
pub const INITIAL_TOTAL: u32 = INITIAL_BACHELORS + INITIAL_MASTERS;

/// Stable mapping from human-readable group names to dense engine indices.
///
/// It is append-only, exactly like the `agent_registry`: a group keeps its
/// index even after all its students graduate, so an old ID can always be
/// resolved.
#[derive(Clone, Debug, Default)]
pub struct GroupRegistry {
    ids: BTreeMap<String, u32>,
}

impl GroupRegistry {
    pub fn intern(&mut self, name: &str) -> u32 {
        if let Some(&id) = self.ids.get(name) {
            return id;
        }
        let id = self.ids.len() as u32;
        self.ids.insert(name.to_string(), id);
        id
    }

    pub fn get(&self, name: &str) -> Option<u32> {
        self.ids.get(name).copied()
    }

    pub fn len(&self) -> usize {
        self.ids.len()
    }

    pub fn is_empty(&self) -> bool {
        self.ids.is_empty()
    }

    pub fn iter(&self) -> impl Iterator<Item = (&str, u32)> {
        self.ids.iter().map(|(name, id)| (name.as_str(), *id))
    }

    pub(crate) fn from_entries(entries: impl IntoIterator<Item = (String, u32)>) -> Self {
        Self {
            ids: entries.into_iter().collect(),
        }
    }
}

#[derive(Clone, Debug)]
pub struct PopulationConfig {
    pub start_year: i32,
    pub seed: u64,
    pub master_chance: f32,
    /// Archetype weights in `ArchetypeKind::ALL` order.  All zero means a
    /// uniform choice, which is the default.
    pub bachelor_weights: [u32; 9],
    pub master_weights: [u32; 9],
    pub sensitivity_min: f32,
    pub sensitivity_max: f32,
}

impl Default for PopulationConfig {
    fn default() -> Self {
        Self {
            start_year: 2024,
            seed: 42,
            master_chance: 0.3,
            bachelor_weights: [1; 9],
            master_weights: [1; 9],
            sensitivity_min: 0.1,
            sensitivity_max: 3.0,
        }
    }
}

#[derive(Clone, Debug)]
pub struct Student {
    /// Human-readable stable identifier: `S-П-24-1-01` or `M-ММ-24-01`.
    pub string_id: String,
    pub name: String,
    pub archetype: ArchetypeKind,
    pub sensitivity: f32,
    pub sportiness: f32,
    pub skip_tendency: f32,
    /// Initial emotional profile.  v2's `EmotionPair` starts at
    /// `randint(-15, 15)` per axis; the semester reset uses the wider
    /// `[-30, 30]` range instead.
    pub emotions: EmotionVector,
    pub group: String,
    /// Dense group index used by `automata_core::AgentSpec`.
    pub group_id: u32,
    pub faculty: String,
    pub direction: Option<String>,
    pub enrollment_year: i32,
    pub course_year: u8,
    pub degree: Degree,
}

impl Student {
    pub fn to_spec(&self) -> AgentSpec {
        let mut spec = AgentSpec::new(
            self.string_id.clone(),
            self.archetype,
            self.sensitivity,
            self.group_id,
            self.course_year,
            self.degree,
        );
        spec.name = self.name.clone();
        spec.emotions = Some(self.emotions);
        spec
    }
}

#[derive(Clone, Debug, Default)]
pub struct RotationReport {
    pub year: i32,
    pub removed_bachelors: u32,
    pub removed_masters: u32,
    pub continued_bachelors: u32,
    pub new_bachelors: u32,
    pub new_external_masters: u32,
    pub total_after: usize,
}

#[derive(Clone, Debug)]
pub struct Population {
    pub students: Vec<Student>,
    pub groups: GroupRegistry,
    pub current_year: i32,
    config: PopulationConfig,
    rng: DeterministicRng,
    /// Empirical archetype distribution of the initial bachelors/masters.
    /// v2 freezes these after the first population and reuses them for every
    /// later cohort, so new students preserve the original mix.
    bachelor_rotation_weights: [u32; 9],
    master_rotation_weights: [u32; 9],
}

impl Population {
    pub fn new(config: PopulationConfig) -> Self {
        let seed = config.seed;
        let mut population = Self {
            students: Vec::with_capacity(INITIAL_TOTAL as usize),
            groups: GroupRegistry::default(),
            current_year: config.start_year,
            config,
            rng: DeterministicRng::new(seed),
            bachelor_rotation_weights: [0; 9],
            master_rotation_weights: [0; 9],
        };

        let bachelor_weights = population.config.bachelor_weights;
        let master_weights = population.config.master_weights;

        // Same nesting as `UniversityManager.create_university_agents`:
        // faculty -> enrollment year -> group -> student.
        for faculty in BACHELOR_FACULTIES {
            for stream in 0..BACHELOR_STREAMS {
                let enrollment_year = population.current_year - i32::from(stream);
                let course_year = stream + 1;
                population.add_bachelor_cohort_for_faculty(
                    faculty,
                    enrollment_year,
                    course_year,
                    bachelor_weights,
                );
            }
        }

        for direction in MASTER_DIRECTIONS {
            for course_year in 1..=MASTER_YEARS {
                let enrollment_year = population.current_year - i32::from(course_year - 1);
                population.add_master_cohort(
                    direction,
                    enrollment_year,
                    course_year,
                    0,
                    master_weights,
                );
            }
        }

        population.bachelor_rotation_weights = count_archetypes(
            population
                .students
                .iter()
                .filter(|s| s.degree == Degree::Bachelor),
        );
        population.master_rotation_weights = count_archetypes(
            population
                .students
                .iter()
                .filter(|s| s.degree == Degree::Master),
        );

        debug_assert_eq!(population.students.len(), INITIAL_TOTAL as usize);
        population
    }

    pub fn rng_state(&self) -> u64 {
        self.rng.state()
    }

    pub(crate) fn config(&self) -> &PopulationConfig {
        &self.config
    }

    pub(crate) fn rotation_weights(&self) -> ([u32; 9], [u32; 9]) {
        (self.bachelor_rotation_weights, self.master_rotation_weights)
    }

    pub(crate) fn from_snapshot_parts(
        students: Vec<Student>,
        groups: GroupRegistry,
        current_year: i32,
        config: PopulationConfig,
        rng_state: u64,
        bachelor_rotation_weights: [u32; 9],
        master_rotation_weights: [u32; 9],
    ) -> Self {
        Self {
            students,
            groups,
            current_year,
            config,
            rng: DeterministicRng::new(rng_state),
            bachelor_rotation_weights,
            master_rotation_weights,
        }
    }

    pub fn total(&self) -> usize {
        self.students.len()
    }

    pub fn bachelors(&self) -> usize {
        self.students
            .iter()
            .filter(|student| student.degree == Degree::Bachelor)
            .count()
    }

    pub fn masters(&self) -> usize {
        self.students
            .iter()
            .filter(|student| student.degree == Degree::Master)
            .count()
    }

    pub fn to_specs(&self) -> Vec<AgentSpec> {
        self.students.iter().map(Student::to_spec).collect()
    }

    /// One academic-year rotation.  `next_year` must be the year after the
    /// current one; the caller invokes it on the first day of September.
    pub fn rotate(&mut self, next_year: i32) -> RotationReport {
        assert_eq!(
            next_year,
            self.current_year + 1,
            "rotation must advance exactly one academic year"
        );

        let mut master_counts: BTreeMap<&'static str, u32> = MASTER_DIRECTIONS
            .iter()
            .map(|direction| (*direction, 0))
            .collect();

        let mut eligible: Vec<usize> = self
            .students
            .iter()
            .enumerate()
            .filter(|(_, student)| {
                student.degree == Degree::Bachelor && student.enrollment_year <= next_year - 4
            })
            .map(|(index, _)| index)
            .collect();

        // v2 shuffles the candidate list before distributing the limited
        // master's places.  Sorting first makes the shuffle reproducible even
        // if the population vector is rebuilt in a different order.
        eligible.sort_by(|&left, &right| {
            self.students[left]
                .string_id
                .cmp(&self.students[right].string_id)
        });
        shuffle(&mut eligible, &mut self.rng);

        let mut remove = vec![false; self.students.len()];
        let mut continued = vec![false; self.students.len()];
        let mut report = RotationReport {
            year: next_year,
            ..RotationReport::default()
        };

        for index in eligible {
            let student = &self.students[index];
            let direction = master_direction_for_faculty(&student.faculty);
            let group = direction.map(|direction| master_group_id(direction, next_year));

            let has_place =
                direction.is_some_and(|direction| master_counts[direction] < MASTER_GROUP_SIZE);

            if has_place && self.rng.next_f32() < self.config.master_chance {
                let direction = direction.expect("has_place implies direction");
                let group = group.expect("has_place implies group");
                let group_id = self.groups.intern(&group);

                let student = &mut self.students[index];
                student.degree = Degree::Master;
                student.enrollment_year = next_year;
                student.course_year = 1;
                student.direction = Some(direction.to_string());
                student.group = group;
                student.group_id = group_id;

                *master_counts
                    .get_mut(direction)
                    .expect("direction is registered") += 1;
                continued[index] = true;
                report.continued_bachelors += 1;
            } else {
                remove[index] = true;
                report.removed_bachelors += 1;
            }
        }

        for (index, student) in self.students.iter().enumerate() {
            if student.degree != Degree::Master {
                continue;
            }
            if student.enrollment_year <= next_year - 2 {
                remove[index] = true;
                report.removed_masters += 1;
            }
        }

        for (index, student) in self.students.iter_mut().enumerate() {
            if student.degree == Degree::Master
                && !remove[index]
                && !continued[index]
                && student.course_year == 1
            {
                student.course_year = 2;
            }
        }

        let old_students = std::mem::take(&mut self.students);
        self.students = old_students
            .into_iter()
            .enumerate()
            .filter_map(|(index, student)| (!remove[index]).then_some(student))
            .collect();

        // Remaining bachelors move one course up.  A cohort keeps its group
        // ID (and therefore its enrollment year), as in v2.
        for student in &mut self.students {
            if student.degree == Degree::Bachelor {
                student.course_year = (student.course_year + 1).min(4);
            }
        }

        let bachelor_weights = self.bachelor_rotation_weights;
        let master_weights = self.master_rotation_weights;

        for faculty in BACHELOR_FACULTIES {
            self.add_bachelor_cohort_for_faculty(faculty, next_year, 1, bachelor_weights);
            report.new_bachelors += BACHELOR_GROUPS_PER_STREAM as u32 * BACHELOR_GROUP_SIZE;
        }

        // Continuing bachelors keep their `S-...` ID; external students fill
        // the remaining places up to ten per cohort.
        for direction in MASTER_DIRECTIONS {
            let filled = master_counts[direction];
            let to_add = MASTER_GROUP_SIZE - filled;
            if to_add > 0 {
                self.add_master_cohort(direction, next_year, 1, filled, master_weights);
                report.new_external_masters += to_add;
            }
        }

        self.current_year = next_year;
        report.total_after = self.students.len();
        debug_assert_eq!(report.total_after, INITIAL_TOTAL as usize);
        report
    }

    fn add_bachelor_cohort_for_faculty(
        &mut self,
        faculty: &str,
        enrollment_year: i32,
        course_year: u8,
        weights: [u32; 9],
    ) {
        let year_suffix = year_suffix(enrollment_year);
        for group_number in 1..=BACHELOR_GROUPS_PER_STREAM {
            let group = format!("{faculty}-{year_suffix}-{group_number}");
            let group_id = self.groups.intern(&group);

            for student_number in 1..=BACHELOR_GROUP_SIZE {
                let string_id = format!("S-{group}-{student_number:02}");
                let archetype = self.pick_archetype(weights);
                let student = self.make_student(
                    string_id,
                    archetype,
                    group.clone(),
                    group_id,
                    faculty.to_string(),
                    None,
                    enrollment_year,
                    course_year,
                    Degree::Bachelor,
                );
                self.students.push(student);
            }
        }
    }

    fn add_master_cohort(
        &mut self,
        direction: &str,
        enrollment_year: i32,
        course_year: u8,
        already_filled: u32,
        weights: [u32; 9],
    ) {
        let group = master_group_id(direction, enrollment_year);
        let group_id = self.groups.intern(&group);
        let parent_faculty = parent_faculty_for_direction(direction);
        let to_add = MASTER_GROUP_SIZE.saturating_sub(already_filled);

        for offset in 0..to_add {
            let student_number = already_filled + offset + 1;
            let string_id = format!("M-{group}-{student_number:02}");
            let archetype = self.pick_archetype(weights);
            let student = self.make_student(
                string_id,
                archetype,
                group.clone(),
                group_id,
                parent_faculty.to_string(),
                Some(direction.to_string()),
                enrollment_year,
                course_year,
                Degree::Master,
            );
            self.students.push(student);
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn make_student(
        &mut self,
        string_id: String,
        archetype: ArchetypeKind,
        group: String,
        group_id: u32,
        faculty: String,
        direction: Option<String>,
        enrollment_year: i32,
        course_year: u8,
        degree: Degree,
    ) -> Student {
        let sensitivity = self.config.sensitivity_min
            + (self.config.sensitivity_max - self.config.sensitivity_min) * self.rng.next_f32();
        let emotions = EmotionVector::random(&mut self.rng, -15, 15);
        let sportiness = self.rng.next_f32();
        let skip_tendency = 0.3 * self.rng.next_f32();

        Student {
            name: string_id.clone(),
            string_id,
            archetype,
            sensitivity,
            sportiness,
            skip_tendency,
            emotions,
            group,
            group_id,
            faculty,
            direction,
            enrollment_year,
            course_year,
            degree,
        }
    }

    fn pick_archetype(&mut self, weights: [u32; 9]) -> ArchetypeKind {
        let total: u32 = weights.iter().sum();
        if total == 0 {
            let index = (self.rng.next_u64() % ArchetypeKind::ALL.len() as u64) as usize;
            return ArchetypeKind::ALL[index];
        }

        let mut draw = (self.rng.next_u64() % u64::from(total)) as u32;
        for (index, weight) in weights.into_iter().enumerate() {
            if draw < weight {
                return ArchetypeKind::ALL[index];
            }
            draw -= weight;
        }
        ArchetypeKind::ALL[8]
    }
}

pub fn year_suffix(year: i32) -> String {
    format!("{:02}", year.rem_euclid(100))
}

pub fn master_group_id(direction: &str, enrollment_year: i32) -> String {
    format!("{direction}-{}", year_suffix(enrollment_year))
}

pub fn master_direction_for_faculty(faculty: &str) -> Option<&'static str> {
    match faculty {
        "П" => Some("ММ"),
        "Р" => Some("РМ"),
        "М" | "Эк" => Some("ЭкМ"),
        "Ф" => Some("ПМ"),
        _ => None,
    }
}

pub fn parent_faculty_for_direction(direction: &str) -> &'static str {
    let index = MASTER_DIRECTIONS
        .iter()
        .position(|candidate| *candidate == direction)
        .unwrap_or(0);
    BACHELOR_FACULTIES[index % BACHELOR_FACULTIES.len()]
}

pub fn all_group_ids(population: &Population) -> BTreeSet<String> {
    population
        .students
        .iter()
        .map(|student| student.group.clone())
        .collect()
}

fn count_archetypes<'a>(students: impl Iterator<Item = &'a Student>) -> [u32; 9] {
    let mut counts = [0u32; 9];
    for student in students {
        counts[student.archetype as usize] += 1;
    }
    counts
}

fn shuffle<T>(values: &mut [T], rng: &mut DeterministicRng) {
    for index in (1..values.len()).rev() {
        let other = (rng.next_u64() % (index as u64 + 1)) as usize;
        values.swap(index, other);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn population() -> Population {
        Population::new(PopulationConfig::default())
    }

    #[test]
    fn initial_population_has_the_expected_structure() {
        let population = population();
        assert_eq!(population.total(), 1620);
        assert_eq!(population.bachelors(), 1500);
        assert_eq!(population.masters(), 120);
        assert_eq!(population.groups.len(), 72);

        let mut per_group: BTreeMap<&str, u32> = BTreeMap::new();
        for student in &population.students {
            *per_group.entry(student.group.as_str()).or_default() += 1;
        }
        assert_eq!(per_group.len(), 60 + 12);
        for (group, count) in per_group {
            if group.starts_with('M') || MASTER_DIRECTIONS.iter().any(|d| group.starts_with(d)) {
                assert_eq!(count, 10, "master group {group}");
            } else {
                assert_eq!(count, 25, "bachelor group {group}");
            }
        }
    }

    #[test]
    fn identifiers_are_unique_and_have_the_v2_shape() {
        let population = population();
        let mut ids = BTreeSet::new();
        for student in &population.students {
            assert!(ids.insert(student.string_id.clone()));
            assert!(
                student.string_id.starts_with("S-") || student.string_id.starts_with("M-"),
                "{}",
                student.string_id
            );
        }
        assert_eq!(ids.len(), 1620);

        assert!(ids.contains("S-П-24-1-01"));
        assert!(ids.contains("M-ММ-24-01"));
    }

    #[test]
    fn to_specs_preserves_identity_and_group() {
        let population = population();
        let specs = population.to_specs();
        assert_eq!(specs.len(), population.total());
        for (student, spec) in population.students.iter().zip(&specs) {
            assert_eq!(student.string_id, spec.string_id);
            assert_eq!(student.group_id, spec.group_id);
            assert_eq!(student.course_year, spec.course_year);
            assert_eq!(student.degree, spec.degree);
        }
    }

    #[test]
    fn rotation_keeps_the_population_size_and_composition() {
        let mut population = population();
        let report = population.rotate(2025);

        assert_eq!(report.total_after, 1620);
        assert_eq!(population.total(), 1620);
        assert_eq!(population.bachelors(), 1500);
        assert_eq!(population.masters(), 120);
        assert_eq!(report.new_bachelors, 375);
        assert_eq!(report.continued_bachelors + report.new_external_masters, 60);
        assert!(report.continued_bachelors <= 40);

        let mut per_master_group: BTreeMap<&str, u32> = BTreeMap::new();
        for student in &population.students {
            if student.degree == Degree::Master {
                *per_master_group.entry(student.group.as_str()).or_default() += 1;
                assert!((1..=2).contains(&student.course_year));
            } else {
                assert!((1..=4).contains(&student.course_year));
            }
        }
        assert_eq!(per_master_group.len(), 12);
        for (group, count) in per_master_group {
            assert_eq!(count, 10, "group {group}");
        }

        let ids: BTreeSet<_> = population
            .students
            .iter()
            .map(|student| student.string_id.clone())
            .collect();
        assert_eq!(ids.len(), 1620);
    }

    #[test]
    fn rotation_is_deterministic() {
        let mut left = population();
        let mut right = population();
        left.rotate(2025);
        right.rotate(2025);

        let left_state: Vec<_> = left
            .students
            .iter()
            .map(|student| {
                (
                    student.string_id.clone(),
                    student.group.clone(),
                    student.course_year,
                    student.enrollment_year,
                    student.archetype,
                )
            })
            .collect();
        let right_state: Vec<_> = right
            .students
            .iter()
            .map(|student| {
                (
                    student.string_id.clone(),
                    student.group.clone(),
                    student.course_year,
                    student.enrollment_year,
                    student.archetype,
                )
            })
            .collect();
        assert_eq!(left_state, right_state);
    }

    #[test]
    fn four_rotations_cover_a_full_bachelor_and_master_cycle() {
        let mut population = population();
        for year in 2025..=2028 {
            population.rotate(year);
            assert_eq!(population.total(), 1620);
            assert_eq!(population.bachelors(), 1500);
            assert_eq!(population.masters(), 120);
        }

        assert!(
            population
                .students
                .iter()
                .all(|student| { student.degree == Degree::Master || student.course_year <= 4 })
        );
        let ids: BTreeSet<_> = population
            .students
            .iter()
            .map(|student| student.string_id.clone())
            .collect();
        assert_eq!(ids.len(), 1620);
    }

    #[test]
    fn homogeneous_archetype_weights_are_preserved() {
        let mut weights = [0u32; 9];
        weights[ArchetypeKind::Nihility as usize] = 1;
        let mut population = Population::new(PopulationConfig {
            bachelor_weights: weights,
            master_weights: weights,
            ..PopulationConfig::default()
        });

        assert!(
            population
                .students
                .iter()
                .all(|student| student.archetype == ArchetypeKind::Nihility)
        );
        population.rotate(2025);
        assert!(
            population
                .students
                .iter()
                .all(|student| student.archetype == ArchetypeKind::Nihility)
        );
    }

    #[test]
    fn master_chance_zero_and_one_have_the_expected_bounds() {
        let mut none = Population::new(PopulationConfig {
            master_chance: 0.0,
            ..PopulationConfig::default()
        });
        let none_report = none.rotate(2025);
        assert_eq!(none_report.continued_bachelors, 0);
        assert_eq!(none_report.new_external_masters, 60);

        let mut all = Population::new(PopulationConfig {
            master_chance: 1.0,
            ..PopulationConfig::default()
        });
        let all_report = all.rotate(2025);
        assert_eq!(all_report.continued_bachelors, 40);
        assert_eq!(all_report.new_external_masters, 20);
    }

    #[test]
    fn group_registry_is_append_only() {
        let mut registry = GroupRegistry::default();
        let first = registry.intern("П-24-1");
        let second = registry.intern("П-24-2");
        assert_ne!(first, second);
        assert_eq!(registry.intern("П-24-1"), first);
        assert_eq!(registry.len(), 2);
    }
}
