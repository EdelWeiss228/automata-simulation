import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "core"))
import emotion_engine  # noqa: E402

try:
    from core.clickhouse_logger import ClickHouseLogger  # noqa: E402
    CLICKHOUSE_LOGGER_AVAILABLE = True
except ImportError:
    ClickHouseLogger = None
    CLICKHOUSE_LOGGER_AVAILABLE = False


class InteractionLoggerTest(unittest.TestCase):
    def test_failure_is_written_as_fail_not_out_of_bounds(self):
        engine = emotion_engine.Engine(2)
        engine.set_agent_names(["A", "B"])
        engine.set_archetype_config(
            0, 0.0, 8.0, 1.0, 2.0, 0, [10.0] * 7,
            "linear", "linear", "linear",
        )
        engine.seed(1)
        engine.perform_daily_cycle(1)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "interactions.csv")
            engine.save_interactions_csv(path, "2024-09-02 00:00:00", True)
            with open(path, newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))

        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0], ["Дата", "Источник", "Цель", "Успех"])
        for row in rows[1:]:
            self.assertEqual(len(row), 4)
            self.assertIn(row[3], {"success", "fail", "refusal", "unknown"})

    @unittest.skipUnless(CLICKHOUSE_LOGGER_AVAILABLE, "clickhouse logger deps not installed")
    def test_zero_relations_are_not_logged(self):
        engine = emotion_engine.Engine(3)
        engine.set_relation(0, 1, 10, 5, 7)
        logger = ClickHouseLogger.__new__(ClickHouseLogger)
        logger.client = object()
        logger.run_id = "run"
        logger.relations_buffer = []

        logger.log_agent_relations(1, 9, engine)

        self.assertEqual(len(logger.relations_buffer), 1)
        chunk = logger.relations_buffer[0]
        # Только одна ненулевая связь из трёх возможных пар.
        self.assertEqual(len(chunk[0]), 1)
        self.assertEqual(int(chunk[3][0]), 0)
        self.assertEqual(int(chunk[4][0]), 1)
        self.assertEqual(int(chunk[5][0]), 10)
        self.assertEqual(int(chunk[6][0]), 5)
        self.assertEqual(int(chunk[7][0]), 7)


if __name__ == "__main__":
    unittest.main()
