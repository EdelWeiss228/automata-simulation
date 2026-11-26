# automata-core (v3 Rust prototype)

A dependency-free vertical slice of the v3 simulation kernel.  It is not a
replacement for the frozen v2 batch yet; it exists to test the properties that
matter for v3: typed state, deterministic execution, and thread-count-independent
parallel phases.

## What is implemented

- seven emotional axes and three relational functions on the internal x10 scale;
- nine archetypes with the corrected v2 parameters, scoring transforms, context
  multipliers and refusal vulnerabilities;
- target-based, context-aware refusal and the `-1 / 0 / +1` sigma model;
- pre-interaction `E(t)` snapshots for both participants;
- daily relation decay, relation-to-emotion reaction, emotion decay,
  emotion-to-relation reaction, and DeGroot-style top-8 emotional influence;
- SplitMix64 RNG with an explicit, serializable state;
- `std::thread::scope` data parallelism over disjoint agent/relation chunks;
- a deterministic FNV-1a state hash and a machine-readable CLI.

`rust/crates/automata-university` now contains the full university world:

- the academic calendar (1213 simulated days, 8 semesters, explicit weekdays);
- the population structure (1620 people, 60 bachelor groups, 12 master cohorts,
  yearly rotation with relation-preserving world rebuild);
- the campus (25 lecture halls, 75 seminar rooms, corridor, gym with three
  isolated sections);
- six-day, four-pair schedules, including post-rotation cohorts;
- softmax seating with at most 15 candidates and free-seat pools instead of
  quadratic rescans;
- the nine-slot day (`pair`, `break`, `pair`, `break`, `pair`, `break`,
  `pair`, `gym`, `cleanup`), attendance/skip logic and Sunday rules;
- room-level interaction topology (four-way neighbourhood, archetype
  temperature, STOP weight) and a runtime bridge to `automata-core`.

The web frontend will be a static SPA served by `automata-web`; the API
contract and stack are also described in the migration document.

## Commands

```sh
cargo test --workspace
cargo test --release -p automata-core --test determinism -- --ignored
cargo test --release -p automata-university full_horizon_matches -- --ignored
cargo clippy --workspace --all-targets -- -D warnings
cargo fmt --all -- --check
```

Run the core prototype:

```sh
cargo run --release -p automata-cli -- core \
  --agents 1620 --days 5 --seed 2024 --threads 8 --init empty
```

Run the university world (the full horizon is 1213 days):

```sh
cargo run --release -p automata-cli -- university \
  --days 1213 --seed 42 --threads 8
```

CSV output for a timing table:

```sh
cargo run --release -p automata-cli -- university \
  --days 1213 --seed 42 --threads 8 --format csv
```

Benchmark harness for the core prototype (writes `bench-results.csv` by
default):

```sh
REPS=3 ./bench.sh
```

## Determinism contract

1. The RNG is a single `SplitMix64` stream per world, seeded once.  There is no
   thread-local RNG and no entropy from the OS.
2. Iteration order is explicit: dense indices, sorted vectors, `BTreeMap` where
   a map is unavoidable.  `HashMap` is not used in the model.
3. Parallel phases are data-parallel only: each worker owns a disjoint slice of
   agents and/or relation rows, and no floating-point reduction crosses a
   thread boundary.
4. The thread count is a performance knob, not a semantic one.  The
   `determinism` integration test checks 1, 2 and 8 threads on the same seed and
   compares the final state hash, RNG state and interaction counters.

The 1620-agent, two-day cross-thread test is part of the release run:

```sh
cargo test --release -p automata-core --test determinism -- --ignored
```

## Toolchain note

The local prototype was built with Rust 1.100.0 (stable) and the test suite was
also run with Rust 1.99.1, which matches the server toolchain.  The core crate
has no external dependencies, so it builds even when crates.io is unavailable.
This is deliberate: the v2 server could not reach crates.io, and the kernel
must not depend on network access.
