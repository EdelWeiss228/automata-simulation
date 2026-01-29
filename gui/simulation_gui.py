import tkinter as tk
import datetime
from tkinter import messagebox
from gui.agent_add_dialog import AgentAddDialog
from gui.agent_state_dialog import AgentStateDialog
from gui.agent_node import AgentNode
from gui.interaction_edge import InteractionEdge
from model.collective import Collective
from model.university_collective import UniversityCollective
from gui.university_gui import UniversityGUI
from core.agent_factory import AgentFactory
from core.data_logger import DataLogger
from gui.color_utils import get_emotion_color
import random
import math

NODE_RADIUS = 20
INITIAL_CANVAS_SIZE = 600
SPACING = 3 * NODE_RADIUS  # 60 пикселей между центрами

class SimulationGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Симуляция агентов")
        # Увеличиваем размер окна
        self.geometry(f"{INITIAL_CANVAS_SIZE + 350}x{INITIAL_CANVAS_SIZE + 250}")
        
        self.collective = Collective()
        self.agent_nodes = {}
        self.edges = []

        self.selected_agent_name = None
        self.auto_running = False
        self.simulation_started = False

        self.logger = DataLogger()
        self.first_log_states = True
        self.first_log_interactions = True

        self.create_widgets()
        self.place_agents_initial()

    def create_widgets(self):
        # Настройка сетки главного окна
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Фрейм для Canvas с прокруткой ---
        self.canvas_frame = tk.Frame(self)
        self.canvas_frame.grid(row=0, column=0, padx=10, pady=10, sticky='nsew')
        
        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.canvas_frame, bg='white', scrollregion=(0, 0, INITIAL_CANVAS_SIZE, INITIAL_CANVAS_SIZE))
        
        self.h_scroll = tk.Scrollbar(self.canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.v_scroll = tk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)
        
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.v_scroll.grid(row=0, column=1, sticky='ns')
        self.h_scroll.grid(row=1, column=0, sticky='ew')

        self.simulation_control_frame = tk.Frame(self)
        self.simulation_control_frame.grid(row=1, column=0, pady=(0, 10), sticky='ew')

        self.btn_simulate = tk.Button(self.simulation_control_frame, text="Симулировать день", command=self.simulate_day)
        self.btn_simulate.pack(side=tk.LEFT, padx=5)

        self.btn_auto = tk.Button(self.simulation_control_frame, text="Автосимуляция", command=self.toggle_autosim)
        self.btn_auto.pack(side=tk.LEFT, padx=5)

        self.btn_restart = tk.Button(self.simulation_control_frame, text="Перезапуск симуляции", command=self.restart_simulation)
        self.btn_restart.pack(side=tk.LEFT, padx=5)

        # --- Панель управления справа ---
        self.control_frame = tk.Frame(self)
        self.control_frame.grid(row=0, column=1, rowspan=2, sticky='ns', padx=10, pady=10)
        self.control_frame.config(width=300)

        # Список агентов
        tk.Label(self.control_frame, text="Агенты:").pack()
        self.agent_listbox = tk.Listbox(self.control_frame, height=25, width=30)
        self.agent_listbox.pack(fill=tk.Y, expand=True)
        self.agent_listbox.bind('<<ListboxSelect>>', self.on_agent_select)

        # Метки информации
        self.date_label = tk.Label(self.control_frame, text=f"Дата: {self.collective.current_date.strftime('%d %b %Y')}")
        self.date_label.pack(pady=3)
        self.day_label = tk.Label(self.control_frame, text=f"День симуляции: {self.collective.current_step}")
        self.day_label.pack(pady=3)

        # Кнопки
        tk.Button(self.control_frame, text="Добавить агента", command=self.add_agent_dialog).pack(pady=3, fill=tk.X)
        tk.Button(self.control_frame, text="Добавить случайного агента", command=self.add_random_agent).pack(pady=3, fill=tk.X)

        frame_n_add = tk.Frame(self.control_frame)
        frame_n_add.pack(pady=3, fill=tk.X)
        self.n_entry = tk.Entry(frame_n_add, width=5)
        self.n_entry.insert(0, "5")
        self.n_entry.pack(side=tk.LEFT)
        tk.Button(frame_n_add, text="Добавить N агентов", command=self.add_multiple_random_agents).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        tk.Button(self.control_frame, text="Удалить агента", command=self.remove_selected_agent).pack(pady=3, fill=tk.X)
        tk.Button(self.control_frame, text="Подробнее", command=self.show_agent_details).pack(pady=3, fill=tk.X)
        tk.Button(self.control_frame, text="V3: Загрузить Университет", command=self.load_university, bg='lightblue').pack(pady=10, fill=tk.X)

    def load_university(self):
        """Переключает на масштабную симуляцию университета."""
        if messagebox.askyesno("Подтверждение", "Это создаст 1875 агентов и может занять некоторое время. Продолжить?"):
            self.collective = UniversityCollective()
            self.restart_gui_for_new_collective()
            messagebox.showinfo("Готово", "Университет загружен. 5 факультетов, 25 потоков, 75 групп.")
            
            # Открываем новое окно с картой
            self.open_university_map()

    def open_university_map(self):
        """Открывает детализированную карту университета."""
        if isinstance(self.collective, UniversityCollective):
            self.uni_map_window = UniversityGUI(self, self.collective)
        else:
            messagebox.showwarning("Внимание", "Карта доступна только в режиме Университета (V3).")

    def restart_gui_for_new_collective(self):
        """Очищает GUI и перерисовывает ноды для текущего коллектива."""
        self.agent_nodes.clear()
        self.edges.clear()
        self.canvas.delete("all")
        self.agent_listbox.delete(0, tk.END)
        self.canvas.config(scrollregion=(0, 0, INITIAL_CANVAS_SIZE, INITIAL_CANVAS_SIZE))
        self.place_agents_initial()
        self.simulation_started = False

    def add_multiple_random_agents(self):
        try:
            count = int(self.n_entry.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Введите корректное число агентов")
            return
        for _ in range(count):
            self.add_random_agent()

    def place_agents_initial(self):
        for agent_name in self.collective.agents.keys():
            self.add_agent_node(agent_name)

    def get_next_grid_position(self):
        """
        Находит случайную свободную позицию в 'активной зоне' сетки.
        Если находит, возвращает координаты.
        """
        # Определяем примерное количество необходимых ячеек с запасом
        idx = len(self.agent_nodes)
        n_agents = idx + 1
        
        # Оцениваем нужный размер поля (columns x rows)
        # Хотим примерно квадратную или прямоугольную область
        # S ~ n_agents * 2 (чтобы было 50% заполнение, для "воздуха")
        target_cells = max(50, n_agents * 2) 
        columns = 10 # Фиксированная ширина для удобства скролла
        
        # Пытаемся найти случайное свободное место
        max_attempts = 50
        margin = NODE_RADIUS + 20
        cell_size = SPACING + 20
        
        for _ in range(max_attempts):
            # Выбираем случайную колонку и ряд в разумных пределах
            # Ряд может расти вниз по мере добавления
            max_row = (n_agents // columns) + 5 # +5 рядов запаса вниз
            
            c = random.randint(0, columns - 1)
            r = random.randint(0, max_row)
            
            # Проверяем, не занята ли ячейка (простая проверка по расстоянию до всех других)
            candidate_x = margin + c * cell_size
            candidate_y = margin + r * cell_size
            
            collision = False
            for node in self.agent_nodes.values():
                dist = ((node.x - candidate_x)**2 + (node.y - candidate_y)**2)**0.5
                if dist < NODE_RADIUS: # Если попали почти в ту же точку
                    collision = True
                    break
            
            if not collision:
                return candidate_x, candidate_y
                
        # Если не повезло с рандомом — ставим в первое свободное место последовательно (fallback)
        # Это старая логика, чтобы точно не зависнуть
        for r in range(1000):
            for c in range(columns):
                candidate_x = margin + c * cell_size
                candidate_y = margin + r * cell_size
                
                collision = False
                for node in self.agent_nodes.values():
                    dist = ((node.x - candidate_x)**2 + (node.y - candidate_y)**2)**0.5
                    if dist < NODE_RADIUS:
                        collision = True
                        break
                
                if not collision:
                    return candidate_x, candidate_y
        
        return 0, 0 # Should not happen

    def add_agent_node(self, agent_name):
        x, y = self.get_next_grid_position()
        
        # Проверяем, нужно ли расширить canvas
        current_scroll = self.canvas.cget("scrollregion")
        if current_scroll:
            try:
                # scrollregion возвращает строку "x1 y1 x2 y2"
                val = list(map(int, current_scroll.split()))
                max_w, max_h = val[2], val[3]
            except:
                max_w, max_h = INITIAL_CANVAS_SIZE, INITIAL_CANVAS_SIZE
        else:
            max_w, max_h = INITIAL_CANVAS_SIZE, INITIAL_CANVAS_SIZE
            
        new_w = max(max_w, x + NODE_RADIUS + 50)
        new_h = max(max_h, y + NODE_RADIUS + 50)
        
        if new_w > max_w or new_h > max_h:
            self.canvas.config(scrollregion=(0, 0, new_w, new_h))

        node = AgentNode(self.canvas, x, y, agent_name)
        
        # Сразу красим, если агент уже со старыми эмоциями
        agent = self.collective.get_agent(agent_name)
        if agent:
             emotion_name, value = agent.get_primary_emotion()
             color = get_emotion_color(emotion_name, value)
             node.set_color(color)
        
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
        
        node = self.agent_nodes.pop(self.selected_agent_name)
        node.delete()
        
        # Обновляем Listbox
        idx = self.agent_listbox.get(0, tk.END).index(self.selected_agent_name)
        self.agent_listbox.delete(idx)
        self.selected_agent_name = None
        
        self.clear_edges()
        # Пересчитываем позиции? Пока сложно, оставим дырки или можно перестроить всё.
        # Для простоты можно оставить дырку, новые агенты встанут в конец.
        
    def clear_edges(self):
        for edge in self.edges:
            edge.delete()
        self.edges.clear()

    def simulate_day(self):
        if not self.simulation_started:
            self.logger.log_agent_states("agent_states.csv", self.collective.current_date, self.collective.agents, self.first_log_states)
            self.first_log_states = False
        
        self.simulation_started = True
        self.clear_edges()
        
        try:
            interactions = self.collective.perform_full_day_cycle(interactive=False)
        except Exception as e:
            messagebox.showerror("Ошибка симуляции", f"Произошла ошибка при симуляции: {e}")
            return

        # Логирование
        self.logger.log_interactions("interaction_log.csv", self.collective.current_date, interactions, self.first_log_interactions)
        self.first_log_interactions = False
        
        self.logger.log_agent_states("agent_states.csv", self.collective.current_date, self.collective.agents, self.first_log_states)
        self.first_log_states = False

        # Визуализация ребер
        for agent_from, agent_to, result in interactions:
            if agent_from in self.agent_nodes and agent_to in self.agent_nodes:
                edge = InteractionEdge(self.canvas, self.agent_nodes[agent_from], self.agent_nodes[agent_to], result)
                self.edges.append(edge)

        # Обновление цветов
        for name, agent in self.collective.agents.items():
            if name in self.agent_nodes:
                emotion_name, value = agent.get_primary_emotion()
                color = get_emotion_color(emotion_name, value)
                self.agent_nodes[name].set_color(color)

        self.date_label.config(text=f"Дата: {self.collective.current_date.strftime('%d %b %Y')}")
        self.day_label.config(text=f"День симуляции: {self.collective.current_step}")

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
            self.after(1000, self.run_autosim)

    def add_random_agent(self):
        new_name = self.collective.add_random_agent()
        self.add_agent_node(new_name)

    def restart_simulation(self):
        self.collective = Collective()
        self.agent_nodes.clear()
        self.edges.clear()
        self.canvas.delete("all")
        self.agent_listbox.delete(0, tk.END)
        # Сброс скролла
        self.canvas.config(scrollregion=(0, 0, INITIAL_CANVAS_SIZE, INITIAL_CANVAS_SIZE))
        
        self.simulation_started = False
        self.first_log_states = True
        self.first_log_interactions = True
        self.date_label.config(text=f"Дата: {self.collective.current_date.strftime('%d %b %Y')}")
        self.day_label.config(text=f"День симуляции: {self.collective.current_step}")
