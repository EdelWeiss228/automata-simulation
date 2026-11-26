#!/usr/bin/env bash
# Machine-readable timing harness for the v3 Rust kernel prototype.
#
# Usage:
#   ./bench.sh [output.csv]
#   REPS=5 ./bench.sh timings.csv
#
# The output has one row per run and is intentionally compatible with the
# Python/C++ timing tables produced for v2: model,seed,agents,days,threads,
# init,archetype,context,init_ms,sim_ms,interactions,success,failure,refusal,
# final_hash,final_rng_state.
set -euo pipefail
cd "$(dirname "$0")"

out="${1:-bench-results.csv}"
reps="${REPS:-3}"
bin="./target/release/automata-cli"

cargo build --release -p automata-cli >/dev/null

run() {
    "$bin" "$@" --format csv | tail -n +2 >> "$out"
}

# Header plus a warm-up row that is discarded from the comparison table.
"$bin" --agents 100 --days 1 --seed 1 --threads 1 --format csv > "$out"

for _ in $(seq 1 "$reps"); do
    for threads in 1 2 8; do
        run --agents 100 --days 30 --seed 42 --threads "$threads" --init mixed
        run --agents 1620 --days 5 --seed 2024 --threads "$threads" --init empty
    done
done

echo "wrote $out"
