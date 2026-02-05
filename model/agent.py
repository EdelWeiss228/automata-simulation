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
        """
        Обновляет отзывчивость. В v4.9 добавлена механика ускоренного выхода из отрицательных значений.
        """
        if target_name in self.relations:
            current = self.relations[target_name].get("responsiveness", 0)
            
            # Механика «Выхода из игнора»: если R < 0, положительная дельта усиливается
            if current < 0 and delta > 0:
                final_delta = delta * 2.5 # Ускоренный рост до 0
            else:
                final_delta = delta
                
            new_responsiveness = self.limit_predicate_value(current + final_delta * self.sensitivity)
            self.relations[target_name]["responsiveness"] = new_responsiveness

    def describe_emotions(self):
        """Возвращает описания эмоциональных пар."""
        return {name: pair.describe() for name, pair in self.automaton.pairs.items()}

    def describe_relations(self):
        """Возвращает словарь отношений."""
        return dict(self.relations)

    def get_primary_emotion(self):
        """
        Определяет основную эмоцию.
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
            
        return random.choice(candidates)

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
            effect = (avg_metrics["affinity"] + avg_metrics["trust"] + avg_metrics["utility"]) / 3.0
            self.automaton.adjust_emotion(axis_name, (effect * coeff * 0.05) * self.sensitivity)

    def apply_emotion_decay(self):
        """Метод вызывает затухание эмоций в автомате."""
        decay_rate = getattr(self.archetype, 'emotion_decay', 0.2)
        self.automaton.apply_decay(decay_rate * self.sensitivity)

    def _adjust_affinity_based_on_responsiveness(self, target_name, delta):
        # В v4.9 влияние всегда пропорционально направлению
        self.relations[target_name]["affinity"] = self.limit_predicate_value(
            self.relations[target_name]["affinity"] + delta * self.sensitivity
        )

    def _adjust_trust_based_on_responsiveness(self, target_name, delta):
        self.relations[target_name]["trust"] = self.limit_predicate_value(
            self.relations[target_name]["trust"] + delta * self.sensitivity
        )

    def _adjust_utility_and_affinity_based_on_responsiveness(self, target_name, delta):
        self.relations[target_name]["affinity"] = self.limit_predicate_value(
            self.relations[target_name]["affinity"] + delta * self.sensitivity
        )
        self.relations[target_name]["utility"] = self.limit_predicate_value(
            self.relations[target_name]["utility"] + delta * self.sensitivity
        )

    def react_to_emotions(self):
        """
        Влияет на отношения в зависимости от текущих эмоций.
        """
        for name, pair in self.automaton.pairs.items():
            val = pair.value
            if abs(val) < 0.1: continue
            
            k = 0.3 # Мягкий коэффициент для пассивного влияния
            
            if name == EmotionAxis.JOY_SADNESS:
                for target_name in self.relations:
                    self._adjust_affinity_based_on_responsiveness(target_name, val * k)

            elif name == EmotionAxis.ANGER_HUMILITY:
                for target_name in self.relations:
                    # Гнев (val < 0) сильнее бьет по Trust
                    factor = 2.0 if val < 0 else 1.0
                    self._adjust_trust_based_on_responsiveness(target_name, val * k * factor)

            elif name == EmotionAxis.FEAR_CALM:
                for target_name in self.relations:
                    self._adjust_trust_based_on_responsiveness(target_name, val * k)

            elif name == EmotionAxis.OPENNESS_ALIENATION:
                for target_name in self.relations:
                    self._adjust_trust_based_on_responsiveness(target_name, val * k)
                    self._adjust_affinity_based_on_responsiveness(target_name, val * k)

            elif name == EmotionAxis.DISGUST_ACCEPTANCE:
                for target_name in self.relations:
                    self._adjust_utility_and_affinity_based_on_responsiveness(target_name, val * k)

    def influence_emotions(self):
        """Влияет на эмоции других агентов (Python-запасной вариант)."""
        primary_emotion_name, primary_emotion_value = self.get_primary_emotion()
        if not primary_emotion_value: return

        total_intensity = sum(abs(pair.value) for pair in self.automaton.pairs.values())
        if total_intensity == 0: return

        dynamic_weight_primary = abs(primary_emotion_value) / total_intensity
        
        for target_name, relation in self.relations.items():
            target_agent = self.get_agent(target_name)
            if not target_agent or target_agent.classify_relationship(self.name) == "avoid":
                continue

            effect_strength = (relation["affinity"] + relation["trust"] + relation["utility"]) / 30.0 # Нормализация 0..1
            
            # Заражение основной эмоцией
            target_agent.automaton.adjust_emotion(
                primary_emotion_name,
                primary_emotion_value * effect_strength * dynamic_weight_primary * self.sensitivity
            )
            
            # Успешное влияние повышает отзывчивость
            self.update_responsiveness(target_name, 0.5)

    def apply_relation_decay(self):
        """
        Закон прощения: Отношения и Отзывчивость стремятся к 0.
        """
        decay_rate = getattr(self.archetype, 'decay_rate', 0.1)
        step = decay_rate * self.sensitivity
        
        for target_name in list(self.relations.keys()):
            # Decay for A, T, U
            for key in ['trust', 'affinity', 'utility']:
                current_val = self.relations[target_name].get(key, 0)
                if current_val > 0:
                    self.relations[target_name][key] = max(0, current_val - step * 0.5)
                elif current_val < 0:
                    self.relations[target_name][key] = min(0, current_val + step) # Негатив прощается быстрее
            
            # ПАССИВНОЕ ОСТЫВАНИЕ (Responsiveness)
            # Если контактов нет, R падает к 0
            r_val = self.relations[target_name].get('responsiveness', 0)
            if r_val > 0:
                self.relations[target_name]['responsiveness'] = max(0, r_val - step * 1.5)
            elif r_val < 0:
                # Из "недоброго духа" уходить чуть легче даже пассивно
                self.relations[target_name]['responsiveness'] = min(0, r_val + step * 1.0)
                    
    def classify_relationship(self, other_name):
        """Классифицирует тип отношений."""
        relation = self.get_relation_vector(other_name)
        trust = relation["trust"]
        affinity = relation["affinity"]
        responsiveness = relation["responsiveness"]

        # Если R слишком низкое - избегаем
        if responsiveness < -6.0:
            return "avoid"
        
        # Softmax будет в InteractionStrategy, тут — жесткие пороги для категорий
        if trust >= 5.0 and affinity >= 4.0 and responsiveness >= 0:
            return "mandatory"
        if trust >= -2.0 and affinity >= -2.0 and responsiveness > -5.0:
            return "optional"
        return "avoid"

    def get_emotions(self):
        """Возвращает числовые значения эмоций."""
        return {axis.value: pair.value for axis, pair in self.automaton.pairs.items()}