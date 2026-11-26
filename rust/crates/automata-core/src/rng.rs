/// Small, dependency-free deterministic RNG.
///
/// SplitMix64 is used instead of `std::collections::hash_map::RandomState` or a
/// platform RNG because the whole point of the kernel is reproducibility.  The
/// algorithm is fixed by this source file, not by a crate version, and the
/// state is a single `u64`, which is easy to serialize in a run manifest.
#[derive(Clone, Debug)]
pub struct DeterministicRng {
    state: u64,
}

impl DeterministicRng {
    pub const fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    pub const fn state(&self) -> u64 {
        self.state
    }

    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform value in `[0, 1)` using the top 24 bits, which are exactly
    /// representable in `f32`.
    pub fn next_f32(&mut self) -> f32 {
        let bits = (self.next_u64() >> 40) as u32;
        bits as f32 / (1u32 << 24) as f32
    }

    /// Integer percentage in `[0, 100)`.
    pub fn next_percent(&mut self) -> u32 {
        (self.next_u64() % 100) as u32
    }

    /// Uniform integer in the inclusive range `[min, max]`.
    pub fn next_i16_inclusive(&mut self, min: i16, max: i16) -> i16 {
        debug_assert!(min <= max);
        let span = (i32::from(max) - i32::from(min) + 1) as u64;
        let offset = (self.next_u64() % span) as i32;
        (i32::from(min) + offset) as i16
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_seed_gives_the_same_stream() {
        let mut left = DeterministicRng::new(42);
        let mut right = DeterministicRng::new(42);
        for _ in 0..1000 {
            assert_eq!(left.next_u64(), right.next_u64());
        }
    }

    #[test]
    fn different_seeds_diverge() {
        let mut left = DeterministicRng::new(42);
        let mut right = DeterministicRng::new(43);
        assert_ne!(left.next_u64(), right.next_u64());
    }

    #[test]
    fn float_is_in_unit_interval() {
        let mut rng = DeterministicRng::new(7);
        for _ in 0..10_000 {
            let value = rng.next_f32();
            assert!((0.0..1.0).contains(&value));
        }
    }

    #[test]
    fn inclusive_range_covers_both_ends() {
        let mut rng = DeterministicRng::new(1);
        let mut seen_min = false;
        let mut seen_max = false;
        for _ in 0..10_000 {
            let value = rng.next_i16_inclusive(-3, 3);
            assert!((-3..=3).contains(&value));
            seen_min |= value == -3;
            seen_max |= value == 3;
        }
        assert!(seen_min && seen_max);
    }
}
