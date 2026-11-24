#!/usr/bin/env python3
"""Последовательный запуск аналитики v2-corrected.

Скрипт рассчитан на сервер: сначала проверяет, что батч завершён (54
маркера `.done`), затем запускает тяжёлые анализаторы по одному, чтобы
ClickHouse не получил несколько полных сканов одновременно.

Результаты каждого шага пишутся в `data/v2-corrected/analysis.log`,
итог — в `data/v2-corrected/analysis_status.json`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "data" / "v2-corrected"
DONE_DIR = OUTPUT_DIR / "done"
LOG_PATH = OUTPUT_DIR / "analysis.log"
STATUS_PATH = OUTPUT_DIR / "analysis_status.json"

STEPS = [
    ("baseline_9", ["scripts/baseline_9.py"]),
    ("hypotheses_9", ["scripts/hypotheses_9.py"]),
    ("mega_research", ["scripts/mega_research.py"]),
    ("sunday_reset", ["scripts/sunday_reset_analysis.py"]),
    ("research_analyzer", ["scripts/research_analyzer.py"]),
]


def done_count() -> int:
    if not DONE_DIR.exists():
        return 0
    return sum(1 for name in os.listdir(DONE_DIR) if name.endswith(".done"))


def python_bin() -> str:
    candidate = ROOT / "venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expected", type=int, default=54,
        help="Сколько .done-маркеров должно быть до старта аналитики",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Запустить, даже если батч ещё не завершён",
    )
    parser.add_argument(
        "--only", action="append", default=None,
        help="Имя шага (можно несколько раз)",
    )
    args = parser.parse_args()

    done = done_count()
    if done < args.expected and not args.force:
        print(
            f"Батч не завершён: {done}/{args.expected} маркеров. "
            "Аналитика не запущена (используйте --force при необходимости).",
            flush=True,
        )
        return 2

    selected = [
        (name, cmd) for name, cmd in STEPS
        if not args.only or name in set(args.only)
    ]
    if not selected:
        print("Нет выбранных шагов.", flush=True)
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    results = []

    with open(LOG_PATH, "a", encoding="utf-8") as log:
        log.write(
            f"\n===== analysis start {started_at} "
            f"(done={done}/{args.expected}) =====\n"
        )
        log.flush()

        for name, cmd in selected:
            step_start = time.time()
            print(f"\n▶ {name}: {' '.join(cmd)}", flush=True)
            log.write(f"\n--- {name}: {' '.join(cmd)} ---\n")
            log.flush()
            returncode = subprocess.call(
                [python_bin(), *cmd],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            elapsed = round(time.time() - step_start, 1)
            ok = returncode == 0
            results.append(
                {
                    "step": name,
                    "command": cmd,
                    "returncode": returncode,
                    "ok": ok,
                    "elapsed_seconds": elapsed,
                }
            )
            print(
                f"{'✅' if ok else '❌'} {name}: "
                f"{'ok' if ok else f'code {returncode}'} за {elapsed:.0f} с",
                flush=True,
            )
            log.write(
                f"--- {name}: returncode={returncode}, {elapsed:.0f} s ---\n"
            )
            log.flush()

    payload = {
        "schema": "automata-analysis-status/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started_at,
        "done_markers": done,
        "expected_markers": args.expected,
        "ok": all(item["ok"] for item in results),
        "steps": results,
    }
    STATUS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nСтатус: {STATUS_PATH}", flush=True)
    print(f"Лог: {LOG_PATH}", flush=True)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
