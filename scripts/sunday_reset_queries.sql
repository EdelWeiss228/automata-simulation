-- ============================================================
-- SQL-запросы: Гипотеза «Эффект воскресного сброса»
-- База: ClickHouse, схема дипломной симуляции
-- ============================================================
-- В модели: WEEK_LEN = 7, воскресенье = day_id % 7 = 0
--           (дни: 7, 14, 21, ..., 1212)
-- ============================================================


-- ────────────────────────────────────────────────────────────
-- ЗАПРОС 1: Классификация агентов по базовому эмоциональному фону
-- Читает agent_states дней 1–6 (до первого воскресного сброса)
-- Возвращает: run_id, agent_id, baseline_mood (среднее по 7 осям)
-- ────────────────────────────────────────────────────────────
SELECT
    run_id,
    agent_id,
    -- Сводный индекс настроения: среднее по всем 7 осям
    (
        avg(sadness_joy) +
        avg(fear_calm) +
        avg(anger_humility) +
        avg(disgust_acceptance) +
        avg(habit_surprise) +
        avg(shame_confidence) +
        avg(alienation_openness)
    ) / 7.0                         AS baseline_mood,

    -- Отдельные оси для детального анализа
    avg(sadness_joy)                 AS base_sadness_joy,
    avg(fear_calm)                   AS base_fear_calm,
    avg(anger_humility)              AS base_anger_humility,
    avg(disgust_acceptance)          AS base_disgust_acceptance,
    avg(habit_surprise)              AS base_habit_surprise,
    avg(shame_confidence)            AS base_shame_confidence,
    avg(alienation_openness)         AS base_alienation_openness
FROM agent_states
WHERE day_id BETWEEN 1 AND 6          -- до первого воскресенья
GROUP BY run_id, agent_id
ORDER BY baseline_mood;


-- ────────────────────────────────────────────────────────────
-- ЗАПРОС 2: Извлечение эмоций в окне [-3, +6] от каждого воскресенья
-- Использует CROSS JOIN с таблицей смещений (offset -3..+6)
-- Тяжёлый запрос — вся агрегация на стороне ClickHouse
-- ────────────────────────────────────────────────────────────
WITH

-- Все воскресные дни симуляции
sundays AS (
    SELECT DISTINCT
        intDiv(day_id - 1, 7) * 7 + 7  AS sunday_day
    FROM agent_states
    WHERE day_id % 7 = 0
),

-- Целевые дни: окно [-3, +6] от каждого воскресенья
windows AS (
    SELECT
        s.sunday_day,
        s.sunday_day + offset        AS target_day,
        offset
    FROM sundays s
    CROSS JOIN (
        SELECT number - 3 AS offset
        FROM numbers(10)             -- числа 0..9 → offset: -3..+6
    ) offsets
    WHERE s.sunday_day + offset BETWEEN 1 AND 1212
      AND s.sunday_day + offset > 0
)

SELECT
    w.sunday_day,
    w.offset,
    ast.run_id,
    ast.agent_id,

    -- Сводной индекс настроения (среднее по 7 осям)
    (
        ast.sadness_joy +
        ast.fear_calm +
        ast.anger_humility +
        ast.disgust_acceptance +
        ast.habit_surprise +
        ast.shame_confidence +
        ast.alienation_openness
    ) / 7.0                          AS mood_composite,

    -- Все оси для детального анализа
    ast.sadness_joy,
    ast.fear_calm,
    ast.anger_humility,
    ast.disgust_acceptance,
    ast.habit_surprise,
    ast.shame_confidence,
    ast.alienation_openness

FROM windows w
JOIN agent_states ast
    ON  ast.day_id  = w.target_day

ORDER BY w.sunday_day, w.offset, ast.agent_id;


-- ────────────────────────────────────────────────────────────
-- ЗАПРОС 3: Агрегация кривых восстановления по группам
-- Требует предварительно вычислить baseline_mood и group для каждого агента
-- Использует классификацию из Запроса 1 как CTE
-- ────────────────────────────────────────────────────────────
WITH

baseline AS (
    SELECT
        run_id,
        agent_id,
        (
            avg(sadness_joy) + avg(fear_calm) + avg(anger_humility) +
            avg(disgust_acceptance) + avg(habit_surprise) +
            avg(shame_confidence) + avg(alienation_openness)
        ) / 7.0  AS baseline_mood,
        -- Классификация: negative / neutral / positive
        multiIf(
            (avg(sadness_joy) + avg(fear_calm) + avg(anger_humility) +
             avg(disgust_acceptance) + avg(habit_surprise) +
             avg(shame_confidence) + avg(alienation_openness)) / 7.0 < -5, 'negative',
            (avg(sadness_joy) + avg(fear_calm) + avg(anger_humility) +
             avg(disgust_acceptance) + avg(habit_surprise) +
             avg(shame_confidence) + avg(alienation_openness)) / 7.0 >  5, 'positive',
            'neutral'
        )        AS agent_group
    FROM agent_states
    WHERE day_id BETWEEN 1 AND 6
    GROUP BY run_id, agent_id
),

sundays AS (
    SELECT DISTINCT
        intDiv(day_id - 1, 7) * 7 + 7  AS sunday_day
    FROM agent_states
    WHERE day_id % 7 = 0
),

windows AS (
    SELECT
        s.sunday_day,
        s.sunday_day + offset  AS target_day,
        offset
    FROM sundays s
    CROSS JOIN (SELECT number - 3 AS offset FROM numbers(10)) offsets
    WHERE s.sunday_day + offset BETWEEN 1 AND 1212
      AND s.sunday_day + offset > 0
)

SELECT
    b.agent_group                       AS grp,
    w.offset,
    avg(
        (ast.sadness_joy + ast.fear_calm + ast.anger_humility +
         ast.disgust_acceptance + ast.habit_surprise +
         ast.shame_confidence + ast.alienation_openness) / 7.0
    )                                   AS mean_mood,
    stddevPop(
        (ast.sadness_joy + ast.fear_calm + ast.anger_humility +
         ast.disgust_acceptance + ast.habit_surprise +
         ast.shame_confidence + ast.alienation_openness) / 7.0
    )                                   AS std_mood,
    count()                             AS n_observations
FROM windows w
JOIN agent_states ast ON ast.day_id = w.target_day
JOIN baseline b
    ON  b.run_id    = ast.run_id
    AND b.agent_id  = ast.agent_id
GROUP BY b.agent_group, w.offset
ORDER BY b.agent_group, w.offset;


-- ────────────────────────────────────────────────────────────
-- ЗАПРОС 4: Recovery gap (mood[+6 дней] − mood[−1 день])
-- Для каждого агента и каждого воскресенья
-- ────────────────────────────────────────────────────────────
WITH

baseline AS (
    SELECT
        run_id, agent_id,
        multiIf(
            (avg(sadness_joy) + avg(fear_calm) + avg(anger_humility) +
             avg(disgust_acceptance) + avg(habit_surprise) +
             avg(shame_confidence) + avg(alienation_openness)) / 7.0 < -5, 'negative',
            (avg(sadness_joy) + avg(fear_calm) + avg(anger_humility) +
             avg(disgust_acceptance) + avg(habit_surprise) +
             avg(shame_confidence) + avg(alienation_openness)) / 7.0 >  5, 'positive',
            'neutral'
        ) AS agent_group
    FROM agent_states
    WHERE day_id BETWEEN 1 AND 6
    GROUP BY run_id, agent_id
),

sundays AS (
    SELECT DISTINCT
        intDiv(day_id - 1, 7) * 7 + 7  AS sunday_day
    FROM agent_states
    WHERE day_id % 7 = 0
),

-- День ДО воскресенья (offset = -1)
pre_sunday AS (
    SELECT
        ast.run_id,
        ast.agent_id,
        s.sunday_day,
        (ast.sadness_joy + ast.fear_calm + ast.anger_humility +
         ast.disgust_acceptance + ast.habit_surprise +
         ast.shame_confidence + ast.alienation_openness) / 7.0  AS mood_pre
    FROM sundays s
    JOIN agent_states ast ON ast.day_id = s.sunday_day - 1
),

-- 6-й день ПОСЛЕ воскресенья (offset = +6)
post_sunday AS (
    SELECT
        ast.run_id,
        ast.agent_id,
        s.sunday_day,
        (ast.sadness_joy + ast.fear_calm + ast.anger_humility +
         ast.disgust_acceptance + ast.habit_surprise +
         ast.shame_confidence + ast.alienation_openness) / 7.0  AS mood_post
    FROM sundays s
    JOIN agent_states ast ON ast.day_id = s.sunday_day + 6
    WHERE s.sunday_day + 6 <= 1212
)

SELECT
    b.agent_group                       AS grp,
    pre.sunday_day,
    avg(post.mood_post - pre.mood_pre)  AS mean_recovery_gap,
    stddevPop(post.mood_post - pre.mood_pre) AS std_recovery_gap,
    countIf(post.mood_post >= pre.mood_pre) * 100.0
        / count()                       AS pct_fully_recovered,
    count()                             AS n_pairs
FROM pre_sunday pre
JOIN post_sunday post
    ON  pre.run_id      = post.run_id
    AND pre.agent_id    = post.agent_id
    AND pre.sunday_day  = post.sunday_day
JOIN baseline b
    ON  b.run_id        = pre.run_id
    AND b.agent_id      = pre.agent_id
GROUP BY b.agent_group, pre.sunday_day
ORDER BY b.agent_group, pre.sunday_day;


-- ────────────────────────────────────────────────────────────
-- ЗАПРОС 5: Скорость возврата к нулю после сброса
-- Проверяет, насколько быстро агент достигает mood ≈ 0
-- после воскресного δ-сдвига (с учётом затухания dE = 0.2 · si)
-- ────────────────────────────────────────────────────────────
WITH

baseline AS (
    SELECT
        run_id, agent_id,
        multiIf(
            (avg(sadness_joy) + avg(fear_calm) + avg(anger_humility) +
             avg(disgust_acceptance) + avg(habit_surprise) +
             avg(shame_confidence) + avg(alienation_openness)) / 7.0 < -5, 'negative',
            (avg(sadness_joy) + avg(fear_calm) + avg(anger_humility) +
             avg(disgust_acceptance) + avg(habit_surprise) +
             avg(shame_confidence) + avg(alienation_openness)) / 7.0 >  5, 'positive',
            'neutral'
        ) AS agent_group
    FROM agent_states
    WHERE day_id BETWEEN 1 AND 6
    GROUP BY run_id, agent_id
),

sundays AS (
    SELECT DISTINCT
        intDiv(day_id - 1, 7) * 7 + 7  AS sunday_day
    FROM agent_states
    WHERE day_id % 7 = 0
)

SELECT
    b.agent_group                        AS grp,
    w_offset.offset,
    -- Доля агентов, у которых |mood| < 3 (практически нейтральный)
    countIf(
        abs(
            ast.sadness_joy + ast.fear_calm + ast.anger_humility +
            ast.disgust_acceptance + ast.habit_surprise +
            ast.shame_confidence + ast.alienation_openness
        ) / 7.0 < 3.0
    ) * 100.0 / count()                  AS pct_near_zero,
    count()                              AS n
FROM sundays s
CROSS JOIN (SELECT number AS offset FROM numbers(7)) w_offset  -- offset: 0..6
JOIN agent_states ast
    ON ast.day_id = s.sunday_day + w_offset.offset
    AND s.sunday_day + w_offset.offset BETWEEN 1 AND 1212
JOIN baseline b
    ON  b.run_id   = ast.run_id
    AND b.agent_id = ast.agent_id
GROUP BY b.agent_group, w_offset.offset
ORDER BY b.agent_group, w_offset.offset;
