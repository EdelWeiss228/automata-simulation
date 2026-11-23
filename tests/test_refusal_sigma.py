import unittest

from core.interaction_strategy import InteractionStrategy, Outcome, normalize_outcome
from model.agent import Agent
from model.archetypes import ArchetypeEnum


def make_pair():
    a = Agent("A", id="A", archetype=ArchetypeEnum.HARMONY, sensitivity=1.0)
    b = Agent("B", id="B", archetype=ArchetypeEnum.HUNT, sensitivity=1.0)
    a.emotion_vector = [0] * 7
    b.emotion_vector = [0] * 7
    return a, b


class OutcomeNormalizationTest(unittest.TestCase):
    def test_strings_bools_and_numbers(self):
        self.assertEqual(normalize_outcome("success"), Outcome.SUCCESS)
        self.assertEqual(normalize_outcome("fail"), Outcome.FAILURE)
        self.assertEqual(normalize_outcome("failure"), Outcome.FAILURE)
        self.assertEqual(normalize_outcome("refusal"), Outcome.REFUSAL)
        self.assertEqual(normalize_outcome(True), Outcome.SUCCESS)
        self.assertEqual(normalize_outcome(False), Outcome.FAILURE)
        self.assertEqual(normalize_outcome(1), Outcome.SUCCESS)
        self.assertEqual(normalize_outcome(-1), Outcome.FAILURE)
        self.assertEqual(normalize_outcome(0), Outcome.REFUSAL)


class SigmaModelTest(unittest.TestCase):
    def test_success_updates_both_sides(self):
        a, b = make_pair()
        InteractionStrategy.process_interaction_result(a, b, Outcome.SUCCESS)
        self.assertEqual(a.relations["B"], {"utility": 30, "affinity": 30, "trust": 20})
        self.assertEqual(b.relations["A"], {"utility": 30, "affinity": 30, "trust": 20})

    def test_failure_updates_both_sides_and_trust_is_stronger(self):
        a, b = make_pair()
        InteractionStrategy.process_interaction_result(a, b, Outcome.FAILURE)
        for rel in (a.relations["B"], b.relations["A"]):
            self.assertLess(rel["affinity"], 0)
            self.assertLess(rel["utility"], 0)
            self.assertLess(rel["trust"], rel["affinity"])

    def test_partner_emotion_scales_success(self):
        a_pos, b_pos = make_pair()
        b_pos.emotion_vector = [20, 0, 0, 0, 0, 0, 0]
        InteractionStrategy.process_interaction_result(a_pos, b_pos, Outcome.SUCCESS)

        a_neg, b_neg = make_pair()
        b_neg.emotion_vector = [-20, 0, 0, 0, 0, 0, 0]
        InteractionStrategy.process_interaction_result(a_neg, b_neg, Outcome.SUCCESS)

        self.assertGreater(a_pos.relations["B"]["affinity"], a_neg.relations["B"]["affinity"])

    def test_refusal_hurts_all_three_axes_of_both_agents(self):
        a, b = make_pair()
        InteractionStrategy.process_refusal(a, b, context="STUDY")
        for rel in (a.relations["B"], b.relations["A"]):
            self.assertLess(rel["utility"], 0)
            self.assertLess(rel["affinity"], 0)
            self.assertLess(rel["trust"], 0)

    def test_refusal_chance_is_target_based(self):
        a, b = make_pair()
        neutral = InteractionStrategy.calculate_refusal_chance(b, a)

        # Инициатор плохо относится к цели — это не должно менять решение цели.
        a.relations["B"] = {"utility": -100, "affinity": -100, "trust": -100}
        self.assertAlmostEqual(
            neutral, InteractionStrategy.calculate_refusal_chance(b, a)
        )

        # А плохое отношение цели к инициатору — должно.
        b.relations["A"] = {"utility": -100, "affinity": -100, "trust": -100}
        self.assertGreater(InteractionStrategy.calculate_refusal_chance(b, a), neutral)

        b.relations["A"] = {"utility": 100, "affinity": 100, "trust": 100}
        self.assertLess(InteractionStrategy.calculate_refusal_chance(b, a), neutral)

    def test_refusal_chance_uses_context(self):
        a, b = make_pair()
        b.context_adaptability = {"STUDY": 2.0, "BREAK": 1.0, "GYM": 0.5}
        study = InteractionStrategy.calculate_refusal_chance(b, a, context="STUDY")
        gym = InteractionStrategy.calculate_refusal_chance(b, a, context="GYM")
        self.assertLess(study, gym)


if __name__ == "__main__":
    unittest.main()
