import datetime
import random
import unittest

from model.agent import Agent
from model.archetypes import ArchetypeEnum
from model.university_collective import UniversityCollective


def build(count=5):
    c = UniversityCollective(
        seed=42,
        config={
            "initial_relations_mode": "EMPTY",
            "total_bac": 0,
            "total_mag": 0,
        },
    )
    for i in range(count):
        agent = Agent(
            f"Agent {i}",
            id=f"R-{i}",
            archetype=list(ArchetypeEnum)[i % len(ArchetypeEnum)],
        )
        agent.degree_type = "BACHELOR"
        agent.course_year = 1
        agent.enrollment_year = 2024
        agent.group_id = "R-24-1"
        c.add_agent(agent)
    return c


class EmotionViewTest(unittest.TestCase):
    def test_emotion_vector_is_a_view_over_automaton(self):
        agent = Agent("A", id="A", archetype=ArchetypeEnum.HARMONY)
        agent.emotion_vector = [1, 2, 3, 4, 5, 6, 7]
        self.assertEqual(
            agent.emotion_vector,
            [pair.value for pair in agent.automaton.pairs.values()],
        )
        agent.emotion_vector = [99] * 7
        self.assertEqual(agent.emotion_vector, [30] * 7)

    def test_reinitialize_emotions_reaches_cpp(self):
        c = build()
        c._sync_to_cpp()
        c._reinitialize_emotions()
        engine_values = list(c.cpp_engine.state.emotions)
        python_values = [value for a in c.agents.values() for value in a.emotion_vector]
        self.assertEqual(engine_values, python_values)

    def test_sunday_shift_is_per_agent_but_equal_on_all_axes(self):
        random.seed(1)
        c = build()
        for agent in c.agents.values():
            agent.emotion_vector = [0] * 7
        c.current_date = datetime.date(2025, 1, 5)  # Sunday
        c._handle_sunday()

        for agent in c.agents.values():
            # Внутри одного вектора все семь осей сдвинуты одинаково.
            self.assertEqual(len(set(agent.emotion_vector)), 1)

        # Но разные агенты получают разные случайные сдвиги.
        shifts = {agent.emotion_vector[0] for agent in c.agents.values()}
        self.assertGreater(len(shifts), 1)
        self.assertEqual(c.current_date, datetime.date(2025, 1, 6))


if __name__ == "__main__":
    unittest.main()
