#!/usr/bin/env python3
"""Сводка таймингов батча для сравнения реализаций.

Читает JSON-файлы `automata-run-timing/v1` из `data/v2-corrected/timings/`
и пишет:
  * `data/v2-corrected/timing_summary.json` — машинно-читаемая сводка;
  * `data/v2-corrected/timing_summary.md` — таблица для отчёта.

Формат специально не зависит от Python: те же поля (`wall_seconds`,
`simulation_seconds`, `interactions`, `max_rss_kb`) сможет заполнить
Rust-реализация v3, и сводки будут сравнимы напрямую.
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_runs(timings_dir: Path) -> list[dict[str, Any]]:
    runs = []
    for path in sorted(timings_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[skip] {path.name}: {exc}")
            continue
        if data.get("schema") != "automata-run-timing/v1":
            print(f"[skip] {path.name}: неизвестная схема {data.get('schema')!r}")
            continue
        runs.append(data)
    return runs


def _stats(values: list[float]) -> dict[str, float]:
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return {"count": 0, "total": 0.0, "mean": 0.0, "median": 0.0,
                "min": 0.0, "max": 0.0, "stdev": 0.0}
    return {
        "count": len(clean),
        "total": round(sum(clean), 3),
        "mean": round(statistics.fmean(clean), 3),
        "median": round(statistics.median(clean), 3),
        "min": round(min(clean), 3),
        "max": round(max(clean), 3),
        "stdev": round(statistics.stdev(clean), 3) if len(clean) > 1 else 0.0,
    }


def build_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    wall = _stats([r.get("wall_seconds") for r in runs])
    simulation = _stats([r.get("simulation_seconds") for r in runs])
    init = _stats([r.get("init_seconds") for r in runs])
    finalize = _stats([r.get("finalize_seconds") for r in runs])
    rss_mb = _stats([(r.get("max_rss_kb") or 0) / 1024 for r in runs])
    cpu_user = _stats([r.get("cpu_user_seconds") for r in runs])
    cpu_system = _stats([r.get("cpu_system_seconds") for r in runs])
    interactions = _stats([r.get("interactions") for r in runs])
    per_run_ips = _stats(
        [
            (r.get("interactions") or 0) / r["simulation_seconds"]
            for r in runs
            if r.get("simulation_seconds")
        ]
    )

    statuses: dict[str, int] = {}
    implementations = set()
    engines = set()
    versions = set()
    for run in runs:
        status = str(run.get("status", "unknown"))
        statuses[status] = statuses.get(status, 0) + 1
        if run.get("implementation"):
            implementations.add(str(run["implementation"]))
        if run.get("engine"):
            engines.add(str(run["engine"]))
        if run.get("version"):
            versions.add(str(run["version"]))

    total_interactions = int(interactions["total"])
    total_sim_seconds = simulation["total"]
    per_scenario = []
    for run in sorted(runs, key=lambda r: str(r.get("scenario", ""))):
        sim = float(run.get("simulation_seconds") or 0.0)
        n = int(run.get("interactions") or 0)
        per_scenario.append(
            {
                "scenario": run.get("scenario"),
                "seed": run.get("seed"),
                "status": run.get("status"),
                "wall_seconds": run.get("wall_seconds"),
                "simulation_seconds": run.get("simulation_seconds"),
                "interactions": n,
                "interactions_per_second": round(n / sim, 2) if sim else 0.0,
                "agents": run.get("agents"),
                "days": run.get("days"),
                "semesters": run.get("semesters"),
                "max_rss_mb": round((run.get("max_rss_kb") or 0) / 1024, 1),
                "cpu_user_seconds": run.get("cpu_user_seconds"),
                "cpu_system_seconds": run.get("cpu_system_seconds"),
                "omp_threads": run.get("omp_threads"),
                "workers": run.get("workers"),
            }
        )

    return {
        "schema": "automata-timing-summary/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": len(runs),
        "implementations": sorted(implementations),
        "engines": sorted(engines),
        "versions": sorted(versions),
        "statuses": statuses,
        "wall_seconds": wall,
        "simulation_seconds": simulation,
        "init_seconds": init,
        "finalize_seconds": finalize,
        "max_rss_mb": rss_mb,
        "cpu_user_seconds": cpu_user,
        "cpu_system_seconds": cpu_system,
        "interactions": interactions,
        "interactions_per_second": per_run_ips,
        "aggregate_interactions_per_second": (
            round(total_interactions / total_sim_seconds, 2)
            if total_sim_seconds
            else 0.0
        ),
        "per_scenario": per_scenario,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    def fmt(value: float, digits: int = 1) -> str:
        return f"{value:,.{digits}f}".replace(",", " ")

    lines = [
        "# Тайминги батча v2-corrected",
        "",
        f"Сформировано: `{summary['generated_at']}`",
        "",
        f"Прогонов: **{summary['runs']}**  ",
        f"Реализация: `{', '.join(summary['implementations']) or '—'}`  ",
        f"Движок: `{', '.join(summary['engines']) or '—'}`  ",
        f"Версия: `{', '.join(summary['versions']) or '—'}`",
        "",
        "## Сводка",
        "",
        "| Метрика | Сумма | Среднее | Медиана | Мин | Макс |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Wall, с | {fmt(summary['wall_seconds']['total'])} | "
        f"{fmt(summary['wall_seconds']['mean'])} | "
        f"{fmt(summary['wall_seconds']['median'])} | "
        f"{fmt(summary['wall_seconds']['min'])} | "
        f"{fmt(summary['wall_seconds']['max'])} |",
        f"| Симуляция, с | {fmt(summary['simulation_seconds']['total'])} | "
        f"{fmt(summary['simulation_seconds']['mean'])} | "
        f"{fmt(summary['simulation_seconds']['median'])} | "
        f"{fmt(summary['simulation_seconds']['min'])} | "
        f"{fmt(summary['simulation_seconds']['max'])} |",
        f"| Контакты | {fmt(summary['interactions']['total'], 0)} | "
        f"{fmt(summary['interactions']['mean'], 0)} | "
        f"{fmt(summary['interactions']['median'], 0)} | "
        f"{fmt(summary['interactions']['min'], 0)} | "
        f"{fmt(summary['interactions']['max'], 0)} |",
        f"| RSS, МБ | — | {fmt(summary['max_rss_mb']['mean'])} | "
        f"{fmt(summary['max_rss_mb']['median'])} | "
        f"{fmt(summary['max_rss_mb']['min'])} | "
        f"{fmt(summary['max_rss_mb']['max'])} |",
        "",
        f"Агрегированная скорость: **{fmt(summary['aggregate_interactions_per_second'])}** контактов/с "
        f"(среднее по прогонам: {fmt(summary['interactions_per_second']['mean'])})",
        "",
        "## Прогоны",
        "",
        "| Сценарий | Wall, мин | Симуляция, с | Контакты | Контактов/с | RSS, МБ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["per_scenario"]:
        wall_min = (row["wall_seconds"] or 0) / 60
        lines.append(
            f"| `{row['scenario']}` | {fmt(wall_min)} | "
            f"{fmt(row['simulation_seconds'] or 0)} | "
            f"{fmt(row['interactions'], 0)} | "
            f"{fmt(row['interactions_per_second'])} | "
            f"{fmt(row['max_rss_mb'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timings-dir", default="data/v2-corrected/timings")
    parser.add_argument("--out-dir", default="data/v2-corrected")
    args = parser.parse_args()

    timings_dir = Path(args.timings_dir)
    runs = load_runs(timings_dir)
    if not runs:
        raise SystemExit(f"В {timings_dir} нет файлов automata-run-timing/v1")

    summary = build_summary(runs)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "timing_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "timing_summary.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )

    print(f"Прогонов: {summary['runs']}")
    print(
        f"Wall: {summary['wall_seconds']['total'] / 60:.1f} мин "
        f"(среднее {summary['wall_seconds']['mean'] / 60:.1f} мин)"
    )
    print(
        f"Контактов/с: {summary['aggregate_interactions_per_second']:.1f}"
    )
    print(f"Сводка: {out_dir / 'timing_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
