from emotion_automaton import EmotionAutomaton

class Agent:
    def __init__(self, name, initial_emotions=None, emotion_effects=None, emotion_coefficients=None, sensitivity=1):
        self.name = name
        self.automaton = EmotionAutomaton()
        self.relations = {}
        self.sensitivity = sensitivity

        self.emotion_effects = emotion_effects or {
            'joy_sadness': {'affinity': 1, 'trust': 1},
            'anger_humility': {'affinity': -2, 'trust': -2, 'utility': -1},
            'fear_calm': {'trust': -1, 'utility': -1},
            'love_alienation': {'affinity': 2, 'trust': 1},
            'disgust_acceptance': {'affinity': -1, 'utility': -1},
            'shame_confidence': {'trust': 1, 'affinity': -1},
            'surprise_habit': {'utility': 1}
        }

        self.emotion_coefficients = emotion_coefficients or {
            'joy_sadness': 1,
            'anger_humility': -1,
            'fear_calm': -1,
            'love_alienation': 1,
            'disgust_acceptance': -1,
            'shame_confidence': 1,
            'surprise_habit': 1
        }

        if initial_emotions:
            for name, value in initial_emotions.items():
                self.automaton.set_emotion(name, value)

    def limit_predicate_value(self, value, min_value=-10, max_value=10):
        return max(min(value, max_value), min_value)

    def update_relation(self, other_agent_name, utility, affinity, trust):
        self.relations[other_agent_name] = {
            'utility': self.limit_predicate_value(utility),
            'affinity': self.limit_predicate_value(affinity),
            'trust': self.limit_predicate_value(trust),
            'responsiveness': self.limit_predicate_value(self.relations.get(other_agent_name, {}).get('responsiveness', 0))
        }

    def get_relation_vector(self, other_agent_name):
        return self.relations.get(other_agent_name, {'utility': 0, 'affinity': 0, 'trust': 0, 'responsiveness': 0})

    def update_responsiveness(self, target_name, delta):
        if target_name in self.relations:
            current = self.relations[target_name].get('responsiveness', 0)
            new_responsiveness = self.limit_predicate_value(current + delta)
            self.relations[target_name]['responsiveness'] = new_responsiveness

            if new_responsiveness < 0:
                self.relations[target_name]['affinity'] = self.limit_predicate_value(self.relations[target_name]['affinity'] - 1 * self.sensitivity)
                self.relations[target_name]['trust'] = self.limit_predicate_value(self.relations[target_name]['trust'] - 1 * self.sensitivity)
            else:
                self.relations[target_name]['affinity'] = self.limit_predicate_value(self.relations[target_name]['affinity'] + 1 * self.sensitivity)
                self.relations[target_name]['trust'] = self.limit_predicate_value(self.relations[target_name]['trust'] + 1 * self.sensitivity)

    def describe_emotions(self):
        return {
            name: pair.describe()
            for name, pair in self.automaton.pairs.items()
        }

    def describe_relations(self):
        return self.relations

    def get_primary_emotion(self):
        max_name = None
        max_value = 0
        for name, pair in self.automaton.pairs.items():
            if abs(pair.value) > abs(max_value):
                max_value = pair.value
                max_name = name
        return max_name, max_value

    def react_to_relations(self):
        for target_name, pred in self.relations.items():
            u, a, t = pred['utility'], pred['affinity'], pred['trust']
            
            a = self.limit_predicate_value(a)
            t = self.limit_predicate_value(t)
            u = self.limit_predicate_value(u)

            self.automaton.adjust_emotion("joy_sadness", a * self.sensitivity)
            self.automaton.adjust_emotion("love_alienation", a * self.sensitivity)

            self.automaton.adjust_emotion("disgust_acceptance", u * self.sensitivity)

            if t < 0:
                self.automaton.adjust_emotion("fear_calm", -abs(t) * self.sensitivity)
                self.automaton.adjust_emotion("anger_humility", -abs(t) * self.sensitivity)
    
    def react_to_emotions(self):
        for name, pair in self.automaton.pairs.items():
            emotion_value = pair.value
            
            if name == "joy_sadness" and emotion_value > 1:
                for target_name in self.relations:
                    if self.relations[target_name]['responsiveness'] < 0:
                        self.relations[target_name]['affinity'] = self.limit_predicate_value(self.relations[target_name]['affinity'] - 1 * self.sensitivity)
                    else:
                        self.relations[target_name]['affinity'] = self.limit_predicate_value(self.relations[target_name]['affinity'] + 1 * self.sensitivity)

            if name == "anger_humility" and emotion_value < -1:
                for target_name in self.relations:
                    if self.relations[target_name]['responsiveness'] < 0:
                        self.relations[target_name]['trust'] = self.limit_predicate_value(self.relations[target_name]['trust'] - 1 * self.sensitivity)
                    else:
                        self.relations[target_name]['trust'] = self.limit_predicate_value(self.relations[target_name]['trust'] + 1 * self.sensitivity)

            if name == "fear_calm" and emotion_value < -1:
                for target_name in self.relations:
                    if self.relations[target_name]['responsiveness'] < 0:
                        self.relations[target_name]['trust'] = self.limit_predicate_value(self.relations[target_name]['trust'] - 1 * self.sensitivity)
                    else:
                        self.relations[target_name]['trust'] = self.limit_predicate_value(self.relations[target_name]['trust'] + 1 * self.sensitivity)

            if name == "kindness_alienation" and emotion_value > 1:
                for target_name in self.relations:
                    self.relations[target_name]['trust'] = self.limit_predicate_value(self.relations[target_name]['trust'] + 1 * self.sensitivity)
                    self.relations[target_name]['affinity'] = self.limit_predicate_value(self.relations[target_name]['affinity'] + 1 * self.sensitivity)

            if name == "disgust_acceptance" and emotion_value < -1:
                for target_name in self.relations:
                    if self.relations[target_name]['responsiveness'] < 0:
                        self.relations[target_name]['affinity'] = self.limit_predicate_value(self.relations[target_name]['affinity'] - 1 * self.sensitivity)
                        self.relations[target_name]['utility'] = self.limit_predicate_value(self.relations[target_name]['utility'] - 1 * self.sensitivity)
                    else:
                        self.relations[target_name]['affinity'] = self.limit_predicate_value(self.relations[target_name]['affinity'] + 1 * self.sensitivity)
                        self.relations[target_name]['utility'] = self.limit_predicate_value(self.relations[target_name]['utility'] + 1 * self.sensitivity)

    def process_primary_emotion(self, target, pred, coeff, direction):
        emotion_effect = self.emotion_coefficients.get(pred, 1)
        updated_value = self.relations[target][pred] + coeff * direction * self.sensitivity * emotion_effect
        self.relations[target][pred] = self.limit_predicate_value(updated_value)

    def influence_emotions(self):
        primary_emotion_name, primary_emotion_value = self.get_primary_emotion()

        if primary_emotion_value == 0:
            return

        for target_name, relation in self.relations.items():
            affinity = self.limit_predicate_value(relation['affinity'])
            trust = self.limit_predicate_value(relation['trust'])
            utility = self.limit_predicate_value(relation['utility'])
            effect_strength = (affinity + trust + utility) / 3

            total_intensity = sum(abs(pair.value) for pair in self.automaton.pairs.values())
            if total_intensity == 0:
                continue

            dynamic_weight_primary = abs(primary_emotion_value) / total_intensity
            dynamic_weight_secondary = (1 - dynamic_weight_primary) / (len(self.automaton.pairs) - 1)

            try:
                target_agent = self.get_agent(target_name)
                target_agent.automaton.adjust_emotion(primary_emotion_name, primary_emotion_value * effect_strength * dynamic_weight_primary * self.sensitivity)

                other_emotions = {
                    name: pair.value for name, pair in self.automaton.pairs.items()
                    if name != primary_emotion_name
                }

                for name, value in other_emotions.items():
                    if value != 0:
                        target_agent.automaton.adjust_emotion(name, value * effect_strength * dynamic_weight_secondary * self.sensitivity)

                self.update_responsiveness(target_name, 1)
            except (ValueError, AttributeError):
                self.update_responsiveness(target_name, -1)

    def get_agent(self, name):
        if hasattr(self, 'group') and self.group:
            agent = self.group.get_agent_by_name(name)
            if agent is not None:
                return agent
            else:
                raise ValueError(f"Agent with name '{name}' not found in the group.")
        else:
            raise AttributeError("Agent is not part of any group or group is not set.")

    def classify_relationship(self, other_name):
        relation = self.get_relation_vector(other_name)
        trust = relation['trust']
        affinity = relation['affinity']
        utility = relation['utility']
        responsiveness = relation['responsiveness']

        if responsiveness < -5:
            return "avoid"
        elif trust >= 5 and affinity >= 5 and responsiveness >= 0:
            return "mandatory"
        elif trust >= 0 or affinity >= 0 or responsiveness > -5:
            return "optional"
        else:
            return "avoid"
    
    def get_emotion_states(self):
        return {name: pair.describe() for name, pair in self.automaton.pairs.items()}
    def decay_responsiveness_passive(self):
        for target_name in self.relations:
            self.update_responsiveness(target_name, -1 * self.sensitivity)