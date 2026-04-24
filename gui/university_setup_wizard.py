import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import random
import sys
import os
from model.archetypes import ArchetypeEnum

class UniversitySetupWizard(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Инициализация Университета v6.7")
        self.geometry("550x750")
        self.result_config = None
        
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')
        
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.transient(parent)
        self.grab_set()
        
        self.create_widgets()
        self.update_remainders()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        header = tk.Label(main_frame, text="МГУ им. М.В. Ломоносова", font=("Times New Roman", 16, "bold"), fg="#1A237E")
        header.pack(pady=(0, 5))
        sub_header = tk.Label(main_frame, text="Коллектив Автоматов: Исследование Жизненного Цикла", font=("Arial", 9, "italic"))
        sub_header.pack(pady=(0, 10))

        btn_load = ttk.Button(main_frame, text="📁 ЗАГРУЗИТЬ ГОТОВЫЙ СЦЕНАРИЙ (JSON)", command=self.on_load_json)
        btn_load.pack(fill=tk.X, pady=(0, 15))

        group1 = ttk.LabelFrame(main_frame, text=" Глобальные параметры ", padding="10")
        group1.pack(fill=tk.X, pady=5)

        ttk.Label(group1, text="Начальный год:").grid(row=0, column=0, sticky=tk.W)
        self.year_var = tk.StringVar(value="2022")
        ttk.Entry(group1, textvariable=self.year_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=10)

        ttk.Label(group1, text="Сид (Seed):").grid(row=0, column=2, sticky=tk.W, padx=(20, 5))
        self.seed_var = tk.StringVar(value=str(random.randint(0, 999999)))
        ttk.Entry(group1, textvariable=self.seed_var, width=12).grid(row=0, column=3, sticky=tk.W)

        ttk.Label(group1, text="Шанс магистратуры:").grid(row=1, column=0, sticky=tk.W, pady=10)
        self.master_var = tk.DoubleVar(value=0.3)
        self.master_slider = ttk.Scale(group1, from_=0.0, to=1.0, variable=self.master_var, orient=tk.HORIZONTAL)
        self.master_slider.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=10)
        self.lbl_master = ttk.Label(group1, text="30%")
        self.lbl_master.grid(row=1, column=3)
        self.master_var.trace_add("write", lambda *a: self.lbl_master.config(text=f"{int(self.master_var.get()*100)}%"))

        # 2. Лимиты мест (v6.9.27)
        self.total_bac = 1500
        self.total_mag = 120
        
        group_cap = ttk.LabelFrame(main_frame, text=" Лимиты мест (Cap) ", padding="10")
        group_cap.pack(fill=tk.X, pady=5)
        
        ttk.Label(group_cap, text="Бакалавриат:").grid(row=0, column=0, sticky=tk.W)
        self.total_bac_var = tk.StringVar(value="1500")
        ent_tb = ttk.Entry(group_cap, textvariable=self.total_bac_var, width=8)
        ent_tb.grid(row=0, column=1, padx=5)
        ent_tb.bind("<KeyRelease>", lambda e: self.on_cap_change())
        
        ttk.Label(group_cap, text="Магистратура:").grid(row=0, column=2, sticky=tk.W, padx=(20, 5))
        self.total_mag_var = tk.StringVar(value="120")
        ent_tm = ttk.Entry(group_cap, textvariable=self.total_mag_var, width=8)
        ent_tm.grid(row=0, column=3, padx=5)
        ent_tm.bind("<KeyRelease>", lambda e: self.on_cap_change())

        # 3. Состав Агентов
        self.group_bac = ttk.LabelFrame(main_frame, text=f" БАКАЛАВРИАТ (Мест: {self.total_bac}) ", padding="10")
        self.group_bac.pack(fill=tk.X, pady=5)
        self.bac_entries = {}
        entry_bac = ttk.Frame(self.group_bac)
        entry_bac.pack(fill=tk.X)
        for i, arch in enumerate(ArchetypeEnum):
            row, col = i // 3, (i % 3) * 2
            ttk.Label(entry_bac, text=f"{arch.localized[:5]}.:").grid(row=row, column=col, sticky=tk.W, padx=2)
            ent = ttk.Entry(entry_bac, width=6)
            ent.insert(0, "0")
            ent.grid(row=row, column=col+1, padx=4, pady=2)
            ent.bind("<KeyRelease>", lambda e: self.update_remainders())
            self.bac_entries[arch.name] = ent

        self.group_mag = ttk.LabelFrame(main_frame, text=f" МАГИСТРАТУРА (Мест: {self.total_mag}) ", padding="10")
        self.group_mag.pack(fill=tk.X, pady=5)
        self.mag_entries = {}
        entry_mag = ttk.Frame(self.group_mag)
        entry_mag.pack(fill=tk.X)
        for i, arch in enumerate(ArchetypeEnum):
            row, col = i // 3, (i % 3) * 2
            ttk.Label(entry_mag, text=f"{arch.localized[:5]}.:").grid(row=row, column=col, sticky=tk.W, padx=2)
            ent = ttk.Entry(entry_mag, width=6)
            ent.insert(0, "0")
            ent.grid(row=row, column=col+1, padx=4, pady=2)
            ent.bind("<KeyRelease>", lambda e: self.update_remainders())
            self.mag_entries[arch.name] = ent

        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=5)
        self.lbl_rem = tk.Label(info_frame, text="", font=("Arial", 9, "bold"))
        self.lbl_rem.pack(side=tk.LEFT)
        tk.Label(info_frame, text="(Остаток заполнится случайно)", font=("Arial", 8, "italic"), fg="gray").pack(side=tk.RIGHT)

        btn_start = tk.Button(main_frame, text="ВСТУПИТЬ В УЧЕБНЫЙ ГОД", command=self.on_start, 
                                font=("Arial", 11, "bold"), bg="#2E7D32", fg="white", pady=10)
        btn_start.pack(fill=tk.X, pady=15)

    def on_cap_change(self):
        try:
            val_b = self.total_bac_var.get()
            val_m = self.total_mag_var.get()
            self.total_bac = int(val_b) if val_b.isdigit() else 0
            self.total_mag = int(val_m) if val_m.isdigit() else 0
            self.group_bac.config(text=f" БАКАЛАВРИАТ (Мест: {self.total_bac}) ")
            self.group_mag.config(text=f" МАГИСТРАТУРА (Мест: {self.total_mag}) ")
            self.update_remainders()
        except Exception:
            pass

    def update_remainders(self):
        try:
            b_total = sum(int(e.get() or 0) for e in self.bac_entries.values())
            m_total = sum(int(e.get() or 0) for e in self.mag_entries.values())
            b_rem = self.total_bac - b_total
            m_rem = self.total_mag - m_total
            text = f"Бак: {b_total}/{self.total_bac} (Ост: {b_rem}) | Маг: {m_total}/{self.total_mag} (Ост: {m_rem})"
            color = "black" if (b_rem >= 0 and m_rem >= 0) else "red"
            self.lbl_rem.config(text=text, fg=color)
        except ValueError:
            self.lbl_rem.config(text="Ошибка ввода", fg="red")

    def on_load_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path: return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if "seed" in data: self.seed_var.set(str(data["seed"]))
            if "total_bac" in data: self.total_bac_var.set(str(data["total_bac"]))
            if "total_mag" in data: self.total_mag_var.set(str(data["total_mag"]))
            self.on_cap_change()
            counts = data.get("bachelor_counts") or data.get("agent_counts")
            if counts:
                for arch_name, count in counts.items():
                    if arch_name in self.bac_entries:
                        self.bac_entries[arch_name].delete(0, tk.END); self.bac_entries[arch_name].insert(0, str(count))
            m_counts = data.get("master_counts")
            if m_counts:
                for arch_name, count in m_counts.items():
                    if arch_name in self.mag_entries:
                        self.mag_entries[arch_name].delete(0, tk.END); self.mag_entries[arch_name].insert(0, str(count))
            self.update_remainders()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить файл: {e}")

    def on_start(self):
        try:
            b_counts = {n: int(e.get() or 0) for n, e in self.bac_entries.items()}
            m_counts = {n: int(e.get() or 0) for n, e in self.mag_entries.items()}
            self.result_config = {
                "start_year": int(self.year_var.get()),
                "master_chance": self.master_var.get(),
                "bachelor_counts": b_counts,
                "master_counts": m_counts,
                "total_bac": self.total_bac,
                "total_mag": self.total_mag,
                "seed": int(self.seed_var.get() if self.seed_var.get().isdigit() else random.randint(0, 999999))
            }
            self.destroy()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка во вводе: {e}")

    def on_cancel(self):
        sys.exit(0)
