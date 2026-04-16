CREATE TABLE IF NOT EXISTS agent_states (
    run_id UUID Codec(ZSTD(3)),          -- ID сценария
    day_id UInt32 Codec(DoubleDelta),    -- Номер дня
    slot_id UInt8 Codec(DoubleDelta),    -- Номер слота (1 пара, перерыв и т.д.)
    agent_id UInt32,                     -- Числовой ID агента
    
    -- Значения эмоций в дискретной x10 шкале: [-30, 30] 
    -- Занимают ровно 1 байт.
    joy_sadness Int8 Codec(ZSTD(1)),
    fear_calm Int8 Codec(ZSTD(1)),
    anger_humility Int8 Codec(ZSTD(1)),
    disgust_acceptance Int8 Codec(ZSTD(1)),
    surprise_habit Int8 Codec(ZSTD(1)),
    shame_confidence Int8 Codec(ZSTD(1)),
    openness_alienation Int8 Codec(ZSTD(1))
) ENGINE = MergeTree()
ORDER BY (run_id, day_id, slot_id, agent_id);

CREATE TABLE IF NOT EXISTS agent_relations (
    run_id UUID Codec(ZSTD(3)),
    day_id UInt32 Codec(DoubleDelta),
    slot_id UInt8 Codec(DoubleDelta),
    subject_id UInt32,                   -- Инициатор отношения
    object_id UInt32,                    -- Объект отношения
    
    -- Дискретная x10 шкала предикат: [-100, 100]
    utility Int8 Codec(ZSTD(1)),
    affinity Int8 Codec(ZSTD(1)),
    trust Int8 Codec(ZSTD(1))
) ENGINE = MergeTree()
ORDER BY (run_id, day_id, slot_id, subject_id, object_id)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS interactions (
    run_id UUID Codec(ZSTD(3)),
    day_id UInt32 Codec(DoubleDelta),
    slot_id UInt8 Codec(DoubleDelta),
    from_id UInt32,
    to_id UInt32,
    
    -- 0 = refusal, 1 = success, 2 = fail (хранится 1 байт, выводится текст)
    type Enum8('refusal' = 0, 'success' = 1, 'fail' = 2) Codec(ZSTD(1))
) ENGINE = MergeTree()
ORDER BY (run_id, day_id, slot_id, from_id);
