use crate::ids::AgentId;

/// Discrete result of one interaction (the sigma model).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
#[repr(i8)]
pub enum Outcome {
    Failure = -1,
    Refusal = 0,
    Success = 1,
}

impl Outcome {
    pub const fn from_i8(value: i8) -> Option<Self> {
        match value {
            -1 => Some(Self::Failure),
            0 => Some(Self::Refusal),
            1 => Some(Self::Success),
            _ => None,
        }
    }

    pub const fn as_i8(self) -> i8 {
        self as i8
    }

    pub const fn is_refusal(self) -> bool {
        matches!(self, Self::Refusal)
    }
}

/// Rate modulation of the half-axis.  A value of `0.5` means ±50 %.
pub const SIGMA_RATE: f32 = 0.5;

/// Multiplier applied to a delta that moves a value on its current half-axis.
///
/// * success accelerates growth on `value >= 0` and slows it on `value < 0`;
/// * failure slows growth on `value >= 0` and accelerates it on `value < 0`;
/// * refusal has no half-axis multiplier; it is handled as a separate sharp
///   negative reaction.
///
/// Zero belongs to the positive half-axis, exactly as in the corrected v2
/// implementation.
pub fn sigma_rate_factor(value: i16, outcome: Outcome) -> f32 {
    if outcome.is_refusal() {
        return 1.0;
    }

    let high = 1.0 + SIGMA_RATE;
    let low = 1.0 - SIGMA_RATE;

    match (outcome, value >= 0) {
        (Outcome::Success, true) => high,
        (Outcome::Success, false) => low,
        (Outcome::Failure, true) => low,
        (Outcome::Failure, false) => high,
        (Outcome::Refusal, _) => 1.0,
    }
}

/// One contact in the event stream.  The world keeps only the current day by
/// default; exporters can persist this stream without touching the kernel.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Interaction {
    pub from: AgentId,
    pub to: AgentId,
    pub outcome: Outcome,
}

impl Interaction {
    pub const fn new(from: AgentId, to: AgentId, outcome: Outcome) -> Self {
        Self { from, to, outcome }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn success_accelerates_the_positive_half_axis() {
        assert_eq!(sigma_rate_factor(0, Outcome::Success), 1.5);
        assert_eq!(sigma_rate_factor(10, Outcome::Success), 1.5);
        assert_eq!(sigma_rate_factor(-10, Outcome::Success), 0.5);
    }

    #[test]
    fn failure_accelerates_the_negative_half_axis() {
        assert_eq!(sigma_rate_factor(0, Outcome::Failure), 0.5);
        assert_eq!(sigma_rate_factor(10, Outcome::Failure), 0.5);
        assert_eq!(sigma_rate_factor(-10, Outcome::Failure), 1.5);
    }

    #[test]
    fn refusal_has_no_half_axis_factor() {
        assert_eq!(sigma_rate_factor(-10, Outcome::Refusal), 1.0);
        assert_eq!(sigma_rate_factor(10, Outcome::Refusal), 1.0);
    }
}
