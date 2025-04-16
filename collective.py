import random
from agent import Agent
from player import Player

class Collective:
    def __init__(self, agents_data=None, relations_data=None, players_data=None):
        self.agents = {}
        self.players = []

        if agents_data:
            for agent_name, agent_initial_data in agents_data:
                agent = Agent(agent_name, **agent_initial_data)  
                self.add_agent(agent)

        if relations_data:
            for (subject_name, object_name), relation_data in relations_data.items():
                self.update_relation(subject_name, object_name, **relation_data)

        if players_data:
            for player_data in players_data:
                player = Player(**player_data)  
                self.add_player(player)

    def add_agent(self, agent):
        self.agents[agent.name] = agent

    def add_player(self, player):
        self.players.append(player)

        primary_emotion_name, primary_emotion_value = player.get_primary_emotion()

        if not hasattr(player, "relations"):
            player.relations = {}

        for agent_name, agent in self.agents.items():
            utility = primary_emotion_value if random.random() > 0.5 else random.randint(-3, 3)
            affinity = primary_emotion_value if random.random() > 0.5 else random.randint(-3, 3)
            trust = primary_emotion_value if random.random() > 0.5 else random.randint(-3, 3)

            player.relations[agent_name] = {'utility': utility, 'affinity': affinity, 'trust': trust}
            agent.update_relation(player.name, utility=utility, affinity=affinity, trust=trust)

    def introduce_new_agent(self, new_agent):
        self.add_agent(new_agent)

        for other_name, other_agent in self.agents.items():
            if other_name == new_agent.name:
                continue

            primary_emotion_name, primary_emotion_value = new_agent.get_primary_emotion() 

            utility = primary_emotion_value if random.random() > 0.5 else random.randint(-3, 3)
            affinity = primary_emotion_value if random.random() > 0.5 else random.randint(-3, 3)
            trust = primary_emotion_value if random.random() > 0.5 else random.randint(-3, 3)

            new_agent.update_relation(other_name, utility=utility, affinity=affinity, trust=trust)

            other_agent.update_relation(new_agent.name, utility=utility, affinity=affinity, trust=trust)

    def get_agent(self, name):
        return self.agents.get(name)

    def update_relation(self, subject_name, object_name, utility, affinity, trust):
        subject = self.get_agent(subject_name)
        if subject and object_name in self.agents:
            subject.update_relation(object_name, utility, affinity, trust)

    def describe_all_emotions(self):
        return {
            name: agent.describe_emotions()
            for name, agent in self.agents.items()
        }

    def describe_all_relations(self):
        return {
            name: agent.describe_relations()
            for name, agent in self.agents.items()
        }

    def make_interaction_decision(self):
        for agent in self.agents.values():
            print(f"\n{agent.name} принимает решение о взаимодействии:")
            candidates = sorted(agent.relations.items(), key=lambda x: (x[1]['affinity'], x[1]['utility']), reverse=True)
            if candidates:
                target, metrics = candidates[0]
                print(f"{agent.name} предпочитает взаимодействовать с {target} (симпатия={metrics['affinity']}, выгода={metrics['utility']})")
            else:
                print(f"{agent.name} никого не выбрал.")

    def influence_emotions(self):
        for agent in self.agents.values():
            agent.influence_emotions()

    def simulate_day(self, interactions_per_day: int = 1):
        print("\n--- Симуляция дня ---")
        
        if self.players:
            for player in self.players:
                player.choose_emotion()
                player.choose_interaction(self.agents)

        for agent in self.agents.values():
            agent.react_to_relations()
            agent.react_to_emotions()
        
        for player in self.players:
            for target_name, target_data in player.relations.items():
                target_agent = self.get_agent(target_name)
                if target_agent:
                    target_agent.automaton.adjust_emotion(player.current_emotion, random.randint(-5, 5))
        for agent in self.agents.values():
            agent.react_to_relations()
            agent.react_to_emotions()

        self.influence_emotions()

        for _ in range(interactions_per_day):
            self.make_interaction_decision()

        for agent in self.agents.values():
            candidates = sorted(agent.relations.items(), key=lambda x: (x[1]['affinity'], x[1]['utility']), reverse=True)
            if candidates:
                target_name, metrics = candidates[0]
                if any(player.name == target_name for player in self.players):
                    for player in self.players:
                        if player.name == target_name:
                            emotion_name, emotion_value = agent.get_primary_emotion()
                            print(f"\n{agent.name} выбирает взаимодействие с игроком. Его примарная эмоция: {emotion_name} с силой {emotion_value}.")
                            player.respond_to_agent(agent.name, emotion_name, emotion_value)