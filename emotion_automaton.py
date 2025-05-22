from enum import Enum
from emotion_pair import EmotionPair

# Определения перечислений осей и архетипов
class EmotionAxis(str, Enum):
    JOY_SADNESS = 'joy_sadness'
    FEAR_CALM = 'fear_calm'
    ANGER_HUMILITY = 'anger_humility'
    DISGUST_ACCEPTANCE = 'disgust_acceptance'
    SURPRISE_HABIT = 'surprise_habit'
    SHAME_CONFIDENCE = 'shame_confidence'
    LOVE_ALIENATION = 'love_alienation'


class Archetype(str, Enum):
    SAGE = 'мудрец'
    REBEL = 'бунтарь'
    HARMONIZER = 'гармонист'
    WARRIOR = 'воин'
    TRICKSTER = 'трикстер'
    GUARDIAN = 'страж'
    QUIET = 'тихоня'
    TRAILBLAZER = 'путеводитель'
    MEMORY = 'память'

# Класс EmotionAutomaton моделирует эмоциональные состояния агента на основе архетипа.
# Каждый архетип задает веса для 7 эмоциональных осей.

class EmotionAutomaton:
    # Весовые коэффициенты по эмоциональным осям для каждого архетипа (пути)
    ARCHETYPE_WEIGHTS = {
        # 1. Мудрец — путь знания
        Archetype.SAGE: {
            EmotionAxis.JOY_SADNESS: 0.9,
            EmotionAxis.FEAR_CALM: 1.4,
            EmotionAxis.ANGER_HUMILITY: 0.6,
            EmotionAxis.DISGUST_ACCEPTANCE: 1.2,
            EmotionAxis.SURPRISE_HABIT: 0.8,
            EmotionAxis.SHAME_CONFIDENCE: 0.7,
            EmotionAxis.LOVE_ALIENATION: 1.0,
        },
        # 2. Бунтарь — путь разрушения
        Archetype.REBEL: {
            EmotionAxis.JOY_SADNESS: 1.2,
            EmotionAxis.FEAR_CALM: 0.6,
            EmotionAxis.ANGER_HUMILITY: 1.8,
            EmotionAxis.DISGUST_ACCEPTANCE: 1.4,
            EmotionAxis.SURPRISE_HABIT: 1.2,
            EmotionAxis.SHAME_CONFIDENCE: 0.6,
            EmotionAxis.LOVE_ALIENATION: 1.0,
        },
        # 3. Гармонист — путь гармонии
        Archetype.HARMONIZER: {
            EmotionAxis.JOY_SADNESS: 1.1,
            EmotionAxis.FEAR_CALM: 1.2,
            EmotionAxis.ANGER_HUMILITY: 0.5,
            EmotionAxis.DISGUST_ACCEPTANCE: 1.4,
            EmotionAxis.SURPRISE_HABIT: 0.9,
            EmotionAxis.SHAME_CONFIDENCE: 1.1,
            EmotionAxis.LOVE_ALIENATION: 1.5,
        },
        # 4. Воин — путь охоты
        Archetype.WARRIOR: {
            EmotionAxis.JOY_SADNESS: 1.0,
            EmotionAxis.FEAR_CALM: 0.7,
            EmotionAxis.ANGER_HUMILITY: 1.6,
            EmotionAxis.DISGUST_ACCEPTANCE: 0.8,
            EmotionAxis.SURPRISE_HABIT: 1.0,
            EmotionAxis.SHAME_CONFIDENCE: 1.3,
            EmotionAxis.LOVE_ALIENATION: 0.8,
        },
        # 5. Трикстер — путь радости
        Archetype.TRICKSTER: {
            EmotionAxis.JOY_SADNESS: 1.5,
            EmotionAxis.FEAR_CALM: 0.9,
            EmotionAxis.ANGER_HUMILITY: 0.9,
            EmotionAxis.DISGUST_ACCEPTANCE: 1.1,
            EmotionAxis.SURPRISE_HABIT: 1.8,
            EmotionAxis.SHAME_CONFIDENCE: 0.8,
            EmotionAxis.LOVE_ALIENATION: 1.2,
        },
        # 6. Страж — путь сохранения
        Archetype.GUARDIAN: {
            EmotionAxis.JOY_SADNESS: 0.9,
            EmotionAxis.FEAR_CALM: 1.0,
            EmotionAxis.ANGER_HUMILITY: 0.7,
            EmotionAxis.DISGUST_ACCEPTANCE: 1.3,
            EmotionAxis.SURPRISE_HABIT: 0.8,
            EmotionAxis.SHAME_CONFIDENCE: 1.4,
            EmotionAxis.LOVE_ALIENATION: 1.6,
        },
        # 7. Тихоня — путь небытия
        Archetype.QUIET: {
            EmotionAxis.JOY_SADNESS: 1.0,
            EmotionAxis.FEAR_CALM: 1.1,
            EmotionAxis.ANGER_HUMILITY: 0.8,
            EmotionAxis.DISGUST_ACCEPTANCE: 1.5,
            EmotionAxis.SURPRISE_HABIT: 0.7,
            EmotionAxis.SHAME_CONFIDENCE: 1.2,
            EmotionAxis.LOVE_ALIENATION: 1.3,
        },
        # 8. Путеводитель — путь вдохновения
        Archetype.TRAILBLAZER: {
            EmotionAxis.JOY_SADNESS: 1.4,
            EmotionAxis.FEAR_CALM: 0.9,
            EmotionAxis.ANGER_HUMILITY: 0.7,
            EmotionAxis.DISGUST_ACCEPTANCE: 1.2,
            EmotionAxis.SURPRISE_HABIT: 1.6,
            EmotionAxis.SHAME_CONFIDENCE: 0.9,
            EmotionAxis.LOVE_ALIENATION: 1.4,
        },
        # 9. Память — путь памяти
        Archetype.MEMORY: {
            EmotionAxis.JOY_SADNESS: 1.1,
            EmotionAxis.FEAR_CALM: 1.3,
            EmotionAxis.ANGER_HUMILITY: 0.6,
            EmotionAxis.DISGUST_ACCEPTANCE: 1.1,
            EmotionAxis.SURPRISE_HABIT: 0.7,
            EmotionAxis.SHAME_CONFIDENCE: 1.5,
            EmotionAxis.LOVE_ALIENATION: 1.2,
        },
    }

    def __init__(self, archetype: Archetype = Archetype.SAGE):
        self.archetype = archetype
        self.weights = self.ARCHETYPE_WEIGHTS.get(archetype, {})
        self.pairs = {axis: EmotionPair(axis.value) for axis in EmotionAxis}

    def adjust_emotion(self, axis: EmotionAxis, delta):
        if axis in self.pairs:
            weight = self.weights.get(axis, 1)
            self.pairs[axis].adjust(delta * weight)

    def set_emotion(self, axis: EmotionAxis, value):
        if axis in self.pairs:
            self.pairs[axis].set(value)

    def get_emotion_description(self, axis: EmotionAxis):
        if axis in self.pairs:
            return self.pairs[axis].describe()
        return "неизвестная эмоция"

    def describe_all(self):
        return {axis: pair.describe() for axis, pair in self.pairs.items()}

    def get_archetype(self):
        return self.archetype

    def get_archetype_weights(self):
        return self.weights
