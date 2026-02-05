from core.agent_factory import AgentFactory
import random
import math
from typing import List, Dict
from model.constants import SportType, AgentStatus
from model.agent import Agent

class UniversityManager:
    """Управляющий структурой университета и расписанием (v4.5: Русские имена)."""
    
    FACULTY_NAMES = ["П", "Ф", "Р", "М", "Эк"]
    START_YEAR = 22
    
    # База имен для русификации (v4.5)
    NAMES_M = ["Александр", "Дмитрий", "Максим", "Сергей", "Андрей", "Алексей", "Артем", "Илья", "Кирилл", "Михаил", "Никита", "Матвей", "Роман", "Егор", "Иван"]
    NAMES_F = ["Мария", "Анастасия", "Анна", "Виктория", "Екатерина", "Наталья", "Елена", "Дарья", "Алиса", "София", "Юлия", "Ольга", "Татьяна", "Ирина", "Полина"]
    SURNAMES = ["Иванов", "Петров", "Смирнов", "Сергеев", "Волков", "Кузнецов", "Васильев", "Романов", "Козлов", "Лебедев", "Новиков", "Морозов", "Павлов", "Соколов", "Федоров"]

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
        """Создает физическую разметку аудиторий (v4.5: Возврат к номерам №)."""
        room_size = 180
        padding = 20
        
        # 1. Лекционные залы (потоковые) - 4 ряда по 200 пикселей (до y=800)
        for s_idx in range(25):
            f_idx = s_idx // 5
            s_idx_in_f = s_idx % 5
            
            f_name = self.FACULTY_NAMES[f_idx]
            year = self.START_YEAR + s_idx_in_f
            room_id = f"Aud_{f_name}_{year}_L"
            
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

        # 2. Коридор (Центральное пространство) - Теперь МЕЖДУ лекциями и семинарами (v4.7)
        # Лекции заканчиваются на y=800. Холл начнем с 850.
        corridor_y = 850
        corridor_h = 450
        self.rooms_info["CORRIDOR"] = {
            "capacity": 2000,
            "type": "CORRIDOR",
            "display_name": "КОРИДОР / ХОЛЛ",
            "x": padding,
            "y": corridor_y,
            "width": 8 * (room_size + padding),
            "height": corridor_h
        }

        # 3. Семинарские комнаты (групповые) - Начнем ПОСЛЕ коридора
        # Коридор заканчивается на 850 + 450 = 1300. Семинары начнем с 1350.
        offset_y_seminars = 1350
        for g_idx in range(75):
            f_idx = g_idx // 15
            s_idx_in_f = (g_idx % 15) // 3
            g_num = (g_idx % 3) + 1
            
            f_name = self.FACULTY_NAMES[f_idx]
            year = self.START_YEAR + s_idx_in_f
            room_id = f"Aud_{f_name}_{year}_{g_num}_S"
            
            col = g_idx % 8
            row = g_idx // 8
            
            self.rooms_info[room_id] = {
                "capacity": 30,
                "type": "SEMINAR",
                "display_name": f"№{201 + g_idx}",
                "x": padding + col * (room_size + padding),
                "y": offset_y_seminars + row * (room_size + padding),
                "width": room_size,
                "height": room_size
            }
            
        # 4. Спортзал (Gym) - Еще ниже
        # Семинары (75 шт, 10 рядов) закончатся на 1350 + 10*200 = 3350.
        self.rooms_info["GYM"] = {
            "capacity": 1000,
            "type": "GYM",
            "display_name": "СПОРТЗАЛ",
            "x": padding,
            "y": 3400,
            "width": room_size * 6,
            "height": room_size * 3
        }

    def get_seat_coordinates(self, room_id, student_index_in_room):
        """Возвращает координаты (x, y) для студента (v4.6: Разряженность и рандом)."""
        info = self.rooms_info.get(room_id)
        if not info: return 0, 0
        
        # Рассадка рядами внутри комнаты (Адаптивно)
        margin = 35
        available_w = info["width"] - 2 * margin
        available_h = info["height"] - 2 * margin
        
        # Оцениваем оптимальное кол-во колонок исходя из пропорций
        if info.get("type") == "CORRIDOR":
            cols = 45 # Больше колонок для длинного холла
        elif info.get("type") == "LECTURE":
            cols = 10
        elif info.get("type") == "GYM":
            cols = 20
        else:
            cols = 5
            
        row = student_index_in_room // cols
        col = student_index_in_room % cols
        
        # Шаг рассадки
        rows_needed = math.ceil(info["capacity"] / cols)
        step_x = available_w / (cols - 1) if cols > 1 else 0
        step_y = available_h / (rows_needed - 1) if rows_needed > 1 else 0
        
        # Базовые координаты
        res_x = info["x"] + margin + col * step_x
        res_y = info["y"] + margin + row * step_y
        
        # v4.6: Добавляем "дриблинг" (jitter) для коридоров и зала, чтобы не было ровных шеренг
        if info.get("type") in ["CORRIDOR", "GYM"]:
            res_x += random.uniform(-15, 15)
            res_y += random.uniform(-15, 15)
            
        return res_x, res_y

    def generate_structure(self, agent_names: List[str]):
        """Распределяет агентов по иерархии (v4.3: Реалистичные названия)."""
        total_groups = self.faculties_count * self.streams_per_faculty * self.groups_per_stream
        agents_per_group = len(agent_names) // total_groups
        
        agent_idx = 0
        for f in range(self.faculties_count):
            f_name = self.FACULTY_NAMES[f]
            self.structure[f_name] = {}
            for s in range(self.streams_per_faculty):
                year = self.START_YEAR + s
                stream_id = f"{f_name}-{year}"
                self.structure[f_name][stream_id] = {}
                for g in range(self.groups_per_stream):
                    group_id = f"{f_name}-{year}-{g+1}"
                    self.structure[f_name][stream_id][group_id] = []
                    
                    # Наполняем группу
                    for _ in range(agents_per_group):
                        if agent_idx < len(agent_names):
                            self.structure[f_name][stream_id][group_id].append(agent_names[agent_idx])
                            agent_idx += 1
        return self.structure

    def generate_schedules(self):
        """Генерирует расписание (v4.4: Синхронизация лекций для потока)."""
        for f in range(self.faculties_count):
            f_name = self.FACULTY_NAMES[f]
            for s in range(self.streams_per_faculty):
                year = self.START_YEAR + s
                
                # 1. Сначала генерируем ОБЩУЮ сетку лекций для всего потока (года)
                # Чтобы все 3 группы были на лекции одновременно
                stream_lecture_slots = {} # day -> list of bool (is_lecture)
                for day in range(6):
                    # В день макс 4 слота. Определим, какие из них лекционные (30% шанс)
                    slots = []
                    for p in range(4):
                        slots.append(random.random() < 0.3)
                    stream_lecture_slots[day] = slots

                # 2. Теперь для каждой группы применяем лекции и добавляем семинары
                for g in range(self.groups_per_stream):
                    g_num = g + 1
                    group_id = f"{f_name}-{year}-{g_num}"
                    
                    group_schedule = {}
                    for day in range(6):
                        pairs = []
                        # Всего пытаемся заполнить 4 слота, но итоговое кол-во пар 2-4
                        target_pairs = random.randint(2, 4)
                        
                        for p in range(4):
                            if len(pairs) >= target_pairs: break
                            
                            if stream_lecture_slots[day][p]:
                                # Если это лекционный слот для потока - все идут в лекторий
                                pairs.append(f"Aud_{f_name}_{year}_L")
                            else:
                                # Иначе семинар или зал (индивидуально для группы)
                                rand = random.random()
                                if rand < 0.15: # 15% шанс физкультуры
                                    pairs.append("GYM")
                                else:
                                    pairs.append(f"Aud_{f_name}_{year}_{g_num}_S")
                        
                        group_schedule[day] = pairs
                    self.schedules[group_id] = group_schedule

    def get_group_schedule(self, group_id, day_index):
        return self.schedules.get(group_id, {}).get(day_index, [])

    def create_university_agents(self) -> List[Agent]:
        """Создает студентов с случайными русскими именами (v4.5)."""
        import numpy as np
        from model.archetypes import ArchetypeEnum
        
        total_students = self.faculties_count * self.streams_per_faculty * self.groups_per_stream * 25
        agents = []
        
        sensitivities = np.random.uniform(0.1, 3.0, total_students)
        archetypes_list = list(ArchetypeEnum)
        archetype_indices = np.random.randint(0, len(archetypes_list), total_students)
        
        idx = 0
        for f in range(self.faculties_count):
            f_name = self.FACULTY_NAMES[f]
            for s in range(self.streams_per_faculty):
                year = self.START_YEAR + s
                for g in range(self.groups_per_stream):
                    g_num = g + 1
                    group_id = f"{f_name}-{year}-{g_num}"
                    for i in range(25):
                        # Рандомное русское имя
                        is_fem = random.random() < 0.5
                        base_name = random.choice(self.NAMES_F if is_fem else self.NAMES_M)
                        surname = random.choice(self.SURNAMES)
                        if is_fem and (surname.endswith("ов") or surname.endswith("ев")):
                            surname += "а"
                        
                        unique_name = f"{base_name} {surname} ({f_name}-{year}-{g_num}-{i+1})"
                        
                        agent = AgentFactory.create_agent(
                            unique_name, 
                            archetype_enum=archetypes_list[archetype_indices[idx]],
                            sensitivity=float(sensitivities[idx])
                        )
                        agent.set_university_info(f_name, f"{f_name}-{year}", group_id)
                        agents.append(agent)
                        idx += 1
        return agents

    def get_all_groups(self) -> List[str]:
        """Возвращает плоский список всех существующих ID групп."""
        groups = []
        for f in range(self.faculties_count):
            f_name = self.FACULTY_NAMES[f]
            for s in range(self.streams_per_faculty):
                year = self.START_YEAR + s
                for g in range(self.groups_per_stream):
                    groups.append(f"{f_name}-{year}-{g+1}")
        return groups

