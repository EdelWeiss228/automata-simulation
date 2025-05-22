import tkinter as tk
import datetime
from tkinter import messagebox
from gui.agent_add_dialog import AgentAddDialog
from gui.agent_state_dialog import AgentStateDialog
from gui.agent_node import AgentNode
from gui.interaction_edge import InteractionEdge
from collective import Collective
from model.emotion_automaton import ArchetypeEnum
import random

NODE_RADIUS = 20
CANVAS_SIZE = 600



class SimulationGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Симуляция агентов")
        self.geometry(f"{CANVAS_SIZE + 300}x{CANVAS_SIZE + 50}")

        self.collective = Collective()
        self.agent_nodes = {}
        self.edges = []

        self.selected_agent_name = None
        self.auto_running = False
        self.current_date = datetime.date(2025, 1, 1)

        self.create_widgets()
        self.place_agents_initial()

    def create_widgets(self):
        # Canvas для отображения графа
        self.canvas = tk.Canvas(self, width=CANVAS_SIZE, height=CANVAS_SIZE, bg='white')
        self.canvas.grid(row=0, column=0, rowspan=10, padx=10, pady=10)

        # Панель управления
        self.control_frame = tk.Frame(self)
        self.control_frame.grid(row=0, column=1, sticky='n')
        self.control_frame.config(width=280)

        # Список агентов
        tk.Label(self.control_frame, text="Агенты:").pack()
        self.agent_listbox = tk.Listbox(self.control_frame, height=20)
        self.agent_listbox.pack()
        self.agent_listbox.bind('<<ListboxSelect>>', self.on_agent_select)

        # Метка даты
        self.date_label = tk.Label(self.control_frame, text=f"Дата: {self.current_date.strftime('%d %b %Y')}")
        self.date_label.pack(pady=3)

        # Метка количества дней симуляции
        self.day_counter = 0
        self.day_label = tk.Label(self.control_frame, text=f"День симуляции: {self.day_counter}")
        self.day_label.pack(pady=3)

        # Кнопки
        self.btn_add = tk.Button(self.control_frame, text="Добавить агента", command=self.add_agent_dialog)
        self.btn_add.pack(pady=3)

        self.btn_remove = tk.Button(self.control_frame, text="Удалить агента", command=self.remove_selected_agent)
        self.btn_remove.pack(pady=3)

        self.btn_details = tk.Button(self.control_frame, text="Подробнее", command=self.show_agent_details)
        self.btn_details.pack(pady=3)

        self.btn_simulate = tk.Button(self.control_frame, text="Симулировать день", command=self.simulate_day)
        self.btn_simulate.pack(pady=3)

        self.btn_auto = tk.Button(self.control_frame, text="Автосимуляция", command=self.toggle_autosim)
        self.btn_auto.pack(pady=3)

        self.btn_add_random = tk.Button(self.control_frame, text="Добавить случайного агента", command=self.add_random_agent)
        self.btn_add_random.pack(pady=3)

    def place_agents_initial(self):
        # Если уже есть агенты в collective, разместить их
        for agent_name in self.collective.agents.keys():
            self.add_agent_node(agent_name)

    def add_agent_node(self, agent_name):
        max_attempts = 100
        x, y = None, None
        for _ in range(max_attempts):
            x = random.randint(NODE_RADIUS + 10, CANVAS_SIZE - NODE_RADIUS - 10)
            y = random.randint(NODE_RADIUS + 10, CANVAS_SIZE - NODE_RADIUS - 10)

            # Проверяем пересечения с уже добавленными узлами
            collision = False
            for node in self.agent_nodes.values():
                dx = node.x - x
                dy = node.y - y
                dist = (dx**2 + dy**2)**0.5
                if dist < NODE_RADIUS * 2 + 10:  # 10 пикселей дополнительный отступ
                    collision = True
                    break

            if not collision:
                break
        else:
            # Если не нашли свободное место, кладём без проверки
            if x is None or y is None:
                x = CANVAS_SIZE // 2
                y = CANVAS_SIZE // 2

        node = AgentNode(self.canvas, x, y, agent_name)
        self.agent_nodes[agent_name] = node
        self.agent_listbox.insert(tk.END, agent_name)

    def on_agent_select(self, event):
        selection = event.widget.curselection()
        if selection:
            index = selection[0]
            self.selected_agent_name = event.widget.get(index)
        else:
            self.selected_agent_name = None

    def add_agent_dialog(self):
        # Всплывающее окно для добавления агента
        dialog = AgentAddDialog(self, self.collective)
        self.wait_window(dialog.top)
        if dialog.agent_added:
            agent_name = dialog.agent_name
            self.add_agent_node(agent_name)

    def remove_selected_agent(self):
        if self.selected_agent_name is None:
            messagebox.showwarning("Внимание", "Выберите агента для удаления")
            return
        self.collective.remove_agent(self.selected_agent_name)
        # Удалить визуально
        node = self.agent_nodes.pop(self.selected_agent_name)
        node.delete()
        # Удалить из списка
        idx = self.agent_listbox.get(0, tk.END).index(self.selected_agent_name)
        self.agent_listbox.delete(idx)
        self.selected_agent_name = None
        # Удалить все ребра и перерисовать (без них)
        self.clear_edges()

    def clear_edges(self):
        for edge in self.edges:
            edge.delete()
        self.edges.clear()

    def simulate_day(self):
        self.clear_edges()
        # Запускаем логику симуляции: каждый агент принимает решение хотя бы раз
        # Для наглядности - будем сохранять взаимодействия (source, target, success)
        interactions = []
        # Вызовем collective.make_interaction_decision(), предполагая, что он возвращает список взаимодействий
        # Формат взаимодействия: (agent_from_name, agent_to_name, success)
        try:
            interactions = self.collective.make_interaction_decision()
        except Exception as e:
            messagebox.showerror("Ошибка симуляции", f"Произошла ошибка при симуляции: {e}")
            return

        # Отобразим ребра по результатам взаимодействий
        for agent_from, agent_to, success in interactions:
            if agent_from in self.agent_nodes and agent_to in self.agent_nodes:
                edge = InteractionEdge(self.canvas, self.agent_nodes[agent_from], self.agent_nodes[agent_to], success)
                self.edges.append(edge)

        # Обновить дату после симуляции
        self.current_date += datetime.timedelta(days=1)
        self.date_label.config(text=f"Дата: {self.current_date.strftime('%d %b %Y')}")
        # Увеличить счетчик дней и обновить метку
        self.day_counter += 1
        self.day_label.config(text=f"День симуляции: {self.day_counter}")

    def show_agent_details(self):
        if self.selected_agent_name is None:
            messagebox.showwarning("Внимание", "Выберите агента")
            return
        agent = self.collective.get_agent(self.selected_agent_name)
        if agent is None:
            messagebox.showerror("Ошибка", "Агент не найден")
            return
        dialog = AgentStateDialog(self, agent, self.collective)
        self.wait_window(dialog.top)

    def toggle_autosim(self):
        self.auto_running = not self.auto_running
        if self.auto_running:
            self.btn_auto.config(text="Остановить")
            self.run_autosim()
        else:
            self.btn_auto.config(text="Автосимуляция")

    def run_autosim(self):
        if self.auto_running:
            self.simulate_day()
            self.after(1000, self.run_autosim)  # запускать каждые 1000 мс (1 сек)

    def add_random_agent(self):
        archetype = random.choice(list(ArchetypeEnum))

        names = ["Рома", "Иван", "Аня", "Катя", "Дима", "Саша", "Маша", "Петя", "Лена", "Никита"]
        name = random.choice(names) + f"_{len(self.collective.agents) + 1}"

        sensitivity = round(random.uniform(0.0, 3.0), 2)

        emotions = {axis: random.randint(-3, 3) for axis in [
            "joy_sadness", "fear_calm", "anger_humility",
            "disgust_acceptance", "surprise_habit",
            "shame_confidence", "love_alienation"
        ]}

        relations = {}
        for other_agent_name in self.collective.agents:
            relations[other_agent_name] = {
                'trust': random.randint(-10, 10) if random.random() > 0.3 else 0,
                'affinity': random.randint(-10, 10) if random.random() > 0.3 else 0,
                'utility': random.randint(-10, 10) if random.random() > 0.3 else 0,
                'responsiveness': random.randint(-10, 10) if random.random() > 0.3 else 0,
            }

        from agent import Agent
        new_agent = Agent(
            name=name,
            archetype=archetype,
            sensitivity=sensitivity,
            emotions=emotions
        )
        for other_name, preds in relations.items():
            new_agent.relations[other_name] = preds

        self.collective.add_agent(new_agent)
        self.add_agent_node(new_agent.name)