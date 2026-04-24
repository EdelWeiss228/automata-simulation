import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys
import random

# Добавляем корневую директорию проекта в path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from model.archetypes import ArchetypeEnum

class UniversityConstructor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Архитектор Университета: Конструктор Сценария v6.4")
        self.geometry("750x700")
        
        self.params = {
            "start_year": 2024,
            "semesters": 8,
            "master_chance": 0.3,
            "archetype_distribution": {arch.name: 1.0 for arch in ArchetypeEnum},
            "avg_sensitivity": 1.5,
            "skip_prob": 0.15
        }
        
        self.create_widgets()

    def create_widgets(self):
        # Основной контейнер с прокруткой если нужно (Canvas + Frame)
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- ЗАГОЛОВОК ---
        header = ttk.Label(main_frame, text="Настройка Академического Среза", font=("Helvetica", 16, "bold"))
        header.pack(pady=(0, 15))

        # --- 1. АКАДЕМИЧЕСКИЕ ПАРАМЕТРЫ ---
        ac_frame = ttk.LabelFrame(main_frame, text=" 1. Академические параметры ", padding="10")
        ac_frame.pack(fill=tk.X, pady=5)

        # Стартовый год
        ttk.Label(ac_frame, text="Начало симуляции (год):").grid(row=0, column=0, sticky=tk.W)
        self.year_entry = ttk.Entry(ac_frame, width=10)
        self.year_entry.insert(0, str(self.params["start_year"]))
        self.year_entry.grid(row=0, column=1, padx=5, pady=5)

        # Вероятность магистратуры
        ttk.Label(ac_frame, text="Шанс преемственности (0.0 - 1.0):").grid(row=1, column=0, sticky=tk.W)
        self.master_slider = ttk.Scale(ac_frame, from_=0.0, to=1.0, orient=tk.HORIZONTAL)
        self.master_slider.set(self.params["master_chance"])
        self.master_slider.grid(row=1, column=1, sticky=tk.EW, padx=5)
        self.master_val_lbl = ttk.Label(ac_frame, text="0.3")
        self.master_val_lbl.grid(row=1, column=2)
        self.master_slider.configure(command=lambda v: self.master_val_lbl.configure(text=f"{float(v):.2f}"))

        # --- 2. РАСПРЕДЕЛЕНИЕ АРХЕТИПОВ ---
        arch_frame = ttk.LabelFrame(main_frame, text=" 2. Профиль Коллектива (Веса Архетипов) ", padding="10")
        arch_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(arch_frame, text="Настройте вероятности выпадения архетипов при генерации студентов:", font=("Arial", 9, "italic")).pack(pady=(0,5))
        
        entry_container = ttk.Frame(arch_frame)
        entry_container.pack(fill=tk.X)
        
        self.arch_vars = {}
        for i, arch in enumerate(ArchetypeEnum):
            row = i // 3
            col = (i % 3) * 2
            ttk.Label(entry_container, text=f"{arch.name}:").grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)
            var = tk.DoubleVar(value=1.0)
            ent = ttk.Entry(entry_container, textvariable=var, width=5)
            ent.grid(row=row, column=col+1, sticky=tk.W, padx=5, pady=2)
            self.arch_vars[arch.name] = var

        # Кнопки пресетов
        preset_frame = ttk.Frame(arch_frame)
        preset_frame.pack(pady=10)
        ttk.Button(preset_frame, text="Технический (ПМИ)", command=self.preset_tech).pack(side=tk.LEFT, padx=5)
        ttk.Button(preset_frame, text="Гуманитарный", command=self.preset_human).pack(side=tk.LEFT, padx=5)
        ttk.Button(preset_frame, text="Сбалансированный", command=self.preset_reset).pack(side=tk.LEFT, padx=5)

        # --- 3. ИНФОРМАЦИЯ О СЦЕНАРИИ ---
        info_frame = ttk.LabelFrame(main_frame, text=" 3. Сводка Сценария ", padding="10")
        info_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.info_text = tk.Text(info_frame, height=10, font=("Courier", 10), background="#f0f0f0")
        self.info_text.pack(fill=tk.BOTH, expand=True)
        self.update_info_summary()

        # Кнопки действий
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="Обновить статистику", command=self.update_info_summary).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Сохранить Сценарий", command=self.save_scenario).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="ЗАПУСТИТЬ УНИВЕРСИТЕТ", command=self.launch_sim, style="Accent.TButton").pack(side=tk.RIGHT, padx=5)

    def preset_tech(self):
        for name, var in self.arch_vars.items():
            if name in ["ERUDITION", "HUNT"]: var.set(5.0)
            else: var.set(1.0)
        self.update_info_summary()

    def preset_human(self):
        for name, var in self.arch_vars.items():
            if name in ["HARMONY", "ENIGMATA"]: var.set(5.0)
            else: var.set(1.0)
        self.update_info_summary()

    def preset_reset(self):
        for var in self.arch_vars.values(): var.set(1.0)
        self.update_info_summary()

    def update_info_summary(self):
        start_y = self.year_entry.get()
        m_prob = self.master_slider.get()
        
        summary = f"СЦЕНАРИЙ УНИВЕРСИТЕТА v6.4\n"
        summary += f"===========================\n"
        summary += f"Период: {start_y} - {int(start_y)+4} (8 семестров)\n"
        summary += f"Бакалавриат: 5 факультетов, 4 курса, ~1500 агентов\n"
        summary += f"Магистратура: 6 направлений, 2 курса, ~120 агентов\n"
        summary += f"Вероятность продолжения: {m_prob*100:.1f}%\n"
        summary += f"---------------------------\n"
        summary += f"Структура групп:\n"
        summary += f"- Бакалавриат: 25 чел/группа (П, Ф, Р, М, Эк)\n"
        summary += f"- Магистратура: 10 чел/группа (ММ, ПМ, ПО, ЭкМ, РМ, ГП)\n"
        
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, summary)

    def save_scenario(self):
        data = {
            "start_year": int(self.year_entry.get()),
            "master_chance": self.master_slider.get(),
            "archetype_weights": {n: v.get() for n, v in self.arch_vars.items()}
        }
        with open("scenario_university.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        messagebox.showinfo("Успех", "Сценарий сохранен в scenario_university.json")

    def launch_sim(self):
        self.save_scenario()
        messagebox.showinfo("Запуск", "Симуляция университета запускается с вашими параметрами...")
        # Логика запуска через subprocess (аналог main.py --university --scenario ...)
        subprocess.Popen([sys.executable, "main.py", "--university", "--scenario", "scenario_university.json"])

if __name__ == "__main__":
    app = UniversityConstructor()
    # Пытаемся применить стиль если есть
    try:
        style = ttk.Style()
        style.theme_use('clam')
    except: pass
    app.mainloop()
