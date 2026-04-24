import random
from model.agent import Agent
from model.player import Player
from model.archetypes import ArchetypeEnum

class AgentFactory:
    """Фабрика для создания агентов и инициализации их отношений."""
    
    @staticmethod
    def create_agent(name, archetype_enum=None, sensitivity=None, agent_id=None):
        """Создает базового агента со случайными или заданными параметрами."""
        if archetype_enum is None:
            archetype_enum = random.choice(list(ArchetypeEnum))
        if sensitivity is None:
            # Диапазон (0, 3] согласно правилам
            sensitivity = random.uniform(0.1, 3.0)
            
        return Agent(name, archetype=archetype_enum, sensitivity=sensitivity, id=agent_id)

    @staticmethod
    def create_agent_with_relations(index, existing_agents):
        """Создает случайного агента с отношениями к уже существующим (v6.9.36)."""
        archetypes = list(ArchetypeEnum)
        arch = random.choice(archetypes)
        agent_id = f"G-RAND-{index:03d}"
        name = f"Agent_{index}"
        agent = Agent(name, archetype=arch, sensitivity=random.uniform(0.5, 2.0), id=agent_id)
        
        # Инициализируем отношения (x10 integer scale - FULL RANGE)
        for other_id in existing_agents:
            agent.update_relation(
                other_id,
                utility=random.randint(-100, 100),
                affinity=random.randint(-100, 100),
                trust=random.randint(-100, 100)
            )
        return agent

    @staticmethod
    def initialize_agent_relations(agent, other_ids):
        """Инициализирует отношения агента со списком других ID (v6.9.36)."""
        for other_id in other_ids:
            if other_id == agent.id:
                continue
            if other_id not in agent.relations:
                agent.update_relation(
                    other_id,
                    utility=random.randint(-50, 50),
                    affinity=random.randint(-50, 50),
                    trust=random.randint(-50, 50)
                )

    @staticmethod
    def initialize_player_relations(player, agent_ids, agents_dict):
        """Инициализирует отношения между игроком и агентами (v6.9.36)."""
        for agent_id in agent_ids:
            # Игрок к агенту
            if agent_id not in player.relations:
                player.relations[agent_id] = {
                    'utility': 0, 'affinity': 0, 'trust': 0
                }
            # Агент к игроку
            agent = agents_dict.get(agent_id)
            if agent and player.name not in agent.relations:
                agent.update_relation(
                    player.name,
                    utility=0, affinity=0, trust=0
                )
