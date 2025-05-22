from typing import Union
from emotion_pair import EmotionPair
from archetypes import Archetype, ArchetypeEnum, ARCHETYPE_WEIGHTS
from enum import Enum

class EmotionAxis(str, Enum):
    JOY_SADNESS = 'joy_sadness'
    FEAR_CALM = 'fear_calm'
    ANGER_HUMILITY = 'anger_humility'
    DISGUST_ACCEPTANCE = 'disgust_acceptance'
    SURPRISE_HABIT = 'surprise_habit'
    SHAME_CONFIDENCE = 'shame_confidence'
    LOVE_ALIENATION = 'love_alienation'

class EmotionAutomaton:
    """
    Класс, моделирующий эмоциональные состояния агента на основе выбранного архетипа.
    Архетип задает веса для 7 эмоциональных осей, влияющие на восприятие изменений эмоций.
    """

    def __init__(self, archetype: Union[Archetype, ArchetypeEnum] = ArchetypeEnum.ERUDITION):
        # Если передан элемент Enum, получить объект Archetype из словаря
        if isinstance(archetype, ArchetypeEnum):
            archetype_obj = ARCHETYPE_WEIGHTS[archetype]
        else:
            archetype_obj = archetype
        
        self.archetype = archetype_obj
        self.weights = archetype_obj.weights
        self.pairs = {axis: EmotionPair(axis.value) for axis in EmotionAxis}

    def adjust_emotion(self, axis: EmotionAxis, delta: float):
        """Корректирует эмоцию по оси с учетом веса архетипа."""
        if axis in self.pairs:
            weight = self.weights.get(axis, 1)
            self.pairs[axis].adjust(delta * weight)

    def set_emotion(self, axis: EmotionAxis, value: float):
        """Устанавливает значение эмоции по оси."""
        if axis in self.pairs:
            self.pairs[axis].set(value)

    def get_emotion_description(self, axis: EmotionAxis) -> str:
        """Возвращает текстовое описание эмоции по оси."""
        if axis in self.pairs:
            return self.pairs[axis].describe()
        return "неизвестная эмоция"

    def describe_all(self) -> dict:
        """Возвращает словарь с описаниями всех эмоций по осям."""
        return {axis: pair.describe() for axis, pair in self.pairs.items()}

    def get_archetype(self) -> Archetype:
        """Возвращает текущий архетип автомата."""
        return self.archetype

    def get_archetype_weights(self) -> dict:
        """Возвращает веса эмоций, соответствующие текущему архетипу."""
        return self.weights

    def set_archetype(self, archetype: Union[Archetype, ArchetypeEnum]):
        """
        Устанавливает новый архетип,
        обновляет веса эмоций и пересчитывает текущие значения эмоций с учетом новых весов.
        """
        if isinstance(archetype, ArchetypeEnum):
            archetype_obj = ARCHETYPE_WEIGHTS[archetype]
        else:
            archetype_obj = archetype

        self.archetype = archetype_obj
        self.weights = archetype_obj.weights
        for axis, pair in self.pairs.items():
            original_value = pair.value
            weight = self.weights.get(axis, 1)
            # Пересчитываем значение эмоции с учетом нового веса
            pair.set(original_value * weight)