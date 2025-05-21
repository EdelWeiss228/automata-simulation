from emotion_pair import EmotionPair

# Класс EmotionAutomaton моделирует эмоциональные состояния агента на основе архетипа.
# Каждый архетип задает веса для 7 эмоциональных осей.

class EmotionAutomaton:
    # Весовые коэффициенты по эмоциональным осям для каждого архетипа (пути)
    ARCHETYPE_WEIGHTS = {
        # 1. Мудрец — путь знания
        # Символика: книга, свет знаний
        # Описание: стремится к мудрости и пониманию, ценит объективность и анализ.
        # Черты: рассудительность, хладнокровие, глубокое мышление.
        'мудрец': {
            'joy_sadness': 0.9,
            'fear_calm': 1.4,
            'anger_humility': 0.6,
            'disgust_acceptance': 1.2,
            'surprise_habit': 0.8,
            'shame_confidence': 0.7,
            'love_alienation': 1.0,
        },
        # 2. Бунтарь — путь тайны
        # Символика: маска, тень
        # Описание: загадочный и непредсказуемый, склонен к разрушению устоев.
        # Черты: эмоциональная нестабильность, страсть, независимость.
        'бунтарь': {
            'joy_sadness': 1.2,
            'fear_calm': 0.6,
            'anger_humility': 1.8,
            'disgust_acceptance': 1.4,
            'surprise_habit': 1.2,
            'shame_confidence': 0.6,
            'love_alienation': 1.0,
        },
        # 3. Гармонист — путь гармонии
        # Символика: цветок, круг
        # Описание: стремится к внутреннему балансу и гармоничным отношениям.
        # Черты: миролюбие, терпимость, эмоциональная устойчивость.
        'гармонист': {
            'joy_sadness': 1.1,
            'fear_calm': 1.2,
            'anger_humility': 0.5,
            'disgust_acceptance': 1.4,
            'surprise_habit': 0.9,
            'shame_confidence': 1.1,
            'love_alienation': 1.5,
        },
        # 4. Воин — путь охоты
        # Символика: меч, щит
        # Описание: решительный и сильный, готов к борьбе и защите.
        # Черты: смелость, решительность, вспыльчивость.
        'воин': {
            'joy_sadness': 1.0,
            'fear_calm': 0.7,
            'anger_humility': 1.6,
            'disgust_acceptance': 0.8,
            'surprise_habit': 1.0,
            'shame_confidence': 1.3,
            'love_alienation': 0.8,
        },
        # 5. Трикстер — путь радости
        # Символика: шутовской колпак, смех
        # Описание: веселый и непредсказуемый, любит удивлять и радовать.
        # Черты: игривость, оптимизм, креативность.
        'трикстер': {
            'joy_sadness': 1.5,
            'fear_calm': 0.9,
            'anger_humility': 0.9,
            'disgust_acceptance': 1.1,
            'surprise_habit': 1.8,
            'shame_confidence': 0.8,
            'love_alienation': 1.2,
        },
        # 6. Страж — путь сохранения
        # Символика: замок, крепость
        # Описание: заботится о безопасности и стабильности, защищает близких.
        # Черты: надежность, осторожность, ответственность.
        'страж': {
            'joy_sadness': 0.9,
            'fear_calm': 1.0,
            'anger_humility': 0.7,
            'disgust_acceptance': 1.3,
            'surprise_habit': 0.8,
            'shame_confidence': 1.4,
            'love_alienation': 1.6,
        },
        # 7. Тайна — путь небытия
        # Символика: тьма, закрытая дверь
        # Описание: склонен к интроспекции, глубоким размышлениям и скрытности.
        # Черты: загадочность, глубина, эмоциональная сложность.
        'тайна': {
            'joy_sadness': 1.0,
            'fear_calm': 1.1,
            'anger_humility': 0.8,
            'disgust_acceptance': 1.5,
            'surprise_habit': 0.7,
            'shame_confidence': 1.2,
            'love_alienation': 1.3,
        },
        # 8. Путеводитель — путь вдохновения
        # Символика: звезда, факел
        # Описание: творческий и эмоционально яркий, вдохновляет других.
        # Черты: энтузиазм, креативность, страсть.
        'путеводитель': {
            'joy_sadness': 1.4,
            'fear_calm': 0.9,
            'anger_humility': 0.7,
            'disgust_acceptance': 1.2,
            'surprise_habit': 1.6,
            'shame_confidence': 0.9,
            'love_alienation': 1.4,
        },
        # 9. Память — путь памяти
        # Символика: часы, древние свитки
        # Описание: ориентирован на сохранение истории и опыта, ценит прошлое.
        # Черты: ностальгия, мудрость, уважение к традициям.
        'память': {
            'joy_sadness': 1.1,
            'fear_calm': 1.3,
            'anger_humility': 0.6,
            'disgust_acceptance': 1.1,
            'surprise_habit': 0.7,
            'shame_confidence': 1.5,
            'love_alienation': 1.2,
        },
    }

    def __init__(self, archetype='мудрец'):
        self.archetype = archetype
        self.pairs = {
            'joy_sadness': EmotionPair('joy_sadness'),
            'fear_calm': EmotionPair('fear_calm'),
            'anger_humility': EmotionPair('anger_humility'),
            'disgust_acceptance': EmotionPair('disgust_acceptance'),
            'surprise_habit': EmotionPair('surprise_habit'),
            'shame_confidence': EmotionPair('shame_confidence'),
            'love_alienation': EmotionPair('love_alienation'),
        }

    def adjust_emotion(self, name, delta):
        if name in self.pairs:
            weight = self.ARCHETYPE_WEIGHTS.get(self.archetype, {}).get(name, 1)
            self.pairs[name].adjust(delta * weight)

    def set_emotion(self, name, value):
        if name in self.pairs:
            self.pairs[name].set(value)

    def get_emotion_description(self, name):
        if name in self.pairs:
            return self.pairs[name].describe()
        return "неизвестная эмоция"

    def describe_all(self):
        return {name: pair.describe() for name, pair in self.pairs.items()}
