import json
import os
import unittest

from model.archetypes import ArchetypeEnum
from scripts import run_research_batch as batch


class ScenarioMatrixTest(unittest.TestCase):
    def test_all_nine_archetypes_have_homogeneous_runs(self):
        self.assertEqual(len(batch.HOMOGENEOUS_RUNS), 9)
        covered = set()
        for counts in batch.HOMOGENEOUS_RUNS.values():
            self.assertEqual(sum(counts.values()), 1500)
            covered.update(counts)
        self.assertEqual(covered, {arch.name for arch in ArchetypeEnum})

    def test_missing_archetypes_are_present(self):
        self.assertIn("Run15_Trailblaze", batch.HOMOGENEOUS_RUNS)
        self.assertIn("Run16_Remembrance", batch.HOMOGENEOUS_RUNS)
        self.assertEqual(
            batch.HOMOGENEOUS_RUNS["Run15_Trailblaze"],
            {"TRAILBLAZE": 1500},
        )
        self.assertEqual(
            batch.HOMOGENEOUS_RUNS["Run16_Remembrance"],
            {"REMEMBRANCE": 1500},
        )

    def test_new_heterogeneous_runs_cover_all_nine(self):
        for run_id in ("Run17_All_Nine_Uniform", "Run18_Weighted_Random"):
            counts = batch.HETEROGENEOUS_RUNS[run_id]
            self.assertEqual(sum(counts.values()), 1500)
            self.assertEqual(
                set(counts), {arch.name for arch in ArchetypeEnum})

    def test_three_initialisations_per_new_family(self):
        new_runs = [
            "Run15_Trailblaze",
            "Run16_Remembrance",
            "Run17_All_Nine_Uniform",
            "Run18_Weighted_Random",
        ]
        for run_id in new_runs:
            for mode in batch.RELATION_MODES:
                path = os.path.join(
                    batch.ARCHIVE_DIR, f"{run_id}_{mode}.json")
                self.assertTrue(os.path.exists(path), path)
                with open(path, "r", encoding="utf-8") as handle:
                    config = json.load(handle)
                self.assertEqual(config["run_name"], run_id)
                self.assertEqual(config["initial_relations_mode"], mode)
                self.assertEqual(config["semesters"], 8)
                self.assertIsInstance(config["seed"], int)
                self.assertEqual(
                    sum(config["master_counts"].values()), 120)

    def test_matrix_has_54_scenarios(self):
        tasks = [
            f"{run_id}_{mode}"
            for run_id in batch.ALL_RUNS
            for mode in batch.RELATION_MODES
        ]
        self.assertEqual(len(tasks), 54)
        self.assertEqual(len(set(tasks)), 54)

    def test_seeds_are_unique_across_archive(self):
        seeds = []
        for name in os.listdir(batch.ARCHIVE_DIR):
            if not name.endswith(".json") or not name.startswith("Run"):
                continue
            path = os.path.join(batch.ARCHIVE_DIR, name)
            with open(path, "r", encoding="utf-8") as handle:
                config = json.load(handle)
            if isinstance(config.get("seed"), int):
                seeds.append(config["seed"])
        self.assertEqual(len(seeds), len(set(seeds)))

    def test_scaled_master_counts_sums_to_120(self):
        for run_id, counts in batch.ALL_RUNS.items():
            if not counts:
                continue
            scaled = batch.scaled_master_counts(counts)
            self.assertEqual(sum(scaled.values()), 120, run_id)
            self.assertEqual(set(scaled), set(counts), run_id)


if __name__ == "__main__":
    unittest.main()
