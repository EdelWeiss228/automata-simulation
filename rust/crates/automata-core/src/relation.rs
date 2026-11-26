pub const RELATION_MIN: i16 = -100;
pub const RELATION_MAX: i16 = 100;

/// Three relational functions.  The discriminant is the storage index.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[repr(usize)]
pub enum RelationAxis {
    Utility = 0,
    Affinity = 1,
    Trust = 2,
}

impl RelationAxis {
    pub const ALL: [Self; 3] = [Self::Utility, Self::Affinity, Self::Trust];

    pub const fn index(self) -> usize {
        self as usize
    }

    pub const fn key(self) -> &'static str {
        match self {
            Self::Utility => "utility",
            Self::Affinity => "affinity",
            Self::Trust => "trust",
        }
    }
}

/// Ordered relation `i -> j` on the internal x10 scale, `[-100, 100]`.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Relation {
    utility: i16,
    affinity: i16,
    trust: i16,
}

impl Relation {
    pub const ZERO: Self = Self {
        utility: 0,
        affinity: 0,
        trust: 0,
    };

    pub fn new(utility: i16, affinity: i16, trust: i16) -> Self {
        Self {
            utility: clamp(utility),
            affinity: clamp(affinity),
            trust: clamp(trust),
        }
    }

    pub const fn get(self, axis: RelationAxis) -> i16 {
        match axis {
            RelationAxis::Utility => self.utility,
            RelationAxis::Affinity => self.affinity,
            RelationAxis::Trust => self.trust,
        }
    }

    pub fn set(&mut self, axis: RelationAxis, value: i16) {
        let value = clamp(value);
        match axis {
            RelationAxis::Utility => self.utility = value,
            RelationAxis::Affinity => self.affinity = value,
            RelationAxis::Trust => self.trust = value,
        }
    }

    /// Adds a floating-point delta using the same truncation rule as v2.
    pub fn adjust_f32(&mut self, axis: RelationAxis, delta: f32) {
        let current = self.get(axis);
        let next = (current as f32 + delta).trunc() as i16;
        self.set(axis, next);
    }

    pub fn adjust_i32(&mut self, axis: RelationAxis, delta: i32) {
        let current = i32::from(self.get(axis));
        let next = (current + delta).clamp(RELATION_MIN as i32, RELATION_MAX as i32) as i16;
        self.set(axis, next);
    }

    /// A relation is "absent" only when all three functions are zero.  This
    /// matches the v2 convention: zero is tabula rasa, not a neutral edge.
    pub const fn is_zero(self) -> bool {
        self.utility == 0 && self.affinity == 0 && self.trust == 0
    }

    pub fn mean(self) -> f32 {
        (self.utility as f32 + self.affinity as f32 + self.trust as f32) / 3.0
    }

    /// Mean in the addition order used by the v2 influence phase
    /// (`affinity + trust + utility`), kept separate so that the floating-point
    /// trajectory stays comparable with the C++ reference.
    pub fn influence_weight_mean(self) -> f32 {
        (self.affinity as f32 + self.trust as f32 + self.utility as f32) / 3.0
    }

    pub const fn as_array(self) -> [i16; 3] {
        [self.utility, self.affinity, self.trust]
    }
}

fn clamp(value: i16) -> i16 {
    value.clamp(RELATION_MIN, RELATION_MAX)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clamps_all_axes() {
        let relation = Relation::new(1000, -1000, 42);
        assert_eq!(relation.get(RelationAxis::Utility), RELATION_MAX);
        assert_eq!(relation.get(RelationAxis::Affinity), RELATION_MIN);
        assert_eq!(relation.get(RelationAxis::Trust), 42);
    }

    #[test]
    fn truncates_toward_zero() {
        let mut relation = Relation::new(10, -10, 0);
        relation.adjust_f32(RelationAxis::Utility, 2.9);
        relation.adjust_f32(RelationAxis::Affinity, -2.9);
        assert_eq!(relation.get(RelationAxis::Utility), 12);
        assert_eq!(relation.get(RelationAxis::Affinity), -12);
    }

    #[test]
    fn zero_is_absent() {
        assert!(Relation::ZERO.is_zero());
        assert!(!Relation::new(0, 0, 1).is_zero());
    }
}
