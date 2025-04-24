import pandas as pd
import random

# Функция для случайной генерации эмоций
def generate_emotions():
    emotion_values = ['очень позитивно', 'позитивно', 'нейтрально', 'негативно', 'очень негативно']
    return {
        "joy_sadness": random.choice(emotion_values),
        "fear_calm": random.choice(emotion_values),
        "anger_humility": random.choice(emotion_values),
        "disgust_acceptance": random.choice(emotion_values),
        "surprise_habit": random.choice(emotion_values),
        "shame_confidence": random.choice(emotion_values),
        "love_alienation": random.choice(emotion_values)
    }

# Функция для генерации отношений между агентами
def generate_relationships(agent_count):
    relationships = {}
    for i in range(agent_count):
        relationships[i] = {}
        interacting_agents = random.sample([j for j in range(agent_count) if j != i], 20)  # 20 случайных агентов для взаимодействия
        for j in range(agent_count):
            if i != j:
                if j in interacting_agents:
                    relationships[i][j] = {
                        "utility": random.randint(-10, 10),
                        "affinity": random.randint(-10, 10),
                        "trust": random.randint(-10, 10),
                        "responsiveness": random.randint(-10, 10)
                    }
                else:
                    relationships[i][j] = None  # Нет взаимодействия
            else:
                relationships[i][j] = None  # Агенты не могут взаимодействовать с собой
    return relationships

# Функция для генерации предикатов для агента на основе его отношений
def generate_predicates(agent_index, relationships, agent_count):
    predicates = {}
    interacting_agents = [j for j in range(agent_count) if j != agent_index and relationships[agent_index].get(j) is not None]
    selected_agents = random.sample(interacting_agents, min(20, len(interacting_agents)))  # 20 случайных агентов с которыми есть взаимодействие
    for other_agent_index in selected_agents:
        relation = relationships[agent_index][other_agent_index]
        predicates[other_agent_index] = {
            "utility": relation["utility"],
            "affinity": relation["affinity"],
            "trust": relation["trust"],
            "responsiveness": relation["responsiveness"]
        }
    return predicates

# Генерация агентов с уникальными характеристиками
def generate_agents(agent_count=1000):
    agents = {}
    relationships = generate_relationships(agent_count)  # Генерация отношений между агентами

    for i in range(agent_count):
        agent_name = f"Agent_{i+1}"
        emotions = generate_emotions()

        # Генерация чувствительности от 0 до 1
        sensitivity = random.uniform(0, 1)
        
        predicates = generate_predicates(i, relationships, agent_count)  # Генерация предикатов на основе отношений
        
        agent_data = {
            "name": agent_name,
            **emotions,
            "sensitivity": sensitivity,  # Добавляем чувствительность
            "relationships": predicates
        }
        agents[agent_name] = agent_data

    # Добавим 100 агентов без отношений
    for i in range(agent_count, agent_count + 100):
        agent_name = f"Agent_{i+1}"
        emotions = generate_emotions()
        sensitivity = random.uniform(0, 1)
        agent_data = {
            "name": agent_name,
            **emotions,
            "sensitivity": sensitivity,
            "relationships": {}  # Нет отношений
        }
        agents[agent_name] = agent_data
    
    return agents

# Сохранение данных в CSV
def save_to_csv(agents):
    # Преобразуем словарь в DataFrame
    agents_list = [data for name, data in agents.items()]
    agents_df = pd.DataFrame(agents_list)
    agents_df.to_csv('agents.csv', index=False)
    print("Данные агентов сохранены в agents.csv.")

# Генерация агентов и сохранение в CSV
agents = generate_agents()
save_to_csv(agents)