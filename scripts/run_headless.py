import json
import sys
import os
import random
import numpy as np
import pandas as pd
from datetime import date, timedelta

# Добавляем корневую директорию проекта в path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from model.collective import Collective
from model.agent import Agent
from core.agent_factory import AgentFactory
from model.archetypes import ArchetypeEnum
from core.data_logger import DataLogger

def generate_research_agents(scenario):
    """
    Генерирует агентов на основе параметров сценария (Normal/Uniform).
    """
    agent_counts = scenario["agent_counts"]
    dist_type = scenario["emotion_dist"]
    e_params = scenario["emotion_params"]
    seed = scenario["seed"]
    
    random.seed(seed)
    np.random.seed(seed)
    
    agents = []
    agent_id_counter = 1
    
    all_arch_names = []
    for arch_name, count in agent_counts.items():
        all_arch_names.extend([arch_name] * count)
    
    current_count = len(all_arch_names)
    total_wanted = scenario.get("total_agents", current_count)
    
    if total_wanted > current_count:
        remainder = total_wanted - current_count
        print(f"Распределяем остаток ({remainder} агентов) случайно...")
        archetypes = [arch.name for arch in ArchetypeEnum]
        random_archs = [random.choice(archetypes) for _ in range(remainder)]
        all_arch_names.extend(random_archs)
    
    total_agents = len(all_arch_names)
    print(f"Инициализация {total_agents} агентов...")
    
    # Генерация эмоций
    if dist_type == "Uniform":
        emotions_matrix = np.random.uniform(e_params["min"], e_params["max"], (total_agents, 7))
    else:
        emotions_matrix = np.random.normal(e_params["mean"], e_params["std"], (total_agents, 7))
        # Clipping
        emotions_matrix = np.clip(emotions_matrix, -3.0, 3.0)
        
    # Смешиваем архетипы
    random.shuffle(all_arch_names)
    
    axes_order = ["joy_sadness", "fear_calm", "anger_humility", "disgust_acceptance", 
                  "surprise_habit", "shame_confidence", "openness_alienation"]
    
    for i, arch_name in enumerate(all_arch_names):
        arch_enum = ArchetypeEnum[arch_name]
        
        # Создаем базового агента
        agent = AgentFactory.create_agent(f"Agent_{agent_id_counter}", arch_enum)
        
        # Устанавливаем эмоции из матрицы
        for axis_idx, axis_name in enumerate(axes_order):
            agent.automaton.set_emotion(axis_name, float(emotions_matrix[i, axis_idx]))
            
        agents.append(agent)
        agent_id_counter += 1
        
    return agents

def run_headless(scenario_path):
    with open(scenario_path, 'r', encoding='utf-8') as f:
        scenario = json.load(f)
    
    # 1. Setup Simulation
    agents = generate_research_agents(scenario)
    from model.simulation_session import SimulationSession
    session = SimulationSession()
    
    for agent in agents:
        session.collective.add_agent(agent)
        
    steps = scenario["steps"]
    
    print(f"Запуск симуляции: {steps} шагов в Silent Mode...")
    
    # 2. Simulation Loop
    for step in range(steps):
        if step % 10 == 0:
            print(f"Шаг {step+1}/{steps}...")
            
        session.run_day()
        
    print(f"--- РАСЧЕТ ЗАВЕРШЕН УСПЕШНО ---")
    print(f"Результаты сохранены в '{session.output_dir}'.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 run_headless.py <scenario_json>")
        sys.exit(1)
    
    run_headless(sys.argv[1])
