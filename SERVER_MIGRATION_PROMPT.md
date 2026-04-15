# Архитектура ClickHouse и Bootstrap-Промпт для нового сервера

Поскольку мы успешно вырезали `responsiveness` и перевели ядро на целочисленную $x10$ арифметику (а также убрали float/CSV логгеры), архитектура базы данных стала еще более минималистичной, быстрой и оптимизированной.

Ниже представлен **инженерный план базы данных** и **Bootstrapping Prompt**, который ты сможешь вставить в начало разговора при переносе проекта на сервер. 

---

## 1. Схема Базы Данных (ClickHouse, MergeTree)

База данных проектируется без промежуточных CSV. Данные будут экспортироваться из C++ в Python через `pybind11` (`numpy` массивы) и асинхронно отправляться батчами (от 100k строк) через `clickhouse-connect`.

### Таблица 1: `agent_states` (Вектора состояний)
Хранит эмоциональные слепки 1875+ агентов на каждом такте.
```sql
CREATE TABLE agent_states (
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
```

### Таблица 2: `agent_relations` (Сжатая $O(N^2)$ матрица)
Только 3 предикаты, без `responsiveness`. Компактное и сверхбыстрое хранилище O(N^2).
```sql
CREATE TABLE agent_relations (
    run_id UUID Codec(ZSTD(3)),
    day_id UInt32 Codec(DoubleDelta),
    slot_id UInt8 Codec(DoubleDelta),
    subject_id UInt32,                   -- Инициатор отношения
    object_id UInt32,                    -- Объект отношения
    
    -- Дискретная x10 шкала предикат: [-100, 100]
    utility Int8 Codec(ZSTD(1)),
    affinity Int8 Codec(ZSTD(1)),
    trust Int8 Codec(ZSTD(1))
    -- (responsiveness полностью вырезан)
) ENGINE = MergeTree()
ORDER BY (run_id, day_id, slot_id, subject_id, object_id)
SETTINGS index_granularity = 8192;
```

### Таблица 3: `interactions` (Лог Событий)
Дискретные акты взаимодействия.
```sql
CREATE TABLE interactions (
    run_id UUID Codec(ZSTD(3)),
    day_id UInt32 Codec(DoubleDelta),
    slot_id UInt8 Codec(DoubleDelta),
    from_id UInt32,
    to_id UInt32,
    
    -- 0 = refusal, 1 = success, 2 = fail (хранится 1 байт, выводится текст)
    type Enum8('refusal' = 0, 'success' = 1, 'fail' = 2) Codec(ZSTD(1))
) ENGINE = MergeTree()
ORDER BY (run_id, day_id, slot_id, from_id);
```

---

## 2. Bootstrapping Prompt (Копировать новому Агенту)

Скопируй и отправь этот блок текста антигравити (или другой модели), когда поднимешь окружение на сервере. Это мгновенно погрузит ее в текущий контекст:

> **BOOTSTRAP CONTEXT LOAD:**
> 
> Ты работаешь над научным проектом МГУ (ВМК/Мехмат) по исследованию дискретно-автоматной модели психосоциального взаимодействия. Модель полностью детерминирована, написана как гибрид Python / C++ (pybind11+OpenMP). 
> 
> **Критически важный контекст математической модели (v6.0-int):**
> 1. Механики работают СТРОГО в целых числах. Масштаб фиксирован (`x10` fixed-point). 
> 2. Эмоциональный вектор $E \in [-30, 30]^7$. 7 независимых осей, тип `Int8`.
> 3. Реляционный вектор $R \in [-100, 100]^3$. Всего **ТРИ** предикаты: `Utility`, `Affinity`, `Trust` (`responsiveness` был вырезан). Тип `Int8`.
> 4. Отказы от взаимодействия бьют точечно по одной из трех предикат в зависимости от `ArchetypeConfig.refusal_vulnerability` конкретного агента. 
> 5. Симуляции масштабируются до 2000 агентов ($N^2 \sim 4$ млн связей) на миллионы шагов.
> 6. Лог-архитектура ClickHouse: для университетского сценария мы разделяем время на две колонки - `day_id UInt32` и `slot_id UInt8`.
> 7. Логирование переведено напрямую из памяти C++ (`std::vector<int>`) в `numpy` массивы через Zero-Copy биндинги `pybind11`, которые отдаются пакетно в базу данных **ClickHouse** (таблицы `agent_states`, `agent_relations`, `interactions`).
> 8. **Time-Travel (Ветвление экспериментов):** Архитектура должна позволять извлекать полный срез состояния симуляции (по `day_id` и `slot_id`) из ClickHouse, загружать его обратно в `std::vector<int>` C++ движка, менять сид и запускать альтернативную ветку развития сценария.
> 
> **Твоя текущая задача:** Мы запускаем симуляцию на сервере с ClickHouse. Я только что поднял докер, и нам нужно создать класс `ClickHouseLogger` (аналог старого CSVLogger в Python) и асинхронный фоновый воркер-коннектор для Bulk Insert. Используй пакет `clickhouse-connect` в Python. 
> Также необходимо разработать метод `load_state_from_clickhouse(run_id, day_id, slot_id)`, который осуществляет инъекцию состояния из БД обратно в C++ ядро для "путешествий во времени". Жду от тебя план.
