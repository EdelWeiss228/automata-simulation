"""
Модуль collective.py содержит класс Collective, представляющий коллектив агентов и игроков.
Класс управляет их взаимодействиями, отношениями и эмоциями в рамках симуляции.
"""

import random
from agent import Agent
from player import Player


class Collective:
    """
    Класс, представляющий коллектив агентов и игроков,
    управляющий их взаимодействиями и отношениями.
    """

    def __init__(self, agents_data=None, relations_data=None, players_data=None):
        """
        Инициализация коллектива.
        :param agents_data: данные агентов
        :param relations_data: данные об отношениях
        :param players_data: данные игроков
        """
        self.agents = {}
        self.players = []
        if agents_data:
            for agent_name, agent_initial_data in agents_data:
                agent = Agent(agent_name, **agent_initial_data)
                agent.group = self
                self.add_agent(agent)
        if relations_data:
            for (subject_name, object_name), relation_data in relations_data.items():
                self.update_relation(subject_name, object_name, **relation_data)
        if players_data:
            for player_data in players_data:
                player = Player(**player_data)
                self.add_player(player)
        for agent in self.agents.values():
            for other_name in self.agents:
                if other_name != agent.name and other_name not in agent.relations:
                    agent.relations[other_name] = {
                        'utility': 0,
                        'affinity': 0,
                        'trust': 0,
                        'responsiveness': 0,
                    }

    def add_agent(self, agent):
        """Добавить агента в коллектив."""
        self.agents[agent.name] = agent

    def add_player(self, player):
        """Добавить игрока в коллектив и инициализировать его отношения с агентами."""
        self.players.append(player)
        _, primary_emotion_value = player.get_primary_emotion()
        if not hasattr(player, "relations"):
            player.relations = {}
        for agent_name, agent in self.agents.items():
            utility = (primary_emotion_value if random.random() > 0.5
                       else random.randint(-3, 3))
            affinity = (primary_emotion_value if random.random() > 0.5
                       else random.randint(-3, 3))
            trust = (primary_emotion_value if random.random() > 0.5
                     else random.randint(-3, 3))
            player.relations[agent_name] = {
                'utility': utility,
                'affinity': affinity,
                'trust': trust
            }
            agent.update_relation(player.name, utility=utility,
                                  affinity=affinity, trust=trust)

    def introduce_new_agent(self, new_agent):
        """Ввести нового агента в коллектив и установить отношения с остальными."""
        self.add_agent(new_agent)
        new_agent.group = self
        for other_name, other_agent in self.agents.items():
            if other_name == new_agent.name:
                continue
            _, primary_emotion_value = new_agent.get_primary_emotion()
            utility = (primary_emotion_value if random.random() > 0.5
                       else random.randint(-3, 3))
            affinity = (primary_emotion_value if random.random() > 0.5
                        else random.randint(-3, 3))
            trust = (primary_emotion_value if random.random() > 0.5
                     else random.randint(-3, 3))
            new_agent.update_relation(other_name, utility=utility,
                                      affinity=affinity, trust=trust)
            other_agent.update_relation(new_agent.name, utility=utility,
                                        affinity=affinity, trust=trust)

    def get_agent(self, name):
        """Получить агента по имени."""
        return self.agents.get(name)

    def get_agent_by_name(self, name):
        """Получить агента по имени (синоним get_agent)."""
        return self.agents.get(name)

    def update_relation(self, subject_name, object_name, **relations):
        """Обновить отношения между агентами."""
        subject = self.get_agent(subject_name)
        if subject and object_name in self.agents:
            subject.update_relation(object_name, **relations)

    def describe_all_emotions(self):
        """Получить описание эмоций всех агентов."""
        return {
            name: agent.describe_emotions()
            for name, agent in self.agents.items()
        }

    def describe_all_relations(self):
        """Получить описание отношений всех агентов."""
        return {
            name: agent.describe_relations()
            for name, agent in self.agents.items()
        }

    def _categorize_relationships(self, _agent):
        """Классифицировать отношения агента на обязательные, опциональные и избегаемые."""
        mandatory = []
        optional = []
        avoid = []
        # The argument '_' is expected to be an agent
        for target_name, metrics in _agent.relations.items():
            category = _agent.classify_relationship(target_name)
            if category == "mandatory":
                mandatory.append((target_name, metrics))
            elif category == "optional":
                optional.append((target_name, metrics))
            else:
                avoid.append((target_name, metrics))
        return mandatory, optional, avoid

    def _choose_target(self, agent, mandatory, optional):
        """Выбрать цель взаимодействия на основе обязательных и опциональных отношений, учитывая responsiveness и trust."""
        def priority_score(metrics):
            # Если responsiveness < 0, его вклад увеличивается в 1.5 раза
            responsiveness = metrics.get('responsiveness', 0)
            multiplier = 1 if responsiveness < 0 else 1
            alpha = 1.5
            return (
                metrics.get('affinity', 0) +
                metrics.get('utility', 0) +
                alpha * metrics.get('trust', 0) +
                multiplier * responsiveness
            )
        chosen = None
        if mandatory:
            chosen = max(mandatory, key=lambda x: priority_score(x[1]))
        elif optional:
            chosen = max(optional, key=lambda x: priority_score(x[1]))
        return chosen

    def _process_refusal(self, agent, target_agent):
        """Обработать отказ взаимодействия между агентами (безопасно обновляет отношения)."""
        print(f"{target_agent.name} отказался взаимодействовать с {agent.name}.")

        # Инициализация при необходимости
        if target_agent.name not in agent.relations:
            agent.relations[target_agent.name] = {
                'trust': 0, 'affinity': 0, 'utility': 0, 'responsiveness': 0
            }
        else:
            for key in ['trust', 'affinity', 'utility', 'responsiveness']:
                agent.relations[target_agent.name].setdefault(key, 0)

        if agent.name not in target_agent.relations:
            target_agent.relations[agent.name] = {
                'trust': 0, 'affinity': 0, 'utility': 0, 'responsiveness': 0
            }
        else:
            for key in ['trust', 'affinity', 'utility', 'responsiveness']:
                target_agent.relations[agent.name].setdefault(key, 0)

        # Обновление предиката responsiveness вместо trust
        sensitivity = getattr(agent, 'sensitivity', 1)
        responsiveness_factor = getattr(agent, 'responsiveness', 1)
        decrement = round(0.5 * sensitivity * responsiveness_factor)
        agent.relations[target_agent.name]['responsiveness'] = max(
            -10, agent.relations[target_agent.name].get('responsiveness', 0) - decrement
        )
        target_agent.relations[agent.name]['responsiveness'] = max(
            -10, target_agent.relations[agent.name].get('responsiveness', 0) - decrement
        )

        # Дополнительно понижаем trust и affinity при отказе
        agent.relations[target_agent.name]['trust'] = max(
            -10, agent.relations[target_agent.name].get('trust', 0) - round(0.5 * sensitivity)
        )
        agent.relations[target_agent.name]['affinity'] = max(
            -10, agent.relations[target_agent.name].get('affinity', 0) - round(0.5 * sensitivity)
        )
        target_agent.relations[agent.name]['trust'] = max(
            -10, target_agent.relations[agent.name].get('trust', 0) - round(0.5 * sensitivity)
        )
        target_agent.relations[agent.name]['affinity'] = max(
            -10, target_agent.relations[agent.name].get('affinity', 0) - round(0.5 * sensitivity)
        )

    def _process_interaction_result(self, agent, target_agent, success):
        """Обработать результат взаимодействия и обновить отношения."""
        # Инициализация при необходимости
        if target_agent.name not in agent.relations:
            agent.relations[target_agent.name] = {
                'trust': 0, 'affinity': 0, 'utility': 0, 'responsiveness': 0
            }
        else:
            for key in ['trust', 'affinity', 'utility', 'responsiveness']:
                agent.relations[target_agent.name].setdefault(key, 0)

        if agent.name not in target_agent.relations:
            target_agent.relations[agent.name] = {
                'trust': 0, 'affinity': 0, 'utility': 0, 'responsiveness': 0
            }
        else:
            for key in ['trust', 'affinity', 'utility', 'responsiveness']:
                target_agent.relations[agent.name].setdefault(key, 0)

        sensitivity = getattr(agent, "responsiveness", 1.0)
        if success:
            delta = int(2 * sensitivity)
            agent.relations[target_agent.name]['trust'] = min(
                10, agent.relations[target_agent.name].get('trust', 0) + delta
            )
            agent.relations[target_agent.name]['affinity'] = min(
                10, agent.relations[target_agent.name].get('affinity', 0) +
                int(1 * sensitivity)
            )
            agent.relations[target_agent.name]['utility'] = min(
                10, agent.relations[target_agent.name].get('utility', 0) +
                int(1 * sensitivity)
            )
            if target_agent.name in target_agent.relations:
                target_agent.relations[agent.name]['trust'] = min(
                    10, target_agent.relations[agent.name].get('trust', 0) + delta
                )
                target_agent.relations[agent.name]['affinity'] = min(
                    10, target_agent.relations[agent.name].get('affinity', 0) +
                    int(1 * sensitivity)
                )
                target_agent.relations[agent.name]['utility'] = min(
                    10, target_agent.relations[agent.name].get('utility', 0) +
                    int(1 * sensitivity)
                )
            # Увеличиваем responsiveness у обоих агентов (максимум 10)
            increment = round(getattr(agent, 'sensitivity', 1))
            agent.relations[target_agent.name]['responsiveness'] = min(
                10, agent.relations[target_agent.name].get('responsiveness', 0) + increment
            )
            if target_agent.name in target_agent.relations:
                target_agent.relations[agent.name]['responsiveness'] = min(
                    10, target_agent.relations[agent.name].get('responsiveness', 0) + increment
                )
        else:
            delta = int(1 * sensitivity)
            agent.relations[target_agent.name]['trust'] = max(
                -10, agent.relations[target_agent.name].get('trust', 0) - delta
            )
            if target_agent.name in target_agent.relations:
                target_agent.relations[agent.name]['trust'] = max(
                    -10, target_agent.relations[agent.name].get('trust', 0) - delta
                )
            # Увеличиваем responsiveness у обоих агентов (максимум 10)
            increment = round(getattr(agent, 'sensitivity', 1))
            agent.relations[target_agent.name]['responsiveness'] = min(
                10, agent.relations[target_agent.name].get('responsiveness', 0) + increment
            )
            if target_agent.name in target_agent.relations:
                target_agent.relations[agent.name]['responsiveness'] = min(
                    10, target_agent.relations[agent.name].get('responsiveness', 0) + increment
                )


    def influence_emotions(self):
        """
        Placeholder method for influencing emotions.
        This stub is present to satisfy calls in simulate_day and should be implemented as needed.
        """


    def make_interaction_decision(self):
        """
        Каждый агент принимает решение о взаимодействии на основе своих отношений.
        Возвращает список взаимодействий (agent_from, agent_to, status).
        """
        interactions = []
        # Убрали interacted_agents, чтобы все агенты могли выбирать независимо
        for agent in self.agents.values():
            print(f"\n{agent.name} принимает решение о взаимодействии:")
            mandatory, optional, _ = self._categorize_relationships(agent)
            chosen = self._choose_target(agent, mandatory, optional)
            if not chosen:
                print(f"{agent.name} решил отказаться от взаимодействия сегодня.")
                for target_name in agent.relations.keys():
                    # Логируем отказ от взаимодействия с каждым партнёром
                    interactions.append((agent.name, target_name, "refusal"))
                for target_name in agent.relations.keys():
                    agent.relations[target_name]['trust'] = (
                        agent.relations[target_name].get('trust', 0) - 1
                    )
                for other_agent in self.agents.values():
                    if (other_agent.name != agent.name and
                            agent.name in other_agent.relations):
                        other_agent.relations[agent.name]['trust'] = (
                            other_agent.relations[agent.name].get('trust', 0) - 1
                        )
                continue
            target, metrics = chosen
            target_agent = self.get_agent(target)
            if target_agent is not None:
                # Новый блок отказа с учетом responsiveness
                responsiveness = agent.relations[target].get("responsiveness", 0)
                base_chance = getattr(agent.archetype, "refusal_chance", 0.3)
                dynamic_modifier = max(0.1, 1 - responsiveness / 10)
                final_chance = min(1, base_chance * dynamic_modifier)
                if random.random() < final_chance:
                    self._process_refusal(agent, target_agent)
                    interactions.append((agent.name, target, "refusal"))
                    continue
                if target_agent.classify_relationship(agent.name) == "avoid":
                    self._process_refusal(agent, target_agent)
                    interactions.append((agent.name, target, "refusal"))
                    continue
            print(
                f"{agent.name} предпочитает взаимодействовать с {target} "
                f"(симпатия={metrics['affinity']}, выгода={metrics['utility']})"
            )
            success = random.random() < 0.5
            if success:
                print(
                    f"Взаимодействие между {agent.name} и {target} прошло УСПЕШНО."
                )
            else:
                print(
                    f"Взаимодействие между {agent.name} и {target} НЕУДАЧНО."
                )
            self._process_interaction_result(agent, target_agent, success)
            # Убрали отметку об "interacted_agents"
            status = "success" if success else "fail"
            interactions.append((agent.name, target, status))
        # В этом блоке тоже не надо отмечать, кто не взаимодействовал, так как все участвуют
        for agent in self.agents.values():
            # Можно убрать или оставить по необходимости
            for rel in agent.relations.values():
                rel['trust'] = rel.get('trust', 0) + 1
        return interactions

    def _process_player_emotions_and_interactions(self):
        """Обработка выбора эмоций и взаимодействий игроков."""
        for player in self.players:
            player.choose_emotion()
            player.choose_interaction(self.agents)

    def _agents_react_to_relations_and_emotions(self):
        """Агенты реагируют на отношения и эмоции."""
        for agent in self.agents.values():
            agent.react_to_relations()
            agent.react_to_emotions()

    def _apply_player_emotional_influence(self):
        """Применение влияния эмоций игроков на агентов."""
        for player in self.players:
            for target_name in player.relations.keys():
                target_agent = self.get_agent(target_name)
                if target_agent:
                    target_agent.automaton.adjust_emotion(
                        player.current_emotion, random.randint(-5, 5)
                    )

    def _agents_react_again(self):
        """Повторная реакция агентов на отношения и эмоции после влияния игроков."""
        for agent in self.agents.values():
            agent.react_to_relations()
            agent.react_to_emotions()

    def _agents_interact_with_players(self):
        """Агенты выбирают взаимодействие с игроками на основе отношений."""
        for agent in self.agents.values():
            candidates = sorted(
                agent.relations.items(),
                key=lambda x: (x[1]['affinity'], x[1]['utility']),
                reverse=True
            )
            if candidates:
                target_name, _ = candidates[0]
                if any(player.name == target_name for player in self.players):
                    for player in self.players:
                        if player.name == target_name:
                            emotion_name, emotion_value = agent.get_primary_emotion()
                            print(
                                f"\n{agent.name} выбирает взаимодействие с игроком. "
                                f"Его примарная эмоция: {emotion_name} с силой "
                                f"{emotion_value}."
                            )
                            player.respond_to_agent(agent.name, emotion_name,
                                                    emotion_value)

    def simulate_day(self, interactions_per_day: int = 1):
        """
        Симуляция дня с эмоциями, реакциями и взаимодействиями агентов и игроков.
        Логика метода разбита на вспомогательные функции.
        """
        print("\n--- Симуляция дня ---")
        if self.players:
            self._process_player_emotions_and_interactions()
        self._agents_react_to_relations_and_emotions()
        self._apply_player_emotional_influence()
        self._agents_react_again()
        self.influence_emotions()
        for _ in range(interactions_per_day):
            self.make_interaction_decision()
        # Нормализация отношений перед взаимодействием с игроками
        for agent in self.agents.values():
            for rel in agent.relations.values():
                for key in ['trust', 'affinity', 'responsiveness', 'utility']:
                    if rel[key] < 0:
                        rel[key] += 1
                    rel[key] = min(10, max(-10, rel[key]))
        self._agents_interact_with_players()

    def remove_agent(self, agent_name):
        """Удалить агента из коллектива и очистить его упоминания из отношений других агентов."""
        if agent_name in self.agents:
            del self.agents[agent_name]
            for other_agent in self.agents.values():
                if agent_name in other_agent.relations:
                    del other_agent.relations[agent_name]
