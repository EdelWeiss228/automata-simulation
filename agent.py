from __future__ import annotations

from typing import Optional
"""Модуль описывает класс Agent и его поведение в симуляции."""

from emotion_automaton import EmotionAutomaton, EmotionAxis
from collective import Collective

class Agent:
    """Класс, представляющий агента с эмоциями и отношениями."""

    def __init__(  # pylint: disable=too-many-arguments, too-many-positional-arguments
        self,
        name,
        initial_emotions=None,
        emotion_effects=None,
        emotion_coefficients=None,
        sensitivity=1,
        archetype=None,
    ):
        self.name = name
        self.automaton = EmotionAutomaton()
        if archetype:
            self.automaton.set_archetype(archetype)
        self.relations = {}
        self.sensitivity = sensitivity
        self.archetype = archetype or self.automaton.get_archetype()
        self.group: Optional["Collective"] = None  # Указатель на коллектив, устанавливается позже

        self.emotion_effects = emotion_effects or {
            "joy_sadness": {"affinity": 1, "trust": 1},
            "anger_humility": {"affinity": -2, "trust": -2, "utility": -1},
            "fear_calm": {"trust": -1, "utility": -1},
            "love_alienation": {"affinity": 2, "trust": 1},
            "disgust_acceptance": {"affinity": -1, "utility": -1},
            "shame_confidence": {"trust": 1, "affinity": -1},
            "surprise_habit": {"utility": 1},
        }

        self.emotion_coefficients = emotion_coefficients or {
            "joy_sadness": 1,
            "anger_humility": -1,
            "fear_calm": -1,
            "love_alienation": 1,
            "disgust_acceptance": -1,
            "shame_confidence": 1,
            "surprise_habit": 1,
        }

        if initial_emotions:
            for emotion_name, value in initial_emotions.items():
                self.automaton.set_emotion(emotion_name, value)

    def limit_predicate_value(self, value, min_value=-10, max_value=10):
        """Ограничивает значение предиката в заданном диапазоне."""
        return max(min(value, max_value), min_value)

    def update_relation(self, other_agent_name, utility, affinity, trust):
        """Обновляет отношение к другому агенту с учетом ограничений."""
        self.relations[other_agent_name] = {
            "utility": self.limit_predicate_value(utility),
            "affinity": self.limit_predicate_value(affinity),
            "trust": self.limit_predicate_value(trust),
            "responsiveness": self.limit_predicate_value(
                self.relations.get(other_agent_name, {}).get("responsiveness", 0)
            ),
        }

    def get_relation_vector(self, other_agent_name):
        """Возвращает вектор отношений к другому агенту."""
        return self.relations.get(
            other_agent_name,
            {"utility": 0, "affinity": 0, "trust": 0, "responsiveness": 0},
        )

    def update_responsiveness(self, target_name, delta):
        """Обновляет чувствительность к взаимодействиям с другим агентом."""
        if target_name in self.relations:
            current = self.relations[target_name].get("responsiveness", 0)
            new_responsiveness = self.limit_predicate_value(current + delta)
            self.relations[target_name]["responsiveness"] = new_responsiveness

            if new_responsiveness < 0:
                self.relations[target_name]["affinity"] = self.limit_predicate_value(
                    self.relations[target_name]["affinity"] - 1 * self.sensitivity
                )
                self.relations[target_name]["trust"] = self.limit_predicate_value(
                    self.relations[target_name]["trust"] - 1 * self.sensitivity
                )
            else:
                self.relations[target_name]["affinity"] = self.limit_predicate_value(
                    self.relations[target_name]["affinity"] + 1 * self.sensitivity
                )
                self.relations[target_name]["trust"] = self.limit_predicate_value(
                    self.relations[target_name]["trust"] + 1 * self.sensitivity
                )

    def describe_emotions(self):
        """Возвращает описания эмоциональных пар."""
        return {name: pair.describe() for name, pair in self.automaton.pairs.items()}

    def describe_relations(self):
        """Возвращает словарь отношений."""
        return dict(self.relations)

    def get_primary_emotion(self):
        """Определяет основную эмоцию по максимальному модулю значения."""
        max_name = None
        max_value = 0
        for name, pair in self.automaton.pairs.items():
            if abs(pair.value) > abs(max_value):
                max_value = pair.value
                max_name = name
        return max_name, max_value

    def react_to_relations(self):
        """Изменяет эмоции агента в зависимости от отношений."""
        for pred in self.relations.values():
            u, a, t = pred["utility"], pred["affinity"], pred["trust"]

            a = self.limit_predicate_value(a)
            t = self.limit_predicate_value(t)
            u = self.limit_predicate_value(u)

            self.automaton.adjust_emotion(EmotionAxis.JOY_SADNESS, a * self.sensitivity)
            self.automaton.adjust_emotion(EmotionAxis.LOVE_ALIENATION, a * self.sensitivity)

            self.automaton.adjust_emotion(EmotionAxis.DISGUST_ACCEPTANCE, u * self.sensitivity)

            if t < 0:
                self.automaton.adjust_emotion(
                    EmotionAxis.FEAR_CALM, -abs(t) * self.sensitivity
                )
                self.automaton.adjust_emotion(
                    EmotionAxis.ANGER_HUMILITY, -abs(t) * self.sensitivity
                )

    def _adjust_affinity_based_on_responsiveness(self, target_name, delta):
        if self.relations[target_name]["responsiveness"] < 0:
            self.relations[target_name]["affinity"] = self.limit_predicate_value(
                self.relations[target_name]["affinity"] - delta * self.sensitivity
            )
        else:
            self.relations[target_name]["affinity"] = self.limit_predicate_value(
                self.relations[target_name]["affinity"] + delta * self.sensitivity
            )

    def _adjust_trust_based_on_responsiveness(self, target_name, delta):
        if self.relations[target_name]["responsiveness"] < 0:
            self.relations[target_name]["trust"] = self.limit_predicate_value(
                self.relations[target_name]["trust"] - delta * self.sensitivity
            )
        else:
            self.relations[target_name]["trust"] = self.limit_predicate_value(
                self.relations[target_name]["trust"] + delta * self.sensitivity
            )

    def _adjust_utility_and_affinity_based_on_responsiveness(self, target_name, delta):
        if self.relations[target_name]["responsiveness"] < 0:
            self.relations[target_name]["affinity"] = self.limit_predicate_value(
                self.relations[target_name]["affinity"] - delta * self.sensitivity
            )
            self.relations[target_name]["utility"] = self.limit_predicate_value(
                self.relations[target_name]["utility"] - delta * self.sensitivity
            )
        else:
            self.relations[target_name]["affinity"] = self.limit_predicate_value(
                self.relations[target_name]["affinity"] + delta * self.sensitivity
            )
            self.relations[target_name]["utility"] = self.limit_predicate_value(
                self.relations[target_name]["utility"] + delta * self.sensitivity
            )

    def react_to_emotions(self):  # pylint: disable=too-many-branches
        """Влияет на отношения в зависимости от текущих эмоций."""
        for name, pair in self.automaton.pairs.items():
            emotion_value = pair.value

            if name == EmotionAxis.JOY_SADNESS and emotion_value > 1:
                for target_name, relation in self.relations.items():
                    self._adjust_affinity_based_on_responsiveness(target_name, 1)

            elif name == EmotionAxis.ANGER_HUMILITY and emotion_value < -1:
                for target_name, relation in self.relations.items():
                    self._adjust_trust_based_on_responsiveness(target_name, 1)

            elif name == EmotionAxis.FEAR_CALM and emotion_value < -1:
                for target_name, relation in self.relations.items():
                    self._adjust_trust_based_on_responsiveness(target_name, 1)

            elif name == EmotionAxis.LOVE_ALIENATION and emotion_value > 1:
                for target_name, relation in self.relations.items():
                    self._adjust_trust_based_on_responsiveness(target_name, 1)
                    self._adjust_affinity_based_on_responsiveness(target_name, 1)

            elif name == EmotionAxis.DISGUST_ACCEPTANCE and emotion_value < -1:
                for target_name, relation in self.relations.items():
                    self._adjust_utility_and_affinity_based_on_responsiveness(target_name, 1)

    def process_primary_emotion(self, target, pred, coeff, direction):
        """Обновляет конкретный предикат для отношения с целью с учётом эмоций и коэффициентов."""
        emotion_effect = self.emotion_coefficients.get(pred, 1)
        updated_value = (
            self.relations[target][pred]
            + coeff * direction * self.sensitivity * emotion_effect
        )
        self.relations[target][pred] = self.limit_predicate_value(updated_value)

    def influence_emotions(self):
        """Влияет на эмоции других агентов на основе основной эмоции и отношений."""
        primary_emotion_name, primary_emotion_value = self.get_primary_emotion()

        if primary_emotion_value is None or primary_emotion_value == 0:
            return

        total_intensity = sum(abs(pair.value) for pair in self.automaton.pairs.values())
        if total_intensity == 0:
            return

        dynamic_weight_primary = abs(primary_emotion_value) / total_intensity
        secondary_count = max(1, len(self.automaton.pairs) - 1)
        dynamic_weight_secondary = (1 - dynamic_weight_primary) / secondary_count

        for target_name, relation in self.relations.items():
            affinity = self.limit_predicate_value(relation["affinity"])
            trust = self.limit_predicate_value(relation["trust"])
            effect_strength = (
                affinity
                + trust
                + self.limit_predicate_value(relation["utility"])
            ) / 3

            # Check relationship classification for avoid
            if self.group is not None:
                target_agent = self.group.get_agent_by_name(target_name)
                if target_agent is not None and target_agent.classify_relationship(self.name) == "avoid":
                    continue

            try:
                target_agent = self.get_agent(target_name)
                target_agent.automaton.adjust_emotion(
                    primary_emotion_name,
                    primary_emotion_value
                    * effect_strength
                    * dynamic_weight_primary
                    * self.sensitivity,
                )

                other_emotions = {
                    name: pair.value
                    for name, pair in self.automaton.pairs.items()
                    if name != primary_emotion_name
                }

                for name, value in other_emotions.items():
                    if value != 0:
                        target_agent.automaton.adjust_emotion(
                            name,
                            value
                            * effect_strength
                            * dynamic_weight_secondary
                            * self.sensitivity,
                        )

                self.update_responsiveness(target_name, 1)
            except (ValueError, AttributeError):
                self.update_responsiveness(target_name, -1)

    def get_agent(self, name):
        """Получает объект агента по имени из группы, если агент состоит в группе."""
        group = getattr(self, "group", None)
        if group:
            agent = group.get_agent_by_name(name)
            if agent is not None:
                return agent
            raise ValueError(
                f"Agent with name '{name}' not found in the group."
            )
        raise AttributeError(
            "Agent is not part of any group or group is not set."
        )

    def classify_relationship(self, other_name):
        """Классифицирует тип отношений с другим агентом на основе предикатов."""
        relation = self.get_relation_vector(other_name)
        trust = relation["trust"]
        affinity = relation["affinity"]
        responsiveness = relation["responsiveness"]

        if responsiveness < -5:
            return "avoid"  # pylint: disable=no-else-return
        if trust >= 5 and affinity >= 5 and responsiveness >= 0:
            return "mandatory"
        if trust >= 0 or affinity >= 0 or responsiveness > -5:
            return "optional"
        return "avoid"

    def get_emotion_states(self):
        """Возвращает состояния всех эмоций в описательном виде."""
        return {name: pair.describe() for name, pair in self.automaton.pairs.items()}

    def get_archetype(self):
        """Возвращает архетип агента."""
        return self.archetype

    def decay_responsiveness_passive(self):
        """Пассивно уменьшает чувствительность к другим агентам со временем."""
        for target_name in self.relations:
            self.update_responsiveness(target_name, -1 * self.sensitivity)
