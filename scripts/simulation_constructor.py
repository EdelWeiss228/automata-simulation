import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import sys
import subprocess
from enum import Enum
import random
import numpy as np
import threading
import re

# Добавляем корневую директорию проекта в path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from model.archetypes import ArchetypeEnum

class SimulationConstructor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Конструктор симуляции (V5.2 High-Perf Core)")
        self.geometry("600x650")
        
        self.params = {
            "total_agents": 1875,
            "agent_counts": {arch.name: 0 for arch in ArchetypeEnum},
            "emotion_dist": "Uniform", # Uniform or Normal
            "emotion_params": {"min": -3.0, "max": 3.0, "mean": 0.0, "std": 1.0},
            "steps": 100,
            "seed": random.randint(0, 1000000),
            "silent_mode": True
        }
        
        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="Готов к запуску")
        
        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(top_frame, text="Макс. количество агентов (N):", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        self.total_entry = ttk.Entry(top_frame, width=10)
        self.total_entry.insert(0, str(self.params["total_agents"]))
        self.total_entry.pack(side=tk.LEFT, padx=5)
        self.total_entry.bind("<KeyRelease>", lambda e: self.update_remainder_label())

        self.remainder_label = ttk.Label(top_frame, text="", foreground="blue")
        self.remainder_label.pack(side=tk.LEFT, padx=5)
# 1. Archetype Distribution
        ttk.Label(main_frame, text="1. Состав Агентов (Архетипы)", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=(0, 5))
        
        arch_frame = ttk.Frame(main_frame)
        arch_frame.pack(fill=tk.X, pady=5)
        
        self.arch_entries = {}
        for i, arch in enumerate(ArchetypeEnum):
            row = i // 2
            col = (i % 2) * 2
            ttk.Label(arch_frame, text=f"{arch.name}:").grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)
            entry = ttk.Entry(arch_frame, width=10)
            entry.insert(0, str(self.params["agent_counts"].get(arch.name, 0)))
            entry.grid(row=row, column=col+1, sticky=tk.W, padx=5, pady=2)
            entry.bind("<KeyRelease>", lambda e: self.update_remainder_label())
            self.arch_entries[arch.name] = entry
        
        self.update_remainder_label()

        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # 2. Emotion Probability Distribution
        ttk.Label(main_frame, text="2. Распределение Эмоций", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=5)
        
        dist_frame = ttk.Frame(main_frame)
        dist_frame.pack(fill=tk.X, pady=5)
        
        self.dist_var = tk.StringVar(value=self.params["emotion_dist"])
        ttk.Radiobutton(dist_frame, text="Uniform (Равномерное)", variable=self.dist_var, value="Uniform", command=self.update_dist_ui).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(dist_frame, text="Normal (Гауссово)", variable=self.dist_var, value="Normal", command=self.update_dist_ui).pack(side=tk.LEFT, padx=10)

        self.params_frame = ttk.Frame(main_frame)
        self.params_frame.pack(fill=tk.X, pady=5)
        self.update_dist_ui()

        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # 3. Global Constants & Simulation Params
        ttk.Label(main_frame, text="3. Параметры симуляции", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=5)
        
        sim_frame = ttk.Frame(main_frame)
        sim_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(sim_frame, text="Шагов (Дней):").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.steps_entry = ttk.Entry(sim_frame, width=10)
        self.steps_entry.insert(0, str(self.params["steps"]))
        self.steps_entry.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(sim_frame, text="Seed (Случайное зерно):").grid(row=1, column=0, sticky=tk.W, padx=5)
        self.seed_entry = ttk.Entry(sim_frame, width=10)
        self.seed_entry.insert(0, str(self.params["seed"]))
        self.seed_entry.grid(row=1, column=1, sticky=tk.W, padx=5)

        self.silent_var = tk.BooleanVar(value=True)
        # Checkbutton removed as per user request to avoid "slop" and enforce silent simulation by default

        # 4. Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(btn_frame, text="Сохранить сценарий (JSON)", command=self.save_scenario).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.run_btn = ttk.Button(btn_frame, text="ЗАПУСТИТЬ ИССЛЕДОВАНИЕ", command=self.run_simulation)
        self.run_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # 5. Progress Section
        progress_frame = ttk.LabelFrame(main_frame, text="Прогресс выполнения", padding="10")
        progress_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(progress_frame, textvariable=self.status_var).pack(anchor=tk.W)
        self.progressbar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progressbar.pack(fill=tk.X, pady=5)

    def update_remainder_label(self):
        try:
            total = int(self.total_entry.get() if self.total_entry.get() else 0)
            assigned = sum(int(e.get() if e.get() else 0) for e in self.arch_entries.values())
            remainder = total - assigned
            if remainder >= 0:
                self.remainder_label.config(text=f"(Случайный остаток: {remainder})", foreground="blue")
            else:
                self.remainder_label.config(text=f"(ПЕРЕБОР: {abs(remainder)}!)", foreground="red")
        except ValueError:
            self.remainder_label.config(text="(Ошибка ввода!)", foreground="red")

    def update_dist_ui(self):
        for widget in self.params_frame.winfo_children():
            widget.destroy()
            
        if self.dist_var.get() == "Uniform":
            ttk.Label(self.params_frame, text="Min (-3 to 3):").grid(row=0, column=0)
            self.min_entry = ttk.Entry(self.params_frame, width=7)
            self.min_entry.insert(0, "-3.0")
            self.min_entry.grid(row=0, column=1, padx=5)
            
            ttk.Label(self.params_frame, text="Max (-3 to 3):").grid(row=0, column=2)
            self.max_entry = ttk.Entry(self.params_frame, width=7)
            self.max_entry.insert(0, "3.0")
            self.max_entry.grid(row=0, column=3, padx=5)
        else:
            ttk.Label(self.params_frame, text="Mean (Среднее):").grid(row=0, column=0)
            self.mean_entry = ttk.Entry(self.params_frame, width=7)
            self.mean_entry.insert(0, "0.0")
            self.mean_entry.grid(row=0, column=1, padx=5)
            
            ttk.Label(self.params_frame, text="Std Dev (Отклонение):").grid(row=0, column=2)
            self.std_entry = ttk.Entry(self.params_frame, width=7)
            self.std_entry.insert(0, "1.0")
            self.std_entry.grid(row=0, column=3, padx=5)

    def collect_params(self):
        try:
            self.params["total_agents"] = int(self.total_entry.get())
            for arch in ArchetypeEnum:
                self.params["agent_counts"][arch.name] = int(self.arch_entries[arch.name].get())
            
            self.params["emotion_dist"] = self.dist_var.get()
            if self.params["emotion_dist"] == "Uniform":
                self.params["emotion_params"]["min"] = float(self.min_entry.get())
                self.params["emotion_params"]["max"] = float(self.max_entry.get())
            else:
                self.params["emotion_params"]["mean"] = float(self.mean_entry.get())
                self.params["emotion_params"]["std"] = float(self.std_entry.get())
            
            self.params["steps"] = int(self.steps_entry.get())
            self.params["seed"] = int(self.seed_entry.get())
            self.params["silent_mode"] = self.silent_var.get()
            return True
        except ValueError as e:
            messagebox.showerror("Ошибка ввода", f"Пожалуйста, введите корректные числовые значения.\n{e}")
            return False

    def save_scenario(self):
        if self.collect_params():
            initial_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "scenarios")
            os.makedirs(initial_dir, exist_ok=True)
            file_path = filedialog.asksaveasfilename(
                initialdir=initial_dir,
                defaultextension=".json", 
                filetypes=[("JSON files", "*.json")]
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.params, f, indent=4, ensure_ascii=False)
                messagebox.showinfo("Успех", f"Сценарий сохранен в {file_path}")

    def run_simulation(self):
        if not self.collect_params():
            return
            
        # Сохраняем временный конфиг
        config_path = os.path.join(os.path.dirname(__file__), "temp_scenario.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(self.params, f, indent=4, ensure_ascii=False)
            
        main_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")
        
        # Сбрасываем прогресс и отключаем кнопку
        self.progress_var.set(0)
        self.status_var.set("Запуск процесса...")
        self.run_btn.config(state=tk.DISABLED)
        
        cmd = [sys.executable, main_path, "--scenario", config_path, "--silent"]
        
        def monitor_process():
            try:
                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                total_steps = self.params["steps"]
                
                for line in process.stdout:
                    line = line.strip()
                    if not line: continue
                    
                    # Парсинг инициализации связей (0-20% бара)
                    init_match = re.search(r"Подготовка связей: (\d+)%", line)
                    if init_match:
                        perc = int(init_match.group(1))
                        self.after(0, lambda p=perc: (self.progress_var.set(p * 0.2), self.status_var.set(f"Инициализация мира: {p}%")))
                        continue
                        
                    # Парсинг шагов (20-100% бара)
                    step_match = re.search(r"Шаг (\d+)/(\d+)", line)
                    if step_match:
                        cur = int(step_match.group(1))
                        tot = int(step_match.group(2))
                        progress = 20 + (cur / tot) * 80
                        self.after(0, lambda pr=progress, c=cur, t=tot: (self.progress_var.set(pr), self.status_var.set(f"Симуляция: Шаг {c}/{t}")))
                        continue
                        
                    # Статусные сообщения
                    if "РАСЧЕТ ЗАВЕРШЕН" in line:
                        self.after(0, lambda: (self.progress_var.set(100), self.status_var.set("Расчет успешно завершен")))
                    elif "Инициализация связей для" in line:
                        self.after(0, lambda: self.status_var.set("Подготовка графа отношений..."))

                process.wait()
                if process.returncode == 0:
                    self.after(0, lambda: self.status_var.set("Готово. Результаты в data/output/"))
                else:
                    self.after(0, lambda rc=process.returncode: self.status_var.set(f"Ошибка выполнения (код {rc})"))
                    
            except Exception as e:
                self.after(0, lambda err=str(e): self.status_var.set(f"Ошибка: {err}"))
            finally:
                self.after(0, lambda: self.run_btn.config(state=tk.NORMAL))

        # Запускаем мониторинг в отдельном потоке
        threading.Thread(target=monitor_process, daemon=True).start()

if __name__ == "__main__":
    app = SimulationConstructor()
    app.mainloop()
