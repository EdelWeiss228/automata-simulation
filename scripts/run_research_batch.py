import argparse
import json
import os
import subprocess
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Варианты изначальных отношений (Варианты 1, 2, 3)
RELATION_MODES = ["EMPTY", "RANDOM", "MIXED"]

# Гомогенные прогоны (Прогоны 1-7)
HOMOGENEOUS_RUNS = {
    "Run01_Erudition": {"ERUDITION": 1500},
    "Run02_Enigmata": {"ENIGMATA": 1500},
    "Run03_Harmony": {"HARMONY": 1500},
    "Run04_Hunt": {"HUNT": 1500},
    "Run05_Elation": {"ELATION": 1500},
    "Run06_Preservation": {"PRESERVATION": 1500},
    "Run07_Nihility": {"NIHILITY": 1500},
}

# Гетерогенные прогоны (Прогоны 8-14)
# Настраиваем распределения (условные 1500 бакалавров, 120 магистров)
HETEROGENEOUS_RUNS = {
    "Run08_Uniform_Random": {}, # Пустой словарь вызовет равномерное случайное распределение в ядре
    "Run09_Normal_Social": { # Преобладание социальных/командных архетипов
        "HARMONY": 400, "PRESERVATION": 400, "INNOVATOR": 300, 
        "ERUDITION": 200, "MEDIATOR": 200
    },
    "Run10_Extremes": { # Поляризованный коллектив
        "DESTRUCTOR": 500, "PROTECTOR": 500, "OPPORTUNIST": 500
    },
    "Run11_Competitive": { # Агрессивная/конкурентная среда
        "HUNT": 500, "COMPETITOR": 500, "NONCONFORMIST": 500
    },
    "Run12_Academic": { # Академически-ориентированный коллектив
        "ERUDITION": 600, "ANALYST": 600, "REFLECTOR": 300
    },
    "Run13_Chaotic": { # Высокая энтропия (Оппортунисты, Энигматы, Деструкторы)
        "OPPORTUNIST": 500, "ENIGMATA": 500, "ELATION": 500
    },
    "Run14_Real_World_Approx": { # Попытка имитации реального распределения
        "ANALYST": 300, "MEDIATOR": 300, "PROTECTOR": 300,
        "COMPETITOR": 200, "ERUDITION": 200, "HARMONY": 100,
        "DESTRUCTOR": 50, "NONCONFORMIST": 50
    }
}

ALL_RUNS = {**HOMOGENEOUS_RUNS, **HETEROGENEOUS_RUNS}
ARCHIVE_DIR = "scenarios_archive"
OUTPUT_ROOT = os.path.join("data", "v2-corrected")

def generate_config(run_id: str, mode: str, counts: dict) -> str:
    scenario_name = f"{run_id}_{mode}"
    filepath = os.path.join(ARCHIVE_DIR, f"{scenario_name}.json")

    # Архивные сценарии уже содержат зафиксированные seed'ы. Их нельзя
    # перегенерировать: встроенный hash() для строк рандомизирован между
    # процессами (PYTHONHASHSEED), и тогда "те же данные" не воспроизводятся.
    if os.path.exists(filepath):
        return filepath

    config = {
        "scenario_name": scenario_name,
        "run_name": run_id,
        "description": f"Research Batch. Archetype Dist: {run_id}. Relations Mode: {mode}",
        "bachelor_counts": counts,
        "master_counts": {k: max(1, int(v * 0.08)) for k, v in counts.items()} if counts else {},
        "initial_relations_mode": mode,
        "semesters": 8,
        # CRC32 стабилен между процессами и платформами.
        "seed": zlib.crc32(scenario_name.encode("utf-8")) % 1000000
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

    return filepath

def run_simulation(config_path: str, is_test: bool = False, force: bool = False):
    scenario = os.path.splitext(os.path.basename(config_path))[0]
    log_dir = os.path.join(OUTPUT_ROOT, "logs")
    done_dir = os.path.join(OUTPUT_ROOT, "done")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(done_dir, exist_ok=True)

    log_path = os.path.join(log_dir, scenario + ".log")
    done_path = os.path.join(done_dir, scenario + ".done")

    if os.path.exists(done_path) and not force:
        print(f"[skip] {scenario} (уже завершён)", flush=True)
        return True

    python_bin = "./venv/bin/python" if os.path.exists("./venv/bin/python") else "python"
    cmd = [python_bin, "main.py", "--university", "--silent", "--scenario", config_path]
    if is_test:
        cmd.extend(["--semesters", "0", "--steps", "1"])

    print(f"[start] {scenario}", flush=True)
    started = time.time()

    # stdout каждого прогона идёт в отдельный лог, чтобы 8 параллельных
    # процессов не перемешивали прогресс и ошибки.
    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        process.wait()

    elapsed = (time.time() - started) / 60
    if process.returncode != 0:
        print(
            f"[fail] {scenario} через {elapsed:.1f} мин; лог: {log_path}",
            flush=True,
        )
        return False

    with open(done_path, "w", encoding="utf-8") as marker:
        marker.write(f"{datetime.now().isoformat()}\t{elapsed:.2f} min\n")

    print(f"[done] {scenario} за {elapsed:.1f} мин", flush=True)
    return True

def main():
    parser = argparse.ArgumentParser(description="Полный матричный прогон v2-corrected")
    parser.add_argument("--test", action="store_true", help="Короткий тестовый запуск")
    parser.add_argument("--workers", type=int, default=8, help="Количество параллельных процессов")
    parser.add_argument("--only", type=str, default=None, help="Фильтр по имени сценария")
    parser.add_argument("--force", action="store_true", help="Перезапустить уже завершённые сценарии")
    args = parser.parse_args()

    # Собираем все задачи в список
    tasks = []
    for run_id, counts in ALL_RUNS.items():
        for mode in RELATION_MODES:
            config_path = generate_config(run_id, mode, counts)
            if args.only and args.only not in os.path.basename(config_path):
                continue
            tasks.append(config_path)

    missing = [path for path in tasks if not os.path.exists(path)]
    if missing:
        print("ОШИБКА: отсутствуют сценарии:", *missing, sep="\n  ", file=sys.stderr)
        sys.exit(1)

    # Манифест фиксирует, что именно было запущено. Сиды берутся из архива.
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    manifest = {
        "created_at": datetime.now().isoformat(),
        "source": "v2-fixed",
        "scenarios": {},
    }
    for path in tasks:
        with open(path, "r", encoding="utf-8") as handle:
            cfg = json.load(handle)
        manifest["scenarios"][os.path.basename(path)] = {
            "seed": cfg.get("seed"),
            "initial_relations_mode": cfg.get("initial_relations_mode"),
            "semesters": cfg.get("semesters"),
            "bachelor_counts": cfg.get("bachelor_counts"),
            "master_counts": cfg.get("master_counts"),
        }
    with open(os.path.join(OUTPUT_ROOT, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)

    print(
        f"Начинаем серию из {len(tasks)} симуляций в {args.workers} потоках...",
        flush=True,
    )
    start_time = time.time()

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(run_simulation, path, args.test, args.force): path
            for path in tasks
        }
        for future in as_completed(futures):
            path = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print(f"[fail] {path}: {exc}", flush=True)
                results.append(False)

    elapsed = (time.time() - start_time) / 60
    if all(results):
        print(f"\nВсе симуляции успешно завершены за {elapsed:.2f} минут.", flush=True)
    else:
        print("\nОШИБКА: Некоторые симуляции завершились неудачно.", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
