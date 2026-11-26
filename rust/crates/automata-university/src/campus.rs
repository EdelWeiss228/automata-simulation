//! Rooms of the university campus.
//!
//! The identifiers are the same as in v2 `UniversityManager._initialize_rooms`:
//! 25 lecture halls, 75 seminar rooms, one corridor and one gym.  Rooms are
//! inert geometry; the schedule decides who goes where and `seating` decides
//! who sits next to whom.

use std::collections::BTreeMap;

use automata_core::Context;

use crate::population::{BACHELOR_FACULTIES, year_suffix};

pub const LECTURE_CAPACITY: usize = 102;
pub const SEMINAR_CAPACITY: usize = 30;
pub const CORRIDOR_CAPACITY: usize = 1500;
pub const GYM_CAPACITY: usize = 1000;

/// Columns used by the seating grid.  Lecture halls and seminars are narrow
/// rooms; the corridor and the gym are wide open spaces.
pub const NARROW_COLS: usize = 6;
pub const WIDE_COLS: usize = 42;
pub const GYM_SECTIONS: usize = 3;

pub const CORRIDOR_ID: &str = "CORRIDOR";
pub const GYM_ID: &str = "GYM";

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum RoomKind {
    Lecture,
    Seminar,
    Corridor,
    Gym,
}

impl RoomKind {
    pub const fn context(self) -> Context {
        match self {
            Self::Lecture | Self::Seminar => Context::Study,
            Self::Corridor => Context::Break,
            Self::Gym => Context::Gym,
        }
    }

    pub const fn cols(self) -> usize {
        match self {
            Self::Lecture | Self::Seminar => NARROW_COLS,
            Self::Corridor | Self::Gym => WIDE_COLS,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Room {
    pub id: String,
    pub kind: RoomKind,
    pub capacity: usize,
}

impl Room {
    pub const fn cols(&self) -> usize {
        self.kind.cols()
    }

    pub const fn context(&self) -> Context {
        self.kind.context()
    }
}

#[derive(Clone, Debug)]
pub struct Campus {
    rooms: BTreeMap<String, Room>,
    lecture_rooms: Vec<String>,
    seminar_rooms: Vec<String>,
}

impl Campus {
    pub fn new(start_year: i32) -> Self {
        let mut rooms = BTreeMap::new();
        let mut lecture_rooms = Vec::with_capacity(25);
        let mut seminar_rooms = Vec::with_capacity(75);

        // 5 faculties x 5 enrolment years = 25 lecture halls.
        for faculty_index in 0..25 {
            let faculty = BACHELOR_FACULTIES[faculty_index / 5];
            let suffix = year_suffix(start_year - (faculty_index % 5) as i32);
            let id = format!("Aud_{faculty}_{suffix}_L");
            lecture_rooms.push(id.clone());
            rooms.insert(
                id.clone(),
                Room {
                    id,
                    kind: RoomKind::Lecture,
                    capacity: LECTURE_CAPACITY,
                },
            );
        }

        rooms.insert(
            CORRIDOR_ID.to_string(),
            Room {
                id: CORRIDOR_ID.to_string(),
                kind: RoomKind::Corridor,
                capacity: CORRIDOR_CAPACITY,
            },
        );

        // 5 faculties x 5 enrolment years x 3 groups = 75 seminar rooms.
        for room_index in 0..75 {
            let faculty = BACHELOR_FACULTIES[room_index / 15];
            let year_offset = ((room_index % 15) / 3) as i32;
            let suffix = year_suffix(start_year - year_offset);
            let group = room_index % 3 + 1;
            let id = format!("Aud_{faculty}_{suffix}_{group}_S");
            seminar_rooms.push(id.clone());
            rooms.insert(
                id.clone(),
                Room {
                    id,
                    kind: RoomKind::Seminar,
                    capacity: SEMINAR_CAPACITY,
                },
            );
        }

        rooms.insert(
            GYM_ID.to_string(),
            Room {
                id: GYM_ID.to_string(),
                kind: RoomKind::Gym,
                capacity: GYM_CAPACITY,
            },
        );

        lecture_rooms.sort();
        seminar_rooms.sort();
        Self {
            rooms,
            lecture_rooms,
            seminar_rooms,
        }
    }

    pub fn room(&self, id: &str) -> Option<&Room> {
        self.rooms.get(id)
    }

    pub fn contains(&self, id: &str) -> bool {
        self.rooms.contains_key(id)
    }

    pub fn len(&self) -> usize {
        self.rooms.len()
    }

    pub fn is_empty(&self) -> bool {
        self.rooms.is_empty()
    }

    pub fn lecture_rooms(&self) -> &[String] {
        &self.lecture_rooms
    }

    pub fn seminar_rooms(&self) -> &[String] {
        &self.seminar_rooms
    }

    pub fn iter(&self) -> impl Iterator<Item = &Room> {
        self.rooms.values()
    }
}

/// Three equal-width sections of the gym.  With 42 columns each section owns
/// exactly 14 columns, so `seat % 42` decides the section.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[repr(usize)]
pub enum GymSection {
    Badminton = 0,
    Football = 1,
    Basketball = 2,
}

impl GymSection {
    pub const ALL: [Self; GYM_SECTIONS] = [Self::Badminton, Self::Football, Self::Basketball];

    pub const fn index(self) -> usize {
        self as usize
    }

    pub const fn local_key(self) -> &'static str {
        match self {
            Self::Badminton => "BADMINTON",
            Self::Football => "FOOTBALL",
            Self::Basketball => "BASKETBALL",
        }
    }

    pub const fn from_index(index: usize) -> Self {
        match index % GYM_SECTIONS {
            0 => Self::Badminton,
            1 => Self::Football,
            _ => Self::Basketball,
        }
    }

    /// Section of a seat in the gym grid.
    pub fn of_seat(seat: usize) -> Self {
        let column = seat % WIDE_COLS;
        Self::from_index(column * GYM_SECTIONS / WIDE_COLS)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;

    #[test]
    fn campus_has_the_v2_rooms() {
        let campus = Campus::new(2024);
        assert_eq!(campus.len(), 25 + 1 + 75 + 1);
        assert_eq!(campus.lecture_rooms().len(), 25);
        assert_eq!(campus.seminar_rooms().len(), 75);

        assert!(campus.contains("Aud_П_24_L"));
        assert!(campus.contains("Aud_П_20_L"));
        assert!(campus.contains("Aud_Эк_24_3_S"));
        assert!(campus.contains(CORRIDOR_ID));
        assert!(campus.contains(GYM_ID));

        let ids: BTreeSet<_> = campus.iter().map(|room| room.id.as_str()).collect();
        assert_eq!(ids.len(), campus.len());
    }

    #[test]
    fn room_geometry_matches_v2() {
        let campus = Campus::new(2024);
        assert_eq!(campus.room("Aud_П_24_L").unwrap().cols(), 6);
        assert_eq!(campus.room("Aud_П_24_L").unwrap().capacity, 102);
        assert_eq!(campus.room("Aud_П_24_1_S").unwrap().cols(), 6);
        assert_eq!(campus.room("Aud_П_24_1_S").unwrap().capacity, 30);
        assert_eq!(campus.room(CORRIDOR_ID).unwrap().cols(), 42);
        assert_eq!(campus.room(CORRIDOR_ID).unwrap().capacity, 1500);
        assert_eq!(campus.room(GYM_ID).unwrap().cols(), 42);
        assert_eq!(campus.room(GYM_ID).unwrap().capacity, 1000);
    }

    #[test]
    fn gym_sections_split_the_grid_into_three_equal_parts() {
        let mut per_section = [0usize; GYM_SECTIONS];
        for seat in 0..GYM_CAPACITY {
            let section = GymSection::of_seat(seat);
            per_section[section.index()] += 1;
            assert_eq!(seat % WIDE_COLS / 14, section.index());
        }
        // 23 full rows plus 34 seats of the 24th row: 336 + 336 + 328.
        assert_eq!(per_section, [336, 336, 328]);
    }

    #[test]
    fn room_kinds_supply_the_interaction_context() {
        assert_eq!(RoomKind::Lecture.context(), Context::Study);
        assert_eq!(RoomKind::Seminar.context(), Context::Study);
        assert_eq!(RoomKind::Corridor.context(), Context::Break);
        assert_eq!(RoomKind::Gym.context(), Context::Gym);
    }
}
