import tkinter as tk
from tkinter import messagebox
from model.university_collective import UniversityCollective
from model.constants import AgentStatus, TimeSlotType
from gui.color_utils import get_emotion_color
import math

NODE_RADIUS = 6
INTERACTION_COLOR = "#FFD700" # Золотистый для связей

class ToolTip:
    def __init__(self, canvas):
        self.canvas = canvas
        self.tip_window = None
        self.id = None
        self.x = self.y = 0

    def show_tip(self, text, x, y):
        if self.tip_window or not text:
            return
        # Смещение для корректного отображения на канвасе с учетом скролла
        self.tip_window = tk.Toplevel(self.canvas)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x+15}+{y+15}")
        
        # Явно задаем черный текст на желтоватом фоне для macOS
        label = tk.Label(self.tip_window, text=text, justify=tk.LEFT,
                         background="#FFF9C4", foreground="#212121", 
                         relief=tk.SOLID, borderwidth=1,
                         font=("Arial", "10", "normal"), padx=5, pady=3)
        label.pack(ipadx=1)

    def hide_tip(self):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

class UniversityGUI(tk.Toplevel):
    def __init__(self, parent, collective: UniversityCollective):
        super().__init__(parent)
        self.title("Университет: Карта Кампуса (V3.2)")
        self.geometry("1100x850")
        
        self.collective = collective
        self.agent_dots = {}  # name -> canvas_id
        self.agent_names_by_id = {} # canvas_id -> name (для тултипов)
        self.room_rects = {}  # room_id -> canvas_id
        self.interaction_lines = []
        self.zoom_level = 1.0
        self.auto_mode = None # 'slots', 'days' или None
        
        self.tooltip = ToolTip(self)
        self.create_widgets()
        self.draw_map()
        self.update_agent_positions()

    def create_widgets(self):
        self.main_frame = tk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas_frame = tk.Frame(self.main_frame)
        self.canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Увеличиваем scrollregion для больших карт
        self.canvas = tk.Canvas(self.canvas_frame, bg='#FFFFFF', scrollregion=(0, 0, 2000, 4500))
        self.h_scroll = tk.Scrollbar(self.canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.v_scroll = tk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.v_scroll.grid(row=0, column=1, sticky='ns')
        self.h_scroll.grid(row=1, column=0, sticky='ew')
        
        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)

        # Правая панель (Темная тема для контраста)
        self.side_panel = tk.Frame(self.main_frame, width=300, padx=15, pady=15, bg='#2C3E50')
        self.side_panel.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Label(self.side_panel, text="ПАРАМЕТРЫ СРЕДЫ", font=('Arial', 14, 'bold'), bg='#2C3E50', fg='#ECF0F1').pack(pady=10)
        
        self.lbl_date = tk.Label(self.side_panel, text="Дата", font=('Arial', 10), bg='#2C3E50', fg='#BDC3C7')
        self.lbl_date.pack()

        self.lbl_slot = tk.Label(self.side_panel, text="Слот", font=('Arial', 12, 'bold'), bg='#2C3E50', fg='#3498DB')
        self.lbl_slot.pack(pady=10)

        self.lbl_zoom = tk.Label(self.side_panel, text="Масштаб: 100%", font=('Arial', 10), bg='#2C3E50', fg='#ECF0F1')
        self.lbl_zoom.pack()

        self.btn_next = tk.Button(self.side_panel, text="СЛЕДУЮЩИЙ ТАКТ >>", command=self.next_step, 
                                  bg='#27AE60', fg='#2C3E50', font=('Arial', 10, 'bold'), height=1)
        self.btn_next.pack(fill=tk.X, pady=(10, 5))

        # Фрейм для кнопок автосимуляции
        auto_frame = tk.Frame(self.side_panel, bg='#2C3E50')
        auto_frame.pack(fill=tk.X, pady=5)

        self.btn_auto_slots = tk.Button(auto_frame, text="АВТО: ОДИН ДЕНЬ", command=self.toggle_auto_slots, 
                                        bg='#8E44AD', fg='#2C3E50', font=('Arial', 9, 'bold'), height=2, width=12)
        self.btn_auto_slots.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        self.btn_auto_days = tk.Button(auto_frame, text="АВТО: ВСЕ ДНИ", command=self.toggle_auto_days, 
                                       bg='#2980B9', fg='#2C3E50', font=('Arial', 9, 'bold'), height=2, width=12)
        self.btn_auto_days.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

        # Кнопка сброса
        self.btn_reset = tk.Button(self.side_panel, text="СБРОСИТЬ ВСЁ", command=self.reset_simulation,
                                   bg='#95A5A6', fg='#2C3E50', font=('Arial', 9, 'bold'))
        self.btn_reset.pack(fill=tk.X, pady=(5, 10))
        
        self.lbl_stats = tk.Label(self.side_panel, text="-", anchor='w', justify=tk.LEFT, bg='#2C3E50', fg='#ECF0F1', font=('Arial', 9))
        self.lbl_stats.pack(fill=tk.X, pady=10)

        # --- Кнопки управления агентами ---
        tk.Label(self.side_panel, text="УПРАВЛЕНИЕ", font=('Arial', 12, 'bold'), bg='#2C3E50', fg='#ECF0F1').pack(pady=(10, 5))
        
        self.btn_edit = tk.Button(self.side_panel, text="РЕДАКТИРОВАТЬ", command=self.show_agent_details,
                                  fg='#2C3E50', font=('Arial', 9, 'bold'), state=tk.DISABLED)
        self.btn_edit.pack(fill=tk.X, pady=2)

        self.btn_add = tk.Button(self.side_panel, text="ДОБАВИТЬ СТУДЕНТА", command=self.add_student_dialog,
                                 fg='#2C3E50', font=('Arial', 9, 'bold'))
        self.btn_add.pack(fill=tk.X, pady=2)

        self.btn_remove = tk.Button(self.side_panel, text="ОТЧИСЛИТЬ", command=self.remove_selected_student,
                                    fg='#C0392B', font=('Arial', 9, 'bold'), state=tk.DISABLED)
        self.btn_remove.pack(fill=tk.X, pady=2)

        self.selected_agent = None # Имя выбранного агента
        self.selection_circle = None # Canvas ID круга выделения

        # Легенда
        legend_frame = tk.LabelFrame(self.side_panel, text="Легенда", bg='#2C3E50', fg='#ECF0F1', padx=5, pady=5)
        legend_frame.pack(fill=tk.X, pady=10)
        
        for text, color in [("Лекция (Поток)", "#E3F2FD"), ("Семинар (Группа)", "#E8F5E9"), ("Спортзал", "#FFF3E0"), ("Коридор", "#F5F5F5")]:
            f = tk.Frame(legend_frame, bg='#2C3E50')
            f.pack(fill=tk.X)
            tk.Label(f, bg=color, width=2, relief=tk.SOLID).pack(side=tk.LEFT, padx=3)
            tk.Label(f, text=text, font=('Arial', 8), bg='#2C3E50', fg='#ECF0F1').pack(side=tk.LEFT)

        # События мыши и клавиатуры
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        
        # Панорамирование (перетаскивание карты)
        self.canvas.bind("<ButtonPress-2>", self.scroll_start)
        self.canvas.bind("<B2-Motion>", self.scroll_move)
        self.canvas.bind("<ButtonPress-3>", self.scroll_start) # Правая кнопка для мышек без колеса
        self.canvas.bind("<B3-Motion>", self.scroll_move)
        
        # Скроллинг мышью и тачпадом (Глобальный биндинг)
        self.bind_all("<MouseWheel>", self.on_mouse_wheel)  # Windows/macOS Vertical
        self.bind_all("<Shift-MouseWheel>", self.on_mouse_wheel_x) # macOS/Windows Horizontal
        self.bind_all("<Button-4>", self.on_mouse_wheel)    # Linux Up
        self.bind_all("<Button-5>", self.on_mouse_wheel)    # Linux Down
        
        # Специально для боковой панели, если она перехватывает
        self.side_panel.bind("<MouseWheel>", self.on_mouse_wheel)
        self.side_panel.bind("<Shift-MouseWheel>", self.on_mouse_wheel_x)
        
        self.bind("<Command-plus>", lambda e: self.zoom(1.2))
        self.bind("<Command-equal>", lambda e: self.zoom(1.2)) # Для удобства (без shift)
        self.bind("<Command-minus>", lambda e: self.zoom(0.8))
        self.bind("<Control-plus>", lambda e: self.zoom(1.2))  # Для Windows/Linux совместимости
        self.bind("<Control-minus>", lambda e: self.zoom(0.8))

    def on_mouse_wheel(self, event):
        """Вертикальный скролл."""
        # На macOS delta обычно кратна 1, на Windows 120
        if event.num == 4: # Linux
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5: # Linux
            self.canvas.yview_scroll(1, "units")
        else:
            self.canvas.yview_scroll(int(-1 * (event.delta)), "units")

    def on_mouse_wheel_x(self, event):
        """Горизонтальный скролл (Shift + Wheel)."""
        self.canvas.xview_scroll(int(-1 * (event.delta)), "units")

    def scroll_start(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def scroll_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def on_canvas_click(self, event):
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        item = self.canvas.find_closest(canvas_x, canvas_y)
        if item:
            coords = self.canvas.coords(item)
            if len(coords) == 4: # oval
                cx, cy = (coords[0] + coords[2])/2, (coords[1] + coords[3])/2
                dist = math.sqrt((canvas_x - cx)**2 + (canvas_y - cy)**2)
                
                if dist < 15 * self.zoom_level and item[0] in self.agent_names_by_id:
                    name = self.agent_names_by_id[item[0]]
                    self.select_agent(name, cx, cy)
                    return
        
        self.deselect_agent()

    def select_agent(self, name, x, y):
        self.deselect_agent()
        self.selected_agent = name
        r = (NODE_RADIUS + 4) * self.zoom_level
        self.selection_circle = self.canvas.create_oval(
            x - r, y - r, x + r, y + r,
            outline="#F1C40F", width=2, dash=(2, 2)
        )
        self.btn_edit.config(state=tk.NORMAL)
        self.btn_remove.config(state=tk.NORMAL)

    def deselect_agent(self):
        if self.selection_circle:
            self.canvas.delete(self.selection_circle)
            self.selection_circle = None
        self.selected_agent = None
        self.btn_edit.config(state=tk.DISABLED)
        self.btn_remove.config(state=tk.DISABLED)

    def show_agent_details(self):
        if not self.selected_agent: return
        from gui.agent_state_dialog import AgentStateDialog
        agent = self.collective.get_agent(self.selected_agent)
        if agent:
            dialog = AgentStateDialog(self, agent, self.collective)
            self.wait_window(dialog.top)
            self.update_agent_positions()

    def add_student_dialog(self):
        from gui.uni_agent_add_dialog import UniAgentAddDialog
        dialog = UniAgentAddDialog(self, self.collective)
        self.wait_window(dialog.top)
        if hasattr(dialog, 'agent_added') and dialog.agent_added:
            self.update_agent_positions()

    def remove_selected_student(self):
        if not self.selected_agent: return
        if messagebox.askyesno("Подтверждение", f"Вы уверены, что хотите отчислить студента {self.selected_agent}?"):
            self.collective.remove_agent(self.selected_agent)
            self.deselect_agent()
            self.update_agent_positions()

    def reset_simulation(self):
        if not messagebox.askyesno("Сброс", "Вы уверены, что хотите сбросить всю симуляцию к началу (1 января)?"):
            return
        
        # Останавливаем всё
        self.auto_mode = None
        self.btn_auto_slots.config(text="АВТО: СЛОТЫ", bg='#8E44AD')
        self.btn_auto_days.config(text="АВТО: ДНИ", bg='#2980B9')
        
        # Пересоздаем коллектив
        self.collective = UniversityCollective()
        self.canvas.delete("all")
        self.draw_map()
        self.deselect_agent()
        self.update_agent_positions()
        # Сбрасываем скролл в начало
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        messagebox.showinfo("Готово", "Симуляция сброшена.")

    def draw_map(self):
        rooms = self.collective.uni_manager.rooms_info
        for room_id, info in rooms.items():
            x, y, w, h = info['x'], info['y'], info['width'], info['height']
            rtype = info.get('type', 'SEMINAR')
            
            # Цвета в зависимости от типа
            bg_color = "#FFFFFF"
            border_color = "#CCCCCC"
            if rtype == "LECTURE": 
                bg_color = "#E3F2FD" # Light Blue
                border_color = "#2196F3"
            elif rtype == "SEMINAR": 
                bg_color = "#E8F5E9" # Light Green
                border_color = "#4CAF50"
            elif rtype == "GYM": 
                bg_color = "#FFF3E0" # Light Orange
                border_color = "#FF9800"
            elif rtype == "CORRIDOR":
                bg_color = "#F5F5F5"
                border_color = "#9E9E9E"

            rect_id = self.canvas.create_rectangle(
                x * self.zoom_level, y * self.zoom_level, 
                (x + w) * self.zoom_level, (y + h) * self.zoom_level, 
                fill=bg_color, outline=border_color, width=2
            )
            
            # Название комнаты + ID
            display_label = info.get("display_name", room_id)
            
            self.canvas.create_text(
                x * self.zoom_level + 5, y * self.zoom_level + 5, 
                text=display_label, anchor='nw', 
                font=('Arial', int(8 * self.zoom_level), 'bold'), 
                fill='#34495E' # Темно-серый для контраста
            )

    def update_agent_positions(self, custom_interactions=None):
        # Удаляем старые связи и точки
        for lid in self.interaction_lines:
            self.canvas.delete(lid)
        self.interaction_lines.clear()
        
        for dot_id in self.agent_dots.values():
            self.canvas.delete(dot_id)
        self.agent_dots.clear()
        self.agent_names_by_id.clear()

        campus_count = 0
        current_rooms = self.collective.current_rooms
        positions = {} # name -> (x, y) для отрисовки линий
        
        # Обновляем точки агентов
        for room_id, student_names in current_rooms.items():
            for idx, name in enumerate(student_names):
                agent = self.collective.agents.get(name)
                if not agent or agent.status == AgentStatus.HOME: continue
                
                campus_count += 1
                rx, ry = self.collective.uni_manager.get_seat_coordinates(room_id, idx)
                x, y = rx * self.zoom_level, ry * self.zoom_level
                positions[name] = (x, y)
                
                # Цвет на основе актуальной эмоции
                emotion_name, value = agent.get_primary_emotion()
                color = get_emotion_color(emotion_name, value)
                
                r = NODE_RADIUS * self.zoom_level
                dot_id = self.canvas.create_oval(
                    x - r, y - r,
                    x + r, y + r,
                    fill=color, outline='#333333', width=1
                )
                self.agent_dots[name] = dot_id
                self.agent_names_by_id[dot_id] = name

        # Отрисовка линий взаимодействия
        interactions_to_show = custom_interactions if custom_interactions is not None else getattr(self.collective, 'last_interactions', [])
        
        for s1, s2, status in interactions_to_show:
            if s1 in positions and s2 in positions:
                p1, p2 = positions[s1], positions[s2]
                color = "#FFD700" if status == "success" else "#FF4500"
                line_id = self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=color, width=2, dash=(4,4))
                self.interaction_lines.append(line_id)

        # Статистика
        current_slot = self.collective.day_schedule_slots[self.collective.current_slot_idx - 1] if self.collective.current_slot_idx > 0 else "Начало дня"
        slot_name = current_slot.value if hasattr(current_slot, 'value') else current_slot
        self.lbl_slot.config(text=f"СЛОТ: {slot_name}")
        self.lbl_date.config(text=f"{self.collective.current_date.strftime('%A, %d %b %Y')}")
        self.lbl_stats.config(text=f"В кампусе: {campus_count} из {len(self.collective.agents)}\n\n"
                                   f"Статус: {slot_name}\n"
                                   f"Взаимодействий: {len(interactions_to_show)}")

    def next_step(self):
        interactions = self.collective.perform_next_step()
        self.update_agent_positions()
        
        # Если новый день
        if any(res == "New_Day_Ready" for _, _, res in interactions if isinstance(res, str)):
             # Если мы в режиме ПОТОК (days), просто идем дальше (бесшовно)
             if self.auto_mode == 'days':
                 return
             
             # Если мы в режиме СМИРНО (slots) или ручном — останавливаемся и показываем окно
             if self.auto_mode == 'slots':
                 self.toggle_auto_slots() # Выключаем авто-режим
             
             messagebox.showinfo("Новый день", "Учебный день завершен.\nВсе вернулись домой для рефлексии.")

    def toggle_auto_slots(self):
        if self.auto_mode == 'slots':
            self.auto_mode = None
            self.btn_auto_slots.config(text="АВТО: СМИРНО", bg='#8E44AD')
        else:
            # Отключаем другой режим если он был
            if self.auto_mode == 'days': self.toggle_auto_days()
            self.auto_mode = 'slots'
            self.btn_auto_slots.config(text="СТОП", bg='#C0392B')
            self.run_auto_step()

    def toggle_auto_days(self):
        if self.auto_mode == 'days':
            self.auto_mode = None
            self.btn_auto_days.config(text="АВТО: ПОТОК", bg='#2980B9')
        else:
            # Отключаем другой режим если он был
            if self.auto_mode == 'slots': self.toggle_auto_slots()
            self.auto_mode = 'days'
            self.btn_auto_days.config(text="СТОП", bg='#C0392B')
            self.run_auto_days()

    def run_auto_step(self):
        if self.auto_mode == 'slots':
            self.next_step()
            self.after(600, self.run_auto_step)

    def run_auto_days(self):
        if self.auto_mode == 'days':
            # Теперь "АВТО: ПОТОК" работает как "АВТО: СЛОТЫ", но быстрее
            self.next_step()
            # Короткая пауза для динамики
            self.after(200, self.run_auto_days)

    def on_mouse_move(self, event):
        # Нахождение ближайшего объекта под мышью
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        item = self.canvas.find_closest(canvas_x, canvas_y)
        if item:
            coords = self.canvas.coords(item)
            if len(coords) == 4: # oval или rect
                cx, cy = (coords[0] + coords[2])/2, (coords[1] + coords[3])/2
                dist = math.sqrt((canvas_x - cx)**2 + (canvas_y - cy)**2)
                
                # Учитываем зум при проверке дистанции до агента
                if dist < 15 * self.zoom_level and item[0] in self.agent_names_by_id:
                    name = self.agent_names_by_id[item[0]]
                    agent = self.collective.agents[name]
                    info = (f"Имя: {name}\n"
                            f"Группа: {agent.group_id}\n"
                            f"Путь: {agent.archetype.name}\n"
                            f"Эмоция: {agent.get_primary_emotion()[0]}")
                    self.tooltip.show_tip(info, event.x_root, event.y_root)
                    return
        
        self.tooltip.hide_tip()

    def zoom(self, factor):
        new_zoom = self.zoom_level * factor
        # Ограничения зума
        if 0.1 <= new_zoom <= 5.0:
            self.zoom_level = new_zoom
            self.canvas.delete("all")
            self.draw_map()
            self.update_agent_positions()
            
            # Обновляем scrollregion
            self.canvas.config(scrollregion=(0, 0, 2500 * self.zoom_level, 5000 * self.zoom_level))
            self.lbl_zoom.config(text=f"Масштаб: {int(self.zoom_level * 100)}%")
