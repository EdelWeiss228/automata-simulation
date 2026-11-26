//! Weekly schedules and the nine slots of a university day.
//!
//! v2 stores six weekdays (Monday .. Saturday) and four pairs per weekday.
//! Sunday is the family day and has no schedule at all.  The slot sequence of
//! a working day is fixed:
//!
//! `pair 1, break 1, pair 2, break 2, pair 3, break 3, pair 4, gym, cleanup`.

use std::collections::BTreeMap;

use automata_core::DeterministicRng;

use crate::campus::{Campus, GYM_ID};
use crate::population::{
    BACHELOR_FACULTIES, BACHELOR_GROUPS_PER_STREAM, BACHELOR_STREAMS, MASTER_DIRECTIONS,
    MASTER_YEARS, Population, master_group_id, year_suffix,
};

pub const WEEKDAYS: usize = 6;
pub const PAIRS_PER_DAY: usize = 4;

/// `None` means an empty pair (a window in the schedule).
pub type PairRoom = Option<String>;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WeekSchedule {
    days: [[PairRoom; PAIRS_PER_DAY]; WEEKDAYS],
}

impl WeekSchedule {
    pub fn empty() -> Self {
        Self {
            days: std::array::from_fn(|_| std::array::from_fn(|_| None)),
        }
    }

    /// `weekday` is 0 for Monday and 5 for Saturday.
    pub fn pairs(&self, weekday: usize) -> &[PairRoom; PAIRS_PER_DAY] {
        &self.days[weekday]
    }

    pub fn pair(&self, weekday: usize, pair: usize) -> Option<&str> {
        self.days[weekday][pair].as_deref()
    }

    pub fn set_pair(&mut self, weekday: usize, pair: usize, room: PairRoom) {
        self.days[weekday][pair] = room;
    }

    pub fn days(&self) -> &[[PairRoom; PAIRS_PER_DAY]; WEEKDAYS] {
        &self.days
    }
}

/// One of the nine steps of a working day.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DaySlot {
    Pair(u8),
    Break,
    Gym,
    Cleanup,
}

impl DaySlot {
    /// Stable 1-based identifier used by logs and by the web timeline.
    pub const fn slot_id(self, index: usize) -> u32 {
        index as u32 + 1
    }

    pub const fn key(self) -> &'static str {
        match self {
            Self::Pair(1) => "PAIR_1",
            Self::Pair(2) => "PAIR_2",
            Self::Pair(3) => "PAIR_3",
            Self::Pair(4) => "PAIR_4",
            Self::Pair(_) => "PAIR",
            Self::Break => "BREAK",
            Self::Gym => "GYM",
            Self::Cleanup => "CLEANUP",
        }
    }
}

pub const DAY_SLOTS: [DaySlot; 9] = [
    DaySlot::Pair(1),
    DaySlot::Break,
    DaySlot::Pair(2),
    DaySlot::Break,
    DaySlot::Pair(3),
    DaySlot::Break,
    DaySlot::Pair(4),
    DaySlot::Gym,
    DaySlot::Cleanup,
];

/// All group schedules of the university.
#[derive(Clone, Debug, Default)]
pub struct ScheduleBook {
    schedules: BTreeMap<String, WeekSchedule>,
}

impl ScheduleBook {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn len(&self) -> usize {
        self.schedules.len()
    }

    pub fn is_empty(&self) -> bool {
        self.schedules.is_empty()
    }

    pub fn get(&self, group: &str) -> Option<&WeekSchedule> {
        self.schedules.get(group)
    }

    pub fn insert(&mut self, group: impl Into<String>, schedule: WeekSchedule) {
        self.schedules.insert(group.into(), schedule);
    }

    pub fn groups(&self) -> impl Iterator<Item = &str> {
        self.schedules.keys().map(String::as_str)
    }

    /// Generates the schedules that exist on 1 September of the first year.
    ///
    /// Bachelors are built stream by stream: the four groups of a stream share
    /// the same 30 % lecture flags, but each group has its own seminar room.
    /// Masters receive one of the random schedules across the whole campus.
    pub fn generate_initial(
        &mut self,
        campus: &Campus,
        start_year: i32,
        rng: &mut DeterministicRng,
    ) {
        for faculty in BACHELOR_FACULTIES {
            for stream in 0..BACHELOR_STREAMS {
                let enrollment_year = start_year - i32::from(stream);
                let suffix = year_suffix(enrollment_year);
                let lecture_room = format!("Aud_{faculty}_{suffix}_L");
                let mut lectures = [[false; PAIRS_PER_DAY]; WEEKDAYS];
                for day in &mut lectures {
                    for flag in day {
                        *flag = rng.next_f32() < 0.3;
                    }
                }

                for group_number in 1..=BACHELOR_GROUPS_PER_STREAM {
                    let group = format!("{faculty}-{suffix}-{group_number}");
                    let seminar_room = format!("Aud_{faculty}_{suffix}_{group_number}_S");
                    let mut schedule = WeekSchedule::empty();

                    for (weekday, flags) in lectures.iter().enumerate() {
                        for (pair, &is_lecture) in flags.iter().enumerate() {
                            let room = if rng.next_f32() < 0.15 {
                                None
                            } else if is_lecture {
                                Some(lecture_room.clone())
                            } else if rng.next_f32() < 0.1 {
                                Some(GYM_ID.to_string())
                            } else {
                                Some(seminar_room.clone())
                            };
                            schedule.set_pair(weekday, pair, room);
                        }
                    }

                    self.insert(group, schedule);
                }
            }
        }

        for direction in MASTER_DIRECTIONS {
            for course_year in 1..=MASTER_YEARS {
                let enrollment_year = start_year - i32::from(course_year - 1);
                let group = master_group_id(direction, enrollment_year);
                self.ensure_master_schedule(campus, &group, rng);
            }
        }
    }

    /// Schedule for a group that appears after an academic rotation.
    ///
    /// v2 regenerates a fresh bachelor group in the same way as a master
    /// cohort: random rooms across the whole campus.  The original fallback
    /// referenced a non-existent `Aud_<faculty>_<year>_<group>_L` room; v3
    /// uses the real lecture hall of that faculty and year.
    pub fn ensure_bachelor_schedule(
        &mut self,
        campus: &Campus,
        group: &str,
        rng: &mut DeterministicRng,
    ) -> bool {
        if self.schedules.contains_key(group) {
            return false;
        }

        let parts: Vec<&str> = group.split('-').collect();
        if parts.len() != 3 {
            return false;
        }
        let (faculty, suffix) = (parts[0], parts[1]);

        let mut schedule = WeekSchedule::empty();
        for weekday in 0..WEEKDAYS {
            for pair in 0..PAIRS_PER_DAY {
                let room = if rng.next_f32() < 0.15 {
                    None
                } else if rng.next_f32() < 0.3 {
                    random_room(campus.lecture_rooms(), rng)
                } else if rng.next_f32() < 0.1 {
                    Some(GYM_ID.to_string())
                } else {
                    random_room(campus.seminar_rooms(), rng)
                };
                schedule.set_pair(weekday, pair, room);
            }
        }

        // If the random choice ever leaves a pair without a room, fall back to
        // the real lecture hall of this faculty instead of a phantom id.
        if campus.lecture_rooms().is_empty() {
            return false;
        }
        let fallback = format!("Aud_{faculty}_{suffix}_L");
        for weekday in 0..WEEKDAYS {
            for pair in 0..PAIRS_PER_DAY {
                if schedule.days()[weekday][pair].is_none() {
                    continue;
                }
                if schedule
                    .pair(weekday, pair)
                    .is_some_and(|room| !campus.contains(room))
                {
                    schedule.set_pair(weekday, pair, Some(fallback.clone()));
                }
            }
        }

        self.insert(group, schedule);
        true
    }

    pub fn ensure_master_schedule(
        &mut self,
        campus: &Campus,
        group: &str,
        rng: &mut DeterministicRng,
    ) -> bool {
        if self.schedules.contains_key(group) {
            return false;
        }

        let mut schedule = WeekSchedule::empty();
        for weekday in 0..WEEKDAYS {
            for pair in 0..PAIRS_PER_DAY {
                let room = if rng.next_f32() < 0.15 {
                    None
                } else if rng.next_f32() < 0.3 {
                    random_room(campus.lecture_rooms(), rng)
                } else if rng.next_f32() < 0.1 {
                    Some(GYM_ID.to_string())
                } else {
                    random_room(campus.seminar_rooms(), rng)
                };
                schedule.set_pair(weekday, pair, room);
            }
        }

        self.insert(group, schedule);
        true
    }

    /// Ensures every active group of `population` has a schedule.  New groups
    /// after rotation are bachelor cohorts (contain a dash-separated year) or
    /// master cohorts; both generators are idempotent.
    pub fn ensure_for_population(
        &mut self,
        campus: &Campus,
        population: &Population,
        rng: &mut DeterministicRng,
    ) {
        for student in &population.students {
            if self.schedules.contains_key(&student.group) {
                continue;
            }
            let is_master = student.degree == automata_core::Degree::Master;
            if is_master {
                self.ensure_master_schedule(campus, &student.group, rng);
            } else {
                self.ensure_bachelor_schedule(campus, &student.group, rng);
            }
        }
    }

    /// Drops the schedules of graduated cohorts, as v2 does after rotation.
    pub fn retain_active(&mut self, population: &Population) {
        let active: std::collections::BTreeSet<&str> = population
            .students
            .iter()
            .map(|student| student.group.as_str())
            .collect();
        self.schedules
            .retain(|group, _| active.contains(group.as_str()));
    }
}

fn random_room(rooms: &[String], rng: &mut DeterministicRng) -> PairRoom {
    if rooms.is_empty() {
        return None;
    }
    Some(rooms[(rng.next_u64() % rooms.len() as u64) as usize].clone())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::population::PopulationConfig;

    fn fixture() -> (Campus, ScheduleBook, DeterministicRng, Population) {
        let campus = Campus::new(2024);
        let mut rng = DeterministicRng::new(7);
        let mut book = ScheduleBook::new();
        book.generate_initial(&campus, 2024, &mut rng);
        let population = Population::new(PopulationConfig::default());
        (campus, book, rng, population)
    }

    #[test]
    fn every_initial_group_has_six_days_and_four_pairs() {
        let (_, book, _, population) = fixture();
        assert_eq!(book.len(), 72);
        for student in &population.students {
            let schedule = book.get(&student.group).expect("schedule");
            assert_eq!(schedule.days().len(), WEEKDAYS);
            for day in schedule.days() {
                assert_eq!(day.len(), PAIRS_PER_DAY);
            }
        }
    }

    #[test]
    fn every_scheduled_room_exists_on_campus() {
        let (campus, book, _, _) = fixture();
        for group in book.groups() {
            let schedule = book.get(group).unwrap();
            for weekday in 0..WEEKDAYS {
                for pair in 0..PAIRS_PER_DAY {
                    if let Some(room) = schedule.pair(weekday, pair) {
                        assert!(
                            campus.contains(room),
                            "group {group}, day {weekday}, pair {pair}: {room}"
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn day_slots_follow_the_v2_sequence() {
        let keys: Vec<_> = DAY_SLOTS
            .iter()
            .enumerate()
            .map(|(index, slot)| (index + 1, slot.key()))
            .collect();
        assert_eq!(
            keys,
            vec![
                (1, "PAIR_1"),
                (2, "BREAK"),
                (3, "PAIR_2"),
                (4, "BREAK"),
                (5, "PAIR_3"),
                (6, "BREAK"),
                (7, "PAIR_4"),
                (8, "GYM"),
                (9, "CLEANUP"),
            ]
        );
    }

    #[test]
    fn generation_is_reproducible() {
        let campus = Campus::new(2024);
        let mut left_rng = DeterministicRng::new(999);
        let mut right_rng = DeterministicRng::new(999);
        let mut left = ScheduleBook::new();
        let mut right = ScheduleBook::new();
        left.generate_initial(&campus, 2024, &mut left_rng);
        right.generate_initial(&campus, 2024, &mut right_rng);

        assert_eq!(left.len(), right.len());
        for group in left.groups() {
            assert_eq!(left.get(group), right.get(group));
        }
    }

    #[test]
    fn new_bachelor_and_master_groups_get_valid_schedules() {
        let (campus, mut book, mut rng, mut population) = fixture();
        population.rotate(2025);
        book.ensure_for_population(&campus, &population, &mut rng);
        book.retain_active(&population);

        // The 2021 cohort graduates; the 2024 cohort simply moves to year 2.
        assert!(book.get("П-21-1").is_none());
        assert!(book.get("П-24-1").is_some());
        for student in &population.students {
            let schedule = book.get(&student.group).expect("active schedule");
            for weekday in 0..WEEKDAYS {
                for pair in 0..PAIRS_PER_DAY {
                    if let Some(room) = schedule.pair(weekday, pair) {
                        assert!(campus.contains(room), "{room}");
                    }
                }
            }
        }
    }
}
