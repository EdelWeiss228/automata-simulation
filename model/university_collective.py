import random
import numpy as np
import datetime
import math
from typing import List, Tuple, Dict, Optional
from model.collective import Collective
from model.agent import Agent
from model.constants import AgentStatus, LocationType, SportType, TimeSlotType
from core.university_manager import UniversityManager
from core.interaction_strategy import InteractionStrategy

class UniversityCollective(Collective):
    """
    Расширенный коллектив для симуляции университета.
    Управляет расписанием, локациями и специфическими правилами v3.0.
    """

    def __init__(self, seed=None, config=None):
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        super().__init__(seed=seed)
        
        # Загрузка конфига (v6.7)
        self.config = config or {}
        self.current_academic_year = self.config.get("start_year", 2024)
        self.current_date = datetime.date(self.current_academic_year, 9, 1)
        self.master_chance = self.config.get("master_chance", 0.3)
        self.bachelor_counts = self.config.get("bachelor_counts", None)
        self.master_counts = self.config.get("master_counts", None)
        self.total_bac = self.config.get("total_bac", 1500)
        self.total_mag = self.config.get("total_mag", 120) # v6.9.27: Новый стандарт 120
        
        self.uni_manager = UniversityManager(start_academic_year=self.current_academic_year)
        self.uni_manager.generate_schedules()
        
        # Группировка для быстрого доступа
        self.groups_map = {} # group_id -> [agent_names]
        
        # Заселяем университет согласно конфигу (v6.9.27)
        if not self.agents:
            initial_agents = self.uni_manager.create_university_agents(
                total_bac=self.total_bac,
                total_mag=self.total_mag,
                bachelor_counts=self.bachelor_counts,
                master_counts=self.master_counts
            )
            for agent in initial_agents:
                self.add_agent(agent)
                
            # Фиксируем "ДНК" университета для будущих поколений (v6.9.2)
            from model.archetypes import ArchetypeEnum
            arch_list = list(ArchetypeEnum)
            
            def calculate_weights(agents_subset, raw_counts):
                # Если пользователь ничего не ввел (всё по 0), стабильность не фиксируем
                if not raw_counts or sum(raw_counts.values()) == 0:
                    return None
                    
                counts = {arch.name: 0 for arch in arch_list}
                for a in agents_subset:
                    counts[a.archetype.name] += 1
                total = len(agents_subset)
                return [counts[arch.name]/total for arch in arch_list]
            
            bac_agents = [a for a in self.agents.values() if getattr(a, 'degree_type', 'BACHELOR') == 'BACHELOR']
            mag_agents = [a for a in self.agents.values() if getattr(a, 'degree_type', 'BACHELOR') == 'MASTER']
            
            self.bac_weights_list = calculate_weights(bac_agents, self.bachelor_counts)
            self.mag_weights_list = calculate_weights(mag_agents, self.master_counts)
        
        # Очередь слотов для пошагового выполнения
        self.day_schedule_slots = [
            TimeSlotType.PAIR_1, TimeSlotType.BREAK_1,
            TimeSlotType.PAIR_2, TimeSlotType.BREAK_2,
            TimeSlotType.PAIR_3, TimeSlotType.BREAK_3,
            TimeSlotType.PAIR_4, TimeSlotType.GYM,
            TimeSlotType.CLEANUP
        ]
        self.current_slot_idx = 0
        self.current_rooms = {} # room_id -> [agent_names] (для GUI)
        self.agent_current_seat = {} # name -> seat_index (v6.9.13)
        self.last_interactions = [] # [(name1, name2, status)] для линий связи

    def add_agent(self, agent):
        """Добавить агента в коллектив и обновить иерархию групп."""
        super().add_agent(agent)
        gid = getattr(agent, 'group_id', None)
        if gid:
            if gid not in self.groups_map:
                self.groups_map[gid] = []
            if agent.name not in self.groups_map[gid]:
                self.groups_map[gid].append(agent.name)

    def remove_agent(self, agent_name):
        """Удалить агента и очистить упоминания в группах."""
        agent = self.get_agent(agent_name)
        if agent:
            gid = getattr(agent, 'group_id', None)
            if gid in self.groups_map and agent_name in self.groups_map[gid]:
                self.groups_map[gid].remove(agent_name)
        
        super().remove_agent(agent_name)

    def perform_next_step(self) -> List[Tuple[str, str, str]]:
        """
        Выполняет один шаг (слот) симуляции университета.
        Возвращает список взаимодействий.
        """
        day_of_week = self.current_date.weekday()
        if day_of_week == 6:
            self.current_slot_idx = 0
            self.last_interactions = []
            return self._handle_sunday()

        if self.current_slot_idx >= len(self.day_schedule_slots):
            self.current_slot_idx = 0
            # Переходим к следующему дню
            self.current_step += 1
            self.current_date += datetime.timedelta(days=1)
            
            # Академический цикл (v6.0)
            self._check_academic_cycle()
            
            self.current_slot_idx = 0 # СБРОС ИНДЕКСА ДЛЯ НОВОГО ДНЯ
            self.current_rooms = {}      # Очистка комнат
            return [("System", "All", "New_Day_Ready")]

        slot_type = self.day_schedule_slots[self.current_slot_idx]
        self.last_interactions = []
        self.agent_current_seat = {} # Сброс мест (v6.9.13)
        
        # Сброс статусов
        if self.current_slot_idx == 0:
            for agent in self.agents.values():
                agent.status = AgentStatus.IN_CLASS

        interactions = []

        if slot_type in [TimeSlotType.PAIR_1, TimeSlotType.PAIR_2, TimeSlotType.PAIR_3, TimeSlotType.PAIR_4]:
            pair_map = {TimeSlotType.PAIR_1: 0, TimeSlotType.PAIR_2: 1, TimeSlotType.PAIR_3: 2, TimeSlotType.PAIR_4: 3}
            interactions = self._handle_study_slot(pair_map[slot_type], day_of_week)
        elif slot_type in [TimeSlotType.BREAK_1, TimeSlotType.BREAK_2, TimeSlotType.BREAK_3]:
            interactions = self._handle_break_slot()
        elif slot_type == TimeSlotType.GYM:
            interactions = self._handle_gym_slot()
        elif slot_type == TimeSlotType.CLEANUP:
            # Агенты уходят домой
            for agent in self.agents.values():
                agent.status = AgentStatus.HOME
            interactions = [("System", "All", "Campus_Closed")]

        self.current_slot_idx += 1
        self.last_interactions = interactions # Сохраняем для GUI
        
        # ОБНОВЛЕНИЕ ЭМОЦИЙ ПОСЛЕ КАЖДОГО СЛОТА (для живого обновления цветов)
        for agent in self.agents.values():
            # Если 10 слотов в день, делим стандартный decay на 2 для баланса
            agent.apply_emotion_decay() # теперь внутри затухание 0.1 вместо 0.2
            agent.react_to_relations()
            agent.react_to_emotions()
        
        # Косвенное влияние эмоций в кампусе
        self.influence_emotions()
        
        return interactions

    def perform_full_day_cycle(self, interactions_per_day: int = 1, interactive: bool = False) -> List[Tuple[str, str, str]]:
        """
        Выполняет все оставшиеся шаги текущего дня до его завершения.
        """
        all_interactions = []
        
        while True:
            interactions = self.perform_next_step()
            all_interactions.extend(interactions)
            # Признак завершения дня и готовности к новому
            if any(res == "New_Day_Ready" for _, _, res in interactions if isinstance(res, str)):
                break
        
        return all_interactions

    def _seat_students(self, room_id, student_names, cols):
        """Алгоритм Умной Рассадки (Софтмакс)"""
        # Получаем реальную вместимость комнаты (v6.9.7)
        room_info = self.uni_manager.rooms_info.get(room_id, {})
        capacity = room_info.get("capacity", max(100, len(student_names)))
        
        seated = [None] * capacity
        random.shuffle(student_names) 
        
        for student_name in student_names:
            agent = self.agents[student_name]
            empty_indices = [i for i, seat in enumerate(seated) if seat is None]
            if not empty_indices: break
                
            seat_weights = []
            for i in empty_indices:
                neighbors = []
                if i % cols > 0: neighbors.append(i - 1)
                if i % cols < cols - 1 and i + 1 < len(seated): neighbors.append(i + 1)
                if i >= cols: neighbors.append(i - cols)
                if i + cols < len(seated): neighbors.append(i + cols)
                
                occupied_neighbors = [seated[n] for n in neighbors if n >= 0 and n < len(seated) and seated[n] is not None]
                
                # Добавляем базовый случайный вес, чтобы не кучковались в начале (v6.9.13)
                base_weight = 0.5 + random.random() * 0.5
                
                if not occupied_neighbors:
                    seat_weights.append(base_weight)
                else:
                    seat_p = base_weight
                    for n_name in occupied_neighbors:
                        metrics = agent.relations.get(n_name, {})
                        score = InteractionStrategy.priority_score(agent, n_name, metrics)
                        # Усиливаем "социальную гравитацию"
                        seat_p += math.exp(score * 1.5) 
                    seat_weights.append(seat_p)
            
            # РУЛЕТКА: Ранжируем места на основе софтмакс-весов
            choices = list(zip(empty_indices, seat_weights))
            choices.sort(key=lambda x: random.random() * x[1], reverse=True)
            
            seated_successfully = False
            for seat_idx, weight in choices:
                neighbors = []
                if seat_idx % cols > 0: neighbors.append(seat_idx - 1)
                if seat_idx % cols < cols - 1 and seat_idx + 1 < len(seated): neighbors.append(seat_idx + 1)
                if seat_idx >= cols: neighbors.append(seat_idx - cols)
                if seat_idx + cols < len(seated): neighbors.append(seat_idx + cols)
                
                refused = False
                for n_idx in neighbors:
                    if n_idx >= 0 and n_idx < len(seated):
                        n_name = seated[n_idx]
                        if n_name:
                            n_agent = self.agents[n_name]
                            metrics = n_agent.relations.get(student_name, {})
                            score = InteractionStrategy.priority_score(n_agent, student_name, metrics)
                            p_accept = math.exp(score) / (math.exp(score) + 1.0)
                            if random.random() > p_accept:
                                refused = True; break
                            ref_chance = InteractionStrategy.calculate_refusal_chance(n_agent, agent)
                            if random.random() < ref_chance:
                                refused = True; break
                            
                if not refused:
                    seated[seat_idx] = student_name
                    seated_successfully = True
                    break
                    
            if not seated_successfully:
                seated[random.choice(empty_indices)] = student_name
                
        return seated

    def _interact_group(self, group_list, context) -> List[Tuple[str, str, str]]:
        """Топология группового взаимодействия (Клика для <=5, Кольцо для >5)"""
        if len(group_list) < 2: return []
        interactions = []
        
        if len(group_list) <= 5:
            # Клика (каждый с каждым)
            for i in range(len(group_list)):
                for j in range(i+1, len(group_list)):
                    res = self._interact_pair(group_list[i], group_list[j], context)
                    if res: interactions.append(res)
        else:
            # Кольцо (по кругу)
            for i in range(len(group_list)):
                s1 = group_list[i]
                s2 = group_list[(i+1) % len(group_list)]
                res = self._interact_pair(s1, s2, context)
                if res: interactions.append(res)
        return interactions

    def _interact_in_room(self, seated, cols, context) -> List[Tuple[str, str, str]]:
        """Вероятностный выбор собеседника (Neighborhood 4-Way) и создание групп"""
        import math
        interactions = []
        active_indices = [i for i, name in enumerate(seated) if name is not None]
        random.shuffle(active_indices) # Случайный порядок обхода
        interacted = set()
        
        for i in active_indices:
            if i in interacted: continue
            agent1 = self.agents[seated[i]]
            
            # Соседи вокруг агента
            neighbors = []
            if i % cols > 0: neighbors.append(i - 1)
            if i % cols < cols - 1 and i + 1 < len(seated): neighbors.append(i + 1)
            if i >= cols: neighbors.append(i - cols)
            if i + cols < len(seated): neighbors.append(i + cols)
            
            valid_n = [n for n in neighbors if n >= 0 and n < len(seated) and seated[n] is not None and n not in interacted]
            if not valid_n: continue
                
            weights = []
            for n_idx in valid_n:
                n_name = seated[n_idx]
                metrics = agent1.relations.get(n_name, {})
                score = InteractionStrategy.priority_score(agent1, n_name, metrics, context)
                weights.append(math.exp(score))
                
            # Естественный барьер размера группы: STOP-выбор с усредненным весом
            valid_n.append(None)
            mean_weight = sum(weights)/len(weights) if weights else 1.0
            weights.append(mean_weight)
            
            group_indices = [i]
            while True:
                chosen_n = random.choices(valid_n, weights=weights, k=1)[0]
                # Естественная остановка: выпал STOP или тот, кто УЖЕ в группе (Парадокс дней рождений)
                if chosen_n is None or chosen_n in group_indices:
                    break
                group_indices.append(chosen_n)
                
            group_names = [seated[idx] for idx in group_indices]
            res_interactions = self._interact_group(group_names, context)
            interactions.extend(res_interactions)
            
            for idx in group_indices:
                interacted.add(idx)
            
        return interactions

    def _handle_study_slot(self, slot_idx, day_idx) -> List[Tuple[str, str, str]]:
        interactions = []
        self.current_rooms = {}
        
        room_assignments = {}
        for name, agent in self.agents.items():
            if agent.status == AgentStatus.HOME: continue
            if random.random() < agent.skip_tendency:
                agent.status = AgentStatus.HOME
                continue
                
            schedule = self.uni_manager.get_group_schedule(agent.group_id, day_idx)
            if slot_idx < len(schedule):
                room_id = schedule[slot_idx]
                if room_id not in room_assignments: room_assignments[room_id] = []
                room_assignments[room_id].append(name)
                
        # Рассадка и общение
        for room_id, students in room_assignments.items():
            cols = self.uni_manager.get_room_cols(room_id)
            seated = self._seat_students(room_id, students, cols)
            
            # Сохраняем места для GUI (v6.9.13)
            for idx, name in enumerate(seated):
                if name: self.agent_current_seat[name] = idx
                
            self.current_rooms[room_id] = seated
            room_interactions = self._interact_in_room(seated, cols, context='STUDY')
            interactions.extend(room_interactions)
            
        return interactions

    def _handle_break_slot(self):
        """Перемена: рассадка по интересам (v6.9.13)"""
        corridor_students = [n for n, a in self.agents.items() if a.status != AgentStatus.HOME]
        cols = self.uni_manager.get_room_cols("CORRIDOR")
        
        # Группируем людей в коридоре, чтобы группы общения были рядом
        seated = self._seat_students("CORRIDOR", corridor_students, cols)
        for idx, name in enumerate(seated):
            if name: self.agent_current_seat[name] = idx
            
        self.current_rooms = {"CORRIDOR": seated}
        interactions = self._interact_in_room(seated, cols, context='BREAK')
        return interactions

    def _handle_gym_slot(self) -> List[Tuple[str, str, str]]:
        interactions = []
        gym_students = []
        for name, agent in self.agents.items():
            if agent.status == AgentStatus.HOME: continue
            if random.random() < agent.sportiness:
                gym_students.append(name)
            else:
                agent.status = AgentStatus.HOME

        # Спортзал: 2D Рассадка и взаимодействие (Группировки)
        cols = self.uni_manager.get_room_cols("GYM")
        seated_gym = self._seat_students("GYM", gym_students, cols)
        for idx, name in enumerate(seated_gym):
            if name: self.agent_current_seat[name] = idx
            
        self.current_rooms = {"GYM": seated_gym}
        interactions = self._interact_in_room(seated_gym, cols, context='GYM')
        return interactions

    def _handle_sunday(self) -> List[Tuple[str, str, str]]:
        # Family Day
        for agent in self.agents.values():
            # Сброс стресса/эмоций (ближе к 0)
            agent.automaton.apply_decay(5) # Было 0.5
            # Рандомное влияние семьи (x10)
            family_impact = random.randint(-10, 10)
            agent.automaton.adjust_emotion("joy_sadness", family_impact)
            
        self.current_date += datetime.timedelta(days=1)
        self.current_step += 1
        # Чтобы следующий шаг (понедельник) начался с первой пары
        self.current_slot_idx = 0
        return [("System", "All", "New_Day_Ready")]

    def _check_academic_cycle(self):
        """Проверяет даты на наступление каникул или смену курса (v6.0)."""
        month = self.current_date.month
        day = self.current_date.day
        
        # 1. Прыжок через каникулы (Июль, Август)
        if month in [7, 8]:
            print(f">>> Наступили летние каникулы. Прыжок в новый учебный год...")
            self.current_date = datetime.date(self.current_date.year, 9, 1)
            self._handle_graduation_and_enrollment()
            return

        # 2. Переход между семестрами (февраль - формальная отбивка)
        if month == 2 and day == 1:
            print(f">>> Начало весеннего семестра {self.current_academic_year} года.")

    def _handle_graduation_and_enrollment(self):
        """Интеллектуальная ротация: Бакалавры -> Магистры (v6.3)."""
        new_enroll_year = self.current_academic_year
        print(f"--- АКАДЕМИЧЕСКАЯ РОТАЦИЯ: {new_enroll_year} ---")
        
        # 1. Формируем списки выпускников по факультетам
        faculty_graduates = {f: [] for f in self.uni_manager.FACULTY_NAMES}
        graduates_to_remove = []
        continuants = []
        
        faculty_to_master = {"П": "ММ", "Р": "РМ", "М": "ЭкМ", "Эк": "ЭкМ", "Ф": "ПМ"}
        
        for name, agent in self.agents.items():
            if agent.degree_type == "BACHELOR" and agent.enrollment_year <= (self.current_academic_year - 3):
                # Используем шанс из конфига (v6.4)
                can_continue = agent.faculty in faculty_to_master
                if can_continue and random.random() < self.master_chance:
                    agent.degree_type = "MASTER"
                    agent.enrollment_year = self.current_academic_year
                    agent.course_year = 1
                    year_suffix = str(self.current_academic_year)[2:]
                    agent.group_id = f"M-{faculty_to_master[agent.faculty]}-{year_suffix}"
                    continuants.append(agent)
                else:
                    graduates_to_remove.append(name)
            elif agent.degree_type == "MASTER" and agent.enrollment_year <= (self.current_academic_year - 1):
                graduates_to_remove.append(name)

        # 2. Распределяем квоты в Магистратуру
        m_counts = {} # Сколько мест уже занято своими
        for c in continuants:
            m_counts[c.group_id] = m_counts.get(c.group_id, 0) + 1
            
        new_batch = self.uni_manager.create_new_cohort(
            new_enroll_year, 
            master_filled_counts=m_counts,
            bachelor_weights=self.bac_weights_list,
            master_weights=self.mag_weights_list
        )
        for agent in new_batch:
            self.add_agent(agent)
            
        print(f"Уходит студентов: {len(graduates_to_remove)}, Продолжают (Continuants): {len(continuants)}")
        
        self.current_academic_year += 1
        
        # 3. Физическое удаление и чистка памяти
        for g_name in graduates_to_remove:
            self.remove_agent(g_name)
            
        for agent in self.agents.values():
            if agent not in continuants:
                for g_name in graduates_to_remove:
                    if g_name in agent.relations:
                        del agent.relations[g_name]
                agent.course_year = min(4 if agent.degree_type == "BACHELOR" else 2, agent.course_year + 1)
            
        print(f"----------------------------------------")

    def _interact_pair(self, name1, name2, context=None) -> Tuple[str, str, str]:
        """
        Моделирует взаимодействие пары (v4.6: Логика сигма {-1, 0, 1}).
        v5.5: Принимает контекст (GYM, STUDY, BREAK).
        Возвращает (имя1, имя2, статус).
        """
        a1, a2 = self.agents[name1], self.agents[name2]
        
        # 1. Проверка на ОТКАЗ (Sigma = 0)
        # Отказ принимается вторым агентом
        refusal_chance = InteractionStrategy.calculate_refusal_chance(a2, a1)
        if random.random() < refusal_chance:
            InteractionStrategy.process_refusal(a1, a2)
            return (name1, name2, "refusal")
            
        # 2. Определение УСПЕХА (Sigma = 1) или ПРОВАЛА (Sigma = -1)
        # Базовая вероятность успеха зависит от Софтмакс-оценки
        score = InteractionStrategy.priority_score(a1, name2, a1.relations.get(name2, {}), context)
        import math
        success_chance = math.exp(score) / (math.exp(score) + 1.0)
        success_chance = max(0.1, min(0.9, success_chance))
        
        success = random.random() < success_chance
        InteractionStrategy.process_interaction_result(a1, a2, "success" if success else "failure", context)
        
        return (name1, name2, "success" if success else "fail")
