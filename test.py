import sys

# sys.stdout = open("simulation_output.txt", "w", encoding="utf-8")

from collective import Collective
from agent import Agent
from player import Player  

agents_data = [
    ("Alice", {"initial_emotions": {"joy_sadness": 2, "anger_humility": -2}, "emotion_coefficients": {"joy_sadness": 1, "anger_humility": -2, "fear_calm": -1}, "sensitivity": 2}),
    ("Bob", {"initial_emotions": {"joy_sadness": 3, "fear_calm": -1}, "emotion_coefficients": {"joy_sadness": 1, "fear_calm": -1}, "sensitivity": 2}),
    ("Charlie", {"initial_emotions": {"joy_sadness": 1, "anger_humility": -1}, "emotion_coefficients": {"joy_sadness": 1, "anger_humility": -1, "fear_calm": -1}, "sensitivity": 2})
]

relations_data = {
    ("Alice", "Bob"): {"utility": 2, "affinity": -1, "trust": 1},
    ("Bob", "Alice"): {"utility": 1, "affinity": 1, "trust": 2},
    ("Charlie", "Alice"): {"utility": -2, "affinity": 2, "trust": 0},
    ("Charlie", "Bob"): {"utility": -2, "affinity": -2, "trust": -2},
    ("Alice", "Charlie"): {"utility": 0, "affinity": 0, "trust": 0},
    ("Bob", "Charlie"): {"utility": 1, "affinity": -1, "trust": 2}
}

group = Collective(agents_data=agents_data, relations_data=relations_data)

player = Player(name="Player1", group=group)
group.add_player(player)

for day in range(1, 7):
    print(f"\nДень {day}:")
    
    if day == 4:
        print("\nДобавляем нового агента!")
        new_agent_data = ("David", {"initial_emotions": {"joy_sadness": 2, "fear_calm": 1}, "emotion_coefficients": {"joy_sadness": 1, "fear_calm": -1}, "sensitivity": 3})
        new_agent = Agent(new_agent_data[0], **new_agent_data[1])
        group.introduce_new_agent(new_agent)  
        
    group.simulate_day(interactions_per_day=3)

    print("\nЭмоции всех агентов:")
    for name, emotions in group.describe_all_emotions().items():
        print(f"{name}: {emotions}")

    print("\nОтношения всех агентов:")
    for name, relations in group.describe_all_relations().items():
        print(f"{name}: {relations}")

# sys.stdout.close()