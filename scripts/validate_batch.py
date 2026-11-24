#!/usr/bin/env python3
"""Проверка целостности полного батча v2-corrected.

Скрипт рассчитан на запуск рядом с ClickHouse (на сервере) и пишет
машиночитаемый отчёт `data/v2-corrected/validation.json` плюс короткую
markdown-сводку. Код возврата 1, если хотя бы одна проверка не прошла.

Проверяется:
  * число прогонов и уникальность сценариев;
  * 1213 дней и 8 семестров в каждом прогоне;
  * совпадение `run_timings.interactions` с числом строк `interactions`;
  * постоянные ID: все state/relation/interaction ID есть в registry;
  * отсутствие дублей (run_id, agent_id) в registry;
  * отсутствие насыщения эмоций на шкале ±30 после старта
    (значения ровно ±30 в день 0 — это граница инициализации);
  * непустые отношения на последнем дне.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import clickhouse_connect
except ImportError:  # локальная машина без клиента
    clickhouse_connect = None


EMOTION_AXES = [
    "sadness_joy",
    "fear_calm",
    "anger_humility",
    "disgust_acceptance",
    "habit_surprise",
    "shame_confidence",
    "alienation_openness",
]
ARCHETYPES = {
    "Erudition",
    "Enigmata",
    "Harmony",
    "Hunt",
    "Elation",
    "Preservation",
    "Nihility",
    "Trailblaze",
    "Remembrance",
}


class BatchValidator:
    def __init__(self, client, expected_days: int, expected_semesters: int):
        self.client = client
        self.expected_days = expected_days
        self.expected_semesters = expected_semesters
        self.checks: list[dict[str, Any]] = []

    # ── утилиты ──────────────────────────────────────────────────────
    def q(self, sql: str):
        return self.client.query_df(sql)

    def scalar(self, sql: str):
        df = self.q(sql)
        return df.iloc[0, 0]

    def check(self, name: str, ok: bool, detail: str, value: Any = None) -> None:
        self.checks.append(
            {"name": name, "ok": bool(ok), "detail": detail, "value": value}
        )

    # ── проверки ─────────────────────────────────────────────────────
    def check_runs(self) -> None:
        df = self.q(
            """
            SELECT count() AS runs,
                   uniqExact(scenario_name) AS scenarios
            FROM simulation_runs
            """
        )
        runs = int(df["runs"].iloc[0])
        scenarios = int(df["scenarios"].iloc[0])
        self.check(
            "runs_present",
            runs > 0 and runs == scenarios,
            f"runs={runs}, unique scenarios={scenarios}",
            {"runs": runs, "scenarios": scenarios},
        )

        timings = self.q(
            """
            SELECT count() AS n,
                   countIf(status = 'ok') AS ok,
                   uniqExact(scenario) AS scenarios
            FROM run_timings
            """
        )
        n = int(timings["n"].iloc[0])
        ok_n = int(timings["ok"].iloc[0])
        timing_scenarios = int(timings["scenarios"].iloc[0])
        self.check(
            "timings_present",
            n == runs and ok_n == n and timing_scenarios == n,
            f"timings={n}, ok={ok_n}, unique scenarios={timing_scenarios}",
            {"timings": n, "ok": ok_n, "scenarios": timing_scenarios},
        )

    def check_cycle(self) -> None:
        df = self.q(
            """
            SELECT scenario, days, semesters, agents
            FROM run_timings
            ORDER BY scenario
            """
        )
        bad_days = df[df["days"] != self.expected_days]
        bad_sem = df[df["semesters"] != self.expected_semesters]
        self.check(
            "days_and_semesters",
            bad_days.empty and bad_sem.empty,
            f"{len(df)} runs: days={self.expected_days}, "
            f"semesters={self.expected_semesters}",
            {
                "bad_days": bad_days.to_dict("records"),
                "bad_semesters": bad_sem.to_dict("records"),
            },
        )

    def check_interaction_counts(self) -> None:
        df = self.q(
            """
            SELECT r.scenario_name AS scenario,
                   t.interactions AS counted,
                   c.n AS logged,
                   t.interactions - c.n AS diff
            FROM run_timings t
            JOIN simulation_runs r ON t.run_id = r.run_id
            LEFT JOIN (
                SELECT run_id, count() AS n
                FROM interactions
                GROUP BY run_id
            ) c ON t.run_id = c.run_id
            ORDER BY scenario
            """
        )
        bad = df[df["diff"] != 0]
        self.check(
            "interaction_count_matches",
            bad.empty,
            f"{len(df)} runs, mismatches={len(bad)}",
            bad.to_dict("records") if not bad.empty else None,
        )

    def check_state_shape(self) -> None:
        # После ротации в прогоне больше ID, чем активная популяция:
        # ушедшие и новые люди оставляют строки, но в каждый день
        # логируется ровно `agents` активных агентов. Поэтому сравниваем
        # states с agents×logged_days, а не с числом уникальных ID.
        df = self.q(
            """
            SELECT r.scenario_name AS scenario,
                   max(s.day_id) AS max_day,
                   uniqExact(s.day_id) AS logged_days,
                   count() AS states,
                   any(t.agents) AS population,
                   uniqExact(s.agent_id) AS ids
            FROM agent_states s
            JOIN simulation_runs r ON s.run_id = r.run_id
            JOIN run_timings t ON t.run_id = s.run_id
            GROUP BY scenario
            ORDER BY scenario
            """
        )
        expected_max = self.expected_days - 1
        bad = df[
            (df["max_day"] != expected_max)
            | (df["states"] != df["population"] * df["logged_days"])
            | (df["ids"] < df["population"])
            | (df["logged_days"] <= 0)
        ]
        self.check(
            "state_grid_complete",
            bad.empty,
            f"{len(df)} runs, max_day={expected_max}, "
            f"states=population×logged_days, ids≥population",
            bad.to_dict("records") if not bad.empty else None,
        )

    def check_registry(self) -> None:
        df = self.q(
            """
            SELECT r.scenario_name AS scenario,
                   count() AS rows,
                   uniqExact(g.agent_id) AS ids,
                   uniqExact(g.string_id) AS people
            FROM agent_registry g
            JOIN simulation_runs r ON g.run_id = r.run_id
            GROUP BY scenario
            ORDER BY scenario
            """
        )
        bad = df[(df["rows"] != df["ids"]) | (df["rows"] != df["people"])]
        self.check(
            "registry_unique",
            bad.empty,
            f"{len(df)} runs, duplicate rows={len(bad)}",
            bad.to_dict("records") if not bad.empty else None,
        )

        unknown = self.q(
            """
            SELECT count() AS n
            FROM agent_registry
            WHERE archetype NOT IN ({})
            """.format(", ".join(f"'{a}'" for a in sorted(ARCHETYPES)))
        )
        n_unknown = int(unknown["n"].iloc[0])
        self.check(
            "registry_archetypes",
            n_unknown == 0,
            f"rows with unknown archetype={n_unknown}",
            n_unknown,
        )

    def check_post_rotation(self) -> None:
        df = self.q(
            """
            SELECT r.scenario_name AS scenario,
                   count() AS post_ids,
                   countIf(s.agent_id != 0) AS with_states
            FROM agent_registry g
            JOIN simulation_runs r ON g.run_id = r.run_id
            LEFT JOIN (
                SELECT DISTINCT run_id, agent_id
                FROM agent_states
            ) s ON g.run_id = s.run_id AND g.agent_id = s.agent_id
            WHERE g.agent_id >= 1620
            GROUP BY scenario
            ORDER BY scenario
            """
        )
        bad = df[(df["post_ids"] == 0) | (df["with_states"] != df["post_ids"])]
        self.check(
            "post_rotation_agents_have_states",
            bad.empty,
            f"{len(df)} runs, post-rotation ids without states={len(bad)}",
            bad.to_dict("records") if not bad.empty else None,
        )

    def check_id_coverage(self) -> None:
        queries = {
            "states": (
                "agent_states",
                "agent_id",
            ),
            "interactions_from": (
                "interactions",
                "from_id",
            ),
            "interactions_to": (
                "interactions",
                "to_id",
            ),
            "relations_subject": (
                "agent_relations",
                "subject_id",
            ),
            "relations_object": (
                "agent_relations",
                "object_id",
            ),
        }
        results = {}
        for label, (table, column) in queries.items():
            # Сначала схлопываем до уникальных (run_id, id): в relations и
            # interactions миллиарды строк, но ID людей всего ~150 тысяч.
            # Anti-join по полному потоку строк раньше упирался в память.
            n = int(
                self.scalar(
                    f"""
                    SELECT count()
                    FROM (
                        SELECT DISTINCT run_id, {column} AS agent_id
                        FROM {table}
                    ) x
                    LEFT ANTI JOIN agent_registry r
                        ON x.run_id = r.run_id AND x.agent_id = r.agent_id
                    """
                )
            )
            results[label] = n
        self.check(
            "ids_resolve_to_registry",
            all(v == 0 for v in results.values()),
            "missing ids by source: "
            + ", ".join(f"{k}={v}" for k, v in results.items()),
            results,
        )

    def check_emotion_range(self) -> None:
        expr_max = "greatest(" + ",".join(EMOTION_AXES) + ")"
        expr_min = "least(" + ",".join(EMOTION_AXES) + ")"
        # День 0 — это начальное состояние до первого воскресного сдвига.
        # Архетипные веса могут дать ровно ±30 уже там; это граница
        # допустимого диапазона, а не насыщение динамики. Проверяем, что
        # после старта эмоции не залипают на границе.
        df = self.q(
            f"""
            SELECT minIf({expr_min}, day_id > 0) AS min_value,
                   maxIf({expr_max}, day_id > 0) AS max_value,
                   countIf(day_id > 0 AND ({expr_max} >= 30 OR {expr_min} <= -30))
                       AS saturated,
                   countIf(day_id = 0 AND ({expr_max} >= 30 OR {expr_min} <= -30))
                       AS day0_boundary
            FROM agent_states
            """
        )
        min_value = float(df["min_value"].iloc[0])
        max_value = float(df["max_value"].iloc[0])
        saturated = int(df["saturated"].iloc[0])
        day0_boundary = int(df["day0_boundary"].iloc[0])
        self.check(
            "emotions_not_saturated_after_init",
            saturated == 0 and min_value >= -30 and max_value <= 30,
            f"range after day 0=[{min_value:.0f}, {max_value:.0f}], "
            f"saturated={saturated}, day0 boundary rows={day0_boundary}",
            {
                "min": min_value,
                "max": max_value,
                "saturated_rows": saturated,
                "day0_boundary_rows": day0_boundary,
            },
        )

    def check_final_relations(self) -> None:
        # Фильтруем день до join: иначе запрос сканирует все 2+ млрд
        # строк agent_relations ради ~50 тыс. строк последнего дня.
        df = self.q(
            """
            SELECT r.scenario_name AS scenario,
                   count() AS final_rows,
                   uniqExact(rel.subject_id) AS subjects
            FROM agent_relations rel
            JOIN simulation_runs r ON rel.run_id = r.run_id
            WHERE rel.day_id = {max_day}
            GROUP BY scenario
            ORDER BY scenario
            """.format(max_day=self.expected_days - 1)
        )
        bad = df[df["final_rows"] == 0]
        runs = int(self.scalar("SELECT count() FROM simulation_runs"))
        self.check(
            "final_day_relations",
            bad.empty and len(df) == runs,
            f"{len(df)}/{runs} runs with rows, empty final day={len(bad)}",
            bad.to_dict("records") if not bad.empty else None,
        )

    # ── запуск ───────────────────────────────────────────────────────
    def run(self) -> dict[str, Any]:
        for fn in (
            self.check_runs,
            self.check_cycle,
            self.check_interaction_counts,
            self.check_state_shape,
            self.check_registry,
            self.check_post_rotation,
            self.check_id_coverage,
            self.check_emotion_range,
            self.check_final_relations,
        ):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                self.checks.append(
                    {
                        "name": fn.__name__,
                        "ok": False,
                        "detail": f"check failed: {exc}",
                        "value": None,
                    }
                )

        ok = all(c["ok"] for c in self.checks)
        return {
            "schema": "automata-batch-validation/v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "expected": {
                "days": self.expected_days,
                "semesters": self.expected_semesters,
            },
            "ok": ok,
            "checks": self.checks,
        }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Проверка батча v2-corrected",
        "",
        f"Сформировано: `{report['generated_at']}`",
        "",
        f"**Итог:** {'✅ OK' if report['ok'] else '❌ ЕСТЬ ОШИБКИ'}",
        "",
        "| Проверка | Результат | Детали |",
        "|---|---|---|",
    ]
    for check in report["checks"]:
        mark = "✅" if check["ok"] else "❌"
        detail = str(check["detail"]).replace("|", "\\|")
        lines.append(f"| `{check['name']}` | {mark} | {detail} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("CLICKHOUSE_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("CLICKHOUSE_PORT", "8123")))
    parser.add_argument("--user", default=os.getenv("CLICKHOUSE_USER", "default"))
    parser.add_argument("--password", default=os.getenv("CLICKHOUSE_PASSWORD", ""))
    parser.add_argument("--secure", action="store_true",
                        default=os.getenv("CLICKHOUSE_SECURE", "False").lower() in ("true", "1", "yes"))
    parser.add_argument("--expected-days", type=int, default=1213)
    parser.add_argument("--expected-semesters", type=int, default=8)
    parser.add_argument("--out-dir", default="data/v2-corrected")
    args = parser.parse_args()

    if clickhouse_connect is None:
        raise SystemExit(
            "clickhouse_connect не установлен. Запустите скрипт в venv сервера."
        )

    client = clickhouse_connect.get_client(
        host=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        secure=args.secure,
    )
    report = BatchValidator(client, args.expected_days, args.expected_semesters).run()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "validation.md").write_text(render_markdown(report), encoding="utf-8")

    for check in report["checks"]:
        mark = "OK  " if check["ok"] else "FAIL"
        print(f"[{mark}] {check['name']}: {check['detail']}")
    print(f"\nОтчёт: {out_dir / 'validation.json'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
