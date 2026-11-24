# Статус батча v2-corrected

Обновлено: 2026-11-24 16:10 UTC.

## Где что лежит

- Сервер: `georgiy@100.87.137.39`, каталог `~/Documents/automata-simulation`.
- Батч: `systemd --user` сервис `automata-batch.service`.
- Telegram-бот: `automata-tg-watcher.service`.
- Логи: `data/v2-corrected/batch.log`, `data/v2-corrected/logs/<scenario>.log`.
- Маркеры: `data/v2-corrected/done/<scenario>.done`.
- Тайминги: `data/v2-corrected/timings/<scenario>.json` и
  `data/v2-corrected/batch_timings.jsonl`.
- Данные: ClickHouse, база `default`, таблицы `agent_states`,
  `agent_relations`, `interactions`, `agent_registry`,
  `simulation_runs`, `run_timings`.

## Текущее состояние

- Старт: 2026-11-24 09:18 UTC, 8 воркеров.
- Готово: 24 из 54 сценариев (волны `Run01`–`Run08`).
- Четвёртая волна: `Run09_Normal_Social`, `Run10_Extremes`,
  `Run11_Competitive` — все три режима.
- Время одного прогона: 128.6–134.6 мин.
- Ожидаемое завершение: около 00:30 UTC 25 ноября.
- Ошибок в логах завершённых прогонов нет.

## Что уже проверено

- В каждом прогоне 1213 дней, 8 семестров, `max(day_id)=1212`.
- `run_timings.interactions` точно совпадает с числом строк в
  `interactions` (разница 0).
- В `agent_registry` 2805 уникальных человек на прогон: 1620 стартовых
  и 1185 добавленных после ротаций; дублей нет.
- Все ID из `agent_states`, `agent_relations` и `interactions` есть в
  `agent_registry` (пропусков 0).
- Ротация происходит на днях 303, 606, 909. В день 303: 395 новых,
  395 выбывших, 1225 остались; у новых агентов ненулевые эмоции и
  контакты, взаимодействия за этот день записаны в ClickHouse.
  Вторая ротация проверена на `Run04_Hunt_EMPTY`: день 606, те же
  395/395, registry вырос до 2410, пропусков ID нет.
- Насыщения эмоций нет: диапазон в одном прогоне `[-28, 28]` при
  внутренней шкале ±30.
- Дубликатов отношений на выборочных днях ротации нет.
- На 16 завершённых прогонах `run_timings.interactions` снова точно
  совпадает с числом строк `interactions` (разница 0), в registry
  2805 уникальных ID, пропусков ID в states/interactions/relations нет.
- Первая гетерогенная волна `Run08_Uniform_Random` (EMPTY/MIXED/RANDOM)
  проверена: все девять архетипов есть и до, и после ротации; тайминги
  совпадают; пропусков ID нет. На дне 0 встречаются значения ровно ±30
  из-за начального масштабирования весами архетипа; после дня 0
  диапазон `[-29, 29]`, насыщения нет.

## После завершения батча

1. `venv/bin/python scripts/validate_batch.py` — полная проверка
   целостности, отчёт `data/v2-corrected/validation.json`.
2. `venv/bin/python scripts/summarize_timings.py` — сводка таймингов,
   `data/v2-corrected/timing_summary.json`.
3. Запустить аналитику: `baseline_9.py`, `mega_research.py`,
   `sunday_reset_analysis.py`, `research_analyzer.py`.
4. Проверить динамику: диапазоны эмоций, ненулевые отношения, доли
   исходов, границы семестров; выводы — в `docs/bug-pipeline.md`.
5. Закоммитить результаты и обновить документацию. LaTeX пока не
   трогать.

## Если сессия/токены сбросились

Батч от чата не зависит. Проверить:

```bash
ssh georgiy@100.87.137.39
systemctl --user is-active automata-batch.service
tail -20 ~/Documents/automata-simulation/data/v2-corrected/batch.log
ls ~/Documents/automata-simulation/data/v2-corrected/done | wc -l
```

Если сервис активен — просто ждать. Если остановлен:
`systemctl --user start automata-batch.service`; уже готовые сценарии
пропустятся по `.done`-маркерам. Telegram-бот показывает статус,
прогресс, ресурсы и логи.
