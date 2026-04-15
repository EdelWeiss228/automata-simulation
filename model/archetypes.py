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
        # Форма функций обновления (раздел 6 и 4 Промта) - ТЕПЕРЬ В x10 ЦЕЛЫХ
        self.emotion_effects = emotion_effects or {
            "joy_sadness": {"affinity": 10, "trust": 10},
            "anger_humility": {"affinity": -20, "trust": -20, "utility": -10},
            "fear_calm": {"trust": -10, "utility": -10},
            "openness_alienation": {"affinity": 20, "trust": 10},
            "disgust_acceptance": {"affinity": -10, "utility": -10},
            "shame_confidence": {"trust": 10, "affinity": -10},
            "surprise_habit": {"utility": 10},
        }
        self.emotion_coefficients = emotion_coefficients or {
            "joy_sadness": 10,
            "anger_humility": -10,
            "fear_calm": -10,
            "openness_alienation": 10,
            "disgust_acceptance": -10,
            "shame_confidence": 10,
            "surprise_habit": 10,
        }


ARCHETYPE_WEIGHTS = {
    ArchetypeEnum.ERUDITION: Archetype(
        name='Erudition',
        description='Эрудиция (Ноус) — хладнокровный расчет, почтение к логике и знанию. Избегает эмоциональных крайностей, анализирует структуру мира.',
        weights={
            'joy_sadness': 8,
            'fear_calm': 12,
            'anger_humility': 5,
            'disgust_acceptance': 10,
            'surprise_habit': 15,
            'shame_confidence': 7,
            'openness_alienation': 9
        },
        refusal_chance=0.2,
        decay_rate=0.8, # ТЕПЕРЬ 0.8 (умножаем на 10 и будем вычитать как целое в логике)
        temperature=0.1,
        scoring_config={
            "affinity": "linear",
            "utility": "log",
            "trust": "linear",
            "responsiveness": "linear"
        }
    ),
    ArchetypeEnum.ENIGMATA: Archetype(
        name='Enigmata',
        description='Энигмата (Мифус) — адепт неопределенности. Отрицает очевидное, окутывает истину туманом секретов, склонен к манипуляции смыслами.',
        weights={
            'joy_sadness': 10,
            'fear_calm': 8,
            'anger_humility': 12,
            'disgust_acceptance': 15,
            'surprise_habit': 18,
            'shame_confidence': 6,
            'openness_alienation': 10
        },
        refusal_chance=0.4,
        decay_rate=2.0,
        temperature=1.5,
        scoring_config={
            "affinity": "linear",
            "utility": "linear",
            "trust": "periodic",
            "responsiveness": "periodic" 
        }
    ),
    ArchetypeEnum.HARMONY: Archetype(
        name='Harmony',
        description='Гармония (Шипе) — единство и семейные узы. Стремится к абсолютному сотрудничеству, вплоть до растворения индивидуальности в коллективе.',
        weights={
            'joy_sadness': 15,
            'fear_calm': 10,
            'anger_humility': 2,
            'disgust_acceptance': 10,
            'surprise_habit': 7,
            'shame_confidence': 12,
            'openness_alienation': 20
        },
        refusal_chance=0.05,
        decay_rate=0.4,
        temperature=0.3,
        scoring_config={
            "affinity": "sigmoid",
            "utility": "linear",
            "trust": "exp",
            "responsiveness": "linear"
        }
    ),
    ArchetypeEnum.HUNT: Archetype(
        name='Hunt',
        description='Охота (Лань) — твердая решимость и месть. Фокусируется на одной цели, беспощаден к врагам, ценит справедливость через действие.',
        weights={
            'joy_sadness': 8,
            'fear_calm': 3,
            'anger_humility': 20,
            'disgust_acceptance': 6,
            'surprise_habit': 9,
            'shame_confidence': 15,
            'openness_alienation': 7
        },
        refusal_chance=0.2,
        decay_rate=1.2,
        temperature=0.1,
        scoring_config={
            "affinity": "linear",
            "utility": "linear",
            "trust": "sigmoid",
            "responsiveness": "exp"
        }
    ),
    ArchetypeEnum.ELATION: Archetype(
        name='Elation',
        description='Радость (Аха) — вселенная это шутка. Ищет веселье в хаосе, легко меняет привязанности, обожает неожиданные повороты сюжета.',
        weights={
            'joy_sadness': 20,
            'fear_calm': 8,
            'anger_humility': 9,
            'disgust_acceptance': 11,
            'surprise_habit': 20,
            'shame_confidence': 5,
            'openness_alienation': 12
        },
        refusal_chance=0.5,
        decay_rate=2.5,
        temperature=3.0,
        scoring_config={
            "affinity": "periodic",
            "utility": "linear",
            "trust": "linear",
            "responsiveness": "exp"
        }
    ),
    ArchetypeEnum.PRESERVATION: Archetype(
        name='Preservation',
        description='Сохранение (Клипот) — защита и стабильность. Возводит стены ради выживания, ценит долг и устойчивость перед лицом энтропии.',
        weights={
            'joy_sadness': 7,
            'fear_calm': 15,
            'anger_humility': 5,
            'disgust_acceptance': 12,
            'surprise_habit': 6,
            'shame_confidence': 18,
            'openness_alienation': 14
        },
        refusal_chance=0.1,
        decay_rate=0.2,
        temperature=0.2,
        scoring_config={
            "affinity": "linear",
            "utility": "linear",
            "trust": "sigmoid",
            "responsiveness": "linear"
        }
    ),
    ArchetypeEnum.NIHILITY: Archetype(
        name='Nihility',
        description='Небытие (IX) — бессмысленность и пустота. Погружен в энтропию, считает связи преходящими, а усилия — бесполезными.',
        weights={
            'joy_sadness': 3,
            'fear_calm': 5,
            'anger_humility': 8,
            'disgust_acceptance': 18,
            'surprise_habit': 5,
            'shame_confidence': 4,
            'openness_alienation': 5
        },
        refusal_chance=0.8,
        decay_rate=1.0,
        temperature=1.0,
        scoring_config={
            "affinity": "log",
            "utility": "linear",
            "trust": "periodic",
            "responsiveness": "linear"
        }
    ),
    ArchetypeEnum.TRAILBLAZE: Archetype(
        name='Trailblaze',
        description='Освоение (Акивили) — дух приключений и открытий. Храбро идет в неизвестность, уважая прошлое и созидая будущее.',
        weights={
            'joy_sadness': 12,
            'fear_calm': 8,
            'anger_humility': 10,
            'disgust_acceptance': 10,
            'surprise_habit': 15,
            'shame_confidence': 13,
            'openness_alienation': 12
        },
        refusal_chance=0.2,
        decay_rate=0.8,
        temperature=1.2,
        scoring_config={
            "affinity": "linear",
            "utility": "log",
            "trust": "linear",
            "responsiveness": "linear"
        }
    ),
    ArchetypeEnum.REMEMBRANCE: Archetype(
        name='Remembrance',
        description='Память (Фули) — зеркало былого. Хранит все мгновения, ценит прошлое выше настоящего, устойчив к эмоциональному забвению.',
        weights={
            'joy_sadness': 7,
            'fear_calm': 13,
            'anger_humility': 4,
            'disgust_acceptance': 12,
            'surprise_habit': 10,
            'shame_confidence': 20,
            'openness_alienation': 18
        },
        refusal_chance=0.2,
        decay_rate=0.1,
        temperature=1.0,
        scoring_config={
            "affinity": "exp",
            "utility": "linear",
            "trust": "linear",
            "responsiveness": "log"
        }
    )
}