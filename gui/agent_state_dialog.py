from model.archetypes import ArchetypeEnum
import tkinter as tk
from tkinter import ttk

class AgentStateDialog:
    def __init__(self, parent, agent, collective):
        self.agent = agent
        self.collective = collective
        self.top = tk.Toplevel(parent)
        self.top.title(f"Агент: {agent.name}")
        self.top.geometry("600x650")
        self.top.configure(bg='#F8F9FA') # Светло-серый фон

        style = ttk.Style()
        style.configure("TNotebook", background="#F8F9FA")
        style.configure("TFrame", background="#F8F9FA")
        style.configure("TLabel", background="#F8F9FA", foreground="#212529")

        notebook = ttk.Notebook(self.top)
        notebook.pack(fill='both', expand=True, padx=5, pady=5)

        # Вкладка Архетип и Чувствительность
        frame_arch = ttk.Frame(notebook)
        notebook.add(frame_arch, text="Архетип")

        tk.Label(frame_arch, text="Архетип:", bg='#F8F9FA', fg='#212529', font=('Arial', 10, 'bold')).pack(pady=(15, 5))
        self.archetype_var = tk.StringVar()
        self.combo = ttk.Combobox(frame_arch, textvariable=self.archetype_var, state="readonly", width=25)
        self.combo['values'] = [a.name for a in ArchetypeEnum]
        self.combo.set(agent.archetype.name)
        self.combo.pack(pady=5)

        tk.Label(frame_arch, text="Чувствительность:", bg='#F8F9FA', fg='#212529', font=('Arial', 10, 'bold')).pack(pady=(15, 5))
        self.sensitivity_scale = tk.Scale(frame_arch, from_=0, to=3, resolution=0.1, orient=tk.HORIZONTAL, 
                                          bg='#F8F9FA', fg='#212529', highlightthickness=0)
        self.sensitivity_scale.set(agent.sensitivity)
        self.sensitivity_scale.pack(pady=5, fill='x', padx=30)

        # Вкладка Эмоции
        frame_emotions = ttk.Frame(notebook)
        notebook.add(frame_emotions, text="Эмоции")

        self.emotion_vars = {}
        for key, value in agent.get_emotions().items():
            tk.Label(frame_emotions, text=key, bg='#F8F9FA', fg='#495057', font=('Arial', 9)).pack(pady=(5, 0))
            scale = tk.Scale(frame_emotions, from_=-3, to=3, orient=tk.HORIZONTAL,
                             bg='#F8F9FA', fg='#212529', highlightthickness=0)
            scale.set(round(value))
            scale.pack(fill='x', padx=30)
            self.emotion_vars[key] = scale

        # Вкладка Отношения
        frame_relations = ttk.Frame(notebook)
        notebook.add(frame_relations, text="Отношения")

        # Фильтр по группе
        filter_frame = tk.Frame(frame_relations, bg='#F8F9FA')
        filter_frame.pack(pady=10, fill='x', padx=20)
        
        tk.Label(filter_frame, text="Фильтр (Группа):", bg='#F8F9FA', fg='#212529', font=('Arial', 9, 'bold')).pack(side=tk.LEFT)
        self.group_filter_var = tk.StringVar()
        
        # Если это Университет, берем список групп
        all_groups = ["Все"]
        if hasattr(self.collective, 'uni_manager'):
            all_groups.extend(self.collective.uni_manager.get_all_groups())
        
        self.group_filter_combo = ttk.Combobox(filter_frame, textvariable=self.group_filter_var, state="readonly", width=15)
        self.group_filter_combo['values'] = all_groups
        self.group_filter_combo.set("Все")
        self.group_filter_combo.pack(side=tk.LEFT, padx=5)
        self.group_filter_combo.bind("<<ComboboxSelected>>", self.update_relation_agent_list)

        tk.Label(frame_relations, text="Выберите агента:", bg='#F8F9FA', fg='#212529', font=('Arial', 9, 'bold')).pack(pady=(10, 5))
        self.other_agent_var = tk.StringVar()
        self.other_agent_combo = ttk.Combobox(frame_relations, textvariable=self.other_agent_var, state="readonly", width=30)
        self.update_relation_agent_list(None)
        self.other_agent_combo.pack(pady=5, fill='x', padx=20)
        self.other_agent_combo.bind("<<ComboboxSelected>>", self.load_relation_values)

        # Ползунки для предикатов
        for label, attr in [("Trust (Доверие)", "trust_scale"), ("Affinity (Симпатия)", "affinity_scale"), 
                             ("Utility (Выгода)", "utility_scale"), ("Responsiveness (Отзывчивость)", "responsiveness_scale")]:
            tk.Label(frame_relations, text=label, bg='#F8F9FA', fg='#495057', font=('Arial', 8)).pack(pady=(5, 0))
            scale = tk.Scale(frame_relations, from_=-10, to=10, orient=tk.HORIZONTAL, 
                             bg='#F8F9FA', fg='#212529', highlightthickness=0)
            scale.pack(fill='x', padx=30)
            setattr(self, attr, scale)

        # Кнопка сохранения
        btn_save = tk.Button(self.top, text="СОХРАНИТЬ ИЗМЕНЕНИЯ", command=self.on_save,
                             bg='#27AE60', fg='#212529', font=('Arial', 10, 'bold'), pady=10)
        btn_save.pack(side='bottom', fill='x', pady=10, padx=20)

    def update_relation_agent_list(self, event):
        selected_group = self.group_filter_var.get()
        if selected_group == "Все":
             names = [name for name in self.collective.agents if name != self.agent.name]
        else:
             # Берем только из этой группы
             if hasattr(self.collective, 'groups_map'):
                 names = [name for name in self.collective.groups_map.get(selected_group, []) if name != self.agent.name]
             else:
                 names = []
        
        self.other_agent_combo['values'] = sorted(names)
        if names: self.other_agent_combo.set("")

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