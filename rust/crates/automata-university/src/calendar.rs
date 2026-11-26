//! Academic calendar of the v2 university world.
//!
//! The simulated year starts on 1 September (a Sunday in 2024), has a autumn
//! semester of 153 days (1 September -- 31 January), a spring semester of
//! 150 days (1 February -- 30 June; 151 in a leap year), and jumps over July
//! and August.  Four academic years therefore produce 1213 simulated days:
//! 4 * 153 + 3 * 150 + 151 = 1213.
//!
//! `day_id` is a dense 0-based index of a *simulated* day.  Sundays are part
//! of the index but are not written to `agent_states`; July and August do not
//! consume an index at all.

/// Total number of simulated days in one full v2 horizon.
pub const TOTAL_DAYS: u32 = 1213;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Date {
    pub year: i32,
    pub month: u8,
    pub day: u8,
}

impl Date {
    pub fn new(year: i32, month: u8, day: u8) -> Self {
        assert!((1..=12).contains(&month), "month out of range: {month}");
        assert!(
            (1..=days_in_month(year, month)).contains(&day),
            "day out of range: {year}-{month}-{day}"
        );
        Self { year, month, day }
    }

    pub fn next_day(self) -> Self {
        if self.day < days_in_month(self.year, self.month) {
            Self {
                day: self.day + 1,
                ..self
            }
        } else if self.month < 12 {
            Self {
                month: self.month + 1,
                day: 1,
                ..self
            }
        } else {
            Self {
                year: self.year + 1,
                month: 1,
                day: 1,
            }
        }
    }

    /// Gregorian weekday, with Sunday = 0 to match `day_id % 7`.
    pub fn weekday(self) -> Weekday {
        let (year, month) = if self.month < 3 {
            (self.year - 1, i32::from(self.month) + 12)
        } else {
            (self.year, i32::from(self.month))
        };
        let k = year.rem_euclid(100);
        let j = year.div_euclid(100);
        let h = (i32::from(self.day) + (13 * (month + 1)) / 5 + k + k / 4 + j / 4 + 5 * j)
            .rem_euclid(7);

        match h {
            0 => Weekday::Saturday,
            1 => Weekday::Sunday,
            2 => Weekday::Monday,
            3 => Weekday::Tuesday,
            4 => Weekday::Wednesday,
            5 => Weekday::Thursday,
            _ => Weekday::Friday,
        }
    }
}

pub const fn is_leap_year(year: i32) -> bool {
    (year % 4 == 0 && year % 100 != 0) || year % 400 == 0
}

pub const fn days_in_month(year: i32, month: u8) -> u8 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if is_leap_year(year) => 29,
        2 => 28,
        _ => 0,
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[repr(u8)]
pub enum Weekday {
    Sunday = 0,
    Monday = 1,
    Tuesday = 2,
    Wednesday = 3,
    Thursday = 4,
    Friday = 5,
    Saturday = 6,
}

impl Weekday {
    pub const fn index(self) -> u8 {
        self as u8
    }

    pub const fn is_sunday(self) -> bool {
        matches!(self, Self::Sunday)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Semester {
    Autumn,
    Spring,
}

impl Semester {
    pub const fn key(self) -> &'static str {
        match self {
            Self::Autumn => "AUTUMN",
            Self::Spring => "SPRING",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CalendarDay {
    /// Dense 0-based index, 0..=1212.
    pub day_id: u32,
    pub date: Date,
    pub weekday: Weekday,
    /// Academic year of the form 2024 for 2024/25.
    pub academic_year: i32,
    pub semester: Semester,
    /// 1-based semester number, 1..=8.
    pub semester_index: u32,
    /// True on 1 September, including the very first simulated day.
    pub starts_autumn: bool,
    /// True on 1 February.
    pub starts_spring: bool,
    pub is_sunday: bool,
}

/// Deterministic generator of the academic calendar.
#[derive(Clone, Debug)]
pub struct Calendar {
    current: Date,
    day_id: u32,
    academic_year: i32,
    semester: Semester,
    semester_index: u32,
}

impl Calendar {
    pub fn new(start_year: i32) -> Self {
        Self {
            current: Date::new(start_year, 9, 1),
            day_id: 0,
            academic_year: start_year,
            semester: Semester::Autumn,
            semester_index: 1,
        }
    }

    pub fn day_id(&self) -> u32 {
        self.day_id
    }

    pub fn next_day(&mut self) -> Option<CalendarDay> {
        if self.day_id >= TOTAL_DAYS {
            return None;
        }

        let date = self.current;
        let day = CalendarDay {
            day_id: self.day_id,
            date,
            weekday: date.weekday(),
            academic_year: self.academic_year,
            semester: self.semester,
            semester_index: self.semester_index,
            starts_autumn: date.month == 9 && date.day == 1,
            starts_spring: date.month == 2 && date.day == 1,
            is_sunday: date.weekday().is_sunday(),
        };

        self.day_id += 1;
        self.advance();
        Some(day)
    }

    fn advance(&mut self) {
        let next = self.current.next_day();

        if next.month == 7 || next.month == 8 {
            // Summer is not simulated.  The next academic year starts on
            // 1 September of the same calendar year.
            self.current = Date::new(next.year, 9, 1);
            self.academic_year = next.year;
            self.semester = Semester::Autumn;
            self.semester_index += 1;
            return;
        }

        if next.month == 2 && next.day == 1 {
            self.semester = Semester::Spring;
            self.semester_index += 1;
        }

        self.current = next;
    }
}

impl Iterator for Calendar {
    type Item = CalendarDay;

    fn next(&mut self) -> Option<Self::Item> {
        self.next_day()
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::*;

    #[test]
    fn first_day_is_sunday_september_first() {
        let day = Calendar::new(2024).next().unwrap();
        assert_eq!(day.day_id, 0);
        assert_eq!(day.date, Date::new(2024, 9, 1));
        assert_eq!(day.weekday, Weekday::Sunday);
        assert!(day.is_sunday);
        assert_eq!(day.semester, Semester::Autumn);
        assert_eq!(day.semester_index, 1);
        assert!(day.starts_autumn);
    }

    #[test]
    fn horizon_has_1213_days_and_ends_in_june_2028() {
        let days: Vec<_> = Calendar::new(2024).collect();
        assert_eq!(days.len(), TOTAL_DAYS as usize);
        assert_eq!(days.first().unwrap().day_id, 0);
        assert_eq!(days.last().unwrap().day_id, TOTAL_DAYS - 1);
        assert_eq!(days.last().unwrap().date, Date::new(2028, 6, 30));
    }

    #[test]
    fn summer_is_never_emitted() {
        let days: Vec<_> = Calendar::new(2024).collect();
        assert!(days.iter().all(|day| !(7..=8).contains(&day.date.month)));
    }

    #[test]
    fn sundays_follow_the_real_weekday() {
        for day in Calendar::new(2024) {
            assert_eq!(day.is_sunday, day.weekday == Weekday::Sunday);
            assert_eq!(day.weekday.index(), day.date.weekday().index());
        }
    }

    #[test]
    fn summer_drift_is_explicit_and_not_hidden_in_day_id() {
        let days: Vec<_> = Calendar::new(2024).collect();

        // First academic year: the dense index happens to align with the
        // weekday because the horizon starts on Sunday.
        let first_sundays: Vec<_> = days
            .iter()
            .filter(|day| day.is_sunday)
            .take(4)
            .map(|day| day.day_id)
            .collect();
        assert_eq!(first_sundays, vec![0, 7, 14, 21]);

        // After the first summer the 62 skipped calendar days shift the
        // weekday by 62 mod 7 = 6.  A dense day_id must not be treated as
        // `weekday = day_id % 7`; v2 analytics made that assumption and it
        // only held for the first year.
        let june_29_2025 = days
            .iter()
            .find(|day| day.date == Date::new(2025, 6, 29))
            .unwrap();
        let september_1_2025 = days
            .iter()
            .find(|day| day.date == Date::new(2025, 9, 1))
            .unwrap();
        let september_7_2025 = days
            .iter()
            .find(|day| day.date == Date::new(2025, 9, 7))
            .unwrap();

        assert_eq!(june_29_2025.weekday, Weekday::Sunday);
        assert_eq!(september_1_2025.weekday, Weekday::Monday);
        assert_eq!(september_7_2025.weekday, Weekday::Sunday);
        assert_eq!(september_7_2025.day_id % 7, 1);
    }

    #[test]
    fn sunday_counts_match_the_v2_state_gaps() {
        let mut sundays_per_year: BTreeMap<i32, u32> = BTreeMap::new();
        for day in Calendar::new(2024) {
            if day.is_sunday {
                *sundays_per_year.entry(day.academic_year).or_default() += 1;
            }
        }
        assert_eq!(sundays_per_year.len(), 4);
        // 2024/25 starts on Sunday, so its Sunday count is one higher.
        assert_eq!(sundays_per_year[&2024], 44);
        for year in 2025..=2027 {
            assert_eq!(sundays_per_year[&year], 43);
        }
        // v2 logs the initial state on day 0 before the first Sunday reset,
        // so the observed gap is 173 - 1 = 172 days, matching ClickHouse.
        assert_eq!(sundays_per_year.values().sum::<u32>() - 1, 172);
    }

    #[test]
    fn every_academic_year_has_153_autumn_and_150_or_151_spring_days() {
        let mut per_year: BTreeMap<(i32, Semester), u32> = BTreeMap::new();
        for day in Calendar::new(2024) {
            *per_year
                .entry((day.academic_year, day.semester))
                .or_default() += 1;
        }

        assert_eq!(per_year.len(), 8);
        for year in 2024..=2027 {
            assert_eq!(per_year[&(year, Semester::Autumn)], 153);
        }
        for year in 2024..=2026 {
            assert_eq!(per_year[&(year, Semester::Spring)], 150);
        }
        assert_eq!(per_year[&(2027, Semester::Spring)], 151);
    }

    #[test]
    fn leap_day_2028_is_present() {
        let days: Vec<_> = Calendar::new(2024).collect();
        assert!(days.iter().any(|day| day.date == Date::new(2028, 2, 29)));
    }

    #[test]
    fn semester_index_runs_from_one_to_eight() {
        let days: Vec<_> = Calendar::new(2024).collect();
        assert_eq!(days.first().unwrap().semester_index, 1);
        assert_eq!(days.last().unwrap().semester_index, 8);
        assert!(days.iter().all(|day| (1..=8).contains(&day.semester_index)));

        for pair in days.windows(2) {
            let previous = pair[0];
            let next = pair[1];
            assert!(
                next.semester_index == previous.semester_index
                    || next.semester_index == previous.semester_index + 1
            );
        }
    }

    #[test]
    fn february_first_starts_spring_and_september_first_starts_autumn() {
        let days: Vec<_> = Calendar::new(2024).collect();
        for day in days {
            assert_eq!(day.starts_spring, day.date.month == 2 && day.date.day == 1);
            assert_eq!(day.starts_autumn, day.date.month == 9 && day.date.day == 1);
            if day.starts_spring {
                assert_eq!(day.semester, Semester::Spring);
            }
            if day.starts_autumn {
                assert_eq!(day.semester, Semester::Autumn);
            }
        }
    }
}
