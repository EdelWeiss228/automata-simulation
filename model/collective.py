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

class RelationsProxy:
    def __init__(self, agent_name, collective):
        self.agent_name = agent_name
        self.collective = collective
        
    @property
    def agent_idx(self):
        return self.collective._id_map[self.agent_name]

    def __getitem__(self, target_name):
        if target_name not in self.collective._id_map:
            raise KeyError(target_name)
        target_idx = self.collective._id_map[target_name]
        matrix = self.collective.relations_matrix
        return {
            'utility': int(matrix[self.agent_idx, target_idx, 0]),
            'affinity': int(matrix[self.agent_idx, target_idx, 1]),
            'trust': int(matrix[self.agent_idx, target_idx, 2])
        }

    def __setitem__(self, target_name, value):
        if target_name not in self.collective._id_map:
            return
        target_idx = self.collective._id_map[target_name]
        matrix = self.collective.relations_matrix
        matrix[self.agent_idx, target_idx, 0] = value.get('utility', 0)
        matrix[self.agent_idx, target_idx, 1] = value.get('affinity', 0)
        matrix[self.agent_idx, target_idx, 2] = value.get('trust', 0)
        
        # Синхронизация с C++
        if self.collective.cpp_engine:
            self.collective.cpp_engine.set_relation(
                self.agent_idx, target_idx,
                int(value.get('utility', 0)),
                int(value.get('affinity', 0)),
                int(value.get('trust', 0))
            )

    def __delitem__(self, target_name):
        if target_name in self.collective._id_map:
            target_idx = self.collective._id_map[target_name]
            self.collective.relations_matrix[self.agent_idx, target_idx] = 0
            if self.collective.cpp_engine:
                self.collective.cpp_engine.set_relation(self.agent_idx, target_idx, 0, 0, 0)

    def get(self, target_name, default=None):
        if target_name not in self.collective._id_map:
            return default
        return self[target_name]

    def __contains__(self, target_name):
        return target_name in self.collective._id_map

    def keys(self):
        for name in self.collective._id_map.keys():
            if name != self.agent_name:
                yield name

    def values(self):
        for name in self.keys():
            yield self[name]

    def items(self):
        for name in self.keys():
            yield name, self[name]

    def __iter__(self):
        return self.keys()

    def __len__(self):
        return len(self.collective._id_map) - 1

    def copy(self):
        return dict(self.items())

    def clear(self):
        self.collective.relations_matrix[self.agent_idx] = 0
        if self.collective.cpp_engine:
            n = self.collective.cpp_engine.state.num_agents
            for j in range(n):
                self.collective.cpp_engine.set_relation(self.agent_idx, j, 0, 0, 0)

    def update(self, other):
        for k, v in other.items():
            self[k] = v

class Collective:
    """
    Класс, представляющий коллектив агентов and игроков,
    управляющий их взаимодействиями and отношениями.
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
        """Добавляет агента в коллектив."""
        agent.group = self
        self.agents[agent.id] = agent
        self.agent_count += 1

    def add_player(self, player):
        """Добавить игрока and инициализировать его отношения."""
        self.players.append(player)
        AgentFactory.initialize_player_relations(player, list(self.agents.keys()), self.agents)

    def introduce_new_agent(self, new_agent):
        """Ввести нового агента and установить связи."""
        self.add_agent(new_agent)
        # Инициализируем отношения с остальными (по ID)
        AgentFactory.initialize_agent_relations(new_agent, list(self.agents.keys()))
        # И у остальных с ним
        new_id = new_agent.id
        for other_agent in self.agents.values():
            if other_agent.id != new_id:
                AgentFactory.initialize_agent_relations(other_agent, [new_id])

    def get_agent(self, agent_id):
        """Получить агента по его уникальному ID."""
        return self.agents.get(agent_id)

    def get_agent_by_name(self, agent_id):
        """Синоним get_agent (по ID)."""
        return self.agents.get(agent_id)

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
        names = list(self.agents.keys())
        for p in self.players:
            if p.name not in names:
                names.append(p.name)
        names = sorted(names)
        
        # Если состав изменился или матрица не создана
        if not hasattr(self, 'relations_matrix') or len(self._id_map) != len(names) or set(self._id_map.keys()) != set(names):
            old_id_map = self._id_map.copy()
            old_matrix = self.relations_matrix if hasattr(self, 'relations_matrix') else None
            
            self._id_map = {name: i for i, name in enumerate(names)}
            self._reverse_id_map = {i: name for name, i in self._id_map.items()}
            
            n = len(names)
            new_matrix = np.zeros((n, n, 3), dtype=np.int8)
            
            for i, name in enumerate(names):
                agent = self.agents.get(name)
                if agent is None:
                    for p in self.players:
                        if p.name == name:
                            agent = p
                            break
                if agent is None: continue
                
                old_relations = agent.relations
                agent.relations = RelationsProxy(name, self)
                
                if isinstance(old_relations, dict):
                    for target_name, rel in old_relations.items():
                        if target_name in self._id_map:
                            j = self._id_map[target_name]
                            new_matrix[i, j, 0] = rel.get('utility', 0)
                            new_matrix[i, j, 1] = rel.get('affinity', 0)
                            new_matrix[i, j, 2] = rel.get('trust', 0)
                elif isinstance(old_relations, RelationsProxy):
                    if old_matrix is not None:
                        for target_name, target_idx in old_id_map.items():
                            if target_name in self._id_map:
                                old_i = old_id_map[old_relations.agent_name]
                                old_j = target_idx
                                new_i = i
                                new_j = self._id_map[target_name]
                                new_matrix[new_i, new_j] = old_matrix[old_i, old_j]
                            
            self.relations_matrix = new_matrix
        else:
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
                getattr(arch, 'refusal_vulnerability', 0),
                e_coeffs,
                arch.scoring_config.get("affinity", "linear"),
                arch.scoring_config.get("utility", "linear"),
                arch.scoring_config.get("trust", "linear")
            )

    def _sync_to_cpp(self, sync_relations=True):
        """Прямая синхронизация всех агентов and их отношений в C++ структуру."""
        if not CPP_ENGINE_AVAILABLE:
            return
            
        self._update_id_maps()
        n = len(self._id_map)
        if not self.cpp_engine or self.cpp_engine.state.num_agents != n:
            import emotion_engine
            self.cpp_engine = emotion_engine.Engine(n)
            
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
            
        # Подготовка данных для массовой синхронизации (в 10-20 раз быстрее точечных вызовов)
        emotions_arr = np.zeros((n, 7), dtype=np.int8)
        sens_arr = np.zeros(n, dtype=np.float32)
        arch_indices = np.zeros(n, dtype=np.int32)
        
        for i in range(n):
            name = self._reverse_id_map[i]
            agent = self.agents.get(name)
            if agent is None:
                for p in self.players:
                    if p.name == name:
                        agent = p
                        break
            if agent is None: continue
            
            # Архитип
            arch_name = getattr(agent.archetype, "name", "Harmony")
            arch_indices[i] = self._arch_map.get(arch_name, 0)
            
            # Эмоции
            if hasattr(agent, 'automaton') and agent.automaton:
                for axis_idx, axis in enumerate(EmotionAxis):
                    emotions_arr[i, axis_idx] = agent.automaton.pairs[axis].value
            
            # Чувствительность
            sens_arr[i] = getattr(agent, 'sensitivity', 1.0)

        # Массовая запись в C++ (через буферный протокол)
        self.cpp_engine.state.emotions = emotions_arr.flatten()
        self.cpp_engine.state.sensitivities = sens_arr
        # Архитипы пока оставим через сеттер, если нет массового
        for i in range(n):
            self.cpp_engine.set_agent_archetype(i, int(arch_indices[i]))

        # Массовая синхронизация отношений (самый тяжелый блок)
        if sync_relations:
            self.cpp_engine.state.relations = self.relations_matrix.flatten()

    def _sync_from_cpp(self, sync_relations: bool = True):
        """Синхронизация данных из C++ обратно в Python объекты (для логов/GUI)."""
        if not self.cpp_engine: return
        
        n = len(self._id_map)
        # Если engine устарел (другое число агентов), пропускаем синхронизацию
        if self.cpp_engine.state.num_agents != n:
            return
        new_emotions = self.cpp_engine.state.emotions
        
        for i in range(n):
            name = self._reverse_id_map[i]
            agent = self.agents.get(name)
            if agent is None: continue
            
            if hasattr(agent, 'automaton') and agent.automaton:
                for axis_idx, axis in enumerate(EmotionAxis):
                    agent.automaton.set_emotion(axis, new_emotions[i * 7 + axis_idx])
                
        if sync_relations:
            self.relations_matrix = np.array(self.cpp_engine.state.relations, dtype=np.int8).reshape((n, n, 3))

    def _run_cpp_influence(self):
        """
        Запуск C++ движка and синхронизация результатов обратно в Python.
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

            sigma = 1 if random.random() < 0.5 else -1
            
            InteractionStrategy.process_interaction_result(agent, target_agent, sigma)
            interactions.append((agent.name, target, "success" if sigma == 1 else "fail"))
            
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
                    base = (i * n + j) * 3
                    agent.relations[t_name]['utility'] = new_relations[base + 0]
                    agent.relations[t_name]['affinity'] = new_relations[base + 1]
                    agent.relations[t_name]['trust'] = new_relations[base + 2]
                    
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
            
            # Получаем записанные взаимодействия для логов and GUI
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
# Затухание отношений (Закон прощения)
        for agent in self.agents.values():
            agent.apply_relation_decay()
            
# Реакция на текущие отношения
        for agent in self.agents.values():
            agent.react_to_relations()
        
# 1 Затухание эмоций
        for agent in self.agents.values():
            agent.apply_emotion_decay()

# 2 Влияние эмоций на отношения
        for agent in self.agents.values():
            agent.react_to_emotions()
        
# Действия игроков
        if interactive:
            for player in self.players:
                player.choose_emotion()
                player.choose_interaction(self.agents)
            
# Групповое влияние эмоций
        self.influence_emotions()
        
# Взаимодействия внутри коллектива
        interactions = []
        for _ in range(interactions_per_day):
            day_interactions = self.make_interaction_decision()
            interactions.extend(day_interactions)
            
# Инициатива агентов к игрокам
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

# Обновление внутренних счетчиков
        self.current_step += 1
        self.current_date += datetime.timedelta(days=1)
        
        return interactions

    def add_random_agent(self):
        """Создает and добавляет случайного агента в коллектив."""
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
        """Удалить агента из коллектива and очистить его упоминания из отношений других агентов."""
        if agent_name in self.agents:
            del self.agents[agent_name]
            for other_agent in self.agents.values():
                if agent_name in other_agent.relations:
                    del other_agent.relations[agent_name]
