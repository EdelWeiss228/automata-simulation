"""Быстрый тест ротации: создаем коллектив, перематываем на июнь, 
проходим до июля и проверяем что ротация работает."""
import sys, os, datetime, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from model.university_collective import UniversityCollective
from model.simulation_session import SimulationSession

with open("scenarios_archive/Run03_Harmony_MIXED.json") as f:
    cfg = json.load(f)

print("=== ТЕСТ РОТАЦИИ ===", flush=True)
print("Создаем коллектив...", flush=True)

univ = UniversityCollective(seed=cfg.get("seed", 42), config=cfg)
session = SimulationSession(collective=univ, run_name="TEST_ROTATION", description="Test rotation", scenario_name="TEST_Rotation")

# Перематываем дату на 25 июня
univ.current_date = datetime.date(2025, 6, 25)
univ.current_step = 280
print(f"Дата перемотана на: {univ.current_date}", flush=True)
print(f"Количество агентов: {len(univ.agents)}", flush=True)

# Запускаем по дням
start = time.time()
days_done = 0
try:
    for d in range(15):
        session.run_day()
        days_done += 1
        elapsed = time.time() - start
        print(f"  День {d+1}/15 ({univ.current_date}) — {elapsed:.1f}с (агентов: {len(univ.agents)})", flush=True)
except Exception as e:
    import traceback
    print(f"\n!!! ОШИБКА на дне {days_done+1}: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

elapsed = time.time() - start
print(f"\n=== ТЕСТ ПРОЙДЕН за {elapsed:.1f}с ===", flush=True)
print(f"Скорость: {elapsed/days_done:.1f}с на день", flush=True)
print(f"Итого агентов: {len(univ.agents)}", flush=True)
