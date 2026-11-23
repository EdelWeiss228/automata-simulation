import contextlib
import io
import unittest
from collections import Counter

from model.university_collective import UniversityCollective


def build(start_year=2024):
    with contextlib.redirect_stdout(io.StringIO()):
        return UniversityCollective(
            seed=777,
            config={
                "start_year": start_year,
                "initial_relations_mode": "EMPTY",
                "total_bac": 1500,
                "total_mag": 120,
            },
        )


def rotate(collective, times=1):
    with contextlib.redirect_stdout(io.StringIO()):
        for _ in range(times):
            collective._handle_graduation_and_enrollment()


class MasterStructureTest(unittest.TestCase):
    def test_initial_structure(self):
        c = build()
        self.assertEqual(len(c.agents), 1620)
        masters = [a for a in c.agents.values() if a.degree_type == "MASTER"]
        bachelors = [a for a in c.agents.values() if a.degree_type == "BACHELOR"]
        self.assertEqual(len(masters), 120)
        self.assertEqual(len(bachelors), 1500)

        groups = Counter(a.group_id for a in masters)
        self.assertEqual(len(groups), 12)
        self.assertEqual(set(groups.values()), {10})

        expected = {
            f"{direction}-{year}"
            for direction in c.uni_manager.MASTER_FACULTIES
            for year in (23, 24)
        }
        self.assertEqual(set(groups), expected)

        # Год набора определяет когорту, курс — отдельное свойство.
        for agent in masters:
            expected_year = 2024 if agent.group_id.endswith("-24") else 2023
            self.assertEqual(agent.enrollment_year, expected_year)
            self.assertEqual(agent.course_year, 1 if expected_year == 2024 else 2)
            self.assertTrue(c.uni_manager.get_group_schedule(agent.group_id, 0))

    def test_rotation_keeps_cohort_id_and_year_counts(self):
        c = build()
        rotate(c, 1)

        self.assertEqual(len(c.agents), 1620)
        masters = [a for a in c.agents.values() if a.degree_type == "MASTER"]
        self.assertEqual(len(masters), 120)
        groups = Counter(a.group_id for a in masters)
        self.assertEqual(len(groups), 12)
        self.assertEqual(set(groups.values()), {10})

        old_m1 = [a for a in masters if a.group_id.endswith("-24")]
        new_m1 = [a for a in masters if a.group_id.endswith("-25")]
        self.assertEqual(len(old_m1), 60)
        self.assertEqual(len(new_m1), 60)
        self.assertEqual({a.course_year for a in old_m1}, {2})
        self.assertEqual({a.course_year for a in new_m1}, {1})
        self.assertFalse(any(a.group_id.endswith("-23") for a in masters))

        # Когорта ММ-24 осталась ММ-24, а не превратилась в ММ-M2.
        self.assertTrue(any(a.group_id == "ММ-24" for a in old_m1))

    def test_three_rotations_are_consistent(self):
        c = build()
        rotate(c, 3)

        self.assertEqual(len(c.agents), 1620)
        masters = [a for a in c.agents.values() if a.degree_type == "MASTER"]
        bachelors = [a for a in c.agents.values() if a.degree_type == "BACHELOR"]
        self.assertEqual(len(masters), 120)
        self.assertEqual(len(bachelors), 1500)
        self.assertEqual(Counter(a.course_year for a in bachelors), {1: 375, 2: 375, 3: 375, 4: 375})
        self.assertEqual(Counter(a.course_year for a in masters), {1: 60, 2: 60})

        flat = [agent_id for ids in c.groups_map.values() for agent_id in ids]
        self.assertEqual(len(flat), 1620)
        self.assertEqual(len(set(flat)), 1620)
        self.assertEqual(set(flat), set(c.agents))

        for agent in c.agents.values():
            self.assertIn(agent.id, c.groups_map[agent.group_id])
            self.assertTrue(c.uni_manager.get_group_schedule(agent.group_id, 0))

        ids = [agent.id for agent in c.agents.values()]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
