import json
import os
import tempfile
import unittest

from core.performance import RunTimer


class RunTimerTest(unittest.TestCase):
    def test_writes_machine_readable_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            timer = RunTimer(
                "Run15_Trailblaze_EMPTY",
                implementation="python-v2",
                engine="cpp-openmp",
                output_dir=directory,
                seed=676423,
                config_path="scenarios_archive/Run15_Trailblaze_EMPTY.json",
            )
            timer.mark("init")
            timer.mark("simulation")
            payload = timer.finish(
                status="ok",
                extra={
                    "agents": 1620,
                    "days": 1213,
                    "semesters": 8,
                    "interactions": 12345,
                },
            )

            path = os.path.join(directory, "Run15_Trailblaze_EMPTY.json")
            self.assertTrue(os.path.exists(path))
            with open(path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)

            self.assertEqual(saved["schema"], "automata-run-timing/v1")
            self.assertEqual(saved["scenario"], "Run15_Trailblaze_EMPTY")
            self.assertEqual(saved["implementation"], "python-v2")
            self.assertEqual(saved["engine"], "cpp-openmp")
            self.assertEqual(saved["status"], "ok")
            self.assertEqual(saved["agents"], 1620)
            self.assertEqual(saved["days"], 1213)
            self.assertEqual(saved["interactions"], 12345)
            self.assertGreaterEqual(saved["wall_seconds"], 0.0)
            self.assertIn("init", saved["phases"])
            self.assertIn("simulation", saved["phases"])
            self.assertEqual(payload["seed"], 676423)

    def test_finish_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            timer = RunTimer("Only_Once", output_dir=directory)
            first = timer.finish()
            second = timer.finish()
            self.assertTrue(first)
            self.assertEqual(second, {})


if __name__ == "__main__":
    unittest.main()
