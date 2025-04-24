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
                agent.group = self
                self.add_agent(agent)

        if relations_data:
            for (subject_name, object_name), relation_data in relations_data.items():
                self.update_relation(subject_name, object_name, **relation_data)

        if players_data:
            for player_data in players_data:
                player = Player(**player_data)  
                self.add_player(player)

        for agent in self.agents.values():
            for other_name in self.agents:
                if other_name != agent.name and other_name not in agent.relations:
                    agent.relations[other_name] = {
                        'utility': 0,
                        'affinity': 0,
                        'trust': 0,
                        'responsiveness': 0
                    }

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
        new_agent.group = self

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
    
    def get_agent_by_name(self, name):
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
        interacted_agents = set()
        for agent in self.agents.values():
            if agent.name in interacted_agents:
                continue
            print(f"\n{agent.name} принимает решение о взаимодействии:")
            mandatory = []
            optional = []
            avoid = []
            for target_name, metrics in agent.relations.items():
                category = agent.classify_relationship(target_name)
                if category == "mandatory":
                    mandatory.append((target_name, metrics))
                elif category == "optional":
                    optional.append((target_name, metrics))
                else:
                    avoid.append((target_name, metrics))
            chosen = None
            if mandatory:
                chosen = max(mandatory, key=lambda x: (x[1]['affinity'], x[1]['utility']))
            elif optional:
                chosen = max(optional, key=lambda x: (x[1]['affinity'], x[1]['utility']))
            else:
                print(f"{agent.name} решил отказаться от взаимодействия сегодня.")
                for target_name in agent.relations.keys():
                    agent.relations[target_name]['trust'] = agent.relations[target_name].get('trust', 0) - 1
                for other_agent in self.agents.values():
                    if other_agent.name != agent.name and agent.name in other_agent.relations:
                        other_agent.relations[agent.name]['trust'] = other_agent.relations[agent.name].get('trust', 0) - 1
                continue
            target, metrics = chosen
            target_agent = self.get_agent(target)
            if target_agent.classify_relationship(agent.name) == "avoid":
                print(f"{target_agent.name} отказался взаимодействовать с {agent.name}.")
                agent.relations[target]['trust'] = max(-10, agent.relations[target].get('trust', 0) - 2)
                target_agent.relations[agent.name]['trust'] = max(-10, target_agent.relations[agent.name].get('trust', 0) - 2)
                continue
            print(f"{agent.name} предпочитает взаимодействовать с {target} (симпатия={metrics['affinity']}, выгода={metrics['utility']})")
            success = (metrics['affinity'] > 0 and metrics['utility'] > 0)
            if success:
                print(f"Взаимодействие между {agent.name} и {target} прошло УСПЕШНО.")
            else:
                print(f"Взаимодействие между {agent.name} и {target} НЕУДАЧНО.")
            sensitivity = getattr(agent, "responsiveness", 1.0)

            if success:
                delta = int(2 * sensitivity)
                agent.relations[target]['trust'] = min(10, agent.relations[target].get('trust', 0) + delta)
                agent.relations[target]['affinity'] = min(10, agent.relations[target].get('affinity', 0) + int(1 * sensitivity))
                agent.relations[target]['utility'] = min(10, agent.relations[target].get('utility', 0) + int(1 * sensitivity))
                if target_agent.name in target_agent.relations:
                    target_agent.relations[agent.name]['trust'] = min(10, target_agent.relations[agent.name].get('trust', 0) + delta)
                    target_agent.relations[agent.name]['affinity'] = min(10, target_agent.relations[agent.name].get('affinity', 0) + int(1 * sensitivity))
                    target_agent.relations[agent.name]['utility'] = min(10, target_agent.relations[agent.name].get('utility', 0) + int(1 * sensitivity))
            else:
                delta = int(1 * sensitivity)
                agent.relations[target]['trust'] = max(-10, agent.relations[target].get('trust', 0) - delta)
                if target_agent.name in target_agent.relations:
                    target_agent.relations[agent.name]['trust'] = max(-10, target_agent.relations[agent.name].get('trust', 0) - delta)
            interacted_agents.add(agent.name)
            interacted_agents.add(target)
        for agent in self.agents.values():
            if agent.name not in interacted_agents:
                for rel in agent.relations.values():
                    rel['trust'] = rel.get('trust', 0) + 1

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