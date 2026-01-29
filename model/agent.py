from __future__ import annotations

from typing import Optional, TYPE_CHECKING
"""Модуль описывает класс Agent и его поведение в симуляции."""

if TYPE_CHECKING:
    from .collective import Collective

from model.emotion_automaton import EmotionAutomaton, EmotionAxis
from model.constants import AgentStatus
import random


class Agent:
    """Класс, представляющий агента с эмоциями и отношениями."""

    def __init__(  # pylint: disable=too-many-arguments, too-many-positional-arguments
        self,
        name,
        emotions=None,
        emotion_effects=None,
        emotion_coefficients=None,
        sensitivity: float = 1.0,
        archetype=None,
        sportiness: Optional[float] = None,
        skip_tendency: Optional[float] = None,
    ):
        self.name = name
        self.automaton = EmotionAutomaton()
        if archetype:
            self.automaton.set_archetype(archetype)
        self.relations = {}
        self.sensitivity = sensitivity
        self.archetype = self.automaton.get_archetype()
        self.group: Optional["Collective"] = None  # Указатель на коллектив, устанавливается позже

        # Новые параметры версии 3.0
        self.sportiness = sportiness if sportiness is not None else random.uniform(0, 1)
        self.skip_tendency = skip_tendency if skip_tendency is not None else random.uniform(0, 0.3)
        self.status = AgentStatus.HOME
        
        # Иерархия
        self.faculty = None
        self.stream = None
        self.group_id = None
        self.current_pair_index = -1
        self.seated_next_to = None

        self.emotion_effects = emotion_effects or self.archetype.emotion_effects
        self.emotion_coefficients = emotion_coefficients or self.archetype.emotion_coefficients
        self.emotions = emotions
        if emotions:
            for emotion_name, value in emotions.items():
                self.automaton.set_emotion(emotion_name, value)

    def set_university_info(self, faculty, stream, group_id):
        """Устанавливает иерархическую информацию об агенте."""
        self.faculty = faculty
        self.stream = stream
        self.group_id = group_id

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
        """
        Определяет основную эмоцию.
        Если несколько эмоций имеют одинаковую максимальную силу, выбирается случайная из них.
        """
        max_abs = 0
        candidates = []
        for name, pair in self.automaton.pairs.items():
            val_abs = abs(pair.value)
            if val_abs > max_abs:
                max_abs = val_abs
                candidates = [(name, pair.value)]
            elif val_abs == max_abs and val_abs > 0:
                candidates.append((name, pair.value))
        
        if not candidates:
            return None, 0
            
        import random
        return random.choice(candidates)

    def react_to_relations(self):
        """
        Изменяет эмоции агента в зависимости от его отношений ко всем остальным.
        Использует средневзвешенное влияние по всем 7 осям на основе коэффициентов архетипа.
        """
        if not self.relations:
            return

        n = len(self.relations)
        # Собираем средние значения метрик
        avg_metrics = {"affinity": 0.0, "utility": 0.0, "trust": 0.0}
        for pred in self.relations.values():
            avg_metrics["affinity"] += self.limit_predicate_value(pred["affinity"])
            avg_metrics["utility"] += self.limit_predicate_value(pred["utility"])
            avg_metrics["trust"] += self.limit_predicate_value(pred["trust"])
        
        for key in avg_metrics:
            avg_metrics[key] /= n

        # Применяем влияние на каждую ось эмоций
        # Коэффициенты берутся из архетипа (emotion_coefficients)
        coeffs = getattr(self.archetype, 'emotion_coefficients', {})
        for axis_name, coeff in coeffs.items():
            # ДЕМПФИРОВАНИЕ: умножаем на 0.1, чтобы отношения не перегружали эмоции
            effect = (avg_metrics["affinity"] + avg_metrics["trust"]) / 2.0
            self.automaton.adjust_emotion(axis_name, (effect * coeff * 0.1) * self.sensitivity)

    def apply_emotion_decay(self):
        """Метод вызывает затухание эмоций в автомате."""
        # Затухание зависит от архетипа и чувствительности
        decay_rate = getattr(self.archetype, 'emotion_decay', 0.2)
        self.automaton.apply_decay(decay_rate * self.sensitivity)

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

            elif name == EmotionAxis.OPENNESS_ALIENATION and emotion_value > 1:
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
            target_agent = self.get_agent(target_name)
            if target_agent is None:
                continue

            if target_agent.classify_relationship(self.name) == "avoid":
                continue

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
            
            # Успешное влияние повышает отзывчивость
            self.update_responsiveness(target_name, 1)

    def get_agent(self, name):
        """Получает объект агента по имени из группы."""
        if self.group:
            # Пытаемся получить через group.get_agent (Collective)
            if hasattr(self.group, 'get_agent'):
                return self.group.get_agent(name)
            # Или напрямую из словаря, если имеем доступ
            if hasattr(self.group, 'agents'):
                return self.group.agents.get(name)
        return None

    def apply_relation_decay(self):
        """
        Закон прощения: Отношения стремятся к нейтральному состоянию (0) со временем.
        Скорость зависит от архетипа и чувствительности.
        """
        decay_rate = getattr(self.archetype, 'decay_rate', 0.1)
        step = decay_rate * self.sensitivity
        
        for target_name in list(self.relations.keys()):
            for key in ['trust', 'affinity', 'utility']:
                current_val = self.relations[target_name].get(key, 0)
                if current_val > 0:
                    self.relations[target_name][key] = max(0, current_val - step)
                elif current_val < 0:
                    self.relations[target_name][key] = min(0, current_val + step)
                    
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
    def get_emotions(self):
        """Возвращает числовые значения эмоций."""
        return {axis.value: pair.value for axis, pair in self.automaton.pairs.items()}