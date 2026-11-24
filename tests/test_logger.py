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
    def test_registry_is_append_only_and_uses_stable_ids(self):
        from model.university_collective import UniversityCollective

        class FakeClient:
            def __init__(self):
                self.rows = []

            def insert(self, table, data, column_names=None):
                self.rows.extend(data)

        collective = UniversityCollective(
            seed=777,
            config={
                "start_year": 2024,
                "initial_relations_mode": "EMPTY",
                "total_bac": 1500,
                "total_mag": 120,
            },
        )
        logger = ClickHouseLogger.__new__(ClickHouseLogger)
        logger.client = FakeClient()
        logger.run_id = "run"
        logger.output_dir = "."
        logger._logged_registry_ids = set()

        logger.log_agent_registry(collective)
        first = len(logger.client.rows)
        self.assertEqual(first, len(collective.agents))

        # Повторный вызов не дублирует уже известных людей.
        logger.log_agent_registry(collective)
        self.assertEqual(len(logger.client.rows), first)

        collective._handle_graduation_and_enrollment()
        logger.log_agent_registry(collective)
        self.assertGreater(len(logger.client.rows), first)

        ids = [row[1] for row in logger.client.rows]
        self.assertEqual(len(ids), len(set(ids)))
        known = {agent.stable_id for agent in collective.agents.values()}
        self.assertTrue(set(ids) & known)

    @unittest.skipUnless(CLICKHOUSE_LOGGER_AVAILABLE, "clickhouse logger deps not installed")
    def test_empty_slot_does_not_read_stale_cpp_interactions(self):
        class FakeClient:
            def __init__(self):
                self.rows = []

            def insert(self, table, data, column_names=None):
                self.rows.extend(data)

        logger = ClickHouseLogger.__new__(ClickHouseLogger)
        logger.client = FakeClient()
        logger.run_id = "run"

        # engine=None: пустой слот не должен обращаться к last_day_interactions.
        logger.log_interactions(
            1, 1, None, interactions_list=[], stable_id_map={"A": 0}
        )
        self.assertEqual(logger.client.rows, [])

    @unittest.skipUnless(CLICKHOUSE_LOGGER_AVAILABLE, "clickhouse logger deps not installed")
    def test_interaction_list_is_written_with_stable_ids(self):
        class FakeClient:
            def __init__(self):
                self.rows = []

            def insert(self, table, data, column_names=None):
                self.rows.extend(data)

        logger = ClickHouseLogger.__new__(ClickHouseLogger)
        logger.client = FakeClient()
        logger.run_id = "run"

        logger.log_interactions(
            1, 1, None,
            interactions_list=[("A", "B", "success"), ("A", "C", "fail")],
            stable_id_map={"A": 7, "B": 11, "C": 13},
        )
        self.assertEqual(
            [(row[3], row[4], row[5]) for row in logger.client.rows],
            [(7, 11, 1), (7, 13, -1)],
        )

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
