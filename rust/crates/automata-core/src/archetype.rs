use crate::emotion::NUM_AXES;
use crate::relation::RelationAxis;

/// Non-linear transformation of one relational function in the priority score.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Scoring {
    Linear,
    Log,
    Exp,
    Sigmoid,
    Periodic,
}

impl Scoring {
    /// Applies the transformation to a value already converted to the external
    /// (non-x10) scale.  This matches v2 `_apply_transformation`.
    pub fn apply(self, value: f32) -> f32 {
        match self {
            Self::Linear => value,
            Self::Log => value.abs().ln_1p() * if value >= 0.0 { 1.0 } else { -1.0 },
            Self::Exp => (value / 5.0).exp(),
            Self::Sigmoid => 10.0 / (1.0 + (-value).exp()),
            Self::Periodic => value.sin() * 5.0,
        }
    }
}

/// Location context.  v3 makes it an explicit property of the world step
/// instead of an optional string passed through the Python call stack.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
#[repr(usize)]
pub enum Context {
    Study = 0,
    Break = 1,
    Gym = 2,
}

impl Context {
    pub const ALL: [Self; 3] = [Self::Study, Self::Break, Self::Gym];

    pub const fn index(self) -> usize {
        self as usize
    }

    pub const fn key(self) -> &'static str {
        match self {
            Self::Study => "STUDY",
            Self::Break => "BREAK",
            Self::Gym => "GYM",
        }
    }
}

const NEUTRAL_CONTEXT: [f32; 3] = [1.0, 1.0, 1.0];

/// Immutable archetype configuration.  The table is a direct transcription of
/// `model/archetypes.py` after the x10 migration.
#[derive(Clone, Copy, Debug)]
pub struct ArchetypeConfig {
    pub weights: [u8; NUM_AXES],
    pub refusal_chance: f32,
    pub decay_rate: f32,
    pub temperature: f32,
    pub emotion_decay: f32,
    pub refusal_vulnerability: RelationAxis,
    /// Indexed by `RelationAxis`: utility, affinity, trust.
    pub scoring: [Scoring; 3],
    /// Indexed by `Context`: study, break, gym.
    pub context_adaptability: [f32; 3],
}

impl ArchetypeConfig {
    pub fn context_multiplier(self, context: Context) -> f32 {
        self.context_adaptability[context.index()]
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ArchetypeKind {
    Erudition,
    Enigmata,
    Harmony,
    Hunt,
    Elation,
    Preservation,
    Nihility,
    Trailblaze,
    Remembrance,
}

impl ArchetypeKind {
    pub const ALL: [Self; 9] = [
        Self::Erudition,
        Self::Enigmata,
        Self::Harmony,
        Self::Hunt,
        Self::Elation,
        Self::Preservation,
        Self::Nihility,
        Self::Trailblaze,
        Self::Remembrance,
    ];

    pub const fn name(self) -> &'static str {
        match self {
            Self::Erudition => "Erudition",
            Self::Enigmata => "Enigmata",
            Self::Harmony => "Harmony",
            Self::Hunt => "Hunt",
            Self::Elation => "Elation",
            Self::Preservation => "Preservation",
            Self::Nihility => "Nihility",
            Self::Trailblaze => "Trailblaze",
            Self::Remembrance => "Remembrance",
        }
    }

    pub const fn localized(self) -> &'static str {
        match self {
            Self::Erudition => "Аналитик",
            Self::Enigmata => "Нонконформист",
            Self::Harmony => "Медиатор",
            Self::Hunt => "Конкурент",
            Self::Elation => "Оппортунист",
            Self::Preservation => "Протектор",
            Self::Nihility => "Деструктор",
            Self::Trailblaze => "Инноватор",
            Self::Remembrance => "Рефлектор",
        }
    }

    pub fn from_name(name: &str) -> Option<Self> {
        let needle = name.trim().to_lowercase();
        Self::ALL.into_iter().find(|kind| {
            kind.name().to_lowercase() == needle || kind.localized().to_lowercase() == needle
        })
    }

    pub fn config(self) -> &'static ArchetypeConfig {
        match self {
            Self::Erudition => &ERUDITION,
            Self::Enigmata => &ENIGMATA,
            Self::Harmony => &HARMONY,
            Self::Hunt => &HUNT,
            Self::Elation => &ELATION,
            Self::Preservation => &PRESERVATION,
            Self::Nihility => &NIHILITY,
            Self::Trailblaze => &TRAILBLAZE,
            Self::Remembrance => &REMEMBRANCE,
        }
    }
}

pub const ERUDITION: ArchetypeConfig = ArchetypeConfig {
    weights: [8, 12, 5, 10, 15, 7, 9],
    refusal_chance: 0.2,
    decay_rate: 8.0,
    temperature: 0.1,
    emotion_decay: 2.0,
    refusal_vulnerability: RelationAxis::Utility,
    scoring: [Scoring::Log, Scoring::Linear, Scoring::Linear],
    context_adaptability: [2.0, 0.5, 0.5],
};

pub const ENIGMATA: ArchetypeConfig = ArchetypeConfig {
    weights: [10, 8, 12, 15, 18, 6, 10],
    refusal_chance: 0.4,
    decay_rate: 20.0,
    temperature: 1.5,
    emotion_decay: 2.0,
    refusal_vulnerability: RelationAxis::Utility,
    scoring: [Scoring::Linear, Scoring::Linear, Scoring::Periodic],
    context_adaptability: NEUTRAL_CONTEXT,
};

pub const HARMONY: ArchetypeConfig = ArchetypeConfig {
    weights: [15, 10, 2, 10, 7, 12, 20],
    refusal_chance: 0.05,
    decay_rate: 4.0,
    temperature: 0.3,
    emotion_decay: 2.0,
    refusal_vulnerability: RelationAxis::Affinity,
    scoring: [Scoring::Linear, Scoring::Sigmoid, Scoring::Exp],
    context_adaptability: [1.0, 2.0, 1.0],
};

pub const HUNT: ArchetypeConfig = ArchetypeConfig {
    weights: [8, 3, 20, 6, 9, 15, 7],
    refusal_chance: 0.2,
    decay_rate: 12.0,
    temperature: 0.1,
    emotion_decay: 2.0,
    refusal_vulnerability: RelationAxis::Trust,
    scoring: [Scoring::Linear, Scoring::Linear, Scoring::Sigmoid],
    context_adaptability: [0.5, 1.0, 3.0],
};

pub const ELATION: ArchetypeConfig = ArchetypeConfig {
    weights: [20, 8, 9, 11, 20, 5, 12],
    refusal_chance: 0.5,
    decay_rate: 25.0,
    temperature: 3.0,
    emotion_decay: 2.0,
    refusal_vulnerability: RelationAxis::Affinity,
    scoring: [Scoring::Linear, Scoring::Periodic, Scoring::Linear],
    context_adaptability: NEUTRAL_CONTEXT,
};

pub const PRESERVATION: ArchetypeConfig = ArchetypeConfig {
    weights: [7, 15, 5, 12, 6, 18, 14],
    refusal_chance: 0.1,
    decay_rate: 2.0,
    temperature: 0.2,
    emotion_decay: 2.0,
    refusal_vulnerability: RelationAxis::Trust,
    scoring: [Scoring::Linear, Scoring::Linear, Scoring::Sigmoid],
    context_adaptability: NEUTRAL_CONTEXT,
};

pub const NIHILITY: ArchetypeConfig = ArchetypeConfig {
    weights: [3, 5, 8, 18, 5, 4, 5],
    refusal_chance: 0.8,
    decay_rate: 10.0,
    temperature: 1.0,
    emotion_decay: 2.0,
    refusal_vulnerability: RelationAxis::Utility,
    scoring: [Scoring::Linear, Scoring::Log, Scoring::Periodic],
    context_adaptability: NEUTRAL_CONTEXT,
};

pub const TRAILBLAZE: ArchetypeConfig = ArchetypeConfig {
    weights: [12, 8, 10, 10, 15, 13, 12],
    refusal_chance: 0.2,
    decay_rate: 8.0,
    temperature: 1.2,
    emotion_decay: 2.0,
    refusal_vulnerability: RelationAxis::Utility,
    scoring: [Scoring::Log, Scoring::Linear, Scoring::Linear],
    context_adaptability: NEUTRAL_CONTEXT,
};

pub const REMEMBRANCE: ArchetypeConfig = ArchetypeConfig {
    weights: [7, 13, 4, 12, 10, 20, 18],
    refusal_chance: 0.2,
    decay_rate: 1.0,
    temperature: 1.0,
    emotion_decay: 2.0,
    refusal_vulnerability: RelationAxis::Trust,
    scoring: [Scoring::Linear, Scoring::Exp, Scoring::Linear],
    context_adaptability: NEUTRAL_CONTEXT,
};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nine_archetypes_are_present() {
        assert_eq!(ArchetypeKind::ALL.len(), 9);
        for kind in ArchetypeKind::ALL {
            assert!(!kind.name().is_empty());
            assert!(!kind.localized().is_empty());
            assert_eq!(kind.config().weights.len(), NUM_AXES);
        }
    }

    #[test]
    fn transforms_match_v2() {
        assert_eq!(Scoring::Linear.apply(2.0), 2.0);
        assert!((Scoring::Log.apply(9.0) - 10.0f32.ln()).abs() < 1e-6);
        assert_eq!(Scoring::Periodic.apply(0.0), 0.0);
    }

    #[test]
    fn names_are_case_insensitive() {
        assert_eq!(
            ArchetypeKind::from_name("nihility"),
            Some(ArchetypeKind::Nihility)
        );
        assert_eq!(
            ArchetypeKind::from_name("Деструктор"),
            Some(ArchetypeKind::Nihility)
        );
    }
}
