//! Cross-thread determinism checks for the v3 kernel prototype.
//!
//! The contract is stronger than "same seed, same thread count": the result
//! must not depend on how many workers execute the independent phases.  These
//! tests are the executable form of the 1/2/8-thread checklist item.

use automata_core::{
    AgentSpec, ArchetypeKind, Context, Degree, InitMode, RunReport, World, WorldConfig,
};

fn specs(count: usize) -> Vec<AgentSpec> {
    (0..count)
        .map(|index| {
            AgentSpec::new(
                format!("S-{:04}", index + 1),
                ArchetypeKind::ALL[index % ArchetypeKind::ALL.len()],
                0.5 + ((index * 37) % 240) as f32 / 100.0,
                (index / 25) as u32,
                ((index % 4) + 1) as u8,
                Degree::Bachelor,
            )
        })
        .collect()
}

fn run(threads: usize, seed: u64, init: InitMode, agents: usize, days: u32) -> RunReport {
    let config = WorldConfig {
        seed,
        parallelism: threads,
        init_mode: init,
        ..WorldConfig::default()
    };
    let mut world = World::from_specs(specs(agents), config);
    world.run(days, Context::Study)
}

#[test]
fn one_two_and_eight_threads_produce_the_same_trajectory() {
    for seed in [1, 42, 2026] {
        for init in [InitMode::Empty, InitMode::Mixed, InitMode::Random] {
            let single = run(1, seed, init, 100, 1);
            let dual = run(2, seed, init, 100, 1);
            let many = run(8, seed, init, 100, 1);

            assert_eq!(
                single.final_hash, dual.final_hash,
                "seed={seed}, init={init:?}"
            );
            assert_eq!(
                single.final_hash, many.final_hash,
                "seed={seed}, init={init:?}"
            );
            assert_eq!(single.final_rng_state, dual.final_rng_state);
            assert_eq!(single.final_rng_state, many.final_rng_state);
            assert_eq!(single.total_interactions, dual.total_interactions);
            assert_eq!(single.total_interactions, many.total_interactions);
            assert_eq!(single.successes, many.successes);
            assert_eq!(single.failures, many.failures);
            assert_eq!(single.refusals, many.refusals);
        }
    }
}

#[test]
fn different_seeds_produce_different_trajectories() {
    let left = run(1, 1, InitMode::Empty, 100, 1);
    let right = run(1, 2, InitMode::Empty, 100, 1);
    assert_ne!(left.final_hash, right.final_hash);
}

#[test]
fn repeating_a_run_is_bit_identical() {
    let first = run(8, 777, InitMode::Random, 100, 3);
    let second = run(8, 777, InitMode::Random, 100, 3);
    assert_eq!(first.final_hash, second.final_hash);
    assert_eq!(first.final_rng_state, second.final_rng_state);
    assert_eq!(first.total_interactions, second.total_interactions);
}

/// The full university scale, one simulated day.  Kept ignored because debug
/// builds are slow at 1620 agents; the release run is part of the benchmark
/// protocol (`cargo test --release -- --ignored`).
#[test]
#[ignore = "1620-agent cross-thread check; run in release mode"]
fn university_scale_is_thread_count_independent() {
    let single = run(1, 2024, InitMode::Empty, 1620, 2);
    let many = run(8, 2024, InitMode::Empty, 1620, 2);
    assert_eq!(single.final_hash, many.final_hash);
    assert_eq!(single.final_rng_state, many.final_rng_state);
    assert_eq!(single.total_interactions, many.total_interactions);
    assert!(single.total_interactions > 0);
}
