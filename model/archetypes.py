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

    @property
    def localized(self):
        mapping = {
            'Erudition': 'Мудрец',
            'Enigmata': 'Бунтарь',
            'Harmony': 'Гармоничный',
            'Hunt': 'Воин',
            'Elation': 'Трикстер',
            'Preservation': 'Страж',
            'Nihility': 'Тайна',
            'Trailblaze': 'Путеводитель',
            'Remembrance': 'Память'
        }
        return mapping.get(self.value, self.value)


class Archetype:
    def __init__(self, name, weights, description, refusal_chance=0.3, decay_rate=0.1, temperature=1.0, refusal_vulnerability=0, emotion_effects=None, emotion_coefficients=None, scoring_config=None, context_adaptability=None, subject_resistance=None):
        self.name = name
        self.weights = weights
        self.description = description
        self.refusal_chance = refusal_chance
        self.decay_rate = decay_rate
        self.temperature = temperature
        self.refusal_vulnerability = refusal_vulnerability
        self.context_adaptability = context_adaptability or {
            'STUDY': 1.0,
            'BREAK': 1.0,
            'GYM': 1.0
        }
        # self.subject_resistance = subject_resistance or {} # Временно закомментировано (Задел на будущее - Влияние предметов)
        self.scoring_config = scoring_config or {
            "affinity": "linear",
            "utility": "linear",
            "trust": "linear"
        }
        # Форма функций обновления (раздел 6 и 4 Промта) - ТЕПЕРЬ В x10 ЦЕЛЫХ
        # НОРМАЛИЗАЦИЯ: Отрицательные значения (-) = плохо, Положительные (+) = хорошо
        self.emotion_effects = emotion_effects or {
            "sadness_joy": {"affinity": 10, "trust": 10},
            "anger_humility": {"affinity": -20, "trust": -20, "utility": -10},
            "fear_calm": {"trust": -10, "utility": -10},
            "alienation_openness": {"affinity": 20, "trust": 10},
            "disgust_acceptance": {"affinity": -10, "utility": -10},
            "shame_confidence": {"trust": 10, "affinity": -10},
            "habit_surprise": {"utility": 10},
        }
        # Коэффициенты масштабирования. Теперь все положительные (10), 
        # так как полярность заложена в самих осях (право = хорошо).
        self.emotion_coefficients = emotion_coefficients or {
            "sadness_joy": 10,
            "anger_humility": 10,
            "fear_calm": 10,
            "alienation_openness": 10,
            "disgust_acceptance": 10,
            "shame_confidence": 10,
            "habit_surprise": 10,
        }


ARCHETYPE_WEIGHTS = {
    ArchetypeEnum.ERUDITION: Archetype(
        name='Erudition',
        description='Эрудиция (Ноус) — хладнокровный расчет, почтение к логике и знанию. Избегает эмоциональных крайностей, анализирует структуру мира.',
        weights={
            'sadness_joy': 8,
            'fear_calm': 12,
            'anger_humility': 5,
            'disgust_acceptance': 10,
            'habit_surprise': 15,
            'shame_confidence': 7,
            'alienation_openness': 9
        },
        refusal_chance=0.2,
        decay_rate=8,     # x10 int
        temperature=0.1,
        refusal_vulnerability=0, # Utility
        scoring_config={
            "affinity": "linear",
            "utility": "log",
            "trust": "linear"
        },
        context_adaptability={
            'STUDY': 2.0,   # Процветает на учебе
            'BREAK': 0.5,   # Игнорирует разговоры в коридоре
            'GYM': 0.5      # Пассивен в зале
        }
        # subject_resistance={
        #    "sadness_joy": 1.5, # Плюс к радости от зубрежки
        #    "fear_calm": 0.5    # Меньше страха на парах
        # }
    ),
    ArchetypeEnum.ENIGMATA: Archetype(
        name='Enigmata',
        description='...',
        weights={
            'sadness_joy': 10, 
            'fear_calm': 8, 
            'anger_humility': 12, 
            'disgust_acceptance': 15, 
            'habit_surprise': 18, 
            'shame_confidence': 6, 
            'alienation_openness': 10
        },
        refusal_chance=0.4,
        decay_rate=20,
        temperature=1.5,
        refusal_vulnerability=0,
        scoring_config={"affinity": "linear", "utility": "linear", "trust": "periodic"}
    ),
    ArchetypeEnum.HARMONY: Archetype(
        name='Harmony',
        description='...',
        weights={
            'sadness_joy': 15, 
            'fear_calm': 10, 
            'anger_humility': 2, 
            'disgust_acceptance': 10, 
            'habit_surprise': 7, 
            'shame_confidence': 12, 
            'alienation_openness': 20
        },
        refusal_chance=0.05,
        decay_rate=4,
        temperature=0.3,
        refusal_vulnerability=1,
        scoring_config={"affinity": "sigmoid", "utility": "linear", "trust": "exp"},
        context_adaptability={
            'STUDY': 1.0,
            'BREAK': 2.0,   # Максимум общения в коридоре
            'GYM': 1.0
        }
    ),
    ArchetypeEnum.HUNT: Archetype(
        name='Hunt',
        description='...',
        weights={
            'sadness_joy': 8, 
            'fear_calm': 3, 
            'anger_humility': 20, 
            'disgust_acceptance': 6, 
            'habit_surprise': 9, 
            'shame_confidence': 15, 
            'alienation_openness': 7
        },
        refusal_chance=0.2,
        decay_rate=12,
        temperature=0.1,
        refusal_vulnerability=2,
        scoring_config={"affinity": "linear", "utility": "linear", "trust": "sigmoid"},
        context_adaptability={
            'STUDY': 0.5,
            'BREAK': 1.0,
            'GYM': 3.0      # Доминирует в спортзале (Спортсмен)
        }
    ),
    ArchetypeEnum.ELATION: Archetype(
        name='Elation',
        description='...',
        weights={
            'sadness_joy': 20, 
            'fear_calm': 8, 
            'anger_humility': 9, 
            'disgust_acceptance': 11, 
            'habit_surprise': 20, 
            'shame_confidence': 5, 
            'alienation_openness': 12
        },
        refusal_chance=0.5,
        decay_rate=25,
        temperature=3.0,
        refusal_vulnerability=1,
        scoring_config={"affinity": "periodic", "utility": "linear", "trust": "linear"}
    ),
    ArchetypeEnum.PRESERVATION: Archetype(
        name='Preservation',
        description='...',
        weights={
            'sadness_joy': 7, 
            'fear_calm': 15, 
            'anger_humility': 5, 
            'disgust_acceptance': 12, 
            'habit_surprise': 6, 
            'shame_confidence': 18, 
            'alienation_openness': 14
        },
        refusal_chance=0.1,
        decay_rate=2,
        temperature=0.2,
        refusal_vulnerability=2,
        scoring_config={"affinity": "linear", "utility": "linear", "trust": "sigmoid"}
    ),
    ArchetypeEnum.NIHILITY: Archetype(
        name='Nihility',
        description='...',
        weights={
            'sadness_joy': 3, 
            'fear_calm': 5, 
            'anger_humility': 8, 
            'disgust_acceptance': 18, 
            'habit_surprise': 5, 
            'shame_confidence': 4, 
            'alienation_openness': 5
        },
        refusal_chance=0.8,
        decay_rate=10,
        temperature=1.0,
        refusal_vulnerability=0,
        scoring_config={"affinity": "log", "utility": "linear", "trust": "periodic"}
    ),
    ArchetypeEnum.TRAILBLAZE: Archetype(
        name='Trailblaze',
        description='...',
        weights={
            'sadness_joy': 12, 
            'fear_calm': 8, 
            'anger_humility': 10, 
            'disgust_acceptance': 10, 
            'habit_surprise': 15, 
            'shame_confidence': 13, 
            'alienation_openness': 12
        },
        refusal_chance=0.2,
        decay_rate=8,
        temperature=1.2,
        refusal_vulnerability=0,
        scoring_config={"affinity": "linear", "utility": "log", "trust": "linear"}
    ),
    ArchetypeEnum.REMEMBRANCE: Archetype(
        name='Remembrance',
        description='...',
        weights={
            'sadness_joy': 7, 
            'fear_calm': 13, 
            'anger_humility': 4, 
            'disgust_acceptance': 12, 
            'habit_surprise': 10, 
            'shame_confidence': 20, 
            'alienation_openness': 18
        },
        refusal_chance=0.2,
        decay_rate=1,
        temperature=1.0,
        refusal_vulnerability=2,
        scoring_config={"affinity": "exp", "utility": "linear", "trust": "linear"}
    )
}