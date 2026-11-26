use std::cmp::Ordering;

use crate::agent::{Agent, AgentSpec};
use crate::archetype::Context;
use crate::emotion::{EmotionAxis, EmotionVector, NUM_AXES};
use crate::ids::AgentId;
use crate::outcome::{Interaction, Outcome, sigma_rate_factor};
use crate::parallel::{for_each_agent_indexed_mut, for_each_agent_row_mut};
use crate::relation::{Relation, RelationAxis};
use crate::rng::DeterministicRng;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum InitMode {
    #[default]
    Empty,
    Random,
    Mixed,
}

/// All tunable constants of the kernel in one place.
///
/// The defaults are the corrected v2 values.  Keeping them explicit makes the
/// model reviewable and lets the future v3 scenario format override them
/// without editing code.
#[derive(Clone, Debug)]
pub struct WorldConfig {
    pub seed: u64,
    pub parallelism: usize,
    pub init_mode: InitMode,
    pub interaction_rounds: u32,
    /// `0.005` is the calibrated C++ v2 value used by the university batch.
    /// The Python fallback used `0.001`; that divergence is documented and not
    /// reproduced here.
    pub relation_to_emotion_rate: f32,
    /// C++ v2 `react_to_emotions` uses `k_factor = 0.05`.
    pub emotion_to_relation_rate: f32,
    pub influence_top_k: usize,
    pub influence_rate: f32,
    pub influence_max_step: f32,
    pub positive_relation_decay_scale: f32,
    pub success_probability: f32,
    pub refusal_min: f32,
    pub refusal_max: f32,
    pub refusal_penalty: f32,
    pub refusal_relation_scale: f32,
    pub refusal_context_floor: f32,
    pub emotional_reaction_rate: f32,
    pub base_affinity_delta: f32,
    pub base_trust_delta: f32,
    pub partner_positive_multiplier: f32,
    pub partner_negative_multiplier: f32,
}

impl Default for WorldConfig {
    fn default() -> Self {
        Self {
            seed: 42,
            parallelism: 1,
            init_mode: InitMode::Empty,
            interaction_rounds: 1,
            relation_to_emotion_rate: 0.005,
            emotion_to_relation_rate: 0.05,
            influence_top_k: 8,
            influence_rate: 0.6,
            influence_max_step: 0.9,
            positive_relation_decay_scale: 0.5,
            success_probability: 0.5,
            refusal_min: 0.01,
            refusal_max: 0.95,
            refusal_penalty: 20.0,
            refusal_relation_scale: 25.0,
            refusal_context_floor: 0.25,
            emotional_reaction_rate: 0.15,
            base_affinity_delta: 15.0,
            base_trust_delta: 10.0,
            partner_positive_multiplier: 2.0,
            partner_negative_multiplier: 0.5,
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct DayReport {
    /// 1-based day number after the step.
    pub day: u32,
    pub interactions: Vec<Interaction>,
}

#[derive(Clone, Debug, Default)]
pub struct RunReport {
    pub days: u32,
    pub total_interactions: usize,
    pub successes: usize,
    pub failures: usize,
    pub refusals: usize,
    pub final_hash: u64,
    pub final_rng_state: u64,
}

#[derive(Clone, Copy, Debug)]
struct InfluenceMeta {
    active: bool,
    primary_axis: EmotionAxis,
    weight_primary: f32,
    weight_secondary: f32,
    emotions: EmotionVector,
}

/// One deterministic simulation world.
///
/// The state is deliberately flat and index-based: `relations[i * n + j]` is
/// the ordered relation `i -> j`.  The stable human identifier lives on the
/// `Agent` and is not used as a map key in hot loops.
#[derive(Debug)]
pub struct World {
    pub agents: Vec<Agent>,
    pub relations: Vec<Relation>,
    pub rng: DeterministicRng,
    pub config: WorldConfig,
    pub day: u32,
}

impl World {
    pub fn from_specs(specs: Vec<AgentSpec>, config: WorldConfig) -> Self {
        let n = specs.len();
        let mut rng = DeterministicRng::new(config.seed);
        let agents = specs
            .into_iter()
            .enumerate()
            .map(|(index, spec)| Agent::from_spec(spec, AgentId::new(index as u32), &mut rng))
            .collect();

        let mut world = Self {
            agents,
            relations: vec![Relation::ZERO; n * n],
            rng,
            config,
            day: 0,
        };
        world.initialize_relations();
        world
    }

    pub fn len(&self) -> usize {
        self.agents.len()
    }

    pub fn is_empty(&self) -> bool {
        self.agents.is_empty()
    }

    pub fn relation(&self, from: usize, to: usize) -> Relation {
        self.relations[from * self.agents.len() + to]
    }

    pub fn set_relation(&mut self, from: usize, to: usize, relation: Relation) {
        let n = self.agents.len();
        self.relations[from * n + to] = relation;
    }

    fn initialize_relations(&mut self) {
        if self.config.init_mode == InitMode::Empty {
            return;
        }

        let n = self.agents.len();
        for i in 0..n {
            for j in 0..n {
                if i == j {
                    continue;
                }
                if self.agents[i].group_id != self.agents[j].group_id {
                    continue;
                }
                if self.config.init_mode == InitMode::Mixed
                    && (self.agents[i].course_year == 1 || self.agents[j].course_year == 1)
                {
                    continue;
                }

                let utility = self.rng.next_i16_inclusive(-100, 100);
                let affinity = self.rng.next_i16_inclusive(-100, 100);
                let trust = self.rng.next_i16_inclusive(-100, 100);
                self.relations[i * n + j] = Relation::new(utility, affinity, trust);
            }
        }
    }

    /// Priority of `target` for `actor`, matching v2
    /// `InteractionStrategy.priority_score`.
    ///
    /// A zero relation means "no relation yet" in the dense v3 matrix.  v2
    /// Python returns a neutral `0.5` in that case, *before* applying the
    /// archetype transformations; leaving it at zero would give a non-neutral
    /// `exp(0)`-based score to first-year students with an `Exp` transform.
    pub fn priority_score(&self, actor: usize, target: usize, context: Context) -> f32 {
        let config = self.agents[actor].archetype.config();
        let relation = self.relation(actor, target);
        if relation.is_zero() {
            return 0.5;
        }

        let affinity = config.scoring[RelationAxis::Affinity.index()]
            .apply(f32::from(relation.get(RelationAxis::Affinity)) / 10.0);
        let utility = config.scoring[RelationAxis::Utility.index()]
            .apply(f32::from(relation.get(RelationAxis::Utility)) / 10.0);
        let trust = config.scoring[RelationAxis::Trust.index()]
            .apply(f32::from(relation.get(RelationAxis::Trust)) / 10.0);

        (affinity + utility + trust) * config.context_multiplier(context)
    }

    /// Probability that the target refuses the initiator.
    ///
    /// The target's archetype supplies the base chance, the target's relation
    /// to the initiator shifts it, and the target's context adaptability
    /// scales it.  This is target-based and context-aware, as in v2 Python.
    pub fn refusal_chance(&self, initiator: usize, target: usize, context: Context) -> f32 {
        let config = self.agents[target].archetype.config();
        let mean = self.relation(target, initiator).mean();
        let relation_factor = 2.0 / (1.0 + (mean / self.config.refusal_relation_scale).exp());
        let context_factor = 1.0
            / config
                .context_multiplier(context)
                .max(self.config.refusal_context_floor);

        (config.refusal_chance * relation_factor * context_factor)
            .clamp(self.config.refusal_min, self.config.refusal_max)
    }

    /// Softmax target choice over an explicit candidate list.
    ///
    /// `candidates` must not contain `actor`.  The world layer will pass the
    /// neighbours of the current room/section; the generic prototype passes all
    /// other agents.  Sorting is not needed here because the candidate order is
    /// supplied by the caller and is part of the deterministic contract.
    pub fn choose_target(
        &mut self,
        actor: usize,
        candidates: &[usize],
        context: Context,
    ) -> Option<usize> {
        if candidates.is_empty() {
            return None;
        }
        if candidates.len() == 1 {
            return Some(candidates[0]);
        }

        let temperature = self.agents[actor].archetype.config().temperature.max(0.01);

        let mut scores = Vec::with_capacity(candidates.len());
        let mut max_score = f32::NEG_INFINITY;
        for &candidate in candidates {
            let score = self.priority_score(actor, candidate, context);
            max_score = max_score.max(score);
            scores.push(score);
        }

        let mut weights = Vec::with_capacity(scores.len());
        let mut sum = 0.0f32;
        for score in scores {
            let weight = ((score - max_score) / temperature).exp();
            weights.push(weight);
            sum += weight;
        }

        if !sum.is_finite() || sum <= 0.0 {
            return Some(candidates[0]);
        }

        let mut threshold = self.rng.next_f32() * sum;
        for (index, weight) in weights.into_iter().enumerate() {
            threshold -= weight;
            if threshold <= 0.0 {
                return Some(candidates[index]);
            }
        }

        candidates.last().copied()
    }

    pub fn choose_target_all(&mut self, actor: usize, context: Context) -> Option<usize> {
        let mut scores = Vec::new();
        self.choose_target_all_with_buffer(actor, context, &mut scores)
    }

    /// Allocation-free variant used by the day loop.  The caller owns the
    /// scratch buffer, so a 1620-agent day performs one allocation instead of
    /// one `Vec` per actor.
    ///
    /// The two-pass softmax (max, then cumulative sum) consumes exactly one
    /// RNG value, which keeps the stream identical to `choose_target` for the
    /// same candidate order.
    fn choose_target_all_with_buffer(
        &mut self,
        actor: usize,
        context: Context,
        scores: &mut Vec<f32>,
    ) -> Option<usize> {
        let n = self.agents.len();
        if n <= 1 {
            return None;
        }

        let temperature = self.agents[actor].archetype.config().temperature.max(0.01);

        scores.clear();
        scores.reserve(n.saturating_sub(1));

        let mut max_score = f32::NEG_INFINITY;
        for candidate in 0..n {
            if candidate == actor {
                continue;
            }
            let score = self.priority_score(actor, candidate, context);
            max_score = max_score.max(score);
            scores.push(score);
        }

        let mut sum = 0.0f32;
        for &score in scores.iter() {
            sum += ((score - max_score) / temperature).exp();
        }

        if !sum.is_finite() || sum <= 0.0 {
            return Some(if actor == 0 { 1 } else { 0 });
        }

        let mut threshold = self.rng.next_f32() * sum;
        for (offset, &score) in scores.iter().enumerate() {
            let weight = ((score - max_score) / temperature).exp();
            threshold -= weight;
            if threshold <= 0.0 {
                let mut candidate = offset;
                if candidate >= actor {
                    candidate += 1;
                }
                return Some(candidate);
            }
        }

        Some(if actor == n - 1 { n - 2 } else { n - 1 })
    }

    /// One contact between two specific agents.
    pub fn interact_pair(&mut self, initiator: usize, target: usize, context: Context) -> Outcome {
        let refusal_chance = self.refusal_chance(initiator, target, context);
        if self.rng.next_f32() < refusal_chance {
            self.process_interaction_result(initiator, target, Outcome::Refusal, context);
            return Outcome::Refusal;
        }

        let outcome = if self.rng.next_f32() < self.config.success_probability {
            Outcome::Success
        } else {
            Outcome::Failure
        };
        self.process_interaction_result(initiator, target, outcome, context);
        outcome
    }

    /// Applies one outcome to both participants and to both ordered relations.
    ///
    /// The emotional snapshot is taken before any update, so the two sides use
    /// the same `E(t)` and the partner-emotion multiplier is not affected by
    /// the actor's own reaction.
    pub fn process_interaction_result(
        &mut self,
        initiator: usize,
        target: usize,
        outcome: Outcome,
        context: Context,
    ) {
        let initiator_emotions = self.agents[initiator].emotions;
        let target_emotions = self.agents[target].emotions;
        let initiator_primary = initiator_emotions.primary_value();
        let target_primary = target_emotions.primary_value();

        if outcome.is_refusal() {
            self.process_refusal(initiator, target, context);
            self.apply_emotional_reaction(
                initiator,
                target,
                outcome,
                context,
                initiator_emotions,
                target_emotions,
            );
            self.apply_emotional_reaction(
                target,
                initiator,
                outcome,
                context,
                target_emotions,
                initiator_emotions,
            );
            return;
        }

        self.apply_emotional_reaction(
            initiator,
            target,
            outcome,
            context,
            initiator_emotions,
            target_emotions,
        );
        self.apply_emotional_reaction(
            target,
            initiator,
            outcome,
            context,
            target_emotions,
            initiator_emotions,
        );

        self.apply_relation_update(initiator, target, outcome, context, target_primary);
        self.apply_relation_update(target, initiator, outcome, context, initiator_primary);
    }

    fn process_refusal(&mut self, initiator: usize, target: usize, context: Context) {
        let n = self.agents.len();
        for (actor, other) in [(initiator, target), (target, initiator)] {
            let config = *self.agents[actor].archetype.config();
            let sensitivity = self.agents[actor].sensitivity;
            let context_mod = config.context_multiplier(context);
            let penalty = self.config.refusal_penalty * sensitivity * context_mod;
            let row = &mut self.relations[actor * n..(actor + 1) * n];

            for axis in RelationAxis::ALL {
                let impact = if axis == config.refusal_vulnerability {
                    1.0
                } else {
                    0.5
                };
                row[other].adjust_f32(axis, -penalty * impact);
            }
        }
    }

    fn apply_emotional_reaction(
        &mut self,
        actor: usize,
        _partner: usize,
        outcome: Outcome,
        context: Context,
        own_emotions: EmotionVector,
        partner_emotions: EmotionVector,
    ) {
        let config = *self.agents[actor].archetype.config();
        let sensitivity = self.agents[actor].sensitivity;
        let context_mod = config.context_multiplier(context);
        let strength = if outcome.is_refusal() { -1.0 } else { 1.0 };
        let rate = self.config.emotional_reaction_rate;

        let mut next = own_emotions;
        for axis in EmotionAxis::ALL {
            let own = own_emotions.get(axis).get();
            let partner_value = partner_emotions.get(axis).get();
            let factor = sigma_rate_factor(own, outcome);
            let delta = strength
                * sensitivity
                * context_mod
                * rate
                * f32::from(partner_value - own)
                * factor;
            let weight = f32::from(config.weights[axis.index()]) / 10.0;
            next.set_emotion(axis, own_emotions.get(axis).adjust_f32(delta * weight));
        }

        self.agents[actor].emotions = next;
    }

    fn apply_relation_update(
        &mut self,
        actor: usize,
        partner: usize,
        outcome: Outcome,
        context: Context,
        partner_primary: i16,
    ) {
        let config = *self.agents[actor].archetype.config();
        let sensitivity = self.agents[actor].sensitivity;
        let context_mod = config.context_multiplier(context);
        let multiplier = if partner_primary >= 0 {
            self.config.partner_positive_multiplier
        } else {
            self.config.partner_negative_multiplier
        };

        let base_affinity = self.config.base_affinity_delta * multiplier;
        let base_trust = self.config.base_trust_delta * multiplier;
        let n = self.agents.len();
        let row = &mut self.relations[actor * n..(actor + 1) * n];
        let relation = &mut row[partner];

        for axis in RelationAxis::ALL {
            let base = if axis == RelationAxis::Trust {
                base_trust
            } else {
                base_affinity
            };
            let factor = sigma_rate_factor(relation.get(axis), outcome);
            relation.adjust_f32(axis, base * sensitivity * context_mod * factor);
        }
    }

    /// End-of-day maintenance in the exact v2 order.
    ///
    /// The university world has nine schedule slots and performs the phase
    /// sequence once, after the last slot; the generic world calls the same
    /// method from `step`.
    pub fn daily_maintenance(&mut self) {
        self.apply_relation_decay();
        self.react_to_relations();
        self.apply_emotion_decay();
        self.react_to_emotions();
        self.influence_emotions();
    }

    /// A Sunday in the university world: one random shift shared by all seven
    /// axes of an agent, followed by the ordinary emotional decay.
    ///
    /// v2 draws one `randint(-30, 30)` per agent and adds it to every axis.
    /// The shift is clamped to the legal emotional range by
    /// `EmotionVector::set`.
    pub fn sunday_shift(&mut self, min: i16, max: i16) {
        for agent in &mut self.agents {
            let delta = self.rng.next_i16_inclusive(min, max);
            for axis in EmotionAxis::ALL {
                let value = i32::from(agent.emotions.get(axis).get()) + i32::from(delta);
                agent.emotions.set(
                    axis,
                    value.clamp(
                        i32::from(crate::emotion::EMOTION_MIN),
                        i32::from(crate::emotion::EMOTION_MAX),
                    ) as i16,
                );
            }
        }
        self.apply_emotion_decay();
    }

    /// One simulated day: daily decay/reactions, emotional influence, then one
    /// sequential interaction round.
    ///
    /// The university world will replace the all-agent candidate list with the
    /// neighbours of the current room/section, but the phase order stays the
    /// same.
    pub fn step(&mut self, context: Context) -> DayReport {
        self.daily_maintenance();

        let mut interactions = Vec::new();
        let mut scores = Vec::with_capacity(self.agents.len().saturating_sub(1));
        for _ in 0..self.config.interaction_rounds {
            for actor in 0..self.agents.len() {
                if let Some(target) =
                    self.choose_target_all_with_buffer(actor, context, &mut scores)
                {
                    let outcome = self.interact_pair(actor, target, context);
                    interactions.push(Interaction::new(
                        AgentId::new(actor as u32),
                        AgentId::new(target as u32),
                        outcome,
                    ));
                }
            }
        }

        self.day += 1;
        DayReport {
            day: self.day,
            interactions,
        }
    }

    pub fn run(&mut self, days: u32, context: Context) -> RunReport {
        let mut report = RunReport::default();
        for _ in 0..days {
            let day = self.step(context);
            report.days += 1;
            report.total_interactions += day.interactions.len();
            for interaction in day.interactions {
                match interaction.outcome {
                    Outcome::Success => report.successes += 1,
                    Outcome::Failure => report.failures += 1,
                    Outcome::Refusal => report.refusals += 1,
                }
            }
        }
        report.final_hash = self.state_hash();
        report.final_rng_state = self.rng.state();
        report
    }

    fn apply_relation_decay(&mut self) {
        let n = self.agents.len();
        let parallelism = self.config.parallelism;
        let positive_scale = self.config.positive_relation_decay_scale;
        let (agents, relations) = (&mut self.agents, &mut self.relations);

        for_each_agent_row_mut(agents, relations, n, parallelism, |index, agent, row| {
            let step = agent.archetype.config().decay_rate * agent.sensitivity;
            for (target, relation) in row.iter_mut().enumerate() {
                if target == index {
                    continue;
                }
                for axis in RelationAxis::ALL {
                    let value = i32::from(relation.get(axis));
                    if value > 0 {
                        let next = ((value as f32 - step * positive_scale).trunc() as i32).max(0);
                        relation.set(axis, next as i16);
                    } else if value < 0 {
                        let next = ((value as f32 + step).trunc() as i32).min(0);
                        relation.set(axis, next as i16);
                    }
                }
            }
        });
    }

    fn react_to_relations(&mut self) {
        let n = self.agents.len();
        let parallelism = self.config.parallelism;
        let rate = self.config.relation_to_emotion_rate;
        let (agents, relations) = (&mut self.agents, &self.relations);

        for_each_agent_indexed_mut(agents, parallelism, |index, agent| {
            let row = &relations[index * n..(index + 1) * n];
            let mut sum_utility = 0i64;
            let mut sum_affinity = 0i64;
            let mut sum_trust = 0i64;
            let mut count = 0i64;

            for (target, relation) in row.iter().enumerate() {
                if target == index || relation.is_zero() {
                    continue;
                }
                sum_utility += i64::from(relation.get(RelationAxis::Utility));
                sum_affinity += i64::from(relation.get(RelationAxis::Affinity));
                sum_trust += i64::from(relation.get(RelationAxis::Trust));
                count += 1;
            }

            if count == 0 {
                return;
            }

            let avg_utility = sum_utility as f32 / count as f32;
            let avg_affinity = sum_affinity as f32 / count as f32;
            let avg_trust = sum_trust as f32 / count as f32;
            let effect = (avg_affinity + avg_trust + avg_utility) / 3.0;
            let config = agent.archetype.config();
            let sensitivity = agent.sensitivity;

            for axis in EmotionAxis::ALL {
                let coeff = f32::from(config.weights[axis.index()]);
                let delta = effect * coeff * rate * sensitivity;
                agent
                    .emotions
                    .set_emotion(axis, agent.emotions.get(axis).adjust_f32(delta));
            }
        });
    }

    fn apply_emotion_decay(&mut self) {
        let parallelism = self.config.parallelism;
        for_each_agent_indexed_mut(&mut self.agents, parallelism, |_index, agent| {
            let step = agent.archetype.config().emotion_decay * agent.sensitivity;
            for axis in EmotionAxis::ALL {
                let value = i32::from(agent.emotions.get(axis).get());
                if value > 0 {
                    let next = ((value as f32 - step).trunc() as i32).max(0);
                    agent.emotions.set(axis, next as i16);
                } else if value < 0 {
                    let next = ((value as f32 + step).trunc() as i32).min(0);
                    agent.emotions.set(axis, next as i16);
                }
            }
        });
    }

    fn react_to_emotions(&mut self) {
        let n = self.agents.len();
        let parallelism = self.config.parallelism;
        let rate = self.config.emotion_to_relation_rate;
        let (agents, relations) = (&mut self.agents, &mut self.relations);

        for_each_agent_row_mut(agents, relations, n, parallelism, |index, agent, row| {
            let sensitivity = agent.sensitivity;

            for axis in EmotionAxis::ALL {
                let value = i32::from(agent.emotions.get(axis).get());
                if value.abs() < 1 {
                    continue;
                }
                let delta = value as f32 * rate * sensitivity;

                for (target, relation) in row.iter_mut().enumerate() {
                    if target == index || relation.is_zero() {
                        continue;
                    }
                    match axis {
                        EmotionAxis::SadnessJoy => {
                            relation.adjust_f32(RelationAxis::Affinity, delta);
                        }
                        EmotionAxis::FearCalm => {
                            relation.adjust_f32(RelationAxis::Trust, delta);
                        }
                        EmotionAxis::AngerHumility => {
                            let factor = if value < 0 { 2.0 } else { 1.0 };
                            relation.adjust_f32(RelationAxis::Trust, delta * factor);
                        }
                        EmotionAxis::DisgustAcceptance => {
                            relation.adjust_f32(RelationAxis::Affinity, delta);
                            relation.adjust_f32(RelationAxis::Utility, delta);
                        }
                        EmotionAxis::HabitSurprise => {
                            relation.adjust_f32(RelationAxis::Utility, delta);
                        }
                        EmotionAxis::ShameConfidence => {
                            relation.adjust_f32(RelationAxis::Trust, delta);
                        }
                        EmotionAxis::AlienationOpenness => {
                            relation.adjust_f32(RelationAxis::Trust, delta);
                            relation.adjust_f32(RelationAxis::Affinity, delta);
                        }
                    }
                }
            }
        });
    }

    fn influence_emotions(&mut self) {
        let n = self.agents.len();
        if n < 2 {
            return;
        }

        let meta: Vec<InfluenceMeta> = self
            .agents
            .iter()
            .map(|agent| {
                let mut max_abs = 0i16;
                let mut max_value = 0i16;
                let mut primary_axis = EmotionAxis::SadnessJoy;
                let mut total_intensity = 0i32;

                for axis in EmotionAxis::ALL {
                    let value = agent.emotions.get(axis).get();
                    let abs = value.abs();
                    total_intensity += i32::from(abs);
                    if abs > max_abs {
                        max_abs = abs;
                        max_value = value;
                        primary_axis = axis;
                    }
                }

                if max_value == 0 || total_intensity == 0 {
                    InfluenceMeta {
                        active: false,
                        primary_axis,
                        weight_primary: 0.0,
                        weight_secondary: 0.0,
                        emotions: agent.emotions,
                    }
                } else {
                    let weight_primary = f32::from(max_abs) / total_intensity as f32;
                    let weight_secondary = (1.0 - weight_primary) / (NUM_AXES as f32 - 1.0);
                    InfluenceMeta {
                        active: true,
                        primary_axis,
                        weight_primary,
                        weight_secondary,
                        emotions: agent.emotions,
                    }
                }
            })
            .collect();

        let parallelism = self.config.parallelism;
        let top_k = self.config.influence_top_k.max(1);
        let rate = self.config.influence_rate;
        let max_step = self.config.influence_max_step;

        // This phase only reads the relation matrix: it writes emotions and
        // nothing else.  Splitting the borrows avoids cloning the 2.6M-entry
        // matrix on every simulated day.
        let (agents, relations) = (&mut self.agents, &self.relations);

        for_each_agent_indexed_mut(agents, parallelism, |recipient, agent| {
            let mut candidates: Vec<(f32, usize)> = Vec::with_capacity(n.saturating_sub(1));
            for influencer in 0..n {
                if influencer == recipient {
                    continue;
                }
                let relation = relations[influencer * n + recipient];
                if relation.is_zero() {
                    continue;
                }
                candidates.push((relation.influence_weight_mean(), influencer));
            }

            if candidates.is_empty() {
                return;
            }

            let compare = |left: &(f32, usize), right: &(f32, usize)| {
                let left_abs = left.0.abs();
                let right_abs = right.0.abs();
                right_abs
                    .partial_cmp(&left_abs)
                    .unwrap_or(Ordering::Equal)
                    .then_with(|| left.1.cmp(&right.1))
            };

            let keep = top_k.min(candidates.len());
            if keep < candidates.len() {
                candidates.select_nth_unstable_by(keep - 1, compare);
                candidates.truncate(keep);
            }
            candidates.sort_by(compare);

            let mut weighted_value = [0.0f32; NUM_AXES];
            let mut weight_sum = [0.0f32; NUM_AXES];

            for &(effect, influencer) in &candidates {
                let source = &meta[influencer];
                if !source.active {
                    continue;
                }
                let relation_weight = (effect.abs() + 20.0) / 100.0;

                for axis in EmotionAxis::ALL {
                    let axis_weight = if axis == source.primary_axis {
                        source.weight_primary
                    } else {
                        source.weight_secondary
                    };
                    let contribution = relation_weight * axis_weight;
                    weighted_value[axis.index()] +=
                        contribution * f32::from(source.emotions.get(axis).get());
                    weight_sum[axis.index()] += contribution;
                }
            }

            let step = (rate * agent.sensitivity).min(max_step);
            let mut next = agent.emotions;

            for axis in EmotionAxis::ALL {
                let denominator = weight_sum[axis.index()];
                if denominator <= 0.0 {
                    continue;
                }
                let current = agent.emotions.get(axis).get();
                let target = weighted_value[axis.index()] / denominator;
                let delta = step * (target - f32::from(current));
                let next_value = (f32::from(current) + delta).round() as i16;
                next.set(axis, next_value);
            }

            agent.emotions = next;
        });
    }

    /// Deterministic fingerprint of the full mutable state and the RNG.
    ///
    /// Used by the `1/2/8` threads test and by the future runner to compare a
    /// Rust trajectory with the Python reference.
    pub fn state_hash(&self) -> u64 {
        let mut hash = 0xcbf2_9ce4_8422_2325u64;
        hash_u64(&mut hash, u64::from(self.day));

        for agent in &self.agents {
            for axis in EmotionAxis::ALL {
                hash_i16(&mut hash, agent.emotions.get(axis).get());
            }
            hash_u32(&mut hash, agent.sensitivity.to_bits());
            hash_u32(&mut hash, agent.group_id);
            hash_u64(&mut hash, u64::from(agent.course_year));
        }

        for relation in &self.relations {
            for axis in RelationAxis::ALL {
                hash_i16(&mut hash, relation.get(axis));
            }
        }

        hash_u64(&mut hash, self.rng.state());
        hash
    }
}

fn hash_i16(hash: &mut u64, value: i16) {
    hash_bytes(hash, &value.to_le_bytes());
}

fn hash_u32(hash: &mut u64, value: u32) {
    hash_bytes(hash, &value.to_le_bytes());
}

fn hash_u64(hash: &mut u64, value: u64) {
    hash_bytes(hash, &value.to_le_bytes());
}

fn hash_bytes(hash: &mut u64, bytes: &[u8]) {
    for &byte in bytes {
        *hash ^= u64::from(byte);
        *hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Degree;
    use crate::archetype::ArchetypeKind;

    fn specs(count: usize, archetype: Option<ArchetypeKind>) -> Vec<AgentSpec> {
        (0..count)
            .map(|index| {
                AgentSpec::new(
                    format!("A-{index:04}"),
                    archetype.unwrap_or(ArchetypeKind::ALL[index % ArchetypeKind::ALL.len()]),
                    0.5 + (index % 5) as f32 * 0.5,
                    (index / 10) as u32,
                    ((index % 4) + 1) as u8,
                    Degree::Bachelor,
                )
            })
            .collect()
    }

    fn run_with_threads(threads: usize) -> u64 {
        let config = WorldConfig {
            seed: 12345,
            parallelism: threads,
            ..WorldConfig::default()
        };
        let mut world = World::from_specs(specs(40, None), config);
        world.run(20, Context::Study).final_hash
    }

    #[test]
    fn same_seed_and_threads_give_the_same_state() {
        assert_eq!(run_with_threads(1), run_with_threads(1));
    }

    #[test]
    fn thread_count_does_not_change_the_trajectory() {
        let single = run_with_threads(1);
        let dual = run_with_threads(2);
        let many = run_with_threads(8);
        assert_eq!(single, dual);
        assert_eq!(single, many);
    }

    #[test]
    fn state_stays_inside_the_declared_ranges() {
        let mut world = World::from_specs(specs(50, None), WorldConfig::default());
        world.run(40, Context::Study);

        for agent in &world.agents {
            for axis in EmotionAxis::ALL {
                let value = agent.emotions.get(axis).get();
                assert!(
                    (crate::emotion::EMOTION_MIN..=crate::emotion::EMOTION_MAX).contains(&value)
                );
            }
        }
        for relation in &world.relations {
            for axis in RelationAxis::ALL {
                let value = relation.get(axis);
                assert!(
                    (crate::relation::RELATION_MIN..=crate::relation::RELATION_MAX)
                        .contains(&value)
                );
            }
        }
    }

    #[test]
    fn allocation_free_target_choice_matches_the_explicit_list() {
        let config = WorldConfig {
            seed: 99,
            init_mode: InitMode::Random,
            ..WorldConfig::default()
        };
        let mut fast = World::from_specs(specs(50, None), config.clone());
        let mut explicit = World::from_specs(specs(50, None), config);

        for actor in 0..fast.len() {
            let candidates: Vec<usize> = (0..fast.len())
                .filter(|&candidate| candidate != actor)
                .collect();
            let expected = explicit.choose_target(actor, &candidates, Context::Study);
            let actual = fast.choose_target_all(actor, Context::Study);
            assert_eq!(actual, expected, "actor={actor}");
        }

        assert_eq!(fast.rng.state(), explicit.rng.state());
    }

    #[test]
    fn refusal_is_target_based() {
        let specs = vec![
            AgentSpec::new("A-1", ArchetypeKind::Harmony, 1.0, 0, 1, Degree::Bachelor),
            AgentSpec::new("A-2", ArchetypeKind::Nihility, 1.0, 0, 1, Degree::Bachelor),
            AgentSpec::new("A-3", ArchetypeKind::Harmony, 1.0, 0, 1, Degree::Bachelor),
        ];
        let world = World::from_specs(specs, WorldConfig::default());
        let from_harmony_to_nihility = world.refusal_chance(0, 1, Context::Study);
        let from_harmony_to_harmony = world.refusal_chance(0, 2, Context::Study);
        assert!(from_harmony_to_nihility > from_harmony_to_harmony);
    }

    #[test]
    fn absent_relation_has_the_neutral_priority_of_python_v2() {
        let specs = vec![
            AgentSpec::new("A-1", ArchetypeKind::Harmony, 1.0, 0, 1, Degree::Bachelor),
            AgentSpec::new("A-2", ArchetypeKind::Harmony, 1.0, 0, 1, Degree::Bachelor),
        ];
        let world = World::from_specs(specs, WorldConfig::default());
        assert_eq!(world.priority_score(0, 1, Context::Study), 0.5);
    }

    #[test]
    fn sunday_shift_is_deterministic_and_leaves_relations_alone() {
        let config = WorldConfig {
            seed: 2024,
            ..WorldConfig::default()
        };
        let mut left = World::from_specs(specs(30, None), config.clone());
        let mut right = World::from_specs(specs(30, None), config);
        let relations_before = left.relations.clone();

        left.sunday_shift(-30, 30);
        right.sunday_shift(-30, 30);

        assert_eq!(left.state_hash(), right.state_hash());
        assert_eq!(left.relations, relations_before);
        assert!(left.agents.iter().any(|agent| {
            EmotionAxis::ALL
                .iter()
                .any(|&axis| agent.emotions.get(axis).get() != 0)
        }));
    }

    #[test]
    fn random_initialization_is_group_local() {
        let mut all_specs = specs(20, None);
        for (index, spec) in all_specs.iter_mut().enumerate() {
            spec.group_id = (index / 10) as u32;
        }
        let config = WorldConfig {
            seed: 7,
            init_mode: InitMode::Random,
            ..WorldConfig::default()
        };
        let world = World::from_specs(all_specs, config);

        let mut within = 0;
        let mut across = 0;
        for i in 0..world.len() {
            for j in 0..world.len() {
                if i == j {
                    continue;
                }
                if world.agents[i].group_id == world.agents[j].group_id {
                    within += usize::from(!world.relation(i, j).is_zero());
                } else {
                    across += usize::from(!world.relation(i, j).is_zero());
                }
            }
        }
        assert!(within > 0);
        assert_eq!(across, 0);
    }
}
