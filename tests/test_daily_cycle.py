import contextlib
import datetime
import io
import unittest

from model.agent import Agent
from model.archetypes import ArchetypeEnum
from model.university_collective import UniversityCollective


def build(count=5):
    with contextlib.redirect_stdout(io.StringIO()):
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
            archetype=ArchetypeEnum.HARMONY,
            sensitivity=1.0,
        )
        agent.degree_type = "BACHELOR"
        agent.course_year = 1
        agent.enrollment_year = 2024
        agent.group_id = "R-24-1"
        agent.skip_tendency = 1.0
        c.add_agent(agent)
    # 2024-09-01 — воскресенье; для проверки полного учебного дня нужен
    # понедельник, иначе perform_full_day_cycle обработает только Sunday.
    c.current_date = datetime.date(2024, 9, 2)
    return c


class DailyCycleTest(unittest.TestCase):
    def test_emotion_decay_runs_once_per_day(self):
        c = build()
        c._sync_to_cpp()
        for agent in c.agents.values():
            agent.emotion_vector = [30] * 7

        c.perform_full_day_cycle()

        # d_E = 0.2 в x10-шкале -> 2 единицы за такт-день, а не за слот.
        for agent in c.agents.values():
            self.assertEqual(agent.emotion_vector, [28] * 7)

    def test_relation_decay_is_applied_in_university_mode(self):
        c = build()
        c._sync_to_cpp()
        actor = c.get_agent("R-0")
        actor.relations["R-1"]["trust"] = 100
        actor.relations["R-1"]["affinity"] = 100

        c.perform_full_day_cycle()

        # Положительные связи ослабевают с весом 0.5 * d_i.
        self.assertLess(actor.relations["R-1"]["trust"], 100)
        self.assertLess(actor.relations["R-1"]["affinity"], 100)


if __name__ == "__main__":
    unittest.main()
