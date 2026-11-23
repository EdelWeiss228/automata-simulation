import random
import unittest
from collections import Counter

from model.agent import Agent
from model.archetypes import ArchetypeEnum
from model.constants import AgentStatus, SportType
from model.university_collective import UniversityCollective


def empty_collective():
    c = UniversityCollective(
        seed=123,
        config={
            "initial_relations_mode": "EMPTY",
            "total_bac": 0,
            "total_mag": 0,
        },
    )
    return c


def add_students(c, count, sportiness):
    for i in range(count):
        agent = Agent(
            f"Student {i}",
            id=f"G-{i}",
            archetype=list(ArchetypeEnum)[i % len(ArchetypeEnum)],
            sportiness=sportiness,
        )
        agent.degree_type = "BACHELOR"
        agent.course_year = 1
        agent.enrollment_year = 2024
        agent.group_id = "G-24-1"
        agent.status = AgentStatus.BREAK
        c.add_agent(agent)


class GymTest(unittest.TestCase):
    def test_sections_are_uniform_and_isolated(self):
        random.seed(12345)
        c = empty_collective()
        add_students(c, 300, sportiness=1.0)
        interactions = c._handle_gym_slot()

        sections = Counter(a.gym_section for a in c.agents.values())
        self.assertEqual(set(sections), set(SportType))
        for count in sections.values():
            self.assertGreater(count, 60)
            self.assertLess(count, 140)

        for from_id, to_id, status in interactions:
            if from_id == "System":
                continue
            self.assertEqual(
                c.agents[from_id].gym_section,
                c.agents[to_id].gym_section,
                msg=f"cross-section contact {from_id} -> {to_id} ({status})",
            )

    def test_sportiness_only_controls_attendance(self):
        random.seed(12345)
        c = empty_collective()
        add_students(c, 40, sportiness=0.0)
        c._handle_gym_slot()
        self.assertFalse(any(c.current_rooms.get("GYM", [])))
        self.assertTrue(all(a.status == AgentStatus.HOME for a in c.agents.values()))

    def test_three_section_names(self):
        self.assertEqual(len(list(SportType)), 3)
        self.assertEqual(
            {s.value for s in SportType},
            {"Badminton", "Football", "Basketball"},
        )


if __name__ == "__main__":
    unittest.main()
