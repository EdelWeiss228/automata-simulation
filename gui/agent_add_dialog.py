import tkinter as tk
from tkinter import simpledialog, messagebox, ttk
from model.archetypes import ArchetypeEnum
from model.agent import Agent

class AgentAddDialog:
    def __init__(self, parent, collective):
        self.parent = parent
        self.collective = collective
        self.top = tk.Toplevel(parent)
        self.top.title("Добавить агента")
        self.top.geometry("600x600")
        self.agent_added = False
        self.agent_name = None

        notebook = ttk.Notebook(self.top)
        notebook.pack(fill='both', expand=True)

        # Вкладка Основное
        frame_main = ttk.Frame(notebook)
        notebook.add(frame_main, text="Основное")

        tk.Label(frame_main, text="Имя агента:").pack()
        self.entry_name = tk.Entry(frame_main)
        self.entry_name.pack()

        tk.Label(frame_main, text="Архетип:").pack()
        self.archetype_var = tk.StringVar()
        self.combo = ttk.Combobox(frame_main, textvariable=self.archetype_var, state="readonly")
        self.combo['values'] = [a.name for a in ArchetypeEnum]
        self.combo.pack()

        tk.Label(frame_main, text="Чувствительность:").pack()
        self.sensitivity_scale = tk.Scale(frame_main, from_=0, to=3, resolution=0.1, orient=tk.HORIZONTAL)
        self.sensitivity_scale.set(1.0)
        self.sensitivity_scale.pack(fill='x', padx=10)

        # Вкладка Эмоции
        frame_emotions = ttk.Frame(notebook)
        notebook.add(frame_emotions, text="Эмоции")

        self.emotion_vars = {}
        emotion_keys = [
            "joy_sadness", "fear_calm", "anger_humility",
            "disgust_acceptance", "surprise_habit",
            "shame_confidence", "openness_alienation"
        ]
        for key in emotion_keys:
            tk.Label(frame_emotions, text=key).pack()
            scale = tk.Scale(frame_emotions, from_=-3, to=3, orient=tk.HORIZONTAL)
            scale.set(0)
            scale.pack(fill='x', padx=10)
            self.emotion_vars[key] = scale

        # Вкладка Предикаты
        frame_predicates = ttk.Frame(notebook)
        notebook.add(frame_predicates, text="Предикаты")

        # Индивидуальные отношения с каждым агентом, как в AgentStateDialog
        self.relations = {}
        tk.Label(frame_predicates, text="Выберите агента:").pack(pady=5)
        self.other_agent_var = tk.StringVar()
        self.other_agent_combo = ttk.Combobox(frame_predicates, textvariable=self.other_agent_var, state="readonly")
        self.other_agent_combo['values'] = list(self.collective.agents.keys())
        self.other_agent_combo.pack(pady=5, fill='x', padx=10)
        self.other_agent_combo.bind("<<ComboboxSelected>>", self.load_add_relations)

        tk.Label(frame_predicates, text="Trust").pack()
        self.trust_scale = tk.Scale(frame_predicates, from_=-10, to=10, orient=tk.HORIZONTAL)
        self.trust_scale.pack(fill='x', padx=10)

        tk.Label(frame_predicates, text="Affinity").pack()
        self.affinity_scale = tk.Scale(frame_predicates, from_=-10, to=10, orient=tk.HORIZONTAL)
        self.affinity_scale.pack(fill='x', padx=10)

        tk.Label(frame_predicates, text="Utility").pack()
        self.utility_scale = tk.Scale(frame_predicates, from_=-10, to=10, orient=tk.HORIZONTAL)
        self.utility_scale.pack(fill='x', padx=10)

        tk.Label(frame_predicates, text="Responsiveness").pack()
        self.responsiveness_scale = tk.Scale(frame_predicates, from_=-10, to=10, orient=tk.HORIZONTAL)
        self.responsiveness_scale.pack(fill='x', padx=10)

        # Кнопка Добавить
        tk.Button(self.top, text="Добавить", command=self.on_add).pack(side='bottom', fill='x', pady=10)

    def on_add(self):
        name = self.entry_name.get().strip()
        if not name:
            messagebox.showerror("Ошибка", "Имя агента не может быть пустым")
            return
        if name in self.collective.agents:
            messagebox.showerror("Ошибка", "Агент с таким именем уже существует")
            return
        archetype_name = self.archetype_var.get()
        archetype_enum = next((a for a in ArchetypeEnum if a.name == archetype_name), None)
        if not archetype_enum:
            messagebox.showerror("Ошибка", "Выберите корректный архетип")
            return

        emotions = {key: scale.get() for key, scale in self.emotion_vars.items()}
        sensitivity = self.sensitivity_scale.get()

        # Сохраняем текущее выбранное отношение, если что-то выбрано
        other = self.other_agent_var.get()
        if other:
            self.relations[other] = {
                'trust': self.trust_scale.get(),
                'affinity': self.affinity_scale.get(),
                'utility': self.utility_scale.get(),
                'responsiveness': self.responsiveness_scale.get(),
            }

        agent_obj = Agent(
            name,
            archetype=archetype_enum,
            sensitivity=sensitivity,
            emotions=emotions
        )
        for other, rel in self.relations.items():
            agent_obj.relations[other] = rel.copy()
        self.collective.add_agent(agent_obj)
        self.agent_added = True
        self.agent_name = name
        self.top.destroy()

    def load_add_relations(self, event):
        other = self.other_agent_var.get()
        if not other:
            return
        rel = self.relations.get(other, {})
        self.trust_scale.set(rel.get('trust', 0))
        self.affinity_scale.set(rel.get('affinity', 0))
        self.utility_scale.set(rel.get('utility', 0))
        self.responsiveness_scale.set(rel.get('responsiveness', 0))