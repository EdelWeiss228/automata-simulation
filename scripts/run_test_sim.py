import random
import os
import datetime
import csv
import sys

# Добавляем корень проекта в путь, чтобы импорты из model и core работали
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from model.collective import Collective
from model.agent import Agent
from model.archetypes import ArchetypeEnum
from core.data_logger import DataLogger

def setup_deterministic_simulation(num_agents=10, seed=42):
    random.seed(seed)
    collective = Collective()
    
    names = ["Рома", "Иван", "Аня", "Катя", "Дима", "Саша", "Маша", "Петя", "Лена", "Никита"]
    archetypes = list(ArchetypeEnum)
    
    # Создаем агентов
    for i in range(num_agents):
        name = f"{random.choice(names)}_{i}"
        arch = random.choice(archetypes)
        sensitivity = round(random.uniform(0.5, 2.5), 2)
        emotions = {
            "joy_sadness": random.randint(-2, 2),
            "fear_calm": random.randint(-2, 2),
            "anger_humility": random.randint(-2, 2),
            "disgust_acceptance": random.randint(-2, 2),
            "surprise_habit": random.randint(-2, 2),
            "shame_confidence": random.randint(-2, 2),
            "openness_alienation": random.randint(-2, 2)
        }
        agent = Agent(name=name, archetype=arch, sensitivity=sensitivity, emotions=emotions)
        collective.add_agent(agent)
    
    # Инициализируем отношения через AgentFactory для чистоты
    from core.agent_factory import AgentFactory
    AgentFactory.initialize_agent_relations(None, []) # Placeholder, factory handles it in Collective now
    
    return collective

def run_sim(days=10, output_prefix="test"):
    collective = setup_deterministic_simulation()
    current_date = datetime.date(2025, 1, 1)
    logger = DataLogger(log_dir="logs")
    
    states_file = f"{output_prefix}_states.csv"
    log_file = f"{output_prefix}_interactions.csv"
    
    for day in range(days):
        is_first = (day == 0)
        # Логируем состояние перед шагом
        logger.log_agent_states(states_file, current_date, collective.agents, is_first)
        
        # Шаг симуляции
        interactions = collective.make_interaction_decision()
        
        # Логируем взаимодействия
        logger.log_interactions(log_file, current_date, interactions, is_first)
            
        current_date += datetime.timedelta(days=1)

if __name__ == "__main__":
    prefix = sys.argv[1] if len(sys.argv) > 1 else "baseline_snapshot"
    run_sim(days=10, output_prefix=prefix)
    print(f"Snapshot generated in logs/: {prefix}_states.csv, {prefix}_interactions.csv")
