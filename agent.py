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

    def update_relation(self, other_agent_name, utility, affinity, trust):
        self.relations[other_agent_name] = {
            'utility': utility,
            'affinity': affinity,
            'trust': trust
        }

    def get_relation_vector(self, other_agent_name):
        return self.relations.get(other_agent_name, {'utility': 0, 'affinity': 0, 'trust': 0})

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
            
            self.automaton.adjust_emotion("joy_sadness", a)
            self.automaton.adjust_emotion("love_alienation", a)

            self.automaton.adjust_emotion("disgust_acceptance", u)

            if t < 0:
                self.automaton.adjust_emotion("fear_calm", -abs(t))
                self.automaton.adjust_emotion("anger_humility", -abs(t))
    
    def react_to_emotions(self):
        for name, pair in self.automaton.pairs.items():
            emotion_value = pair.value
            
            if name == "joy_sadness" and emotion_value > 1:
                for target_name in self.relations:
                    self.relations[target_name]['affinity'] += 1

            if name == "anger_humility" and emotion_value < -1:
                for target_name in self.relations:
                    self.relations[target_name]['trust'] -= 1

            if name == "fear_calm" and emotion_value < -1:
                for target_name in self.relations:
                    self.relations[target_name]['trust'] -= 1

            if name == "kindness_alienation" and emotion_value > 1:
                for target_name in self.relations:
                    self.relations[target_name]['trust'] += 1
                    self.relations[target_name]['affinity'] += 1

            if name == "disgust_acceptance" and emotion_value < -1:
                for target_name in self.relations:
                    self.relations[target_name]['affinity'] -= 1
                    self.relations[target_name]['utility'] -= 1

    def process_primary_emotion(self, target, pred, coeff, direction):
        emotion_effect = self.emotion_coefficients.get(pred, 1)
        self.relations[target][pred] += coeff * direction * self.sensitivity * emotion_effect

    def influence_emotions(self):
        primary_emotion_name, primary_emotion_value = self.get_primary_emotion()
        
        if primary_emotion_value == 0:
            return  
        
        for target_name, target_agent in self.relations.items():
            affinity = target_agent['affinity']
            trust = target_agent['trust']
            utility = target_agent['utility']
            
            effect_strength = (affinity + trust + utility) / 3  
            effect_value = primary_emotion_value * effect_strength
            
            target_agent = self.get_agent(target_name)
            target_agent.automaton.adjust_emotion(primary_emotion_name, effect_value)

    def get_agent(self, name):
        return self  
    def get_emotion_states(self):
      return {name: pair.describe() for name, pair in self.automaton.pairs.items()}