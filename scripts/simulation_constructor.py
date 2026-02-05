import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import sys
import subprocess
from enum import Enum
import random
import numpy as np

# Добавляем корневую директорию проекта в path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from model.archetypes import ArchetypeEnum

class SimulationConstructor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Research Constructor: Agent Simulation v4.8")
        self.geometry("600x800")
        
        self.params = {
            "total_agents": 1875,
            "agent_counts": {arch.name: 0 for arch in ArchetypeEnum},
            "emotion_dist": "Uniform", # Uniform or Normal
            "emotion_params": {"min": -3.0, "max": 3.0, "mean": 0.0, "std": 1.0},
            "steps": 100,
            "seed": random.randint(0, 1000000),
            "silent_mode": False
        }
        
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

        self.silent_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sim_frame, text="Silent Mode (Без GUI, только расчет)", variable=self.silent_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        # 4. Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(btn_frame, text="Сохранить сценарий (JSON)", command=self.save_scenario).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(btn_frame, text="ЗАПУСТИТЬ ИССЛЕДОВАНИЕ", command=self.run_simulation, style="Accent.TButton").pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

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
            
        if self.params["silent_mode"]:
            # Запуск Headless скрипта
            messagebox.showinfo("Silent Mode", "Запускается высокоскоростной расчет.\nРезультаты будут в 'data/output/agent_states.csv' и 'data/output/interaction_log.csv'.\n\nМожете закрыть это окно или оставить его для новых сценариев.")
            headless_path = os.path.join(os.path.dirname(__file__), "run_headless.py")
            subprocess.Popen([sys.executable, headless_path, config_path])
        else:
            # Запуск обычной GUI симуляции с предзагруженным конфигом
            gui_path = os.path.join(os.path.dirname(__file__), "run_research_gui.py")
            subprocess.Popen([sys.executable, gui_path, config_path])

if __name__ == "__main__":
    app = SimulationConstructor()
    app.mainloop()
