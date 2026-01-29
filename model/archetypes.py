from enum import Enum

# archetypes.py

class ArchetypeEnum(Enum):
    ERUDITION = 'Erudition'
    ENIGMATA = 'Enigmata'
    HARMONY = 'Harmony'
    HUNT = 'Hunt'
    ELATION = 'Elation'
    PRESERVATION = 'Preservation'
    NIHILITY = 'Nihility'
    TRAILBLAZE = 'Trailblaze'
    REMEMBRANCE = 'Remembrance'


class Archetype:
    def __init__(self, name, weights, description, refusal_chance=0.3, decay_rate=0.1, temperature=1.0, emotion_effects=None, emotion_coefficients=None, scoring_config=None):
        self.name = name
        self.weights = weights
        self.description = description
        self.refusal_chance = refusal_chance
        self.decay_rate = decay_rate
        self.temperature = temperature
        self.scoring_config = scoring_config or {
            "affinity": "linear",
            "utility": "linear",
            "trust": "linear",
            "responsiveness": "linear"
        }
        # Форма функций обновления (раздел 6 и 4 Промта)
        self.emotion_effects = emotion_effects or {
            "joy_sadness": {"affinity": 1, "trust": 1},
            "anger_humility": {"affinity": -2, "trust": -2, "utility": -1},
            "fear_calm": {"trust": -1, "utility": -1},
            "openness_alienation": {"affinity": 2, "trust": 1},
            "disgust_acceptance": {"affinity": -1, "utility": -1},
            "shame_confidence": {"trust": 1, "affinity": -1},
            "surprise_habit": {"utility": 1},
        }
        self.emotion_coefficients = emotion_coefficients or {
            "joy_sadness": 1,
            "anger_humility": -1,
            "fear_calm": -1,
            "openness_alienation": 1,
            "disgust_acceptance": -1,
            "shame_confidence": 1,
            "surprise_habit": 1,
        }


ARCHETYPE_WEIGHTS = {
    ArchetypeEnum.ERUDITION: Archetype(
        name='Erudition',
        description='Эрудиция (Ноус) — хладнокровный расчет, почтение к логике и знанию. Избегает эмоциональных крайностей, анализирует структуру мира.',
        weights={
            'joy_sadness': 0.8,
            'fear_calm': 1.2,
            'anger_humility': 0.5,
            'disgust_acceptance': 1.0,
            'surprise_habit': 1.5,
            'shame_confidence': 0.7,
            'openness_alienation': 0.9
        },
        refusal_chance=0.2,
        decay_rate=0.08,
        temperature=0.1,
        scoring_config={
            "affinity": "linear",
            "utility": "log",        # Рациональная уценка сверхвыгоды
            "trust": "linear",
            "responsiveness": "linear"
        }
    ),
    ArchetypeEnum.ENIGMATA: Archetype(
        name='Enigmata',
        description='Энигмата (Мифус) — адепт неопределенности. Отрицает очевидное, окутывает истину туманом секретов, склонен к манипуляции смыслами.',
        weights={
            'joy_sadness': 1.0,
            'fear_calm': 0.8,
            'anger_humility': 1.2,
            'disgust_acceptance': 1.5,
            'surprise_habit': 1.8,
            'shame_confidence': 0.6,
            'openness_alienation': 1.0
        },
        refusal_chance=0.4,
        decay_rate=0.2,
        temperature=1.5,
        scoring_config={
            "affinity": "linear",
            "utility": "linear",
            "trust": "periodic",    # Вечные сомнения и тайны
            "responsiveness": "periodic" 
        }
    ),
    ArchetypeEnum.HARMONY: Archetype(
        name='Harmony',
        description='Гармония (Шипе) — единство и семейные узы. Стремится к абсолютному сотрудничеству, вплоть до растворения индивидуальности в коллективе.',
        weights={
            'joy_sadness': 1.5,
            'fear_calm': 1.0,
            'anger_humility': 0.2,
            'disgust_acceptance': 1.0,
            'surprise_habit': 0.7,
            'shame_confidence': 1.2,
            'openness_alienation': 2.0
        },
        refusal_chance=0.05,
        decay_rate=0.04,
        temperature=0.3,
        scoring_config={
            "affinity": "sigmoid",   # Тяга к близости
            "utility": "linear",
            "trust": "exp",         # Доверие критично для единства
            "responsiveness": "linear"
        }
    ),
    ArchetypeEnum.HUNT: Archetype(
        name='Hunt',
        description='Охота (Лань) — твердая решимость и месть. Фокусируется на одной цели, беспощаден к врагам, ценит справедливость через действие.',
        weights={
            'joy_sadness': 0.8,
            'fear_calm': 0.3,
            'anger_humility': 2.0,
            'disgust_acceptance': 0.6,
            'surprise_habit': 0.9,
            'shame_confidence': 1.5,
            'openness_alienation': 0.7
        },
        refusal_chance=0.2,
        decay_rate=0.12,
        temperature=0.1,
        scoring_config={
            "affinity": "linear",
            "utility": "linear",
            "trust": "sigmoid",     # Доверие узко направлено
            "responsiveness": "exp" # Острая реакция на контакт
        }
    ),
    ArchetypeEnum.ELATION: Archetype(
        name='Elation',
        description='Радость (Аха) — вселенная это шутка. Ищет веселье в хаосе, легко меняет привязанности, обожает неожиданные повороты сюжета.',
        weights={
            'joy_sadness': 2.0,
            'fear_calm': 0.8,
            'anger_humility': 0.9,
            'disgust_acceptance': 1.1,
            'surprise_habit': 2.0,
            'shame_confidence': 0.5,
            'openness_alienation': 1.2
        },
        refusal_chance=0.5,
        decay_rate=0.25,
        temperature=3.0,
        scoring_config={
            "affinity": "periodic",  # Переменчивость
            "utility": "linear",
            "trust": "linear",
            "responsiveness": "exp" # Вспыльчивая реакция
        }
    ),
    ArchetypeEnum.PRESERVATION: Archetype(
        name='Preservation',
        description='Сохранение (Клипот) — защита и стабильность. Возводит стены ради выживания, ценит долг и устойчивость перед лицом энтропии.',
        weights={
            'joy_sadness': 0.7,
            'fear_calm': 1.5,
            'anger_humility': 0.5,
            'disgust_acceptance': 1.2,
            'surprise_habit': 0.6,
            'shame_confidence': 1.8,
            'openness_alienation': 1.4
        },
        refusal_chance=0.1,
        decay_rate=0.02,
        temperature=0.2,
        scoring_config={
            "affinity": "linear",
            "utility": "linear",
            "trust": "sigmoid",     # Стабильное доверие
            "responsiveness": "linear"
        }
    ),
    ArchetypeEnum.NIHILITY: Archetype(
        name='Nihility',
        description='Небытие (IX) — бессмысленность и пустота. Погружен в энтропию, считает связи преходящими, а усилия — бесполезными.',
        weights={
            'joy_sadness': 0.3,
            'fear_calm': 0.5,
            'anger_humility': 0.8,
            'disgust_acceptance': 1.8,
            'surprise_habit': 0.5,
            'shame_confidence': 0.4,
            'openness_alienation': 0.5
        },
        refusal_chance=0.8,
        decay_rate=0.1,
        temperature=1.0,
        scoring_config={
            "affinity": "log",       # Быстрое обесценивание связей
            "utility": "linear",
            "trust": "periodic",    # Экзистенциальные сомнения
            "responsiveness": "linear"
        }
    ),
    ArchetypeEnum.TRAILBLAZE: Archetype(
        name='Trailblaze',
        description='Освоение (Акивили) — дух приключений и открытий. Храбро идет в неизвестность, уважая прошлое и созидая будущее.',
        weights={
            'joy_sadness': 1.2,
            'fear_calm': 0.8,
            'anger_humility': 1.0,
            'disgust_acceptance': 1.0,
            'surprise_habit': 1.5,
            'shame_confidence': 1.3,
            'openness_alienation': 1.2
        },
        refusal_chance=0.2,
        decay_rate=0.08,
        temperature=1.2,
        scoring_config={
            "affinity": "linear",
            "utility": "log",        # Поиск новых путей (исследовательская ценность)
            "trust": "linear",
            "responsiveness": "linear"
        }
    ),
    ArchetypeEnum.REMEMBRANCE: Archetype(
        name='Remembrance',
        description='Память (Фули) — зеркало былого. Хранит все мгновения, ценит прошлое выше настоящего, устойчив к эмоциональному забвению.',
        weights={
            'joy_sadness': 0.7,
            'fear_calm': 1.3,
            'anger_humility': 0.4,
            'disgust_acceptance': 1.2,
            'surprise_habit': 1.0,
            'shame_confidence': 2.0,
            'openness_alienation': 1.8
        },
        refusal_chance=0.2,
        decay_rate=0.01,
        scoring_config={
            "affinity": "exp",       # Почти вечная память о связях
            "utility": "linear",
            "trust": "linear",
            "responsiveness": "log"  # Крайняя инертность
        }
    )
}