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
    def __init__(self, name, weights, description, refusal_chance=0.3):
        self.name = name
        self.weights = weights
        self.description = description
        self.refusal_chance = refusal_chance


ARCHETYPE_WEIGHTS = {
    ArchetypeEnum.ERUDITION: Archetype(
        name='Erudition',
        description='🧙 Мудрец — хладнокровен, избегает крайностей, ценит знание.',
        weights={
            'joy_sadness': 0.9,
            'fear_calm': 1.4,
            'anger_humility': 0.6,
            'disgust_acceptance': 1.2,
            'surprise_habit': 0.8,
            'shame_confidence': 0.7,
            'love_alienation': 1.0
        },
        refusal_chance=0.2
    ),
    ArchetypeEnum.ENIGMATA: Archetype(
        name='Enigmata',
        description='🌪 Бунтарь — импульсивный, склонен к конфликту, ищет перемен.',
        weights={
            'joy_sadness': 1.2,
            'fear_calm': 0.6,
            'anger_humility': 1.8,
            'disgust_acceptance': 1.4,
            'surprise_habit': 1.2,
            'shame_confidence': 0.6,
            'love_alienation': 1.0
        },
        refusal_chance=0.7
    ),
    ArchetypeEnum.HARMONY: Archetype(
        name='Harmony',
        description='🌸 Гармонист — стремится к балансу, поддерживает отношения, избегает конфликта.',
        weights={
            'joy_sadness': 1.1,
            'fear_calm': 1.2,
            'anger_humility': 0.5,
            'disgust_acceptance': 1.4,
            'surprise_habit': 0.9,
            'shame_confidence': 1.1,
            'love_alienation': 1.5
        },
        refusal_chance=0.1
    ),
    ArchetypeEnum.HUNT: Archetype(
        name='Hunt',
        description='🗡 Воин — смелый и решительный, слабо подвержен страху и отвращению.',
        weights={
            'joy_sadness': 1.0,
            'fear_calm': 0.7,
            'anger_humility': 1.6,
            'disgust_acceptance': 0.8,
            'surprise_habit': 1.0,
            'shame_confidence': 1.3,
            'love_alienation': 0.8
        },
        refusal_chance=0.3
    ),
    ArchetypeEnum.ELATION: Archetype(
        name='Elation',
        description='🎭 Трикстер — не предсказуем, легко переходит от эмоции к эмоции, любит удивлять.',
        weights={
            'joy_sadness': 1.5,
            'fear_calm': 0.9,
            'anger_humility': 0.9,
            'disgust_acceptance': 1.1,
            'surprise_habit': 1.8,
            'shame_confidence': 0.8,
            'love_alienation': 1.2
        },
        refusal_chance=0.5
    ),
    ArchetypeEnum.PRESERVATION: Archetype(
        name='Preservation',
        description='🛡 Страж — заботится о других, стремится к стабильности, обострено чувство вины и долга.',
        weights={
            'joy_sadness': 0.9,
            'fear_calm': 1.0,
            'anger_humility': 0.7,
            'disgust_acceptance': 1.3,
            'surprise_habit': 0.8,
            'shame_confidence': 1.4,
            'love_alienation': 1.6
        },
        refusal_chance=0.15
    ),
    ArchetypeEnum.NIHILITY: Archetype(
        name='Nihility',
        description='🌀 Тайна — сосредоточен на распаде, сомнении, исчезновении, влияет через разрушение.',
        weights={
            'joy_sadness': 0.5,
            'fear_calm': 1.3,
            'anger_humility': 1.0,
            'disgust_acceptance': 1.5,
            'surprise_habit': 1.1,
            'shame_confidence': 0.6,
            'love_alienation': 0.7
        },
        refusal_chance=0.6
    ),
    ArchetypeEnum.TRAILBLAZE: Archetype(
        name='Trailblaze',
        description='🚶‍♂️ Путеводитель — уравновешенный, ищет смысл, открыт новым путям.',
        weights={
            'joy_sadness': 1.0,
            'fear_calm': 1.0,
            'anger_humility': 1.0,
            'disgust_acceptance': 1.0,
            'surprise_habit': 1.0,
            'shame_confidence': 1.0,
            'love_alienation': 1.0
        },
        refusal_chance=0.25
    ),
    ArchetypeEnum.REMEMBRANCE: Archetype(
        name='Remembrance',
        description='🕯 Память — ценит прошлое, устойчив к эмоциональным изменениям, склонен к рефлексии.',
        weights={
            'joy_sadness': 0.8,
            'fear_calm': 1.1,
            'anger_humility': 0.6,
            'disgust_acceptance': 1.2,
            'surprise_habit': 0.9,
            'shame_confidence': 1.5,
            'love_alienation': 1.3
        },
        refusal_chance=0.2
    )
}