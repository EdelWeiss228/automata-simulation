import unittest

from core.interaction_strategy import (
    InteractionStrategy,
    Outcome,
    normalize_outcome,
    sigma_rate_factor,
)
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


class SigmaRateFactorTest(unittest.TestCase):
    def test_positive_and_negative_half_axes(self):
        self.assertGreater(sigma_rate_factor(10, Outcome.SUCCESS), 1.0)
        self.assertLess(sigma_rate_factor(10, Outcome.FAILURE), 1.0)
        self.assertLess(sigma_rate_factor(-10, Outcome.SUCCESS), 1.0)
        self.assertGreater(sigma_rate_factor(-10, Outcome.FAILURE), 1.0)

    def test_refusal_does_not_use_half_axis_factor(self):
        self.assertEqual(sigma_rate_factor(10, Outcome.REFUSAL), 1.0)
        self.assertEqual(sigma_rate_factor(-10, Outcome.REFUSAL), 1.0)


class SigmaModelTest(unittest.TestCase):
    def test_success_updates_both_sides(self):
        a, b = make_pair()
        InteractionStrategy.process_interaction_result(a, b, Outcome.SUCCESS)
        # Нейтральное отношение попадает на положительную полуось:
        # успех ускоряется множителем 1.5.
        self.assertEqual(a.relations["B"], {"utility": 45, "affinity": 45, "trust": 30})
        self.assertEqual(b.relations["A"], {"utility": 45, "affinity": 45, "trust": 30})

    def test_failure_updates_both_sides_but_weaker_than_success(self):
        a_s, b_s = make_pair()
        InteractionStrategy.process_interaction_result(a_s, b_s, Outcome.SUCCESS)

        a, b = make_pair()
        InteractionStrategy.process_interaction_result(a, b, Outcome.FAILURE)
        for rel in (a.relations["B"], b.relations["A"]):
            # Неудача — это тоже состоявшийся контакт: U/T/A растут,
            # но на положительной полуоси сигма -1 замедляет рост.
            # Отрицательным остаётся только отказ.
            self.assertGreater(rel["affinity"], 0)
            self.assertGreater(rel["utility"], 0)
            self.assertGreater(rel["trust"], 0)
            self.assertLess(rel["affinity"], a_s.relations["B"]["affinity"])
            self.assertLess(rel["trust"], a_s.relations["B"]["trust"])

    def test_positive_relation_success_beats_failure(self):
        a_s, b_s = make_pair()
        a_s.relations["B"] = {"utility": 50, "affinity": 50, "trust": 50}
        b_s.relations["A"] = {"utility": 50, "affinity": 50, "trust": 50}
        InteractionStrategy.process_interaction_result(a_s, b_s, Outcome.SUCCESS)

        a_f, b_f = make_pair()
        a_f.relations["B"] = {"utility": 50, "affinity": 50, "trust": 50}
        b_f.relations["A"] = {"utility": 50, "affinity": 50, "trust": 50}
        InteractionStrategy.process_interaction_result(a_f, b_f, Outcome.FAILURE)

        # На положительной полуоси успех растёт быстрее неудачи,
        # но оба исхода повышают отношение.
        self.assertGreater(
            a_s.relations["B"]["affinity"], a_f.relations["B"]["affinity"])
        self.assertGreater(a_s.relations["B"]["affinity"], 50)
        self.assertGreater(a_f.relations["B"]["affinity"], 50)

    def test_negative_relation_failure_moves_faster_toward_zero(self):
        a_s, b_s = make_pair()
        a_s.relations["B"] = {"utility": -50, "affinity": -50, "trust": -50}
        b_s.relations["A"] = {"utility": -50, "affinity": -50, "trust": -50}
        InteractionStrategy.process_interaction_result(a_s, b_s, Outcome.SUCCESS)

        a_f, b_f = make_pair()
        a_f.relations["B"] = {"utility": -50, "affinity": -50, "trust": -50}
        b_f.relations["A"] = {"utility": -50, "affinity": -50, "trust": -50}
        InteractionStrategy.process_interaction_result(a_f, b_f, Outcome.FAILURE)

        # На отрицательной полуоси сигма -1 ускоряет рост, а сигма +1
        # замедляет; оба исхода двигают значение к нулю.
        self.assertGreater(
            a_f.relations["B"]["affinity"], a_s.relations["B"]["affinity"])
        self.assertGreater(a_s.relations["B"]["affinity"], -50)
        self.assertGreater(a_f.relations["B"]["affinity"], -50)

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


class EmotionalReactionTest(unittest.TestCase):
    def test_success_pulls_emotions_toward_partner(self):
        a, b = make_pair()
        a.emotion_vector = [-20] * 7
        b.emotion_vector = [20] * 7
        InteractionStrategy.process_interaction_result(a, b, Outcome.SUCCESS)
        # Успешный контакт сближает эмоциональные профили.
        self.assertGreater(a.emotion_vector[0], -20)
        self.assertLess(b.emotion_vector[0], 20)

    def test_sigma_speeds_or_slows_convergence_by_emotion_axis(self):
        a_s, b_s = make_pair()
        a_s.emotion_vector = [-20] * 7
        b_s.emotion_vector = [20] * 7
        InteractionStrategy.process_interaction_result(a_s, b_s, Outcome.SUCCESS)

        a_f, b_f = make_pair()
        a_f.emotion_vector = [-20] * 7
        b_f.emotion_vector = [20] * 7
        InteractionStrategy.process_interaction_result(a_f, b_f, Outcome.FAILURE)

        # a на отрицательной полуоси: неудача ускоряет сближение,
        # успех замедляет.
        self.assertGreater(a_f.emotion_vector[0], a_s.emotion_vector[0])
        # b на положительной полуоси: успех ускоряет сближение,
        # неудача замедляет.
        self.assertLess(b_s.emotion_vector[0], b_f.emotion_vector[0])

    def test_refusal_pushes_emotions_apart(self):
        a, b = make_pair()
        a.emotion_vector = [-20] * 7
        b.emotion_vector = [20] * 7
        InteractionStrategy.process_interaction_result(a, b, Outcome.REFUSAL)
        # Отказ — единственный исход, который разводит профили.
        self.assertLess(a.emotion_vector[0], -20)
        self.assertGreater(b.emotion_vector[0], 20)


if __name__ == "__main__":
    unittest.main()
