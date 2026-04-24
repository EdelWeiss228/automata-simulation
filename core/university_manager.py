import random
import math
from typing import List, Dict
from core.agent_factory import AgentFactory
from model.constants import SportType, AgentStatus
from model.agent import Agent

class UniversityManager:
    """Управляющий структурой университета (v6.9.29: Русские имена)."""
    
    FACULTY_NAMES = ["П", "Ф", "Р", "М", "Эк"]
    MASTER_FACULTIES = ["ММ", "ПМ", "ПО", "ЭкМ", "РМ", "ГП"]
    
    NAMES_M = ["Иван", "Александр", "Сергей", "Дмитрий", "Андрей", "Алексей", "Максим", "Евгений", "Михаил", "Владимир", "Никита", "Артем", "Игорь"]
    SURNAMES_M = ["Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов", "Попов", "Васильев", "Соколов", "Михайлов", "Новиков", "Федоров", "Морозов"]
    
    NAMES_F = ["Мария", "Анна", "Елена", "Ольга", "Наталья", "Екатерина", "Татьяна", "Ирина", "Светлана", "Юлия", "Виктория", "Анастасия", "Дарья"]
    SURNAMES_F = ["Иванова", "Петрова", "Сидорова", "Смирнова", "Кузнецова", "Попова", "Васильева", "Соколова", "Михайлова", "Новикова", "Федорова", "Морозова"]

    def __init__(self, faculties=5, streams_per_faculty=4, groups_per_stream=3, start_academic_year=2022):
        self.faculties_count = faculties
        self.streams_per_faculty = streams_per_faculty
        self.groups_per_stream = groups_per_stream
        self.start_academic_year = start_academic_year
        self.rooms_info = {} 
        self._initialize_rooms()
        self.generate_schedules()

    def _initialize_rooms(self):
        padding = 40
        l_w, l_h = 240, 480
        for s_idx in range(25):
            room_id = f"Aud_{self.FACULTY_NAMES[s_idx // 5]}_{str(self.start_academic_year - (s_idx % 5))[2:]}_L"
            self.rooms_info[room_id] = {
                "capacity": 102, "type": "LECTURE", "display_name": f"№{101 + s_idx} (Л)",
                "x": padding + (s_idx % 4) * (l_w + padding), "y": padding + (s_idx // 4) * (l_h + padding),
                "width": l_w, "height": l_h
            }
        self.rooms_info["CORRIDOR"] = {"capacity": 1500, "type": "CORRIDOR", "display_name": "ХОЛЛ", "x": padding, "y": 3800, "width": 1100, "height": 600}
        s_w, s_h = 240, 240
        for g_idx in range(75):
            room_id = f"Aud_{self.FACULTY_NAMES[g_idx // 15]}_{str(self.start_academic_year - ((g_idx % 15) // 3))[2:]}_{(g_idx % 3) + 1}_S"
            self.rooms_info[room_id] = {
                "capacity": 30, "type": "SEMINAR", "display_name": f"№{201 + g_idx}",
                "x": padding + (g_idx % 5) * (s_w + padding), "y": 4500 + (g_idx // 5) * (s_h + padding),
                "width": s_w, "height": s_h
            }
        self.rooms_info["GYM"] = {"capacity": 1000, "type": "GYM", "display_name": "СПОРТЗАЛ", "x": padding, "y": 9000, "width": 1200, "height": 600}

    def get_room_cols(self, room_id: str) -> int:
        info = self.rooms_info.get(room_id, {})
        rtype = info.get("type", "SEMINAR")
        if rtype in ["CORRIDOR", "GYM"]: return 40
        return 6

    def get_seat_coordinates(self, room_id, s_idx):
        info = self.rooms_info.get(room_id)
        if not info: return 0, 0
        cols = self.get_room_cols(room_id)
        mx, my = 35, 45 
        step_x = (info["width"] - 2*mx) / (cols - 1) if cols > 1 else 0
        rows_num = math.ceil(info["capacity"] / cols)
        step_y = (info["height"] - 2*my) / (rows_num - 1) if rows_num > 1 else 10
        rx = info["x"] + mx + (s_idx % cols) * step_x
        ry = info["y"] + my + (s_idx // cols) * step_y
        if info["type"] in ["CORRIDOR", "GYM"]:
            rnd = random.Random(s_idx + hash(room_id))
            rx += rnd.uniform(-15, 15); ry += rnd.uniform(-15, 15)
        return rx, ry

    def get_desk_geometry(self, room_id, s_idx):
        info = self.rooms_info.get(room_id)
        if not info or info["type"] not in ["LECTURE", "SEMINAR"]: return None
        sx, sy = self.get_seat_coordinates(room_id, s_idx)
        cols = self.get_room_cols(room_id)
        step_x = (info["width"] - 70) / (cols - 1)
        return {"dx": sx - 6, "dy": sy + 5, "dw": step_x + 12, "dh": 8}

    def generate_schedules(self):
        self.schedules = {}
        for f in range(self.faculties_count):
            f_name = self.FACULTY_NAMES[f]
            for s in range(self.streams_per_faculty):
                year_suffix = str(self.start_academic_year - s)[2:]
                stream_lecture_slots = {day: [random.random() < 0.3 for _ in range(4)] for day in range(6)}
                for g in range(self.groups_per_stream):
                    group_id = f"{f_name}-{year_suffix}-{g+1}"
                    group_schedule = {}
                    for day in range(6):
                        pairs = []
                        for p in range(4):
                            if stream_lecture_slots[day][p]: pairs.append(f"Aud_{f_name}_{year_suffix}_L")
                            else: pairs.append("GYM" if random.random() < 0.1 else f"Aud_{f_name}_{year_suffix}_{g+1}_S")
                        group_schedule[day] = pairs
                    self.schedules[group_id] = group_schedule
        for m_name in self.MASTER_FACULTIES:
            for year in [1, 2]:
                group_id = f"{m_name}-M{year}-1"
                group_schedule = {}
                for day in range(6):
                    pairs = []
                    for p in range(4):
                        # У магистров больше шансов на лекции и свободное время (v6.9.34)
                        if random.random() < 0.4: 
                            # Генерируем случайную лекционную аудиторию
                            f_code = self.FACULTY_NAMES[random.randint(0,4)]
                            y_code = str(self.start_academic_year - random.randint(0, 4))[2:]
                            pairs.append(f"Aud_{f_code}_{y_code}_L")
                        else: 
                            pairs.append("GYM" if random.random() < 0.2 else "CORRIDOR")
                    group_schedule[day] = pairs
                self.schedules[group_id] = group_schedule

    def get_group_schedule(self, group_id, day_idx):
        return getattr(self, 'schedules', {}).get(group_id, {}).get(day_idx, [])

    def _generate_human_name(self) -> str:
        if random.random() < 0.5:
            return f"{random.choice(self.NAMES_M)} {random.choice(self.SURNAMES_M)}"
        return f"{random.choice(self.NAMES_F)} {random.choice(self.SURNAMES_F)}"

    def create_university_agents(self, total_bac=1500, total_mag=180, bachelor_counts=None, master_counts=None) -> List[Agent]:
        from core.agent_factory import AgentFactory
        from model.archetypes import ArchetypeEnum
        agents = []
        b_counts = bachelor_counts or {}
        m_counts = master_counts or {}
        
        def build_pool(counts, total):
            pool = []
            arch_list = list(ArchetypeEnum)
            for name, count in counts.items():
                arch = next(a for a in arch_list if a.name == name)
                pool.extend([arch] * int(count))
            while len(pool) < total:
                pool.append(random.choice(arch_list))
            random.shuffle(pool)
            return pool[:total]

        bac_pool = build_pool(b_counts, total_bac)
        mag_pool = build_pool(m_counts, total_mag)

        for f in range(self.faculties_count):
            if not bac_pool: break
            f_name = self.FACULTY_NAMES[f]
            for s in range(self.streams_per_faculty):
                if not bac_pool: break
                year_suffix = str(self.start_academic_year - s)[2:]
                for g in range(self.groups_per_stream):
                    if not bac_pool: break
                    group_id = f"{f_name}-{year_suffix}-{g+1}"
                    for i in range(25):
                        if not bac_pool: break
                        # Уникальный ID: S-П-22-1-01 (v6.9.32)
                        agent_id = f"S-{group_id}-{i+1:02d}"
                        agent = AgentFactory.create_agent(self._generate_human_name(), archetype_enum=bac_pool.pop(), agent_id=agent_id)
                        agent.set_university_info(f_name, f"{f_name}-{year_suffix}", group_id)
                        agents.append(agent)

        # 3. Генерация магистров
        for m_idx, m_name in enumerate(self.MASTER_FACULTIES):
            if not mag_pool: break
            for year in [1, 2]:
                if not mag_pool: break
                group_id = f"{m_name}-M{year}-1"
                for i in range(15):
                    if not mag_pool: break
                    # Униканый ID: M-ММ-M1-01
                    agent_id = f"M-{group_id}-{i+1:02d}"
                    agent = AgentFactory.create_agent(self._generate_human_name(), archetype_enum=mag_pool.pop(), agent_id=agent_id)
                    agent.degree_type = "MASTER"
                    parent_faculty = self.FACULTY_NAMES[m_idx % len(self.FACULTY_NAMES)]
                    agent.set_university_info(parent_faculty, f"{m_name}-M{year}", group_id)
                    agents.append(agent)
        return agents
