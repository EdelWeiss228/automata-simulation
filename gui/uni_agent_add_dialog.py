import tkinter as tk
from tkinter import messagebox, ttk
from model.archetypes import ArchetypeEnum
from model.agent import Agent

class UniAgentAddDialog:
    def __init__(self, parent, collective):
        self.parent = parent
        self.collective = collective
        self.top = tk.Toplevel(parent)
        self.top.title("Зачислить студента")
        self.top.geometry("500x580")
        self.top.configure(bg='#F8F9FA')
        self.agent_added = False

        style = ttk.Style()
        # Повторяем настройку стиля для этого окна
        style.configure("TNotebook", background="#F8F9FA")
        style.configure("TFrame", background="#F8F9FA")
        style.configure("TLabel", background="#F8F9FA", foreground="#212529")

        self.create_widgets()

    def create_widgets(self):
        notebook = ttk.Notebook(self.top)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # Вкладка Основное
        frame_main = ttk.Frame(notebook)
        notebook.add(frame_main, text="Личные данные")

        tk.Label(frame_main, text="Имя студента:", bg='#F8F9FA', fg='#212529', font=('Arial', 10, 'bold')).pack(pady=(15, 0))
        self.entry_name = tk.Entry(frame_main, width=30)
        self.entry_name.pack(pady=5)

        tk.Label(frame_main, text="Архетип (Путь):", bg='#F8F9FA', fg='#212529', font=('Arial', 10, 'bold')).pack(pady=(15, 0))
        self.archetype_var = tk.StringVar()
        self.combo_arch = ttk.Combobox(frame_main, textvariable=self.archetype_var, state="readonly", width=27)
        self.combo_arch['values'] = [a.name for a in ArchetypeEnum]
        self.combo_arch.pack(pady=5)

        tk.Label(frame_main, text="Чувствительность:", bg='#F8F9FA', fg='#212529', font=('Arial', 10, 'bold')).pack(pady=(15, 0))
        self.sensitivity_scale = tk.Scale(frame_main, from_=0, to=3, resolution=0.1, orient=tk.HORIZONTAL,
                                          bg='#F8F9FA', fg='#212529', highlightthickness=0)
        self.sensitivity_scale.set(1.0)
        self.sensitivity_scale.pack(fill='x', padx=30, pady=5)

        # Вкладка Университет
        frame_uni = ttk.Frame(notebook)
        notebook.add(frame_uni, text="Университет")

        tk.Label(frame_uni, text="Группа:", bg='#F8F9FA', fg='#212529', font=('Arial', 10, 'bold')).pack(pady=(30, 5))
        self.group_var = tk.StringVar()
        self.combo_group = ttk.Combobox(frame_uni, textvariable=self.group_var, state="readonly", width=30)
        
        # Получаем список групп из менеджера
        all_groups = self.collective.uni_manager.get_all_groups()
        self.combo_group['values'] = all_groups
        if all_groups: self.combo_group.set(all_groups[0])
        self.combo_group.pack(pady=5)

        tk.Label(frame_uni, text="* Студент будет автоматически распределен\nв соответствии с выбранной группой.", 
                 bg='#F8F9FA', fg='#6C757D', font=('Arial', 8, 'italic')).pack(pady=20)

        # Кнопка Добавить
        btn_frame = tk.Frame(self.top, bg='#F8F9FA')
        btn_frame.pack(side='bottom', fill='x', pady=15)
        
        tk.Button(btn_frame, text="ЗАЧИСЛИТЬ", command=self.on_add, 
                  bg='#27AE60', fg='#212529', font=('Arial', 10, 'bold'), width=20,
                  relief=tk.FLAT, bd=0).pack()

    def on_add(self):
        name = self.entry_name.get().strip()
        if not name:
            messagebox.showerror("Ошибка", "Имя не может быть пустым")
            return
        if name in self.collective.agents:
            messagebox.showerror("Ошибка", "Студент с таким именем уже существует")
            return
            
        arch_name = self.archetype_var.get()
        archetype = next((a for a in ArchetypeEnum if a.name == arch_name), None)
        if not archetype:
            messagebox.showerror("Ошибка", "Выберите архетип")
            return

        group_id = self.group_var.get()
        if not group_id:
            messagebox.showerror("Ошибка", "Выберите группу")
            return

        # Парсим ID (Group_F_S_G)
        parts = group_id.split('_')
        faculty_id = f"Faculty_{parts[1]}"
        stream_id = f"Stream_{parts[1]}_{parts[2]}"

        # Создаем агента
        agent = Agent(name, archetype=archetype, sensitivity=self.sensitivity_scale.get())
        agent.set_university_info(faculty_id, stream_id, group_id)
        
        # Добавляем в коллектив
        self.collective.add_agent(agent)
        
        # Инициализируем отношения (упрощенно - только с группой)
        from core.agent_factory import AgentFactory
        group_mates = self.collective.groups_map.get(group_id, [])
        AgentFactory.initialize_agent_relations(agent, group_mates)
        
        self.agent_added = True
        messagebox.showinfo("Успех", f"Студент {name} зачислен в группу {group_id}")
        self.top.destroy()
