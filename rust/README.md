# automata v3 Rust backend

The Rust backend for v3: a dependency-free simulation kernel, the university
world, and the I/O layer that writes resumable CSV/ClickHouse runs.  Python
stays responsible for analytics and Telegram; the web frontend is still a
separate stage.

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

`rust/crates/automata-io` contains the production I/O layer:

- the 54-run v3 matrix with reserved ClickHouse numbers 55–108 and
  deterministic UUIDv5 `run_id`s;
- a durable `key=value` manifest with status, counters and checkpoint offsets;
- streaming CSV writers with byte-offset truncation;
- a std-only ClickHouse HTTP client (`INSERT ... FORMAT CSV`,
  `SELECT ... FORMAT TSV`, idempotent `ALTER TABLE ... DELETE`);
- a resumable single-scenario runner: snapshot every N days, rollback to the
  last checkpoint, registry rebuild after a resume, `CLEANUP` states/relations
  and per-slot interactions;
- a sequential batch runner that skips completed scenarios, resumes failed or
  interrupted ones, and writes a `batch.txt` summary.

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

Run the university world in memory (the full horizon is 1213 days):

```sh
cargo run --release -p automata-cli -- university \
  --days 1213 --seed 42 --threads 8
```

Continue a university snapshot, or write one after the run:

```sh
cargo run --release -p automata-cli -- university \
  --snapshot-in snapshot.bin --days 100 --threads 8 \
  --snapshot-out snapshot.bin
```

CSV output for a timing table:

```sh
cargo run --release -p automata-cli -- university \
  --days 1213 --seed 42 --threads 8 --format csv
```

Run one reserved v3 scenario with CSV/ClickHouse logging and resumable
checkpoints:

```sh
cargo run --release -p automata-cli -- run \
  --run-number 77 --output-dir data/v3/Run77_Uniform_Random_MIXED \
  --days 1213 --threads 8 --checkpoint-every 30 --clickhouse
```

Run the whole 54-run matrix sequentially (completed runs are skipped on
restart):

```sh
cargo run --release -p automata-cli -- batch \
  --output-dir data/v3 --days 1213 --threads 8 \
  --checkpoint-every 30 --clickhouse
```

`--clickhouse` reads `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`,
`CLICKHOUSE_DATABASE`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD` and
`CLICKHOUSE_TIMEOUT_MS`; the password is never printed.  Without a reachable
server the runner keeps writing CSV and warns, unless
`--clickhouse-required` is set.  Use `--no-interactions`, `--no-states` or
`--no-relations` for a state-only verification run.

The full 1213-day runner was verified locally with `Run77_Uniform_Random_MIXED`
and no detail logs: 4,294,325 contacts, 3 rotations, hash
`0x79f5809385358043`, ~58 s including 30-day snapshots.

Start the read-only web API and dashboard:

```sh
cargo run --release -p automata-web -- \
  --bind 127.0.0.1:8080 --data-dir data/v3
```

The server exposes `GET /api/health`, `/api/runs`, `/api/runs/<key>`,
`/api/runs/<key>/reports`, `/api/events` (SSE), `/files/runs/<key>/<file>`,
`/plots/<file>` and serves `web/dist` (or a built-in dashboard) at `/`.
It never runs a simulation: long runs stay in `automata-cli`/systemd.
`AUTOMATA_WEB_TOKEN` protects the API, files and plots with a bearer token;
the dashboard itself is public so it can ask for the token.

Build the React/Vite frontend (source in `web/`, output in `web/dist/`):

```sh
cd web
npm install
npm run build
```

For development, `npm run dev` proxies `/api`, `/files` and `/plots` to
`127.0.0.1:8080`; run `automata-web` in another terminal.  Without a built
`web/dist`, the Rust binary serves its embedded dashboard instead.

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
