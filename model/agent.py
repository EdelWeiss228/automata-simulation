"""
Модуль описывает класс Agent и его поведение в симуляции.
"""

from __future__ import annotations

import random
from typing import Optional, TYPE_CHECKING

from model.emotion_automaton import EmotionAutomaton, EmotionAxis
from model.constants import AgentStatus

if TYPE_CHECKING:
    from .collective import Collective


class Agent:
    """
    Класс, представляющий агента с эмоциями и отношениями.
    """

    def __init__(  # pylint: disable=too-many-arguments, too-many-positional-arguments
        self,
        name: str,
        id: Optional[str] = None,  # pylint: disable=redefined-builtin
        archetype=None,
        emotions: Optional[dict] = None,
        emotion_effects=None,
        emotion_coefficients=None,
        sensitivity: float = 1.0,
        sportiness: Optional[float] = None,
        skip_tendency: Optional[float] = None,
        course_year: int = 1,
        enrollment_year: int = 2024,
        degree_type: str = "BACHELOR",
    ):
        self.name = name
        self.id = id if id else name
        self.automaton = EmotionAutomaton()
        if archetype:
            self.automaton.set_archetype(archetype)
        self.relations = {}
        self.sensitivity = max(0.1, float(sensitivity))
        self.archetype = self.automaton.get_archetype()
        self.group: Optional["Collective"] = None  # Указатель на коллектив, устанавливается позже

        # Дополнительные характеристики поведения агента
        self.sportiness = sportiness if sportiness is not None else random.uniform(0, 1)
        self.skip_tendency = skip_tendency if skip_tendency is not None else random.uniform(0, 0.3)
        self.status = AgentStatus.HOME
        
        # Жизненный цикл
        self.course_year = course_year
        self.enrollment_year = enrollment_year
        self.degree_type = degree_type
        
        # Иерархия
        self.faculty = None
        self.stream = None
        self.group_id = None
        self.current_pair_index = -1
        self.seated_next_to = None
        
        # Контекст и Предметы
        if self.archetype:
            self.context_adaptability = self.archetype.context_adaptability
        else:
            self.context_adaptability = {'STUDY': 1.0, 'BREAK': 1.0, 'GYM': 1.0}

        self.emotion_effects = emotion_effects or self.archetype.emotion_effects
        self.emotion_coefficients = emotion_coefficients or self.archetype.emotion_coefficients
        self.emotions = emotions
        
        # Инициализация вектора эмоций (7 измерений) в диапазоне [-30, 30]
        if emotions:
            # Если передан словарь эмоций, используем его значения для вектора (соответствие осям)
            self.emotion_vector = [int(emotions.get(axis.value, random.randint(-30, 30))) for axis in EmotionAxis]
            for emotion_name, value in emotions.items():
                self.automaton.set_emotion(emotion_name, value)
        else:
            # Случайный вектор эмоций по умолчанию
            self.emotion_vector = [random.randint(-30, 30) for _ in range(7)]

    def set_university_info(self, faculty, stream, group_id):
        """
        Устанавливает иерархическую информацию об агенте.
        """
        self.faculty = faculty
        self.stream = stream
        self.group_id = group_id

    def limit_predicate_value(self, value: float, min_value: int = -100, max_value: int = 100) -> int:
        """
        Ограничивает значение предиката в заданном диапазоне (масштаб x10).
        """
        return max(min(int(value), max_value), min_value)

    def update_relation(self, other_agent_name: str, utility: float, affinity: float, trust: float):
        """
        Обновляет отношение к другому агенту с учетом ограничений.
        """
        self.relations[other_agent_name] = {
            "utility": self.limit_predicate_value(utility),
            "affinity": self.limit_predicate_value(affinity),
            "trust": self.limit_predicate_value(trust)
        }

    def get_relation_vector(self, other_agent_name: str) -> dict:
        """
        Возвращает вектор отношений к другому агенту.
        """
        return self.relations.get(
            other_agent_name,
            {"utility": 0, "affinity": 0, "trust": 0},
        )

    def describe_emotions(self) -> dict:
        """
        Возвращает текстовые описания эмоциональных пар.
        """
        return {name: pair.describe() for name, pair in self.automaton.pairs.items()}

    def describe_relations(self) -> dict:
        """
        Возвращает словарь текущих отношений.
        """
        return dict(self.relations)

    def get_primary_emotion(self) -> Tuple[str, str, int]:
        """
        Возвращает название, текстовое описание и интенсивность доминирующей эмоции.
        """
        max_pair = None
        max_val = -1
        for axis, pair in self.automaton.pairs.items():
            if abs(pair.value) > max_val:
                max_val = abs(pair.value)
                max_pair = (axis, pair.value)
        
        if not max_pair or max_val == 0:
            return "neutral", "Нейтрально", 0
        
        axis, val = max_pair
        label = axis.get_localized_label(val)
        return axis.value, label, val

    def react_to_relations(self):
        """
        Изменяет эмоции агента в зависимости от его отношений ко всем остальным.
        """
        if not self.relations:
            return

        n = len(self.relations)
        avg_metrics = {"affinity": 0.0, "utility": 0.0, "trust": 0.0}
        for pred in self.relations.values():
            avg_metrics["affinity"] += self.limit_predicate_value(pred["affinity"])
            avg_metrics["utility"] += self.limit_predicate_value(pred["utility"])
            avg_metrics["trust"] += self.limit_predicate_value(pred["trust"])
        
        for key in avg_metrics:
            avg_metrics[key] /= n

        coeffs = getattr(self.archetype, 'emotion_coefficients', {})
        for axis_name, coeff in coeffs.items():
            avg_sum = avg_metrics["affinity"] + avg_metrics["trust"] + avg_metrics["utility"]
            effect = (avg_sum // 3)
            delta = (effect * coeff * self.sensitivity) // 1000
            self.automaton.adjust_emotion(axis_name, delta)

    def apply_emotion_decay(self):
        """
        Вызывает постепенное затухание эмоций в автомате (целочисленный масштаб x10).
        """
        decay_rate = getattr(self.archetype, 'emotion_decay', 2)
        self.automaton.apply_decay((decay_rate * self.sensitivity) // 10)

    def _adjust_affinity(self, target_name: str, delta: float, target_emotion: Optional[list] = None):
        """
        Корректирует симпатию к целевому агенту с учётом его эмоционального состояния.
        """
        weight = 1.0
        if target_emotion is not None:
            weight = sum(abs(e) for e in target_emotion) / (7 * 30)
        adjusted = int(delta) * self.sensitivity // 10
        self.relations[target_name]["affinity"] = self.limit_predicate_value(
            self.relations[target_name]["affinity"] + int(adjusted * weight)
        )

    def _adjust_trust(self, target_name: str, delta: float, target_emotion: Optional[list] = None):
        """
        Корректирует доверие к целевому агенту с учётом его эмоционального состояния.
        """
        weight = 1.0
        if target_emotion is not None:
            weight = sum(abs(e) for e in target_emotion) / (7 * 30)
        adjusted = int(delta) * self.sensitivity // 10
        self.relations[target_name]["trust"] = self.limit_predicate_value(
            self.relations[target_name]["trust"] + int(adjusted * weight)
        )

    def _adjust_utility(self, target_name: str, delta: float, target_emotion: Optional[list] = None):
        """
        Корректирует выгоду от целевого агента с учётом его эмоционального состояния.
        """
        weight = 1.0
        if target_emotion is not None:
            weight = sum(abs(e) for e in target_emotion) / (7 * 30)
        adjusted = int(delta) * self.sensitivity // 10
        self.relations[target_name]["utility"] = self.limit_predicate_value(
            self.relations[target_name]["utility"] + int(adjusted * weight)
        )

    def _adjust_utility_and_affinity(self, target_name: str, delta: float, target_emotion: Optional[list] = None):
        """
        Устаревший комбинированный метод для обратной совместимости.
        """
        self._adjust_affinity(target_name, delta, target_emotion=target_emotion)
        self._adjust_utility(target_name, delta, target_emotion=target_emotion)

    def react_to_emotions(self):
        """
        Влияет на реляционные функции в зависимости от текущих эмоций и состояния партнёра.
        """
        for name, pair in self.automaton.pairs.items():
            val = pair.value
            if abs(val) < 1:
                continue

            if name == EmotionAxis.SADNESS_JOY:
                for target_name in self.relations:
                    target_agent = self.group.get_agent(target_name) if self.group else None
                    target_emotion = getattr(target_agent, 'emotion_vector', None)
                    self._adjust_affinity(target_name, (val * 3) // 10, target_emotion=target_emotion)

            elif name == EmotionAxis.ANGER_HUMILITY:
                for target_name in self.relations:
                    target_agent = self.group.get_agent(target_name) if self.group else None
                    target_emotion = getattr(target_agent, 'emotion_vector', None)
                    factor = 2 if val < 0 else 1
                    self._adjust_trust(target_name, (val * 3 * factor) // 10, target_emotion=target_emotion)

            elif name == EmotionAxis.FEAR_CALM:
                for target_name in self.relations:
                    target_agent = self.group.get_agent(target_name) if self.group else None
                    target_emotion = getattr(target_agent, 'emotion_vector', None)
                    self._adjust_trust(target_name, (val * 3) // 10, target_emotion=target_emotion)

            elif name == EmotionAxis.ALIENATION_OPENNESS:
                for target_name in self.relations:
                    target_agent = self.group.get_agent(target_name) if self.group else None
                    target_emotion = getattr(target_agent, 'emotion_vector', None)
                    self._adjust_trust(target_name, (val * 3) // 10, target_emotion=target_emotion)
                    self._adjust_affinity(target_name, (val * 3) // 10, target_emotion=target_emotion)

            elif name == EmotionAxis.DISGUST_ACCEPTANCE:
                for target_name in self.relations:
                    target_agent = self.group.get_agent(target_name) if self.group else None
                    target_emotion = getattr(target_agent, 'emotion_vector', None)
                    self._adjust_utility(target_name, (val * 3) // 10, target_emotion=target_emotion)
                    self._adjust_affinity(target_name, (val * 3) // 10, target_emotion=target_emotion)

    def influence_emotions(self):
        """
        Влияет на эмоции других агентов (резервный механизм на стороне Python).
        """
        primary_emotion_name, _, primary_emotion_value = self.get_primary_emotion()
        if not primary_emotion_value:
            return

        total_intensity = sum(abs(pair.value) for pair in self.automaton.pairs.values())
        if total_intensity == 0:
            return

        for target_name, relation in self.relations.items():
            target_agent = self.group.get_agent(target_name) if self.group else None
            if not target_agent or target_agent.classify_relationship(self.id) == "avoid":
                continue

            avg_rel = (relation["affinity"] + relation["trust"] + relation["utility"]) // 3
            d_weight_scaled = (abs(primary_emotion_value) * 100) // total_intensity
            
            target_agent.automaton.adjust_emotion(
                primary_emotion_name,
                (primary_emotion_value * avg_rel * d_weight_scaled * self.sensitivity) // 100000
            )

    def apply_relation_decay(self):
        """
        Закон прощения: Отношения стремятся к нулю со временем (integer x10 scale).
        """
        decay_rate = getattr(self.archetype, 'decay_rate', 1)
        step = (decay_rate * self.sensitivity) // 10
        
        for target_name in list(self.relations.keys()):
            for key in ['trust', 'affinity', 'utility']:
                current_val = self.relations[target_name].get(key, 0)
                if current_val > 0:
                    self.relations[target_name][key] = max(0, current_val - int(step * 0.5))
                elif current_val < 0:
                    self.relations[target_name][key] = min(0, current_val + step)

    def classify_relationship(self, other_name: str) -> str:
        """
        Классифицирует тип отношений к другому агенту.
        """
        relation = self.get_relation_vector(other_name)
        trust = relation["trust"]
        affinity = relation["affinity"]

        if trust >= 50 and affinity >= 40:
            return "mandatory"
        if trust >= -20 and affinity >= -20:
            return "optional"
        return "avoid"

    def get_emotions(self) -> dict:
        """
        Возвращает словарь числовых значений всех осей эмоций.
        """
        return {axis.value: pair.value for axis, pair in self.automaton.pairs.items()}