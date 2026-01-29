import pandas as pd
import random
import os
import uuid
from kursa4.model.archetypes import ArchetypeEnum

def generate_emotions():
    return {
        "joy_sadness": random.randint(-3, 3),
        "fear_calm": random.randint(-3, 3),
        "anger_humility": random.randint(-3, 3),
        "disgust_acceptance": random.randint(-3, 3),
        "surprise_habit": random.randint(-3, 3),
        "shame_confidence": random.randint(-3, 3),
        "openness_alienation": random.randint(-3, 3)
    }

def generate_relationships(agent_count):
    relationships = {}
    for i in range(agent_count):
        relationships[i] = {}
        interacting_agents = random.sample([j for j in range(agent_count) if j != i], 20)  
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
                    relationships[i][j] = None  
            else:
                relationships[i][j] = None  
    return relationships

def generate_predicates(agent_index, relationships, agent_count):
    predicates = {}
    interacting_agents = [j for j in range(agent_count) if j != agent_index and relationships[agent_index].get(j) is not None]
    selected_agents = random.sample(interacting_agents, min(20, len(interacting_agents)))  
    for other_agent_index in selected_agents:
        relation = relationships[agent_index][other_agent_index]
        predicates[other_agent_index] = {
            "utility": relation["utility"],
            "affinity": relation["affinity"],
            "trust": relation["trust"],
            "responsiveness": relation["responsiveness"]
        }
    return predicates

def generate_agents(agent_count=1000):
    agents = {}
    relationships = generate_relationships(agent_count)

    for i in range(agent_count):
        agent_name = i+1
        emotion_dict = generate_emotions()

        sensitivity = random.uniform(0, 1)
        archetype = random.choice(list(ArchetypeEnum))
        predicates = generate_predicates(i, relationships, agent_count)  
        
        agent_data = {
            "name": agent_name,
            "emotions": emotion_dict,
            "sensitivity": round(sensitivity, 2),
            "relationships": predicates,
            "archetype": archetype
        }
        agents[agent_name] = agent_data

    for i in range(agent_count, agent_count + 100):
        agent_name = i+1
        emotion_dict = generate_emotions()
        sensitivity = random.uniform(0, 1)
        archetype = random.choice(list(ArchetypeEnum))
        agent_data = {
            "name": agent_name,
            "emotions": emotion_dict,
            "sensitivity": round(sensitivity, 2),
            "relationships": {},  
            "archetype": archetype
        }
        agents[agent_name] = agent_data
    
    return agents

def save_to_csv(agents):
    agents_list = []
    for data in agents.values():
        agent_copy = data.copy()
        agent_copy["archetype"] = agent_copy["archetype"].name
        agents_list.append(agent_copy)
    agents_df = pd.DataFrame(agents_list)
    agents_df.to_csv("agents.csv", index=False)
    print("Данные агентов сохранены в agents.csv.")

agents = generate_agents()
save_to_csv(agents)