from core.agent_factory import AgentFactory
import random
import math
from typing import List, Dict
from model.constants import SportType, AgentStatus
from model.agent import Agent

class UniversityManager:
    """Управляющий структурой университета и расписанием."""
    
    def __init__(self, faculties=5, streams_per_faculty=5, groups_per_stream=3):
        self.faculties_count = faculties
        self.streams_per_faculty = streams_per_faculty
        self.groups_per_stream = groups_per_stream
        
        # Структура: faculties -> streams -> groups -> list of agent_names
        self.structure = {}
        self.schedules = {} # group_id -> {day_index: [pair1_room, pair2_room, ...]}
        
        # Аудитории
        self.rooms_info = {} # room_id -> {"capacity": int, "x": int, "y": int, "width": int, "height": int}
        self._initialize_rooms()

    def _initialize_rooms(self):
        """Создает физическую разметку аудиторий на сетке."""
        # Для простоты: сетка комнат 9x9
        # Каждая комната 150x150 пикселей
        room_size = 180
        padding = 20
        
        # 1. Лекционные залы (потоковые) - по одному на поток (25 шт)
        for s_idx in range(25):
            f_num = (s_idx // 5) + 1
            s_num = (s_idx % 5) + 1
            room_id = f"Aud_Faculty_{f_num}_Stream_{f_num}_{s_num}_L"
            
            col = s_idx % 8
            row = s_idx // 8
            
            self.rooms_info[room_id] = {
                "capacity": 100, 
                "type": "LECTURE",
                "display_name": f"№{101 + s_idx}",
                "x": padding + col * (room_size + padding),
                "y": padding + row * (room_size + padding),
                "width": room_size,
                "height": room_size
            }

        # 2. Семинарские комнаты (групповые) - по одной на группу (75 шт)
        # Начнем их со второго "этажа" (смещение по Y)
        offset_y = 5 * (room_size + padding)
        for g_idx in range(75):
            f_num = (g_idx // 15) + 1
            s_num = ((g_idx % 15) // 3) + 1
            g_num = (g_idx % 3) + 1
            room_id = f"Aud_Group_{f_num}_{s_num}_{g_num}_S"
            
            col = g_idx % 8
            row = g_idx // 8
            
            self.rooms_info[room_id] = {
                "capacity": 30,
                "type": "SEMINAR",
                "display_name": f"№{201 + g_idx}",
                "x": padding + col * (room_size + padding),
                "y": offset_y + padding + row * (room_size + padding),
                "width": room_size,
                "height": room_size
            }
            
        # 3. Спортзал (Gym)
        self.rooms_info["GYM"] = {
            "capacity": 1000,
            "type": "GYM",
            "display_name": "СПОРТЗАЛ",
            "x": padding,
            "y": offset_y + 10 * (room_size + padding),
            "width": room_size * 5,
            "height": room_size * 2
        }

        # 4. Коридор (Центральное пространство)
        # Разместим его между этажами
        self.rooms_info["CORRIDOR"] = {
            "capacity": 2000,
            "type": "CORRIDOR",
            "display_name": "КОРИДОР / ЗОНА ОТДЫХА",
            "x": padding,
            "y": offset_y - 200,
            "width": 8 * (room_size + padding),
            "height": 180
        }

    def get_seat_coordinates(self, room_id, student_index_in_room):
        """Возвращает координаты (x, y) для студента внутри комнаты."""
        info = self.rooms_info.get(room_id)
        if not info: return 0, 0
        
        # Рассадка рядами внутри комнаты (Адаптивно)
        margin = 25
        available_w = info["width"] - 2 * margin
        available_h = info["height"] - 2 * margin
        
        # Оцениваем оптимальное кол-во колонок исходя из пропорций
        # Для коридора (широкий) делаем много колонок
        if info.get("type") == "CORRIDOR":
            cols = 40
        elif info.get("type") == "LECTURE":
            cols = 10
        else:
            cols = 5
            
        row = student_index_in_room // cols
        col = student_index_in_room % cols
        
        # Шаг рассадки
        rows_needed = math.ceil(info["capacity"] / cols)
        step_x = available_w / (cols - 1) if cols > 1 else 0
        step_y = available_h / (rows_needed - 1) if rows_needed > 1 else 0
        
        res_x = info["x"] + margin + col * step_x
        res_y = info["y"] + margin + row * step_y
        return res_x, res_y

    def generate_structure(self, agent_names: List[str]):
        """Распределяет агентов по иерархии."""
        total_groups = self.faculties_count * self.streams_per_faculty * self.groups_per_stream
        agents_per_group = len(agent_names) // total_groups
        
        agent_idx = 0
        for f in range(self.faculties_count):
            faculty_id = f"Faculty_{f+1}"
            self.structure[faculty_id] = {}
            for s in range(self.streams_per_faculty):
                stream_id = f"Stream_{f+1}_{s+1}"
                self.structure[faculty_id][stream_id] = {}
                for g in range(self.groups_per_stream):
                    group_id = f"Group_{f+1}_{s+1}_{g+1}"
                    self.structure[faculty_id][stream_id][group_id] = []
                    
                    # Наполняем группу
                    for _ in range(agents_per_group):
                        if agent_idx < len(agent_names):
                            self.structure[faculty_id][stream_id][group_id].append(agent_names[agent_idx])
                            agent_idx += 1
        return self.structure

    def generate_schedules(self):
        """Генерирует расписание на 6 дней для каждой группы."""
        # Для простоты: у факультета свои аудитории
        # Каждая группа имеет 6 дней по 0-4 пары
        
        for f in range(self.faculties_count):
            faculty_id = f"Faculty_{f+1}"
            for s in range(self.streams_per_faculty):
                stream_id = f"Stream_{f+1}_{s+1}"
                for g in range(self.groups_per_stream):
                    group_id = f"Group_{f+1}_{s+1}_{g+1}"
                    
                    group_schedule = {}
                    for day in range(6): # Пн-Сб
                        # Рандомно 2-4 пары
                        num_pairs = random.randint(2, 4)
                        pairs = []
                        for p in range(num_pairs):
                            # Рандомно: лекция, семинар или физкультура (GYM)
                            rand = random.random()
                            if rand < 0.1: # 10% шанс физкультуры
                                room = "GYM"
                            elif rand < 0.4: # 30% шанс лекции
                                room = f"Aud_{faculty_id}_{stream_id}_L"
                            else: # Остальное - семинар
                                room = f"Aud_{group_id}_S"
                            pairs.append(room)
                        group_schedule[day] = pairs
                    self.schedules[group_id] = group_schedule

    def get_group_schedule(self, group_id, day_index):
        return self.schedules.get(group_id, {}).get(day_index, [])

    def create_university_agents(self) -> List[Agent]:
        """Создает 1875 агентов и распределяет их по структуре."""
        agents = []
        for f in range(self.faculties_count):
            faculty_id = f"Faculty_{f+1}"
            for s in range(self.streams_per_faculty):
                stream_id = f"Stream_{f+1}_{s+1}"
                for g in range(self.groups_per_stream):
                    group_id = f"Group_{f+1}_{s+1}_{g+1}"
                    # В каждой группе 25 студентов
                    for i in range(25):
                        name = f"Student_{f+1}_{s+1}_{g+1}_{i+1}"
                        agent = AgentFactory.create_agent(name)
                        agent.set_university_info(faculty_id, stream_id, group_id)
                        agents.append(agent)
        return agents

    def get_all_groups(self) -> List[str]:
        """Возвращает плоский список всех существующих ID групп."""
        groups = []
        for f in range(self.faculties_count):
            for s in range(self.streams_per_faculty):
                for g in range(self.groups_per_stream):
                    groups.append(f"Group_{f+1}_{s+1}_{g+1}")
        return groups

