import os
import shutil
from collective import Collective
from agent import Agent
import datetime
import csv

def run_batch_simulations(runs=1, days_per_run=100):
    if os.path.exists("batch_results"):
        shutil.rmtree("batch_results")
    os.makedirs("batch_results")

    for i in range(runs):
        print(f"--- Запуск симуляции {i+1} ---")
        run_single_simulation(run_id=i+1, days=days_per_run)

def run_single_simulation(run_id, days=100):
    collective = Collective()
    # Добавляем 5 агентов случайным образом, как в GUI
    from gui.agent_add_dialog import ArchetypeEnum
    import random

    names = ["Рома", "Иван", "Аня", "Катя", "Дима", "Саша", "Маша", "Петя", "Лена", "Никита"]

    for i in range(10000):
        name = random.choice(names) + f"_{i+1}"
        archetype = random.choice(list(ArchetypeEnum))
        sensitivity = round(random.uniform(0.0, 3.0), 2)
        emotions = {
            axis: random.randint(-3, 3) for axis in [
                "joy_sadness", "fear_calm", "anger_humility",
                "disgust_acceptance", "surprise_habit",
                "shame_confidence", "love_alienation"
            ]
        }
        # Предикаты к другим агентам будут инициализированы после добавления всех агентов
        agent = Agent(name=name, archetype=archetype, sensitivity=sensitivity, emotions=emotions)
        collective.add_agent(agent)

    # Инициализация предикатов после добавления всех агентов
    for agent in collective.agents.values():
        for other in collective.agents.values():
            if agent.name != other.name:
                agent.relations[other.name] = {
                    "utility": random.randint(-10, 10),
                    "affinity": random.randint(-10, 10),
                    "trust": random.randint(-10, 10),
                    "responsiveness": random.randint(-10, 10)
                }

    current_date = datetime.date(2025, 1, 1)
    interaction_log = []
    agent_states = []

    for day in range(days):
        interactions = collective.make_interaction_decision()
        for a_from, a_to, success in interactions:
            interaction_log.append([
                current_date.isoformat(), a_from, a_to, success
            ])
        for agent in collective.agents.values():
            emotion_str = "; ".join(f"{k}:{v}" for k, v in agent.get_emotions().items())
            pred_strs = []
            for target, preds in agent.relations.items():
                pred_str = f"{target}=" + ",".join(f"{k}:{v}" for k, v in preds.items())
                pred_strs.append(pred_str)
            agent_states.append([
                current_date.isoformat(), agent.name, emotion_str, " | ".join(pred_strs)
            ])
        current_date += datetime.timedelta(days=1)

    os.makedirs("batch_results", exist_ok=True)
    with open(f"batch_results/interaction_log_{run_id}.csv", "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Дата", "Источник", "Цель", "Успех"])
        writer.writerows(interaction_log)

    with open(f"batch_results/agent_states_{run_id}.csv", "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Дата", "Имя агента", "Эмоции", "Предикаты"])
        writer.writerows(agent_states)

if __name__ == "__main__":
    run_batch_simulations()