from model.archetypes import ArchetypeEnum
class AgentStateDialog:
    def __init__(self, parent, agent, collective):
        import tkinter as tk
        from tkinter import ttk

        self.agent = agent
        self.collective = collective
        self.top = tk.Toplevel(parent)
        self.top.title(f"Агент: {agent.name}")
        self.top.geometry("600x600")

        notebook = ttk.Notebook(self.top)
        notebook.pack(fill='both', expand=True)

        # Вкладка Архетип и Чувствительность
        frame_arch = ttk.Frame(notebook)
        notebook.add(frame_arch, text="Архетип")

        tk.Label(frame_arch, text="Архетип:").pack(pady=5)
        self.archetype_var = tk.StringVar()
        self.combo = ttk.Combobox(frame_arch, textvariable=self.archetype_var, state="readonly")
        self.combo['values'] = [a.name for a in ArchetypeEnum]
        self.combo.set(agent.archetype.name)
        self.combo.pack(pady=5)

        tk.Label(frame_arch, text="Чувствительность:").pack(pady=5)
        self.sensitivity_scale = tk.Scale(frame_arch, from_=0, to=3, resolution=0.1, orient=tk.HORIZONTAL)
        self.sensitivity_scale.set(agent.sensitivity)
        self.sensitivity_scale.pack(pady=5, fill='x')

        # Вкладка Эмоции
        frame_emotions = ttk.Frame(notebook)
        notebook.add(frame_emotions, text="Эмоции")

        self.emotion_vars = {}
        for key, value in agent.get_emotions().items():
            tk.Label(frame_emotions, text=key).pack()
            scale = tk.Scale(frame_emotions, from_=-3, to=3, orient=tk.HORIZONTAL)
            scale.set(round(value))
            scale.pack(fill='x', padx=10)
            self.emotion_vars[key] = scale

        # Вкладка Отношения
        frame_relations = ttk.Frame(notebook)
        notebook.add(frame_relations, text="Отношения")

        tk.Label(frame_relations, text="Выберите агента:").pack(pady=5)
        self.other_agent_var = tk.StringVar()
        self.other_agent_combo = ttk.Combobox(frame_relations, textvariable=self.other_agent_var, state="readonly")
        self.other_agent_combo['values'] = [name for name in self.collective.agents if name != self.agent.name]
        self.other_agent_combo.pack(pady=5, fill='x', padx=10)
        self.other_agent_combo.bind("<<ComboboxSelected>>", self.load_relation_values)

        # Ползунки для предикатов
        tk.Label(frame_relations, text="Trust").pack()
        self.trust_scale = tk.Scale(frame_relations, from_=-10, to=10, orient=tk.HORIZONTAL)
        self.trust_scale.pack(fill='x', padx=10)

        tk.Label(frame_relations, text="Affinity").pack()
        self.affinity_scale = tk.Scale(frame_relations, from_=-10, to=10, orient=tk.HORIZONTAL)
        self.affinity_scale.pack(fill='x', padx=10)

        tk.Label(frame_relations, text="Utility").pack()
        self.utility_scale = tk.Scale(frame_relations, from_=-10, to=10, orient=tk.HORIZONTAL)
        self.utility_scale.pack(fill='x', padx=10)

        tk.Label(frame_relations, text="Responsiveness").pack()
        self.responsiveness_scale = tk.Scale(frame_relations, from_=-10, to=10, orient=tk.HORIZONTAL)
        self.responsiveness_scale.pack(fill='x', padx=10)

        # Кнопка сохранения
        btn_save = tk.Button(self.top, text="Сохранить", command=self.on_save)
        btn_save.pack(side='bottom', fill='x', pady=10)

    def load_relation_values(self, event):
        other = self.other_agent_var.get()
        if not other:
            return
        rel = self.agent.relations.get(other, {})
        self.trust_scale.set(rel.get('trust', 0))
        self.affinity_scale.set(rel.get('affinity', 0))
        self.utility_scale.set(rel.get('utility', 0))
        self.responsiveness_scale.set(rel.get('responsiveness', 0))

    def on_save(self):
        selected_arch = self.archetype_var.get()
        new_arch = next((a for a in ArchetypeEnum if a.name == selected_arch), None)
        if new_arch:
            self.agent.archetype = new_arch

        for key, scale in self.emotion_vars.items():
            self.agent.automaton.set_emotion(key, scale.get())

        self.agent.sensitivity = self.sensitivity_scale.get()

        other = self.other_agent_var.get()
        if other:
            if other not in self.agent.relations:
                self.agent.relations[other] = {}
            self.agent.relations[other]['trust'] = self.trust_scale.get()
            self.agent.relations[other]['affinity'] = self.affinity_scale.get()
            self.agent.relations[other]['utility'] = self.utility_scale.get()
            self.agent.relations[other]['responsiveness'] = self.responsiveness_scale.get()

        self.top.destroy()