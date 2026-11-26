use crate::archetype::ArchetypeKind;
use crate::emotion::{EMOTION_MAX, EMOTION_MIN, EmotionVector};
use crate::ids::AgentId;
use crate::rng::DeterministicRng;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Degree {
    Bachelor,
    Master,
}

/// Input description of one person.  It contains no engine index: the index is
/// assigned by `World::from_specs`, while `string_id` remains the stable human
/// identifier used by logs and by academic rotation.
#[derive(Clone, Debug)]
pub struct AgentSpec {
    pub string_id: String,
    pub name: String,
    pub archetype: ArchetypeKind,
    pub sensitivity: f32,
    pub emotions: Option<EmotionVector>,
    pub group_id: u32,
    pub course_year: u8,
    pub degree: Degree,
}

impl AgentSpec {
    pub fn new(
        string_id: impl Into<String>,
        archetype: ArchetypeKind,
        sensitivity: f32,
        group_id: u32,
        course_year: u8,
        degree: Degree,
    ) -> Self {
        let string_id = string_id.into();
        Self {
            name: string_id.clone(),
            string_id,
            archetype,
            sensitivity,
            emotions: None,
            group_id,
            course_year,
            degree,
        }
    }
}

/// Runtime agent.  Stable behavioural parameters are immutable after
/// construction, which makes the parallel phases easier to reason about and
/// prevents accidental "temporary" changes from leaking across days.
#[derive(Clone, Debug)]
pub struct Agent {
    pub id: AgentId,
    pub string_id: String,
    pub name: String,
    pub archetype: ArchetypeKind,
    pub sensitivity: f32,
    pub emotions: EmotionVector,
    pub group_id: u32,
    pub course_year: u8,
    pub degree: Degree,
}

impl Agent {
    pub fn from_spec(spec: AgentSpec, id: AgentId, rng: &mut DeterministicRng) -> Self {
        let sensitivity = sanitize_sensitivity(spec.sensitivity);
        let emotions = spec
            .emotions
            .unwrap_or_else(|| EmotionVector::random(rng, EMOTION_MIN, EMOTION_MAX));

        Self {
            id,
            string_id: spec.string_id,
            name: spec.name,
            archetype: spec.archetype,
            sensitivity,
            emotions,
            group_id: spec.group_id,
            course_year: spec.course_year,
            degree: spec.degree,
        }
    }

    pub fn primary_emotion(&self) -> Option<(crate::emotion::EmotionAxis, i16)> {
        self.emotions
            .primary()
            .map(|(axis, value)| (axis, value.get()))
    }
}

fn sanitize_sensitivity(value: f32) -> f32 {
    if !value.is_finite() || value <= 0.0 {
        1.0
    } else {
        value.clamp(0.1, 3.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sensitivity_is_clamped_to_the_model_range() {
        assert_eq!(sanitize_sensitivity(0.0), 1.0);
        assert_eq!(sanitize_sensitivity(10.0), 3.0);
        assert_eq!(sanitize_sensitivity(0.5), 0.5);
    }

    #[test]
    fn missing_emotions_are_initialized_deterministically() {
        let spec = AgentSpec::new("A-1", ArchetypeKind::Harmony, 1.0, 0, 1, Degree::Bachelor);
        let mut left_rng = DeterministicRng::new(42);
        let mut right_rng = DeterministicRng::new(42);
        let left = Agent::from_spec(spec.clone(), AgentId::new(0), &mut left_rng);
        let right = Agent::from_spec(spec, AgentId::new(0), &mut right_rng);
        assert_eq!(left.emotions, right.emotions);
    }
}
