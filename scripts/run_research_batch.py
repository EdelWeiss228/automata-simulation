import os
import sys
import json
import subprocess
import time
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

def generate_config(run_id: str, mode: str, counts: dict) -> str:
    scenario_name = f"{run_id}_{mode}"
    config = {
        "scenario_name": scenario_name,
        "run_name": run_id,
        "description": f"Research Batch. Archetype Dist: {run_id}. Relations Mode: {mode}",
        "bachelor_counts": counts,
        "master_counts": {k: max(1, int(v * 0.08)) for k, v in counts.items()} if counts else {},
        "initial_relations_mode": mode,
        "semesters": 8,
        "seed": hash(scenario_name) % 1000000 # Фиксируем seed для воспроизводимости (до миллиона для C++)
    }
    
    filepath = os.path.join(ARCHIVE_DIR, f"{scenario_name}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
        
    return filepath

def run_simulation(config_path: str, is_test: bool = False):
    python_bin = "./venv/bin/python" if os.path.exists("./venv/bin/python") else "python"
    
    cmd = [python_bin, "main.py", "--university", "--silent", "--scenario", config_path]
    if is_test:
        cmd.extend(["--semesters", "0"]) # В тестовом режиме 0 семестров (или минимально)
        cmd.extend(["--steps", "1"])
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Выполнение: {' '.join(cmd)}")
    
    # Запускаем как subprocess, ждем завершения
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    
    for line in process.stdout:
        if "System" in line or "АКАДЕМИЧЕСКАЯ РОТАЦИЯ" in line or "[Progress]" in line:
            sys.stdout.write("  " + line)
            sys.stdout.flush()
            
    process.wait()
    
    if process.returncode != 0:
        print(f"Ошибка при выполнении {config_path}")
        print(process.stderr.read())
        return False
    return True

def main():
    import argparse
    from multiprocessing import Pool
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Запустить по 1 шагу для проверки работоспособности")
    parser.add_argument("--workers", type=int, default=10, help="Количество параллельных процессов")
    args = parser.parse_args()

    # Собираем все задачи в список
    tasks = []
    for run_id, counts in ALL_RUNS.items():
        for mode in RELATION_MODES:
            config_path = generate_config(run_id, mode, counts)
            tasks.append((config_path, args.test))

    print(f"Начинаем серию из {len(tasks)} симуляций в {args.workers} потоках...")
    
    start_time = time.time()
    
    # Запускаем пул воркеров
    with Pool(processes=args.workers) as pool:
        results = pool.starmap(run_simulation, tasks)
    
    if all(results):
        elapsed = time.time() - start_time
        print(f"\nВсе симуляции успешно завершены за {elapsed/60:.2f} минут.")
    else:
        print("\nОШИБКА: Некоторые симуляции завершились неудачно.")
        sys.exit(1)

if __name__ == "__main__":
    main()
