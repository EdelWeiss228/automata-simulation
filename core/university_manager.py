import random
import math
from typing import List, Dict
from core.agent_factory import AgentFactory
from model.constants import SportType, AgentStatus
from model.agent import Agent

class UniversityManager:
    """Управляющий структурой и логикой университета."""

    FACULTY_NAMES = ["П", "Ф", "Р", "М", "Эк"]
    MASTER_FACULTIES = ["ММ", "ПМ", "ПО", "ЭкМ", "РМ", "ГП"]
    MASTER_YEARS = (1, 2)
    MASTER_GROUP_SIZE = 10
    MASTER_GROUPS = len(MASTER_FACULTIES) * len(MASTER_YEARS)
    MASTER_CAPACITY = MASTER_GROUPS * MASTER_GROUP_SIZE
    
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
        self.rooms_info["CORRIDOR"] = {"capacity": 1500, "type": "CORRIDOR", "display_name": "ХОЛЛ", "x": padding, "y": 3800, "width": 1150, "height": 600}
        s_w, s_h = 240, 240
        for g_idx in range(75):
            room_id = f"Aud_{self.FACULTY_NAMES[g_idx // 15]}_{str(self.start_academic_year - ((g_idx % 15) // 3))[2:]}_{(g_idx % 3) + 1}_S"
            self.rooms_info[room_id] = {
                "capacity": 30, "type": "SEMINAR", "display_name": f"№{201 + g_idx}",
                "x": padding + (g_idx % 5) * (s_w + padding), "y": 4500 + (g_idx // 5) * (s_h + padding),
                "width": s_w, "height": s_h
            }
        self.rooms_info["GYM"] = {"capacity": 1000, "type": "GYM", "display_name": "СПОРТЗАЛ", "x": padding, "y": 9000, "width": 1260, "height": 600}

    def get_room_cols(self, room_id: str) -> int:
        info = self.rooms_info.get(room_id, {})
        rtype = info.get("type", "SEMINAR")
        if rtype in ["CORRIDOR", "GYM"]: return 42
        return 6

    @staticmethod
    def stable_hash(text: str) -> int:
        """Стабильный FNV-1a хэш.

        Встроенный hash() для строк рандомизирован в каждом процессе
        (PYTHONHASHSEED), из-за чего визуальные координаты менялись от запуска
        к запуску. Для воспроизводимости нужен собственный хэш.
        """
        value = 2166136261
        for byte in text.encode("utf-8"):
            value ^= byte
            value = (value * 16777619) & 0xFFFFFFFF
        return value

    @staticmethod
    def year_suffix(year: int) -> str:
        """Двузначный суффикс года набора: 2024 -> 24."""
        return str(int(year))[2:]

    @classmethod
    def master_group_id(cls, direction: str, enrollment_year: int) -> str:
        """Идентификатор магистерской когорты по направлению и году набора."""
        return f"{direction}-{cls.year_suffix(enrollment_year)}"

    @classmethod
    def master_group_ids(cls, academic_year: int) -> List[str]:
        """Активные магистерские когорты: текущий набор и предыдущий.

        У магистратуры нет подгрупп внутри курса: 6 направлений x 2 курса,
        по одной группе-когорте на направление и год набора. Идентификатор
        когорты не меняется при переходе с первого курса на второй.
        """
        return [
            cls.master_group_id(direction, academic_year - offset)
            for direction in cls.MASTER_FACULTIES
            for offset in (0, 1)
        ]

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
            rnd = random.Random(s_idx + self.stable_hash(room_id))
            jx = (step_x / 3) if step_x > 0 else 5
            jy = (step_y / 3) if step_y > 0 else 5
            rx += rnd.uniform(-jx, jx); ry += rnd.uniform(-jy, jy)
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
                            if random.random() < 0.15:
                                pairs.append("EMPTY")
                            elif stream_lecture_slots[day][p]: 
                                pairs.append(f"Aud_{f_name}_{year_suffix}_L")
                            else: 
                                pairs.append("GYM" if random.random() < 0.1 else f"Aud_{f_name}_{year_suffix}_{g+1}_S")
                        group_schedule[day] = pairs
                    self.schedules[group_id] = group_schedule
                    
        for m_name in self.MASTER_FACULTIES:
            for course_year in self.MASTER_YEARS:
                enrollment_year = self.start_academic_year - (course_year - 1)
                group_id = self.master_group_id(m_name, enrollment_year)
                self.ensure_master_schedule(group_id)

    def _build_master_schedule(self) -> dict:
        all_lectures = [r for r in self.rooms_info if r.endswith("_L")]
        all_seminars = [r for r in self.rooms_info if r.endswith("_S")]
        group_schedule = {}
        for day in range(6):
            pairs = []
            for _ in range(4):
                if random.random() < 0.15:
                    pairs.append("EMPTY")
                elif random.random() < 0.3 and all_lectures:
                    pairs.append(random.choice(all_lectures))
                elif all_seminars:
                    pairs.append(
                        "GYM" if random.random() < 0.1
                        else random.choice(all_seminars)
                    )
                else:
                    pairs.append("GYM")
            group_schedule[day] = pairs
        return group_schedule

    def ensure_master_schedule(self, group_id: str) -> None:
        """Создать расписание для магистерской когорты, если его ещё нет."""
        if group_id not in self.schedules:
            self.schedules[group_id] = self._build_master_schedule()

    def ensure_bachelor_schedule(self, group_id: str) -> None:
        """Создать расписание для новой бакалаврской группы.

        `generate_schedules` строит расписание только для лет, существующих на
        старте симуляции. После ротации появляются группы следующего года,
        и без расписания их студенты не попадают ни на одну пару.
        """
        if group_id in self.schedules:
            return
        parts = group_id.split("-")
        if len(parts) != 3:
            return
        f_name, year_suffix, _ = parts
        all_lectures = [r for r in self.rooms_info if r.endswith("_L")]
        all_seminars = [r for r in self.rooms_info if r.endswith("_S")]
        group_schedule = {}
        for day in range(6):
            pairs = []
            for _ in range(4):
                if random.random() < 0.15:
                    pairs.append("EMPTY")
                elif random.random() < 0.3 and all_lectures:
                    pairs.append(random.choice(all_lectures))
                elif all_seminars:
                    pairs.append("GYM" if random.random() < 0.1 else random.choice(all_seminars))
                else:
                    pairs.append(f"Aud_{f_name}_{year_suffix}_L")
            group_schedule[day] = pairs
        self.schedules[group_id] = group_schedule

    def get_group_schedule(self, group_id, day_idx):
        return getattr(self, 'schedules', {}).get(group_id, {}).get(day_idx, [])

    def get_all_groups(self) -> List[str]:
        return list(getattr(self, 'schedules', {}).keys())

    def create_new_cohort(self, academic_year, master_filled_counts=None, bachelor_weights=None, master_weights=None) -> List[Agent]:
        from model.archetypes import ArchetypeEnum
        agents = []
        master_filled = master_filled_counts or {}
        b_weights = bachelor_weights or {}
        m_weights = master_weights or {}
        
        # 1. Новые бакалавры (1 курс)
        year_suffix = str(academic_year)[2:]
        for f in range(self.faculties_count):
            f_name = self.FACULTY_NAMES[f]
            # В ротации добавляем один новый набор (1-й курс)
            for g in range(self.groups_per_stream):
                group_id = f"{f_name}-{year_suffix}-{g+1}"
                self.ensure_bachelor_schedule(group_id)
                for i in range(25):
                    agent_id = f"S-{group_id}-{i+1:02d}"
                    arch = self._pick_archetype(b_weights)
                    agent = AgentFactory.create_agent(self._generate_human_name(), archetype_enum=arch, agent_id=agent_id)
                    agent.set_university_info(f_name, f"{f_name}-{year_suffix}", group_id)
                    agent.course_year = 1
                    agent.enrollment_year = academic_year
                    agents.append(agent)
                    
        # 2. Новые магистры (1 курс). Когорта набора academic_year добивается
        # до 10 человек: продолжающие занимают часть мест, остальные — внешние.
        for m_idx, m_name in enumerate(self.MASTER_FACULTIES):
            group_id = self.master_group_id(m_name, academic_year)
            self.ensure_master_schedule(group_id)
            already_filled = int(master_filled.get(group_id, 0))
            to_add = max(0, self.MASTER_GROUP_SIZE - already_filled)
            for i in range(to_add):
                agent_id = (
                    f"M-{group_id}-{already_filled + i + 1:02d}"
                )
                arch = self._pick_archetype(m_weights)
                agent = AgentFactory.create_agent(self._generate_human_name(), archetype_enum=arch, agent_id=agent_id)
                agent.degree_type = "MASTER"
                agent.course_year = 1
                agent.enrollment_year = academic_year
                parent_faculty = self.FACULTY_NAMES[m_idx % len(self.FACULTY_NAMES)]
                agent.set_university_info(parent_faculty, m_name, group_id)
                agents.append(agent)

        return agents

    def _pick_archetype(self, weights):
        from model.archetypes import ArchetypeEnum
        arch_list = list(ArchetypeEnum)
        if not weights:
            return random.choice(arch_list)
        
        # weights может быть list (пропорции по порядку ArchetypeEnum) или dict {name: weight}
        if isinstance(weights, list):
            probs = weights
            if sum(probs) == 0:
                return random.choice(arch_list)
            return random.choices(arch_list, weights=probs, k=1)[0]
        else:
            # dict формат
            choices = list(weights.keys())
            probs = [weights[c] for c in choices]
            if sum(probs) == 0:
                return random.choice(arch_list)
            arch_name = random.choices(choices, weights=probs, k=1)[0]
            return next(a for a in arch_list if a.name == arch_name)

    def _generate_human_name(self) -> str:
        if random.random() < 0.5:
            return f"{random.choice(self.NAMES_M)} {random.choice(self.SURNAMES_M)}"
        return f"{random.choice(self.NAMES_F)} {random.choice(self.SURNAMES_F)}"

    def create_university_agents(self, total_bac=1500, total_mag=None, bachelor_counts=None, master_counts=None) -> List[Agent]:
        from core.agent_factory import AgentFactory
        from model.archetypes import ArchetypeEnum
        agents = []
        b_counts = bachelor_counts or {}
        m_counts = master_counts or {}

        if total_mag is None:
            total_mag = self.MASTER_CAPACITY
        total_mag = max(0, min(int(total_mag), self.MASTER_CAPACITY))
        
        def build_pool(counts, total):
            pool = []
            arch_list = list(ArchetypeEnum)
            
            # Маппинг устаревших/альтернативных имен к Honkai-архетипам
            name_mapping = {
                "INNOVATOR": "TRAILBLAZE",
                "MEDIATOR": "HARMONY",
                "DESTRUCTOR": "NIHILITY",
                "PROTECTOR": "PRESERVATION",
                "OPPORTUNIST": "ELATION",
                "COMPETITOR": "HUNT",
                "NONCONFORMIST": "ENIGMATA",
                "ANALYST": "ERUDITION",
                "REFLECTOR": "REMEMBRANCE"
            }
            
            for name, count in counts.items():
                mapped_name = name_mapping.get(name.upper(), name.upper())
                arch = next((a for a in arch_list if a.name == mapped_name), None)
                if arch:
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
                        # Формирование уникального идентификатора по шаблону S-П-22-1-01
                        agent_id = f"S-{group_id}-{i+1:02d}"
                        agent = AgentFactory.create_agent(self._generate_human_name(), archetype_enum=bac_pool.pop(), agent_id=agent_id)
                        agent.set_university_info(f_name, f"{f_name}-{year_suffix}", group_id)
                        agent.course_year = s + 1
                        agent.enrollment_year = self.start_academic_year - s
                        agents.append(agent)

        # 3. Генерация магистров. 6 направлений x 2 активные когорты
        # (текущий набор и предыдущий), по 10 человек. Пул распределяется
        # по всем 12 когортам, а не заполняет первые группы подряд.
        active_master_groups = []
        for m_name in self.MASTER_FACULTIES:
            for course_year in self.MASTER_YEARS:
                enrollment_year = self.start_academic_year - (course_year - 1)
                active_master_groups.append((
                    self.master_group_id(m_name, enrollment_year),
                    m_name,
                    enrollment_year,
                    course_year,
                ))

        group_counters = {gid: 0 for gid, _, _, _ in active_master_groups}
        for pool_idx in range(len(mag_pool)):
            group_id, direction, enrollment_year, course_year = (
                active_master_groups[pool_idx % len(active_master_groups)]
            )
            group_counters[group_id] += 1
            agent_id = f"M-{group_id}-{group_counters[group_id]:02d}"
            agent = AgentFactory.create_agent(
                self._generate_human_name(),
                archetype_enum=mag_pool[pool_idx],
                agent_id=agent_id,
            )
            agent.degree_type = "MASTER"
            agent.course_year = course_year
            agent.enrollment_year = enrollment_year
            parent_faculty = self.FACULTY_NAMES[
                self.MASTER_FACULTIES.index(direction) % len(self.FACULTY_NAMES)
            ]
            agent.set_university_info(parent_faculty, direction, group_id)
            agents.append(agent)
        return agents
