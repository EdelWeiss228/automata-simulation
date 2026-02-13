import random
import numpy as np
from .agent import Agent
from .player import Player
from .emotion_automaton import EmotionAxis
from core.interaction_strategy import InteractionStrategy
from typing import List, Tuple
from core.agent_factory import AgentFactory
import datetime
import os
import sys

# Добавляем путь к core, чтобы найти скомпилированный C++ модуль
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'core'))

try:
    import emotion_engine
    CPP_ENGINE_AVAILABLE = True
except ImportError:
    CPP_ENGINE_AVAILABLE = False

class Collective:
    """
    Класс, представляющий коллектив агентов и игроков,
    управляющий их взаимодействиями и отношениями.
    """

    def __init__(self, agents_data=None, relations_data=None, players_data=None, seed=None):
        """
        Инициализация коллектива.
        """
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        self.seed = seed
        self.agents = {}
        self.players = []
        self.agent_count = 0
        self.current_step = 0
        self.current_date = datetime.date(2025, 1, 1)
        self.cpp_engine = None
        self._id_map = {} # Name to index
        self._reverse_id_map = {} # Index to name
        
        if agents_data:
            for agent_name, agent_initial_data in agents_data:
                agent = Agent(agent_name, **agent_initial_data)
                self.add_agent(agent)
                
        if relations_data:
            for (subject_name, object_name), relation_data in relations_data.items():
                self.update_relation(subject_name, object_name, **relation_data)
                
        if players_data:
            for player_data in players_data:
                player = Player(**player_data)
                self.add_player(player)
                
        # Гарантируем наличие отношений между всеми агентами
        for agent in self.agents.values():
            AgentFactory.initialize_agent_relations(agent, list(self.agents.keys()))

    def add_agent(self, agent):
        """Добавить агента в коллектив."""
        agent.group = self
        self.agents[agent.name] = agent
        self.agent_count += 1

    def add_player(self, player):
        """Добавить игрока и инициализировать его отношения."""
        self.players.append(player)
        AgentFactory.initialize_player_relations(player, list(self.agents.keys()), self.agents)

    def introduce_new_agent(self, new_agent):
        """Ввести нового агента и установить связи."""
        self.add_agent(new_agent)
        # Инициализируем отношения с остальными
        AgentFactory.initialize_agent_relations(new_agent, list(self.agents.keys()))
        # И у остальных с ним
        for other_agent in self.agents.values():
            if other_agent.name != new_agent.name:
                AgentFactory.initialize_agent_relations(other_agent, [new_agent.name])

    def get_agent(self, name):
        """Получить агента по имени."""
        return self.agents.get(name)

    def get_agent_by_name(self, name):
        """Получить агента по имени (синоним get_agent)."""
        return self.agents.get(name)

    def update_relation(self, subject_name, object_name, **relations):
        """Обновить отношения между агентами."""
        subject = self.get_agent(subject_name)
        if subject:
            subject.update_relation(object_name, **relations)

    def describe_all_emotions(self):
        """Получить описание эмоций всех агентов."""
        return {name: agent.describe_emotions() for name, agent in self.agents.items()}

    def describe_all_relations(self):
        """Получить описание отношений всех агентов."""
        return {name: agent.describe_relations() for name, agent in self.agents.items()}

    def influence_emotions(self):
        """
        Агенты влияют на эмоции друг друга. Использует C++ если доступно.
        """
        if CPP_ENGINE_AVAILABLE and len(self.agents) > 1:
            self._run_cpp_influence()
        else:
            for agent in self.agents.values():
                agent.influence_emotions()

    def _update_id_maps(self):
        """Обновляет маппинг имен агентов в целочисленные индексы."""
        names = sorted(self.agents.keys())
        self._id_map = {name: i for i, name in enumerate(names)}
        self._reverse_id_map = {i: name for name, i in self._id_map.items()}

    def _sync_archetypes(self):
        """Синхронизирует конфигурации архетипов в C++."""
        from model.archetypes import ARCHETYPE_WEIGHTS, ArchetypeEnum
        from model.emotion_automaton import EmotionAxis
        
        # Создаем маппинг архетипов (по значению, т.к. это используется в Archetype.name)
        self._arch_map = {arch.value: i for i, arch in enumerate(ArchetypeEnum)}
        
        for arch_enum, arch in ARCHETYPE_WEIGHTS.items():
            idx = self._arch_map[arch.name]
            
            # Подготовка коэффициентов эмоций
            e_coeffs = []
            for axis in EmotionAxis:
                e_coeffs.append(arch.emotion_coefficients.get(axis.value, 0.0))
            
            self.cpp_engine.set_archetype_config(
                idx,
                arch.refusal_chance,
                arch.decay_rate,
                arch.temperature,
                getattr(arch, 'emotion_decay', 0.2),
                e_coeffs,
                arch.scoring_config.get("affinity", "linear"),
                arch.scoring_config.get("utility", "linear"),
                arch.scoring_config.get("trust", "linear"),
                arch.scoring_config.get("responsiveness", "linear")
            )

    def _sync_to_cpp(self):
        """Прямая синхронизация всех агентов и их отношений в C++ структуру."""
        n = len(self.agents)
        
        # Синхронизируем конфиги архетипов один раз (или при изменении состава)
        self._sync_archetypes()
        
        # Устанавливаем сид для детерминизма
        if hasattr(self, 'seed') and self.seed is not None:
            self.cpp_engine.seed(self.seed)
        elif hasattr(self, 'random_seed') and self.random_seed is not None:
            self.cpp_engine.seed(self.random_seed)
            
        # Устанавливаем имена агентов для логгера
        names_list = [self._reverse_id_map[i] for i in range(n)]
        self.cpp_engine.set_agent_names(names_list)
            
        for i in range(n):
            name = self._reverse_id_map[i]
            agent = self.agents[name]
            
            # Sync archetypes
            arch_name = getattr(agent.archetype, "name", "Harmony")
            self.cpp_engine.set_agent_archetype(i, self._arch_map.get(arch_name, 0))
            
            # Sync emotions
            for axis_idx, axis in enumerate(EmotionAxis):
                val = agent.automaton.pairs[axis].value
                self.cpp_engine.set_emotion(i, axis_idx, val)
            
            # Sync sensitivities
            self.cpp_engine.state.sensitivities[i] = agent.sensitivity

            # Sync Emission Weights (Archetype effects)
            effects = getattr(agent, "emotion_effects", {})
            for axis_idx, axis in enumerate(EmotionAxis):
                axis_name = axis.value
                ax_eff = effects.get(axis_name, {})
                self.cpp_engine.set_emission_weight(
                    i, axis_idx,
                    ax_eff.get("utility", 0.0),
                    ax_eff.get("affinity", 0.0),
                    ax_eff.get("trust", 0.0),
                    0.0
                )

            # Sync Relations
            for j in range(n):
                target_name = self._reverse_id_map[j]
                if target_name in agent.relations:
                    rel = agent.relations[target_name]
                    self.cpp_engine.set_relation(
                        i, j,
                        rel.get('utility', 0.0),
                        rel.get('affinity', 0.0),
                        rel.get('trust', 0.0),
                        rel.get('responsiveness', 0.0)
                    )

    def _sync_from_cpp(self, sync_relations: bool = True):
        """Синхронизация данных из C++ обратно в Python объекты (для логов/GUI)."""
        if not self.cpp_engine: return
        
        n = len(self.agents)
        new_emotions = self.cpp_engine.state.emotions
        
        for i in range(n):
            name = self._reverse_id_map[i]
            agent = self.agents[name]
            
            for axis_idx, axis in enumerate(EmotionAxis):
                agent.automaton.set_emotion(axis, new_emotions[i * 7 + axis_idx])
                
            if sync_relations:
                new_relations = self.cpp_engine.state.relations
                for j in range(n):
                    target_name = self._reverse_id_map[j]
                    if target_name in agent.relations:
                        base = (i * n + j) * 4
                        agent.relations[target_name]['utility'] = new_relations[base + 0]
                        agent.relations[target_name]['affinity'] = new_relations[base + 1]
                        agent.relations[target_name]['trust'] = new_relations[base + 2]
                        agent.relations[target_name]['responsiveness'] = new_relations[base + 3]

    def _run_cpp_influence(self):
        """
        Запуск C++ движка и синхронизация результатов обратно в Python.
        """
        self._update_id_maps()
        n = len(self.agents)
        if not self.cpp_engine or self.cpp_engine.state.num_agents != n:
             import emotion_engine
             self.cpp_engine = emotion_engine.Engine(n)

        self._sync_to_cpp()
        self.cpp_engine.influence_emotions()
        # Мы НЕ синхронизируем данные обратно здесь для Lazy Sync

    def make_interaction_decision(self) -> List[Tuple[str, str, str]]:
        """
        Каждый агент принимает решение о взаимодействии. Использует C++ если доступно.
        """
        if CPP_ENGINE_AVAILABLE and len(self.agents) > 1:
            return self._run_cpp_interactions()
            
        interactions = []
        for agent in self.agents.values():
            mandatory, optional, avoid = InteractionStrategy.categorize_relationships(agent)
            chosen = InteractionStrategy.choose_target(agent, mandatory, optional)
            
            if not chosen:
                # При отказе от всех контактов отношения немного деградируют
                for target_name in agent.relations.keys():
                    target_agent = self.get_agent(target_name)
                    if target_agent:
                        InteractionStrategy.process_refusal(agent, target_agent)
                    interactions.append((agent.name, target_name, "refusal"))
                continue
                
            target, metrics = chosen
            target_agent = self.get_agent(target)
            
            if target_agent is not None:
                final_chance = InteractionStrategy.calculate_refusal_chance(agent, target_agent)
                if random.random() < final_chance or target_agent.classify_relationship(agent.name) == "avoid":
                    InteractionStrategy.process_refusal(agent, target_agent)
                    interactions.append((agent.name, target, "refusal"))
                    continue

            success = random.random() < 0.5
            
            InteractionStrategy.process_interaction_result(agent, target_agent, success)
            interactions.append((agent.name, target, "success" if success else "fail"))
            
        return interactions

    def _run_cpp_interactions(self) -> List[Tuple[str, str, str]]:
        """Запуск логики взаимодействий через C++."""
        self._update_id_maps()
        n = len(self.agents)
        if not self.cpp_engine or self.cpp_engine.state.num_agents != n:
             import emotion_engine
             self.cpp_engine = emotion_engine.Engine(n)

        self._sync_to_cpp()
        
        interactions = []
        for i in range(n):
            agent_name = self._reverse_id_map[i]
            target_idx = self.cpp_engine.choose_target(i)
            
            if target_idx == -1:
                # Все отказались или некого выбирать
                for j in range(n):
                    if i == j: continue
                    target_name = self._reverse_id_map[j]
                    self.cpp_engine.process_refusal(i, j)
                    interactions.append((agent_name, target_name, "refusal"))
                continue
                
            target_name = self._reverse_id_map[target_idx]
            
            # Проверка на отказ со стороны цели
            if self.cpp_engine.should_refuse(i, target_idx):
                self.cpp_engine.process_refusal(i, target_idx)
                interactions.append((agent_name, target_name, "refusal"))
            else:
                success = random.random() < 0.5
                self.cpp_engine.process_interaction(i, target_idx, success)
                interactions.append((agent_name, target_name, "success" if success else "fail"))

        # После всех взаимодействий синхронизируем реляционные изменения обратно
        new_relations = self.cpp_engine.state.relations
        for i in range(n):
            name = self._reverse_id_map[i]
            agent = self.agents[name]
            for j in range(n):
                t_name = self._reverse_id_map[j]
                if t_name in agent.relations:
                    base = (i * n + j) * 4
                    agent.relations[t_name]['utility'] = new_relations[base + 0]
                    agent.relations[t_name]['affinity'] = new_relations[base + 1]
                    agent.relations[t_name]['trust'] = new_relations[base + 2]
                    agent.relations[t_name]['responsiveness'] = new_relations[base + 3]
                    
        return interactions

    def perform_full_day_cycle(self, interactions_per_day: int = 1, interactive: bool = False, skip_sync: bool = False) -> List[Tuple[str, str, str]]:
        """
        Выполняет полный цикл симуляции одного дня в C++.
        """
        if CPP_ENGINE_AVAILABLE and not interactive and len(self.agents) > 1:
            self._update_id_maps()
            n = len(self.agents)
            engine_just_created = False
            if not self.cpp_engine or self.cpp_engine.state.num_agents != n:
                 import emotion_engine
                 self.cpp_engine = emotion_engine.Engine(n)
                 engine_just_created = True
            
            # Синхронизируем ТОЛЬКО в начале или если был ручной ввод (interactive)
            # В не-интерактивном режиме данные живут в C++.
            if engine_just_created or self.current_step == 0:
                self._sync_to_cpp() 
            
            self.cpp_engine.perform_daily_cycle(interactions_per_day)
            
            # Получаем записанные взаимодействия для логов и GUI
            interactions = []
            type_map = {0: "refusal", 1: "success", 2: "fail"}
            for interact in self.cpp_engine.last_day_interactions:
                from_name = self._reverse_id_map.get(interact.from_idx)
                to_name = self._reverse_id_map.get(interact.to_idx)
                if from_name and to_name:
                    interactions.append((from_name, to_name, type_map.get(interact.type, "refusal")))
            
            # Обновление счетчиков
            self.current_step += 1
            self.current_date += datetime.timedelta(days=1)
            
            return interactions

        # ПИТОНОВСКИЙ ВАРИАНТ (медленный)
        # 0. Затухание отношений (Закон прощения)
        for agent in self.agents.values():
            agent.apply_relation_decay()
            
        # 1. Реакция на текущие отношения
        for agent in self.agents.values():
            agent.react_to_relations()
        
        # 1.1 Затухание эмоций
        for agent in self.agents.values():
            agent.apply_emotion_decay()

        # 1.2 Влияние эмоций на отношения
        for agent in self.agents.values():
            agent.react_to_emotions()
        
        # 2. Действия игроков
        if interactive:
            for player in self.players:
                player.choose_emotion()
                player.choose_interaction(self.agents)
            
        # 3. Групповое влияние эмоций
        self.influence_emotions()
        
        # 4. Взаимодействия внутри коллектива
        interactions = []
        for _ in range(interactions_per_day):
            day_interactions = self.make_interaction_decision()
            interactions.extend(day_interactions)
            
        # 5. Инициатива агентов к игрокам
        for agent in self.agents.values():
            candidates = sorted(
                agent.relations.items(),
                key=lambda x: (x[1].get('affinity', 0), x[1].get('utility', 0)),
                reverse=True
            )
            for target_name, _ in candidates:
                for player in self.players:
                    if player.name == target_name:
                        InteractionStrategy.handle_player_interaction(agent, player)
                        break

        # 6. Обновление внутренних счетчиков
        self.current_step += 1
        self.current_date += datetime.timedelta(days=1)
        
        return interactions

    def add_random_agent(self):
        """Создает и добавляет случайного агента в коллектив."""
        existing_names = list(self.agents.keys())
        new_agent = AgentFactory.create_agent_with_relations(len(existing_names) + 1, existing_names)
        self.add_agent(new_agent)
        
        # ВАЖНО: Инициализируем отношения существующих агентов К новому агенту
        for other_agent in self.agents.values():
            if other_agent.name != new_agent.name:
                AgentFactory.initialize_agent_relations(other_agent, [new_agent.name])
                
        return new_agent.name

    def simulate_day(self, interactions_per_day: int = 1):
        """
        Устаревший метод для обратной совместимости или консольного запуска.
        """
        self.perform_full_day_cycle(interactions_per_day, interactive=True)

    def remove_agent(self, agent_name):
        """Удалить агента из коллектива и очистить его упоминания из отношений других агентов."""
        if agent_name in self.agents:
            del self.agents[agent_name]
            for other_agent in self.agents.values():
                if agent_name in other_agent.relations:
                    del other_agent.relations[agent_name]
