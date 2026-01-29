import random
from model.agent import Agent
from model.player import Player
from model.archetypes import ArchetypeEnum

class AgentFactory:
    """Фабрика для создания агентов и инициализации их отношений."""
    
    @staticmethod
    def create_agent(name, archetype_enum=None, sensitivity=1.0):
        """Создает базового агента."""
        return Agent(name, archetype=archetype_enum, sensitivity=sensitivity)

    @staticmethod
    def create_agent_with_relations(index, existing_agents):
        """Создает случайного агента с отношениями к уже существующим."""
        archetypes = list(ArchetypeEnum)
        arch = random.choice(archetypes)
        name = f"Agent_{index}_{arch.value}"
        agent = Agent(name, archetype=arch, sensitivity=random.uniform(0.5, 2.0))
        
        # Инициализируем отношения
        for other_name in existing_agents:
            agent.update_relation(
                other_name,
                utility=random.uniform(-3, 3),
                affinity=random.uniform(-3, 3),
                trust=random.uniform(-3, 3)
            )
        return agent

    @staticmethod
    def initialize_agent_relations(agent, other_names):
        """Инициализирует отношения агента со списком других имен (если их еще нет)."""
        for other_name in other_names:
            if other_name == agent.name:
                continue
            if other_name not in agent.relations:
                agent.update_relation(
                    other_name,
                    utility=random.uniform(-1, 1),
                    affinity=random.uniform(-1, 1),
                    trust=random.uniform(-1, 1)
                )

    @staticmethod
    def initialize_player_relations(player, agent_names, agents_dict):
        """Инициализирует отношения между игроком и агентами."""
        for agent_name in agent_names:
            # Игрок к агенту
            if agent_name not in player.relations:
                player.relations[agent_name] = {
                    'utility': 0, 'affinity': 0, 'trust': 0
                }
            # Агент к игроку
            agent = agents_dict.get(agent_name)
            if agent and player.name not in agent.relations:
                agent.update_relation(
                    player.name,
                    utility=0, affinity=0, trust=0
                )
