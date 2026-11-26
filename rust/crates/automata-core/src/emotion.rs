use crate::rng::DeterministicRng;

pub const NUM_AXES: usize = 7;
pub const EMOTION_MIN: i16 = -30;
pub const EMOTION_MAX: i16 = 30;

/// Seven bipolar emotional axes.  The discriminant is also the storage index.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[repr(usize)]
pub enum EmotionAxis {
    SadnessJoy = 0,
    FearCalm = 1,
    AngerHumility = 2,
    DisgustAcceptance = 3,
    HabitSurprise = 4,
    ShameConfidence = 5,
    AlienationOpenness = 6,
}

impl EmotionAxis {
    pub const ALL: [Self; NUM_AXES] = [
        Self::SadnessJoy,
        Self::FearCalm,
        Self::AngerHumility,
        Self::DisgustAcceptance,
        Self::HabitSurprise,
        Self::ShameConfidence,
        Self::AlienationOpenness,
    ];

    pub const fn index(self) -> usize {
        self as usize
    }

    /// Stable machine-readable key used by CSV/JSON exporters.
    pub const fn key(self) -> &'static str {
        match self {
            Self::SadnessJoy => "sadness_joy",
            Self::FearCalm => "fear_calm",
            Self::AngerHumility => "anger_humility",
            Self::DisgustAcceptance => "disgust_acceptance",
            Self::HabitSurprise => "habit_surprise",
            Self::ShameConfidence => "shame_confidence",
            Self::AlienationOpenness => "alienation_openness",
        }
    }

    /// Human-readable label for the current sign, matching the v2 interface.
    pub const fn localized(self, value: i16) -> &'static str {
        match self {
            Self::SadnessJoy => {
                if value >= 0 {
                    "Радость"
                } else {
                    "Печаль"
                }
            }
            Self::FearCalm => {
                if value >= 0 {
                    "Спокойствие"
                } else {
                    "Страх"
                }
            }
            Self::AngerHumility => {
                if value >= 0 {
                    "Смирение"
                } else {
                    "Гнев"
                }
            }
            Self::DisgustAcceptance => {
                if value >= 0 {
                    "Принятие"
                } else {
                    "Отвращение"
                }
            }
            Self::HabitSurprise => {
                if value >= 0 {
                    "Удивление"
                } else {
                    "Привычка"
                }
            }
            Self::ShameConfidence => {
                if value >= 0 {
                    "Уверенность"
                } else {
                    "Стыд"
                }
            }
            Self::AlienationOpenness => {
                if value >= 0 {
                    "Открытость"
                } else {
                    "Отчуждение"
                }
            }
        }
    }
}

/// One emotion on the internal x10 scale, `[-30, 30]`.
///
/// The internal scale is an implementation detail.  Exporters divide by ten;
/// the thesis operates with the external `[-3, 3]` scale.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Emotion(i16);

impl Emotion {
    pub const ZERO: Self = Self(0);
    pub const MIN: Self = Self(EMOTION_MIN);
    pub const MAX: Self = Self(EMOTION_MAX);

    /// Constructs a value and clamps it to the legal range.
    pub fn new(value: i16) -> Self {
        Self(value.clamp(EMOTION_MIN, EMOTION_MAX))
    }

    pub const fn get(self) -> i16 {
        self.0
    }

    pub const fn is_zero(self) -> bool {
        self.0 == 0
    }

    /// Adds a floating-point delta using the model's truncation rule.
    ///
    /// v2 Python uses `int(value + delta)`, which truncates toward zero.  The
    /// same rule is kept here so that migration does not silently change the
    /// trajectory because of a different rounding convention.
    pub fn adjust_f32(self, delta: f32) -> Self {
        Self::new((self.0 as f32 + delta).trunc() as i16)
    }

    /// Adds an integer delta.
    pub fn adjust_i32(self, delta: i32) -> Self {
        Self::new((self.0 as i32 + delta).clamp(EMOTION_MIN as i32, EMOTION_MAX as i32) as i16)
    }
}

/// Fixed-size emotional vector.  Kept as a value type so that snapshots are
/// cheap and cannot be accidentally mutated by a parallel phase.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct EmotionVector([Emotion; NUM_AXES]);

impl EmotionVector {
    pub const ZERO: Self = Self([Emotion::ZERO; NUM_AXES]);

    pub fn from_values(values: [i16; NUM_AXES]) -> Self {
        let mut result = Self::ZERO;
        for axis in EmotionAxis::ALL {
            result.set(axis, values[axis.index()]);
        }
        result
    }

    pub fn random(rng: &mut DeterministicRng, min: i16, max: i16) -> Self {
        let mut result = Self::ZERO;
        for axis in EmotionAxis::ALL {
            result.set(axis, rng.next_i16_inclusive(min, max));
        }
        result
    }

    pub fn get(self, axis: EmotionAxis) -> Emotion {
        self.0[axis.index()]
    }

    pub fn set(&mut self, axis: EmotionAxis, value: i16) {
        self.0[axis.index()] = Emotion::new(value);
    }

    pub fn set_emotion(&mut self, axis: EmotionAxis, value: Emotion) {
        self.0[axis.index()] = value;
    }

    pub fn as_array(self) -> [Emotion; NUM_AXES] {
        self.0
    }

    /// Dominant axis by absolute value.  Ties keep the first axis, matching
    /// `Agent.get_primary_emotion()` in v2.  `None` means a neutral profile.
    pub fn primary(self) -> Option<(EmotionAxis, Emotion)> {
        let mut best_axis = EmotionAxis::SadnessJoy;
        let mut best_abs = -1i16;
        let mut best_value = 0i16;

        for axis in EmotionAxis::ALL {
            let value = self.get(axis).get();
            let abs = value.abs();
            if abs > best_abs {
                best_abs = abs;
                best_axis = axis;
                best_value = value;
            }
        }

        if best_abs <= 0 {
            None
        } else {
            Some((best_axis, Emotion::new(best_value)))
        }
    }

    /// Primary emotion value, or zero for a neutral profile.  This is the
    /// multiplier used by the relation update in v2.
    pub fn primary_value(self) -> i16 {
        self.primary().map_or(0, |(_, value)| value.get())
    }

    pub fn total_intensity(self) -> i32 {
        self.0
            .iter()
            .map(|value| i32::from(value.get().abs()))
            .sum()
    }
}

impl std::ops::Index<EmotionAxis> for EmotionVector {
    type Output = Emotion;

    fn index(&self, axis: EmotionAxis) -> &Self::Output {
        &self.0[axis.index()]
    }
}

impl std::ops::IndexMut<EmotionAxis> for EmotionVector {
    fn index_mut(&mut self, axis: EmotionAxis) -> &mut Self::Output {
        &mut self.0[axis.index()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clamps_to_the_legal_range() {
        assert_eq!(Emotion::new(100).get(), EMOTION_MAX);
        assert_eq!(Emotion::new(-100).get(), EMOTION_MIN);
    }

    #[test]
    fn truncates_toward_zero_like_v2() {
        assert_eq!(Emotion::new(10).adjust_f32(2.9).get(), 12);
        assert_eq!(Emotion::new(-10).adjust_f32(-2.9).get(), -12);
        assert_eq!(Emotion::new(1).adjust_f32(-2.9).get(), -1);
    }

    #[test]
    fn primary_uses_first_axis_on_a_tie() {
        let mut emotions = EmotionVector::ZERO;
        emotions.set(EmotionAxis::FearCalm, 10);
        emotions.set(EmotionAxis::AngerHumility, -10);
        assert_eq!(
            emotions.primary(),
            Some((EmotionAxis::FearCalm, Emotion::new(10)))
        );
    }

    #[test]
    fn neutral_profile_has_no_primary_axis() {
        assert_eq!(EmotionVector::ZERO.primary(), None);
        assert_eq!(EmotionVector::ZERO.primary_value(), 0);
    }
}
