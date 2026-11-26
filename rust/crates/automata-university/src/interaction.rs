//! Neighbourhood interaction inside one room.
//!
//! v2 `_interact_in_room` does not create a complete graph of the room.  It
//! shuffles the occupied seats, starts from an unprocessed seat, collects its
//! four-way neighbours, and extends the group with a temperature-softmax until
//! a STOP choice or an already-used seat.  Every pair inside the resulting
//! group then makes one contact.  This module keeps that topology; only the
//! representation changed from names to dense indices.

use automata_core::{AgentId, Context, DeterministicRng, Outcome, World};

use crate::campus::GymSection;
use crate::seating::{SeatMap, neighbors};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct UniversityInteraction {
    pub slot_id: u32,
    pub context: Context,
    pub from: AgentId,
    pub to: AgentId,
    pub outcome: Outcome,
}

const STOP: usize = usize::MAX;

pub fn interact_in_room(
    world: &mut World,
    rng: &mut DeterministicRng,
    map: &SeatMap,
    gym_sections: &[Option<GymSection>],
    slot_id: u32,
    context: Context,
) -> Vec<UniversityInteraction> {
    let mut interactions = Vec::new();
    if map.seats.len() < 2 {
        return interactions;
    }

    let mut active: Vec<usize> = map.occupied().map(|(seat, _)| seat).collect();
    shuffle(&mut active, rng);

    let mut interacted = vec![false; map.seats.len()];
    let mut valid_seats: Vec<usize> = Vec::with_capacity(4);
    let mut scores: Vec<f32> = Vec::with_capacity(4);
    let mut weights: Vec<f32> = Vec::with_capacity(5);
    let mut group: Vec<usize> = Vec::with_capacity(5);

    for seat in active {
        if interacted[seat] {
            continue;
        }
        let Some(agent) = map.agent_at(seat) else {
            continue;
        };

        valid_seats.clear();
        scores.clear();
        weights.clear();

        for neighbor in neighbors(seat, map.cols, map.seats.len()) {
            if interacted[neighbor] {
                continue;
            }
            let Some(other) = map.agent_at(neighbor) else {
                continue;
            };
            if context == Context::Gym
                && gym_sections.get(agent).copied() != gym_sections.get(other).copied()
            {
                continue;
            }
            valid_seats.push(neighbor);
        }

        if valid_seats.is_empty() {
            continue;
        }

        let temperature = world.agents[agent].archetype.config().temperature.max(0.01);
        let mut max_score = f32::NEG_INFINITY;
        for &neighbor in &valid_seats {
            let other = map.agent_at(neighbor).expect("valid seat is occupied");
            let score = world.priority_score(agent, other, context);
            scores.push(score);
            max_score = max_score.max(score);
        }

        let mut sum = 0.0f32;
        for &score in &scores {
            let weight = ((score - max_score) / temperature).exp();
            weights.push(weight);
            sum += weight;
        }

        // STOP choice with the mean weight: a natural group-size barrier.
        let mean_weight = if weights.is_empty() {
            1.0
        } else {
            sum / weights.len() as f32
        };
        valid_seats.push(STOP);
        weights.push(mean_weight);

        group.clear();
        group.push(seat);
        loop {
            let chosen = weighted_pick(rng, &valid_seats, &weights);
            if chosen == STOP || group.contains(&chosen) {
                break;
            }
            group.push(chosen);
        }

        for left in 0..group.len() {
            for right in (left + 1)..group.len() {
                let from = map.agent_at(group[left]).expect("group seat is occupied");
                let to = map.agent_at(group[right]).expect("group seat is occupied");
                let outcome = world.interact_pair(from, to, context);
                interactions.push(UniversityInteraction {
                    slot_id,
                    context,
                    from: AgentId::new(from as u32),
                    to: AgentId::new(to as u32),
                    outcome,
                });
            }
        }

        for &chosen in &group {
            interacted[chosen] = true;
        }
    }

    interactions
}

fn weighted_pick(rng: &mut DeterministicRng, items: &[usize], weights: &[f32]) -> usize {
    let total: f32 = weights.iter().sum();
    if !total.is_finite() || total <= 0.0 {
        return items.first().copied().unwrap_or(STOP);
    }

    let mut threshold = rng.next_f32() * total;
    for (index, &weight) in weights.iter().enumerate() {
        threshold -= weight;
        if threshold < 0.0 {
            return items[index];
        }
    }
    items.last().copied().unwrap_or(STOP)
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
    use crate::campus::{Campus, GymSection};
    use crate::seating::seat_students;

    fn world(count: usize) -> World {
        let specs = (0..count)
            .map(|index| {
                AgentSpec::new(
                    format!("A-{index:03}"),
                    ArchetypeKind::ALL[index % ArchetypeKind::ALL.len()],
                    1.0,
                    0,
                    1,
                    Degree::Bachelor,
                )
            })
            .collect();
        World::from_specs(specs, WorldConfig::default())
    }

    #[test]
    fn adjacent_seats_can_produce_a_contact() {
        let mut world = world(3);
        let mut seats = vec![None; 12];
        seats[0] = Some(0);
        seats[1] = Some(1);
        seats[2] = Some(2);
        let map = SeatMap {
            room: "TEST".to_string(),
            cols: 6,
            seats,
        };

        let mut total = 0;
        for seed in 0..50 {
            let mut rng = DeterministicRng::new(seed);
            let interactions = interact_in_room(&mut world, &mut rng, &map, &[], 1, Context::Study);
            total += interactions.len();
            for event in interactions {
                assert_eq!(event.slot_id, 1);
                assert_eq!(event.context, Context::Study);
                assert_ne!(event.from, event.to);
            }
        }

        // A group is always allowed to stop immediately, so one seed is not
        // enough; over fifty seeds the neighbourhood must produce contacts.
        assert!(total > 0);
    }

    #[test]
    fn gym_sections_never_interact_across_the_boundary() {
        let campus = Campus::new(2024);
        let room = campus.room(crate::campus::GYM_ID).unwrap();
        let mut world = world(300);
        let students: Vec<usize> = (0..300).collect();
        let sections: Vec<Option<GymSection>> = (0..300)
            .map(|index| Some(GymSection::from_index(index % 3)))
            .collect();
        let mut rng = DeterministicRng::new(5);
        let map = seat_students(&world, &mut rng, room, &students, &sections);
        let interactions = interact_in_room(&mut world, &mut rng, &map, &sections, 8, Context::Gym);

        assert!(!interactions.is_empty());
        for event in interactions {
            let from = event.from.index();
            let to = event.to.index();
            assert_eq!(sections[from], sections[to]);
        }
    }
}
