import argparse
import json
import os
import subprocess
import sys
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Варианты изначальных отношений (Варианты 1, 2, 3)
RELATION_MODES = ["EMPTY", "RANDOM", "MIXED"]

# Гомогенные прогоны: по одному на каждый из девяти архетипов.
# Run15/Run16 добавлены после аудита: Trailblaze и Remembrance были
# определены в модели, но не входили в исходную матрицу.
HOMOGENEOUS_RUNS = {
    "Run01_Erudition": {"ERUDITION": 1500},
    "Run02_Enigmata": {"ENIGMATA": 1500},
    "Run03_Harmony": {"HARMONY": 1500},
    "Run04_Hunt": {"HUNT": 1500},
    "Run05_Elation": {"ELATION": 1500},
    "Run06_Preservation": {"PRESERVATION": 1500},
    "Run07_Nihility": {"NIHILITY": 1500},
    "Run15_Trailblaze": {"TRAILBLAZE": 1500},
    "Run16_Remembrance": {"REMEMBRANCE": 1500},
}

# Гетерогенные прогоны.
# Настраиваем распределения (условные 1500 бакалавров, 120 магистров).
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
    },
    "Run17_All_Nine_Uniform": { # Все девять архетипов поровну
        "ERUDITION": 167, "ENIGMATA": 167, "HARMONY": 167,
        "HUNT": 167, "ELATION": 166, "PRESERVATION": 166,
        "NIHILITY": 167, "TRAILBLAZE": 166, "REMEMBRANCE": 167,
    },
    "Run18_Weighted_Random": { # Взвешенная смесь всех девяти архетипов
        "ERUDITION": 260, "ENIGMATA": 130, "HARMONY": 210,
        "HUNT": 150, "ELATION": 120, "PRESERVATION": 180,
        "NIHILITY": 100, "TRAILBLAZE": 190, "REMEMBRANCE": 160,
    },
}

ALL_RUNS = {**HOMOGENEOUS_RUNS, **HETEROGENEOUS_RUNS}
ARCHIVE_DIR = "scenarios_archive"
OUTPUT_ROOT = os.path.join("data", "v2-corrected")
BATCH_TIMINGS_FILE = os.path.join(OUTPUT_ROOT, "batch_timings.jsonl")
TIMINGS_LOCK = threading.Lock()


def _clickhouse_client():
    """Клиент ClickHouse для очистки частичных прогонов.

    Если зависимостей или БД нет, очистка пропускается: сам прогон от
    этого не должен падать.
    """
    try:
        import clickhouse_connect
        return clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            secure=os.getenv("CLICKHOUSE_SECURE", "False").lower()
            in ("true", "1", "yes"),
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[cleanup] ClickHouse недоступен: {exc}", flush=True)
        return None


def cleanup_scenario(scenario: str):
    """Удалить строки прошлых незавершённых попыток этого сценария.

    Маркер .done создаётся только после успешного завершения. Если его нет,
    значит, предыдущая попытка оборвалась (перезагрузка/падение), и её
    частичные строки нельзя смешивать с новым прогоном.
    """
    client = _clickhouse_client()
    if client is None:
        return

    try:
        result = client.query(
            "SELECT run_id FROM simulation_runs "
            "WHERE scenario_name = {scenario:String}",
            parameters={"scenario": scenario},
        )
        run_ids = [str(row[0]) for row in result.result_rows]
        existing = {
            row[0] for row in client.query(
                "SELECT name FROM system.tables WHERE database = currentDatabase()"
            ).result_rows
        }
        tables = [
            "agent_states", "agent_relations", "interactions",
            "agent_registry", "simulation_runs", "run_timings",
        ]
        for run_id in run_ids:
            for table in tables:
                if table not in existing:
                    continue
                client.command(
                    f"ALTER TABLE {table} DELETE WHERE run_id = '{run_id}' "
                    "SETTINGS mutations_sync = 1"
                )
        if run_ids:
            print(
                f"[cleanup] {scenario}: удалено частичных прогонов "
                f"{len(run_ids)}",
                flush=True,
            )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[cleanup] {scenario}: ошибка очистки: {exc}", flush=True)
    finally:
        try:
            client.close()
        except Exception:
            pass

def scaled_master_counts(counts: dict, total_mag: int = 120,
                         total_bac: int = 1500) -> dict:
    """Пропорционально распределить магистров, сохранив ровно total_mag.

    Старое `int(v * 0.08)` могло дать 117 мест вместо 120 и оставляло
    добор случайным архетипам. Для воспроизводимости распределяем
    остаток по наибольшим дробным частям.
    """
    if not counts:
        return {}
    total = sum(int(v) for v in counts.values())
    if total <= 0:
        return {}
    raw = {k: int(v) * total_mag / total for k, v in counts.items()}
    result = {k: int(value) for k, value in raw.items()}
    remainder = total_mag - sum(result.values())
    order = sorted(
        raw,
        key=lambda key: (raw[key] - result[key], key),
        reverse=True,
    )
    for key in order[:max(0, remainder)]:
        result[key] += 1
    return result


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
        "master_counts": scaled_master_counts(counts),
        "initial_relations_mode": mode,
        "semesters": 8,
        # CRC32 стабилен между процессами и платформами.
        "seed": zlib.crc32(scenario_name.encode("utf-8")) % 1000000
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

    return filepath

def append_batch_timing(payload: dict):
    """Дописать машинно-читаемую запись о времени сценария.

    `main.py` пишет подробный JSON по каждому запуску, а здесь
    фиксируется ещё и время оркестратора, включая очистку частичных
    строк. Это нужно для сравнения Python и будущего Rust-ядра.
    """
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False)
    with TIMINGS_LOCK:
        with open(BATCH_TIMINGS_FILE, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def run_simulation(config_path: str, is_test: bool = False,
                   force: bool = False, workers: int = 1):
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

    started_at = datetime.now().astimezone()
    cleanup_started = time.time()
    # Если маркера нет, предыдущая попытка оборвалась — убираем её
    # частичные строки, чтобы новый run_id не смешивался со старым.
    cleanup_scenario(scenario)
    cleanup_seconds = time.time() - cleanup_started

    python_bin = "./venv/bin/python" if os.path.exists("./venv/bin/python") else "python"
    cmd = [python_bin, "main.py", "--university", "--silent", "--scenario", config_path]
    if is_test:
        cmd.extend(["--semesters", "0", "--steps", "1"])

    print(f"[start] {scenario}", flush=True)
    started = time.time()

    # stdout каждого прогона идёт в отдельный лог, чтобы 8 параллельных
    # процессов не перемешивали прогресс и ошибки.
    env = os.environ.copy()
    env["SIM_WORKERS"] = str(workers)
    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        process.wait()

    elapsed_seconds = time.time() - started
    elapsed = elapsed_seconds / 60
    success = process.returncode == 0
    record = {
        "schema": "automata-run-timing/v1",
        "scenario": scenario,
        "implementation": "python-v2",
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "elapsed_minutes": round(elapsed, 3),
        "cleanup_seconds": round(cleanup_seconds, 3),
        "returncode": process.returncode,
        "success": success,
        "workers": workers,
        "log": log_path,
    }
    append_batch_timing(record)

    if not success:
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

    # Стабильный порядок волн: Run01..Run18, внутри — EMPTY/MIXED/RANDOM.
    tasks.sort(key=lambda path: os.path.basename(path))

    missing = [path for path in tasks if not os.path.exists(path)]
    if missing:
        print("ОШИБКА: отсутствуют сценарии:", *missing, sep="\n  ", file=sys.stderr)
        sys.exit(1)

    # Манифест фиксирует, что именно было запущено. Сиды берутся из архива.
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    manifest = {
        "created_at": datetime.now().isoformat(),
        "source": "v2-fixed",
        "scenario_count": len(tasks),
        "workers": args.workers,
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
            pool.submit(
                run_simulation, path, args.test, args.force, args.workers
            ): path
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
