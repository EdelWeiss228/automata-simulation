import argparse
import sys
import os
import json
import random
import numpy as np

# Добавляем корневую директорию проекта в path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from model.agent import Agent
from core.agent_factory import AgentFactory
from model.archetypes import ArchetypeEnum
from model.simulation_session import SimulationSession

def generate_research_agents(scenario):
    """
    Генерирует агентов на основе параметров сценария (Normal/Uniform).
    Перенесено из старой версии run_headless для использования в сессии.
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
        archetypes = [arch.name for arch in ArchetypeEnum]
        random_archs = [random.choice(archetypes) for _ in range(remainder)]
        all_arch_names.extend(random_archs)
    
    total_agents = len(all_arch_names)
    
    # Генерация эмоций
    if dist_type == "Uniform":
        emotions_matrix = np.random.uniform(e_params["min"], e_params["max"], (total_agents, 7))
    else:
        emotions_matrix = np.random.normal(e_params["mean"], e_params["std"], (total_agents, 7))
        emotions_matrix = np.clip(emotions_matrix, -3.0, 3.0)
        
    random.shuffle(all_arch_names)
    
    axes_order = ["joy_sadness", "fear_calm", "anger_humility", "disgust_acceptance", 
                  "surprise_habit", "shame_confidence", "openness_alienation"]
    
    for i, arch_name in enumerate(all_arch_names):
        arch_enum = ArchetypeEnum[arch_name]
        agent = AgentFactory.create_agent(f"Agent_{agent_id_counter}", arch_enum)
        for axis_idx, axis_name in enumerate(axes_order):
            agent.automaton.set_emotion(axis_name, float(emotions_matrix[i, axis_idx]))
        agents.append(agent)
        agent_id_counter += 1
        
    return agents

def main():
    parser = argparse.ArgumentParser(description="Silent Research Runner v5.0")
    parser.add_argument("scenario", type=str, help="Path to scenario JSON file")
    parser.add_argument("--steps", type=int, help="Number of steps (overrides scenario)")
    parser.add_argument("--silent", "--headless", action="store_true", default=True, help="Run in silent mode (default)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.scenario):
        print(f"Error: Scenario file '{args.scenario}' not found.", file=sys.stderr)
        sys.exit(1)
        
    session = SimulationSession()
    session.run_scenario(args.scenario, override_steps=args.steps)

if __name__ == "__main__":
    main()
