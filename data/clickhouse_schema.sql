-- Таблица 1: Вектора состояний (эмоции)
CREATE TABLE IF NOT EXISTS agent_states (
    run_id UUID Codec(ZSTD(3)),          -- ID сценария
    day_id UInt32 Codec(DoubleDelta),    -- Номер дня
    slot_id UInt8 Codec(DoubleDelta),    -- Номер слота (1 пара, перерыв и т.д.)
    agent_id UInt32,                     -- Числовой ID агента
    
    sadness_joy Int8 Codec(ZSTD(1)),      -- Печаль (-30), Радость (+30)
    fear_calm Int8 Codec(ZSTD(1)),        -- Страх (-30), Спокойствие (+30)
    anger_humility Int8 Codec(ZSTD(1)),   -- Гнев (-30), Смирение (+30)
    disgust_acceptance Int8 Codec(ZSTD(1)), -- Отвращение (-30), Принятие (+30)
    habit_surprise Int8 Codec(ZSTD(1)),   -- Привычка (-30), Удивление (+30)
    shame_confidence Int8 Codec(ZSTD(1)), -- Стыд (-30), Уверенность (+30)
    alienation_openness Int8 Codec(ZSTD(1)) -- Отчужденность (-30), Открытость (+30)
) ENGINE = MergeTree()
ORDER BY (run_id, day_id, slot_id, agent_id);

-- Таблица 2: Сжатая матрица отношений (3 предикаты)
CREATE TABLE IF NOT EXISTS agent_relations (
    run_id UUID Codec(ZSTD(3)),
    day_id UInt32 Codec(DoubleDelta),
    slot_id UInt8 Codec(DoubleDelta),
    subject_id UInt32,                   -- Инициатор отношения
    object_id UInt32,                    -- Объект отношения
    
    utility Int8 Codec(ZSTD(1)),
    affinity Int8 Codec(ZSTD(1)),
    trust Int8 Codec(ZSTD(1))
) ENGINE = MergeTree()
ORDER BY (run_id, day_id, slot_id, subject_id, object_id)
SETTINGS index_granularity = 8192;

-- Таблица 3: Лог событий
CREATE TABLE IF NOT EXISTS interactions (
    run_id UUID Codec(ZSTD(3)),
    day_id UInt32 Codec(DoubleDelta),
    slot_id UInt8 Codec(DoubleDelta),
    from_id UInt32,
    to_id UInt32,
    
    type Int8 Codec(ZSTD(1))               -- -1 (Fail), 0 (Refusal), 1 (Success)
) ENGINE = MergeTree()
ORDER BY (run_id, day_id, slot_id, from_id);

-- Таблица 4: Реестр агентов (Справочник)
CREATE TABLE IF NOT EXISTS agent_registry (
    run_id UUID Codec(ZSTD(3)),          -- ID сценария
    agent_id UInt32,                     -- Числовой ID агента (используется в симуляции)
    string_id String,                    -- Уникальный строковой ID (например S-П-22-1-03)
    name String,                         -- Имя агента
    group_id String,                     -- ID группы
    archetype String                     -- Архетип
) ENGINE = MergeTree()
ORDER BY (run_id, agent_id);
