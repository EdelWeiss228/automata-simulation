import json
import sys
import os

# Добавляем корневую директорию проекта в path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from gui.simulation_gui import SimulationGUI
from model.collective import Collective
from scripts.run_headless import generate_research_agents
from core.agent_factory import AgentFactory

def run_research_gui(scenario_path):
    with open(scenario_path, 'r', encoding='utf-8') as f:
        scenario = json.load(f)
    
    # 1. Setup Simulation Data
    agents = generate_research_agents(scenario)
    collective = Collective()
    
    for agent in agents:
        collective.add_agent(agent)
        
    print("Инициализация связей для визуализации...")
    agent_names = list(collective.agents.keys())
    for agent in collective.agents.values():
        AgentFactory.initialize_agent_relations(agent, agent_names)
    
    # 2. Launch GUI
    app = SimulationGUI(collective=collective)
    app.title(f"Research Mode: {scenario['emotion_dist']} Dist (Seed: {scenario['seed']})")
    app.mainloop()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 run_research_gui.py <scenario_json>")
        sys.exit(1)
    
    run_research_gui(sys.argv[1])
