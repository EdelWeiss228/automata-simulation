import json
import tempfile
import unittest
from pathlib import Path

from scripts import summarize_timings


def _run(name, wall, sim, interactions, status="ok", rss_kb=256000):
    return {
        "schema": "automata-run-timing/v1",
        "scenario": name,
        "implementation": "python-v2",
        "engine": "cpp-openmp",
        "version": "v2-fixed",
        "wall_seconds": wall,
        "simulation_seconds": sim,
        "init_seconds": 0.3,
        "finalize_seconds": 0.0001,
        "cpu_user_seconds": sim * 0.9,
        "cpu_system_seconds": 30.0,
        "max_rss_kb": rss_kb,
        "interactions": interactions,
        "agents": 1620,
        "days": 1213,
        "semesters": 8,
        "status": status,
        "seed": 1,
        "omp_threads": "1",
        "workers": "8",
    }


class TimingSummaryTest(unittest.TestCase):
    def test_summary_aggregates_runs_and_keeps_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            timings = Path(tmp) / "timings"
            timings.mkdir()
            (timings / "a.json").write_text(
                json.dumps(_run("A", 100.0, 90.0, 9000)), encoding="utf-8"
            )
            (timings / "b.json").write_text(
                json.dumps(_run("B", 120.0, 100.0, 12000)), encoding="utf-8"
            )
            # Файлы с чужой схемой не должны попадать в сводку.
            (timings / "ignored.json").write_text(
                json.dumps({"schema": "other"}), encoding="utf-8"
            )

            runs = summarize_timings.load_runs(timings)
            self.assertEqual([r["scenario"] for r in runs], ["A", "B"])

            summary = summarize_timings.build_summary(runs)
            self.assertEqual(summary["schema"], "automata-timing-summary/v1")
            self.assertEqual(summary["runs"], 2)
            self.assertEqual(summary["wall_seconds"]["total"], 220.0)
            self.assertEqual(summary["interactions"]["total"], 21000)
            self.assertEqual(summary["aggregate_interactions_per_second"], 110.53)
            self.assertEqual(summary["statuses"], {"ok": 2})
            self.assertEqual(
                [row["scenario"] for row in summary["per_scenario"]], ["A", "B"]
            )

            markdown = summarize_timings.render_markdown(summary)
            self.assertIn("`A`", markdown)
            self.assertIn("110.5", markdown)

    def test_failed_run_is_counted_in_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            timings = Path(tmp)
            (timings / "a.json").write_text(
                json.dumps(_run("A", 1.0, 1.0, 10, status="error")),
                encoding="utf-8",
            )
            summary = summarize_timings.build_summary(
                summarize_timings.load_runs(timings)
            )
            self.assertEqual(summary["statuses"], {"error": 1})


if __name__ == "__main__":
    unittest.main()
