import os
import subprocess
import csv

def get_file_hash(filepath):
    import hashlib
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def run_and_save(run_id):
    os.system("python3 run_test_sim.py")
    # Переименовываем результаты
    os.rename("baseline_snapshot_states.csv", f"check_states_{run_id}.csv")
    os.rename("baseline_snapshot_interactions.csv", f"check_interactions_{run_id}.csv")

if __name__ == "__main__":
    print("Запуск первой итерации...")
    run_and_save(1)
    print("Запуск второй итерации...")
    run_and_save(2)
    
    match_s = get_file_hash("check_states_1.csv") == get_file_hash("check_states_2.csv")
    match_i = get_file_hash("check_interactions_1.csv") == get_file_hash("check_interactions_2.csv")
    
    if match_s and match_i:
        print("\nИТОГ: Модель полностью ДЕТЕРМИНИРОВАНА.")
        print("Хеши файлов совпали на 100%.")
    else:
        print("\nКРИТИЧНАЯ ОШИБКА: Модель НЕ детерминирована!")
        if not match_s: print("- Различия в состояниях агентов.")
        if not match_i: print("- Различия во взаимодействиях.")
