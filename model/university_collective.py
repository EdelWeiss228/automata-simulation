import random
import datetime
from typing import List, Tuple, Dict
from .collective import Collective
from .agent import Agent
from .constants import AgentStatus, LocationType, SportType, TimeSlotType
from core.university_manager import UniversityManager
from core.interaction_strategy import InteractionStrategy

class UniversityCollective(Collective):
    """
    Расширенный коллектив для симуляции университета.
    Управляет расписанием, локациями и специфическими правилами v3.0.
    """

    def __init__(self):
        super().__init__()
        self.uni_manager = UniversityManager()
        self.uni_manager.generate_schedules()
        
        # Группировка для быстрого доступа
        self.groups_map = {} # group_id -> [agent_names]
        
        # Пересоздаем список агентов согласно иерархии
        self.agents = {}
        agents_list = self.uni_manager.create_university_agents()
        for agent in agents_list:
            self.add_agent(agent)
        
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
            self.current_slot_idx = 0 # СБРОС ИНДЕКСА ДЛЯ НОВОГО ДНЯ
            self.current_rooms = {}      # Очистка комнат
            return [("System", "All", "New_Day_Ready")]

        slot_type = self.day_schedule_slots[self.current_slot_idx]
        self.last_interactions = []
        
        # Сброс статусов в начале дня (перед первой парой)
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

    def _handle_study_slot(self, slot_idx, day_idx) -> List[Tuple[str, str, str]]:
        interactions = []
        # Распределяем по аудиториям
        self.current_rooms = {} # room_id -> [agent_names]
        
        for name, agent in self.agents.items():
            if agent.status == AgentStatus.HOME: continue
            
            # Проверка на побег (Skip Tendency)
            if random.random() < agent.skip_tendency:
                agent.status = AgentStatus.HOME
                continue
                
            schedule = self.uni_manager.get_group_schedule(agent.group_id, day_idx)
            if slot_idx < len(schedule):
                room_id = schedule[slot_idx]
                if room_id not in self.current_rooms: self.current_rooms[room_id] = []
                self.current_rooms[room_id].append(name)
            else:
                # Нет пары в этот слот — сидит в коридоре или ушел
                pass

        # Взаимодействие в аудитории (только с соседом)
        for room_id, student_names in self.current_rooms.items():
            # Рассадка по парам
            random.shuffle(student_names)
            for i in range(0, len(student_names), 2):
                if i + 1 < len(student_names):
                    s1, s2 = student_names[i], student_names[i+1]
                    # Взаимодействие
                    res = self._interact_pair(s1, s2)
                    if res: interactions.append(res)
        
        return interactions

    def _handle_break_slot(self) -> List[Tuple[str, str, str]]:
        # На перерыве все выходят в коридор
        interactions = []
        self.current_rooms = {"CORRIDOR": []}
        
        for name, agent in self.agents.items():
            if agent.status == AgentStatus.HOME: continue
            self.current_rooms["CORRIDOR"].append(name)
            
        # Выбираем случайные 10% агентов для активного поиска на перерыве
        active_searchers = random.sample(list(self.agents.keys()), len(self.agents)//10)
        
        for name in active_searchers:
            agent = self.agents[name]
            if agent.status == AgentStatus.HOME: continue
            
            # Ищет друга (макс симпатия)
            best_friend = None
            max_aff = -11
            for target_name, rel in agent.relations.items():
                if rel['affinity'] > max_aff:
                    max_aff = rel['affinity']
                    best_friend = target_name
            
            if best_friend and self.agents[best_friend].status != AgentStatus.HOME:
                res = self._interact_pair(name, best_friend)
                if res: interactions.append(res)
        return interactions

    def _handle_gym_slot(self) -> List[Tuple[str, str, str]]:
        interactions = []
        self.current_rooms = {"GYM": []}
        
        for name, agent in self.agents.items():
            if agent.status == AgentStatus.HOME: continue
            
            # Решение пойти в зал
            if random.random() < agent.sportiness:
                self.current_rooms["GYM"].append(name)
            else:
                agent.status = AgentStatus.HOME

        for sport_name, players in self.current_rooms.items():
            random.shuffle(players)
            for i in range(0, len(players), 2):
                if i + 1 < len(players):
                    res = self._interact_pair(players[i], players[i+1])
                    if res: interactions.append(res)
        return interactions

    def _handle_sunday(self) -> List[Tuple[str, str, str]]:
        # Family Day
        for agent in self.agents.values():
            # Сброс стресса/эмоций (ближе к 0)
            agent.automaton.apply_decay(0.5)
            # Рандомное влияние семьи
            family_impact = random.uniform(-1, 1)
            agent.automaton.adjust_emotion("joy_sadness", family_impact)
            
        self.current_date += datetime.timedelta(days=1)
        self.current_step += 1
        # Чтобы следующий шаг (понедельник) начался с первой пары
        self.current_slot_idx = 0
        return [("System", "All", "New_Day_Ready")]

    def _interact_pair(self, name1, name2) -> Tuple[str, str, str]:
        """
        Моделирует взаимодействие пары (v4.6: Логика сигма {-1, 0, 1}).
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
        # Базовая вероятность успеха зависит от текущей симпатии
        affinity = a1.relations.get(name2, {}).get("affinity", 0)
        success_chance = 0.5 + (affinity / 20.0) # От 0.0 до 1.0 (в среднем 0.5)
        success_chance = max(0.1, min(0.9, success_chance))
        
        success = random.random() < success_chance
        InteractionStrategy.process_interaction_result(a1, a2, success)
        
        return (name1, name2, "success" if success else "fail")
