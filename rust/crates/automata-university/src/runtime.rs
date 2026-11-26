//! The university world: one academic day at a time.
//!
//! The runtime owns the dense core world, the roster, the campus and the
//! schedules.  It is the only place where the academic calendar drives the
//! simulation: a Sunday performs the family-day shift, a working day walks
//! through `DAY_SLOTS`, and the first day of a semester resets emotions.

use std::collections::BTreeMap;

use automata_core::{
    AgentId, DeterministicRng, EMOTION_MAX, EMOTION_MIN, EmotionVector, InitMode, Interaction,
    Outcome, Relation, World, WorldConfig,
};

use crate::calendar::{Calendar, CalendarDay, Date, TOTAL_DAYS, Weekday};
use crate::campus::{CORRIDOR_ID, Campus, GYM_ID, GymSection, Room};
use crate::interaction::{UniversityInteraction, interact_in_room};
use crate::population::{Population, PopulationConfig, RotationReport, Student};
use crate::schedule::{DAY_SLOTS, DaySlot, ScheduleBook};
use crate::seating::{SeatMap, seat_students};

const POPULATION_STREAM: u64 = 0x9E37_79B9_7F4A_7C15;
const UNIVERSITY_STREAM: u64 = 0xD1B5_4A32_D192_ED03;
const WORLD_STREAM: u64 = 0x94D0_49BB_1331_11EB;

#[derive(Clone, Debug)]
pub struct UniversityConfig {
    pub seed: u64,
    pub start_year: i32,
    pub parallelism: usize,
    pub init_mode: InitMode,
    pub master_chance: f32,
    /// Archetype weights in `ArchetypeKind::ALL` order.
    pub bachelor_weights: [u32; 9],
    pub master_weights: [u32; 9],
}

impl Default for UniversityConfig {
    fn default() -> Self {
        Self {
            seed: 42,
            start_year: 2024,
            parallelism: 1,
            init_mode: InitMode::Mixed,
            master_chance: 0.3,
            bachelor_weights: [1; 9],
            master_weights: [1; 9],
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum AgentStatus {
    #[default]
    Home,
    InClass,
    Break,
    Gym,
}

#[derive(Clone, Debug)]
pub struct UniversityDay {
    pub day_id: u32,
    pub date: Date,
    pub weekday: Weekday,
    pub is_sunday: bool,
    pub semester_index: u32,
    pub interactions: Vec<UniversityInteraction>,
    pub rotation: Option<RotationReport>,
}

impl UniversityDay {
    pub fn count(&self, outcome: Outcome) -> usize {
        self.interactions
            .iter()
            .filter(|event| event.outcome == outcome)
            .count()
    }

    pub fn successes(&self) -> usize {
        self.count(Outcome::Success)
    }

    pub fn failures(&self) -> usize {
        self.count(Outcome::Failure)
    }

    pub fn refusals(&self) -> usize {
        self.count(Outcome::Refusal)
    }
}

#[derive(Debug)]
pub struct University {
    pub world: World,
    pub population: Population,
    pub campus: Campus,
    pub schedules: ScheduleBook,
    pub calendar: Calendar,
    pub config: UniversityConfig,
    /// RNG for university-scale choices: schedules, attendance, seating,
    /// section choice and semester emotion resets.  The core has a separate
    /// stream for its own interactions and initial relations.
    pub rng: DeterministicRng,
    pub current_rooms: BTreeMap<String, SeatMap>,
    pub rotations: Vec<RotationReport>,
    statuses: Vec<AgentStatus>,
    arrived_today: Vec<bool>,
    left_campus_today: Vec<bool>,
    gym_sections: Vec<Option<GymSection>>,
    sportiness: Vec<f32>,
    skip_tendency: Vec<f32>,
    last_day: Option<CalendarDay>,
    days_completed: u32,
}

impl University {
    pub fn new(config: UniversityConfig) -> Self {
        let population = Population::new(PopulationConfig {
            start_year: config.start_year,
            seed: config.seed ^ POPULATION_STREAM,
            master_chance: config.master_chance,
            bachelor_weights: config.bachelor_weights,
            master_weights: config.master_weights,
            ..PopulationConfig::default()
        });

        let mut rng = DeterministicRng::new(config.seed ^ UNIVERSITY_STREAM);
        let campus = Campus::new(config.start_year);
        let mut schedules = ScheduleBook::new();
        schedules.generate_initial(&campus, config.start_year, &mut rng);

        let world = World::from_specs(
            population.to_specs(),
            WorldConfig {
                seed: config.seed ^ WORLD_STREAM,
                parallelism: config.parallelism,
                init_mode: config.init_mode,
                ..WorldConfig::default()
            },
        );

        let n = world.len();
        let mut university = Self {
            world,
            population,
            campus,
            schedules,
            calendar: Calendar::new(config.start_year),
            config,
            rng,
            current_rooms: BTreeMap::new(),
            rotations: Vec::new(),
            statuses: vec![AgentStatus::Home; n],
            arrived_today: vec![false; n],
            left_campus_today: vec![false; n],
            gym_sections: vec![None; n],
            sportiness: Vec::new(),
            skip_tendency: Vec::new(),
            last_day: None,
            days_completed: 0,
        };
        university.sync_university_state();
        debug_assert_eq!(university.world.len(), university.population.students.len());
        university
    }

    pub fn len(&self) -> usize {
        self.world.len()
    }

    pub fn is_empty(&self) -> bool {
        self.world.is_empty()
    }

    pub fn days_completed(&self) -> u32 {
        self.days_completed
    }

    pub fn day_id(&self) -> Option<u32> {
        self.last_day.map(|day| day.day_id)
    }

    pub fn date(&self) -> Option<Date> {
        self.last_day.map(|day| day.date)
    }

    pub fn weekday(&self) -> Option<Weekday> {
        self.last_day.map(|day| day.weekday)
    }

    pub fn semester_index(&self) -> Option<u32> {
        self.last_day.map(|day| day.semester_index)
    }

    pub fn is_finished(&self) -> bool {
        self.days_completed >= TOTAL_DAYS
    }

    pub fn student(&self, index: usize) -> &Student {
        &self.population.students[index]
    }

    pub fn status(&self, index: usize) -> AgentStatus {
        self.statuses[index]
    }

    pub fn statuses(&self) -> &[AgentStatus] {
        &self.statuses
    }

    pub fn gym_section(&self, index: usize) -> Option<GymSection> {
        self.gym_sections[index]
    }

    pub fn sportiness(&self, index: usize) -> f32 {
        self.sportiness[index]
    }

    pub fn skip_tendency(&self, index: usize) -> f32 {
        self.skip_tendency[index]
    }

    pub fn find_agent(&self, string_id: &str) -> Option<usize> {
        self.world
            .agents
            .iter()
            .position(|agent| agent.string_id == string_id)
    }

    /// Processes the next simulated day.  Returns `None` after 1213 days.
    pub fn step_day(&mut self) -> Option<UniversityDay> {
        let day = self.calendar.next_day()?;
        self.last_day = Some(day);

        let rotates = day.starts_autumn && day.academic_year > self.config.start_year;
        let resets_emotions = rotates || day.starts_spring;

        // The semester boundary is applied before the day's own slots.  In
        // v2 the reset happens at the transition into 1 February / 1
        // September; a Sunday on that date then applies the family shift to
        // the freshly reset emotions.
        let rotation = if rotates {
            let report = self.rotate(day.academic_year);
            Some(report)
        } else {
            None
        };
        if resets_emotions {
            self.reset_emotions();
        }

        if day.is_sunday {
            self.world.sunday_shift(EMOTION_MIN, EMOTION_MAX);
            self.sync_emotions_to_population();

            self.days_completed += 1;
            self.world.day = day.day_id + 1;
            debug_assert_eq!(self.days_completed, day.day_id + 1);
            return Some(UniversityDay {
                day_id: day.day_id,
                date: day.date,
                weekday: day.weekday,
                is_sunday: true,
                semester_index: day.semester_index,
                interactions: Vec::new(),
                rotation,
            });
        }

        self.begin_day();
        let weekday = day.weekday.index() as usize - 1;
        let mut interactions = Vec::new();

        for (slot_index, slot) in DAY_SLOTS.iter().enumerate() {
            let slot_id = slot_index as u32 + 1;
            if !matches!(slot, DaySlot::Cleanup) {
                self.current_rooms.clear();
            }

            match *slot {
                DaySlot::Pair(pair) => {
                    interactions.extend(self.process_pair(weekday, pair as usize - 1, slot_id));
                }
                DaySlot::Break => {
                    interactions.extend(self.process_break(slot_id));
                }
                DaySlot::Gym => {
                    interactions.extend(self.process_gym(slot_id));
                }
                DaySlot::Cleanup => {
                    self.process_cleanup();
                    self.world.daily_maintenance();
                    self.sync_emotions_to_population();
                }
            }
        }

        self.days_completed += 1;
        self.world.day = day.day_id + 1;
        debug_assert_eq!(self.days_completed, day.day_id + 1);
        Some(UniversityDay {
            day_id: day.day_id,
            date: day.date,
            weekday: day.weekday,
            is_sunday: false,
            semester_index: day.semester_index,
            interactions,
            rotation,
        })
    }

    pub fn run_days(&mut self, days: u32) -> Vec<UniversityDay> {
        let mut report = Vec::new();
        for _ in 0..days {
            match self.step_day() {
                Some(day) => report.push(day),
                None => break,
            }
        }
        report
    }

    pub fn run_to_end(&mut self) -> Vec<UniversityDay> {
        self.run_days(TOTAL_DAYS)
    }

    fn begin_day(&mut self) {
        self.statuses.fill(AgentStatus::Home);
        self.arrived_today.fill(false);
        self.left_campus_today.fill(false);
        self.gym_sections.fill(None);
        self.current_rooms.clear();
    }

    fn process_pair(
        &mut self,
        weekday: usize,
        pair: usize,
        slot_id: u32,
    ) -> Vec<UniversityInteraction> {
        let mut assignments: BTreeMap<String, Vec<usize>> = BTreeMap::new();

        for index in 0..self.world.len() {
            if self.left_campus_today[index] {
                continue;
            }

            if self.rng.next_f32() < self.skip_tendency[index] {
                if self.arrived_today[index] {
                    self.left_campus_today[index] = true;
                }
                self.statuses[index] = AgentStatus::Home;
                continue;
            }

            let schedule = self.schedules.get(&self.population.students[index].group);
            let room = schedule.and_then(|schedule| schedule.pair(weekday, pair));

            if let Some(room) = room {
                self.arrived_today[index] = true;
                self.statuses[index] = AgentStatus::InClass;
                if room == GYM_ID {
                    self.gym_sections[index] = Some(random_section(&mut self.rng));
                }
                assignments.entry(room.to_string()).or_default().push(index);
            } else if !self.arrived_today[index] {
                self.statuses[index] = AgentStatus::Home;
            } else {
                let has_more_classes = schedule.is_some_and(|schedule| {
                    schedule.pairs(weekday)[pair + 1..]
                        .iter()
                        .any(Option::is_some)
                });
                let stay = has_more_classes || self.rng.next_f32() < self.sportiness[index];
                if stay {
                    self.statuses[index] = AgentStatus::Break;
                    assignments
                        .entry(CORRIDOR_ID.to_string())
                        .or_default()
                        .push(index);
                } else {
                    self.statuses[index] = AgentStatus::Home;
                    self.left_campus_today[index] = true;
                }
            }
        }

        let mut interactions = Vec::new();
        for (room, students) in assignments {
            interactions.extend(self.seat_and_interact(&room, &students, slot_id));
        }
        interactions
    }

    fn process_break(&mut self, slot_id: u32) -> Vec<UniversityInteraction> {
        let students: Vec<usize> = self
            .statuses
            .iter()
            .enumerate()
            .filter_map(|(index, status)| (*status != AgentStatus::Home).then_some(index))
            .collect();
        self.seat_and_interact(CORRIDOR_ID, &students, slot_id)
    }

    fn process_gym(&mut self, slot_id: u32) -> Vec<UniversityInteraction> {
        let mut students = Vec::new();
        for index in 0..self.world.len() {
            if self.statuses[index] == AgentStatus::Home {
                continue;
            }
            if self.rng.next_f32() < self.sportiness[index] {
                self.gym_sections[index] = Some(random_section(&mut self.rng));
                self.statuses[index] = AgentStatus::Gym;
                students.push(index);
            } else {
                self.statuses[index] = AgentStatus::Home;
            }
        }
        self.seat_and_interact(GYM_ID, &students, slot_id)
    }

    fn process_cleanup(&mut self) {
        self.statuses.fill(AgentStatus::Home);
    }

    fn seat_and_interact(
        &mut self,
        room_id: &str,
        students: &[usize],
        slot_id: u32,
    ) -> Vec<UniversityInteraction> {
        let room: Room = self
            .campus
            .room(room_id)
            .expect("every scheduled room exists on campus")
            .clone();

        let map = seat_students(
            &self.world,
            &mut self.rng,
            &room,
            students,
            &self.gym_sections,
        );
        let interactions = interact_in_room(
            &mut self.world,
            &mut self.rng,
            &map,
            &self.gym_sections,
            slot_id,
            room.context(),
        );
        self.current_rooms.insert(room_id.to_string(), map);
        interactions
    }

    fn rotate(&mut self, next_year: i32) -> RotationReport {
        let report = self.population.rotate(next_year);
        self.schedules
            .ensure_for_population(&self.campus, &self.population, &mut self.rng);
        self.schedules.retain_active(&self.population);
        self.rebuild_world();
        self.rotations.push(report.clone());
        report
    }

    /// Rebuilds the dense core matrix for the new roster.
    ///
    /// Continuing students keep their relations with each other; graduates
    /// disappear together with their incoming and outgoing edges, and new
    /// students start with an empty row and column, exactly as after
    /// `Collective.remove_agent` + `add_agent` in v2.
    fn rebuild_world(&mut self) {
        let old_ids: BTreeMap<String, usize> = self
            .world
            .agents
            .iter()
            .enumerate()
            .map(|(index, agent)| (agent.string_id.clone(), index))
            .collect();

        let mut config = self.world.config.clone();
        config.init_mode = InitMode::Empty;
        let mut world = World::from_specs(self.population.to_specs(), config);

        let old_n = self.world.len();
        let new_n = world.len();
        let mut relations = vec![Relation::ZERO; new_n * new_n];
        for (new_from, student) in self.population.students.iter().enumerate() {
            let Some(&old_from) = old_ids.get(&student.string_id) else {
                continue;
            };
            for (new_to, target) in self.population.students.iter().enumerate() {
                let Some(&old_to) = old_ids.get(&target.string_id) else {
                    continue;
                };
                relations[new_from * new_n + new_to] =
                    self.world.relations[old_from * old_n + old_to];
            }
        }

        world.relations = relations;

        // Continuing students keep the emotions they had before the
        // rotation, exactly as if their dense index had not changed.  The
        // semester reset that follows immediately in `step_day` overwrites
        // them, but a direct `rotate` remains semantically faithful too.
        for (new_index, student) in self.population.students.iter_mut().enumerate() {
            let Some(&old_index) = old_ids.get(&student.string_id) else {
                continue;
            };
            let emotions = self.world.agents[old_index].emotions;
            world.agents[new_index].emotions = emotions;
            student.emotions = emotions;
        }

        world.rng = self.world.rng.clone();
        world.day = self.world.day;
        self.world = world;
        self.sync_university_state();
    }

    fn sync_university_state(&mut self) {
        let n = self.world.len();
        self.statuses = vec![AgentStatus::Home; n];
        self.arrived_today = vec![false; n];
        self.left_campus_today = vec![false; n];
        self.gym_sections = vec![None; n];
        self.sportiness = self
            .population
            .students
            .iter()
            .map(|student| student.sportiness)
            .collect();
        self.skip_tendency = self
            .population
            .students
            .iter()
            .map(|student| student.skip_tendency)
            .collect();
        self.current_rooms.clear();
    }

    fn reset_emotions(&mut self) {
        let (world, rng) = (&mut self.world, &mut self.rng);
        for agent in &mut world.agents {
            agent.emotions = EmotionVector::random(rng, EMOTION_MIN, EMOTION_MAX);
        }
        self.sync_emotions_to_population();
    }

    /// Mirrors the live emotional state into the roster.
    ///
    /// The dense core is authoritative during a run; the roster needs the
    /// same values when it is serialized or when a new dense matrix is built
    /// after a rotation.
    fn sync_emotions_to_population(&mut self) {
        for (student, agent) in self
            .population
            .students
            .iter_mut()
            .zip(self.world.agents.iter())
        {
            student.emotions = agent.emotions;
        }
    }

    /// Fingerprint of the persistent state: core agents and relations, both
    /// RNG streams, the roster and the day counter.
    pub fn state_hash(&self) -> u64 {
        let mut hash = self.world.state_hash();
        mix(&mut hash, self.rng.state());
        mix(&mut hash, self.population.rng_state());
        mix(&mut hash, u64::from(self.days_completed));
        for student in &self.population.students {
            hash_text(&mut hash, &student.string_id);
            hash_text(&mut hash, &student.group);
            mix(&mut hash, u64::from(student.course_year));
            mix(&mut hash, student.archetype as u64);
        }
        for status in &self.statuses {
            mix(&mut hash, *status as u64);
        }
        hash
    }

    /// Flat contact stream of the last day, useful for exporters that do not
    /// want the per-slot wrapper.
    pub fn flat_interactions(day: &UniversityDay) -> Vec<Interaction> {
        day.interactions
            .iter()
            .map(|event| Interaction::new(event.from, event.to, event.outcome))
            .collect()
    }

    pub fn agent_id(index: usize) -> AgentId {
        AgentId::new(index as u32)
    }
}

fn random_section(rng: &mut DeterministicRng) -> GymSection {
    GymSection::from_index((rng.next_u64() % crate::campus::GYM_SECTIONS as u64) as usize)
}

fn mix(hash: &mut u64, value: u64) {
    *hash ^= value;
    *hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
}

fn hash_text(hash: &mut u64, text: &str) {
    for byte in text.bytes() {
        mix(hash, u64::from(byte));
    }
    mix(hash, 0xff);
}

#[cfg(test)]
mod tests {
    use automata_core::Context;

    use super::*;

    fn university() -> University {
        University::new(UniversityConfig::default())
    }

    #[test]
    fn first_day_is_a_sunday_without_contacts() {
        let mut university = university();
        let day = university.step_day().unwrap();

        assert_eq!(day.day_id, 0);
        assert_eq!(day.date, Date::new(2024, 9, 1));
        assert_eq!(day.weekday, Weekday::Sunday);
        assert!(day.is_sunday);
        assert!(day.interactions.is_empty());
        assert_eq!(university.days_completed(), 1);
        assert!(
            university
                .statuses()
                .iter()
                .all(|s| *s == AgentStatus::Home)
        );
    }

    #[test]
    fn monday_runs_the_nine_slot_day_and_ends_at_home() {
        let mut university = university();
        university.step_day().expect("sunday");
        let day = university.step_day().expect("monday");

        assert_eq!(day.day_id, 1);
        assert_eq!(day.weekday, Weekday::Monday);
        assert!(!day.is_sunday);
        assert!(!day.interactions.is_empty());
        assert!(
            day.interactions
                .iter()
                .all(|event| (1..=8).contains(&event.slot_id))
        );
        assert!(
            university
                .statuses()
                .iter()
                .all(|s| *s == AgentStatus::Home)
        );
        assert_eq!(university.current_rooms.len(), 1);
        assert!(university.current_rooms.contains_key(GYM_ID));
    }

    #[test]
    fn slot_context_matches_the_room() {
        let mut university = university();
        university.step_day();
        let day = university.step_day().unwrap();

        for event in &day.interactions {
            match event.slot_id {
                2 | 4 | 6 => assert_eq!(event.context, Context::Break),
                8 => assert_eq!(event.context, Context::Gym),
                // A pair slot can also put a student with a free window
                // into the corridor; only breaks and the gym are fixed.
                1 | 3 | 5 | 7 => {}
                other => panic!("unexpected interaction slot {other}"),
            }
        }
    }

    #[test]
    fn sunday_changes_emotions_but_not_relations() {
        let mut university = university();
        let relations = university.world.relations.clone();
        university.step_day().unwrap();
        assert_eq!(university.world.relations, relations);
    }

    #[test]
    fn repeated_runs_are_bit_identical() {
        let mut left = university();
        let mut right = university();
        for _ in 0..4 {
            left.step_day();
            right.step_day();
        }
        assert_eq!(left.state_hash(), right.state_hash());
        assert_eq!(left.rng.state(), right.rng.state());
        assert_eq!(left.population.rng_state(), right.population.rng_state());
    }

    #[test]
    fn thread_count_does_not_change_the_university_trajectory() {
        let mut single = University::new(UniversityConfig {
            parallelism: 1,
            ..UniversityConfig::default()
        });
        let mut many = University::new(UniversityConfig {
            parallelism: 8,
            ..UniversityConfig::default()
        });
        for _ in 0..3 {
            single.step_day();
            many.step_day();
        }
        assert_eq!(single.state_hash(), many.state_hash());
    }

    #[test]
    fn semester_reset_uses_the_wider_emotion_range() {
        let mut university = university();
        let before = university.rng.state();
        university.reset_emotions();
        assert_ne!(before, university.rng.state());
        for agent in &university.world.agents {
            for axis in automata_core::EmotionAxis::ALL {
                let value = agent.emotions.get(axis).get();
                assert!((EMOTION_MIN..=EMOTION_MAX).contains(&value));
            }
        }
    }

    #[test]
    fn rotation_keeps_continuing_relations_and_drops_graduates() {
        let mut university = university();
        let graduate = university.find_agent("S-П-21-1-01").expect("graduate");
        let continuing = university.find_agent("S-П-22-1-01").expect("continuing");
        let other = university.find_agent("S-П-22-1-02").expect("continuing");
        let relation = Relation::new(40, 30, 20);
        university
            .world
            .set_relation(graduate, continuing, relation);
        university.world.set_relation(continuing, other, relation);

        let report = university.rotate(2025);
        assert_eq!(report.total_after, 1620);
        assert_eq!(university.len(), 1620);
        assert!(university.find_agent("S-П-21-1-01").is_none());

        let continuing = university.find_agent("S-П-22-1-01").unwrap();
        let other = university.find_agent("S-П-22-1-02").unwrap();
        assert_eq!(university.world.relation(continuing, other), relation);

        // The graduate's row and column are gone; the roster is fully dense.
        assert_eq!(university.world.relations.len(), 1620 * 1620);
    }

    #[test]
    fn rotation_uses_sixty_master_places_and_keeps_population_size() {
        let mut university = university();
        let report = university.rotate(2025);
        assert_eq!(report.continued_bachelors + report.new_external_masters, 60);
        assert_eq!(report.new_bachelors, 375);
        assert_eq!(university.population.bachelors(), 1500);
        assert_eq!(university.population.masters(), 120);
    }

    #[test]
    fn a_full_horizon_has_1213_days() {
        assert_eq!(university().calendar.clone().count(), TOTAL_DAYS as usize);
    }

    /// Release-scale regression: the full trajectory is expensive in a debug
    /// build, so it stays ignored and is run explicitly before a commit that
    /// touches the university runtime.
    #[test]
    #[ignore = "release-scale; run with --release -- --ignored"]
    fn full_horizon_matches_the_recorded_trajectory() {
        let mut university = university();
        let mut days = 0;
        let mut sundays = 0;
        let mut rotations = 0;
        let mut interactions = 0u64;

        while let Some(day) = university.step_day() {
            days += 1;
            sundays += u32::from(day.is_sunday);
            rotations += u32::from(day.rotation.is_some());
            interactions += day.interactions.len() as u64;
        }

        assert_eq!(days, TOTAL_DAYS);
        assert_eq!(sundays, 173);
        assert_eq!(rotations, 3);
        assert_eq!(interactions, 4_294_325);
        assert_eq!(university.population.bachelors(), 1500);
        assert_eq!(university.population.masters(), 120);
        assert_eq!(university.state_hash(), 0x79f5_8093_8535_8043);
    }
}
