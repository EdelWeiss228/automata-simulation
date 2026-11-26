//! Softmax seating.
//!
//! v2 `_seat_students` shuffles the arrivals, samples at most 15 free seats,
//! and prefers seats next to relations with a high priority score.  The gym
//! grid is split into three isolated sections.  This module keeps the same
//! distribution but uses free-seat pools instead of rescanning the whole room
//! for every student, which was the main quadratic cost of the Python path.

use automata_core::{Context, DeterministicRng, World};

use crate::campus::{GYM_ID, GYM_SECTIONS, GymSection, Room};

pub const MAX_CANDIDATES: usize = 15;
pub const SEAT_SCORE_SCALE: f32 = 1.5;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SeatMap {
    pub room: String,
    pub cols: usize,
    pub seats: Vec<Option<usize>>,
}

impl SeatMap {
    pub fn occupied(&self) -> impl Iterator<Item = (usize, usize)> + '_ {
        self.seats
            .iter()
            .enumerate()
            .filter_map(|(seat, agent)| agent.map(|agent| (seat, agent)))
    }

    pub fn agent_at(&self, seat: usize) -> Option<usize> {
        self.seats.get(seat).copied().flatten()
    }

    pub fn len(&self) -> usize {
        self.seats.len()
    }

    pub fn is_empty(&self) -> bool {
        self.seats.is_empty()
    }
}

/// Seats `students` in `room`.  Returns the full grid including empty seats.
pub fn seat_students(
    world: &World,
    rng: &mut DeterministicRng,
    room: &Room,
    students: &[usize],
    gym_sections: &[Option<GymSection>],
) -> SeatMap {
    let capacity = room.capacity;
    let cols = room.cols();
    let context = room.context();

    let mut seated = vec![None; capacity];
    if capacity == 0 || students.is_empty() {
        return SeatMap {
            room: room.id.clone(),
            cols,
            seats: seated,
        };
    }

    let mut order: Vec<usize> = students.to_vec();
    shuffle(&mut order, rng);

    if room.id == GYM_ID {
        let mut free = gym_free_seats(capacity);
        for student in order {
            let section = gym_sections
                .get(student)
                .copied()
                .flatten()
                .unwrap_or(GymSection::Badminton);
            let pool = &mut free[section.index()];
            if pool.is_empty() {
                continue;
            }
            place_student(
                world,
                rng,
                context,
                student,
                &mut seated,
                capacity,
                cols,
                pool,
            );
        }
    } else {
        let mut free: Vec<usize> = (0..capacity).collect();
        for student in order {
            place_student(
                world,
                rng,
                context,
                student,
                &mut seated,
                capacity,
                cols,
                &mut free,
            );
        }
    }

    SeatMap {
        room: room.id.clone(),
        cols,
        seats: seated,
    }
}

#[allow(clippy::too_many_arguments)]
fn place_student(
    world: &World,
    rng: &mut DeterministicRng,
    context: Context,
    student: usize,
    seated: &mut [Option<usize>],
    capacity: usize,
    cols: usize,
    free: &mut Vec<usize>,
) {
    let candidates = candidate_seats(free, rng);
    if candidates.is_empty() {
        return;
    }

    let mut weights = Vec::with_capacity(candidates.len());
    for &(_, seat) in &candidates {
        let mut weight = 0.5 + rng.next_f32() * 0.5;
        for neighbor in neighbors(seat, cols, capacity) {
            if let Some(other) = seated[neighbor] {
                let score = world.priority_score(student, other, context);
                weight += (score * SEAT_SCORE_SCALE).exp();
            }
        }
        weights.push(weight);
    }

    let mut best = 0usize;
    let mut best_key = f32::NEG_INFINITY;
    for (index, &weight) in weights.iter().enumerate() {
        let key = rng.next_f32() * weight;
        if key > best_key {
            best_key = key;
            best = index;
        }
    }

    let (position, seat) = candidates[best];
    free.swap_remove(position);
    seated[seat] = Some(student);
}

/// At most `MAX_CANDIDATES` free seats.
///
/// When a room has no more than 15 free seats, v2 keeps the ascending seat
/// order; with more it draws a uniform sample without replacement.
fn candidate_seats(free: &[usize], rng: &mut DeterministicRng) -> Vec<(usize, usize)> {
    if free.len() <= MAX_CANDIDATES {
        let mut candidates: Vec<(usize, usize)> = free.iter().copied().enumerate().collect();
        candidates.sort_by_key(|&(_, seat)| seat);
        return candidates;
    }

    let mut positions = Vec::with_capacity(MAX_CANDIDATES);
    while positions.len() < MAX_CANDIDATES {
        let position = (rng.next_u64() % free.len() as u64) as usize;
        if !positions.contains(&position) {
            positions.push(position);
        }
    }
    positions
        .into_iter()
        .map(|position| (position, free[position]))
        .collect()
}

pub(crate) fn neighbors(seat: usize, cols: usize, capacity: usize) -> Vec<usize> {
    let mut result = Vec::with_capacity(4);
    let column = seat % cols;
    if column > 0 {
        result.push(seat - 1);
    }
    if column + 1 < cols && seat + 1 < capacity {
        result.push(seat + 1);
    }
    if seat >= cols {
        result.push(seat - cols);
    }
    if seat + cols < capacity {
        result.push(seat + cols);
    }
    result
}

/// Free seats of every gym section, in ascending order.
fn gym_free_seats(capacity: usize) -> [Vec<usize>; GYM_SECTIONS] {
    let mut free: [Vec<usize>; GYM_SECTIONS] = std::array::from_fn(|_| Vec::new());
    for seat in 0..capacity {
        free[GymSection::of_seat(seat).index()].push(seat);
    }
    free
}

fn shuffle(values: &mut [usize], rng: &mut DeterministicRng) {
    for index in (1..values.len()).rev() {
        let other = (rng.next_u64() % (index as u64 + 1)) as usize;
        values.swap(index, other);
    }
}

#[cfg(test)]
mod tests {
    use automata_core::{AgentSpec, ArchetypeKind, Degree, World, WorldConfig};

    use super::*;
    use crate::campus::Campus;

    fn world(count: usize) -> World {
        let specs = (0..count)
            .map(|index| {
                AgentSpec::new(
                    format!("A-{index:03}"),
                    ArchetypeKind::ALL[index % ArchetypeKind::ALL.len()],
                    1.0,
                    (index / 25) as u32,
                    ((index % 4) + 1) as u8,
                    Degree::Bachelor,
                )
            })
            .collect();
        World::from_specs(specs, WorldConfig::default())
    }

    #[test]
    fn every_student_gets_a_unique_seat_when_the_room_is_large_enough() {
        let campus = Campus::new(2024);
        let room = campus.room("Aud_П_24_1_S").unwrap();
        let world = world(25);
        let students: Vec<usize> = (0..25).collect();
        let mut rng = DeterministicRng::new(1);
        let map = seat_students(&world, &mut rng, room, &students, &[]);

        let seats: Vec<usize> = map.occupied().map(|(seat, _)| seat).collect();
        assert_eq!(seats.len(), 25);
        let unique: std::collections::BTreeSet<_> = seats.iter().copied().collect();
        assert_eq!(unique.len(), 25);
        assert!(seats.iter().all(|&seat| seat < room.capacity));
    }

    #[test]
    fn seating_is_deterministic() {
        let campus = Campus::new(2024);
        let room = campus.room(crate::campus::GYM_ID).unwrap();
        let world = world(200);
        let students: Vec<usize> = (0..200).collect();
        let sections: Vec<Option<GymSection>> = (0..200)
            .map(|index| Some(GymSection::from_index(index % GYM_SECTIONS)))
            .collect();

        let mut left_rng = DeterministicRng::new(77);
        let mut right_rng = DeterministicRng::new(77);
        let left = seat_students(&world, &mut left_rng, room, &students, &sections);
        let right = seat_students(&world, &mut right_rng, room, &students, &sections);
        assert_eq!(left, right);
    }

    #[test]
    fn gym_sections_are_isolated() {
        let campus = Campus::new(2024);
        let room = campus.room(crate::campus::GYM_ID).unwrap();
        let world = world(300);
        let students: Vec<usize> = (0..300).collect();
        let sections: Vec<Option<GymSection>> = (0..300)
            .map(|index| Some(GymSection::from_index(index % GYM_SECTIONS)))
            .collect();
        let mut rng = DeterministicRng::new(5);
        let map = seat_students(&world, &mut rng, room, &students, &sections);

        for (seat, agent) in map.occupied() {
            assert_eq!(
                GymSection::of_seat(seat),
                sections[agent].unwrap(),
                "agent {agent} seated in the wrong section"
            );
        }
    }
}
