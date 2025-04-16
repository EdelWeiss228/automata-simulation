from emotion_pair import EmotionPair

class EmotionAutomaton:
    def __init__(self):
        self.pairs = {
            'joy_sadness': EmotionPair('joy_sadness'),
            'fear_calm': EmotionPair('fear_calm'),
            'anger_humility': EmotionPair('anger_humility'),
            'disgust_acceptance': EmotionPair('disgust_acceptance'),
            'surprise_habit': EmotionPair('surprise_habit'),
            'shame_confidence': EmotionPair('shame_confidence'),
            'love_alienation': EmotionPair('love_alienation'),
        }

    def adjust_emotion(self, name, delta):
        if name in self.pairs:
            self.pairs[name].adjust(delta)

    def set_emotion(self, name, value):
        if name in self.pairs:
            self.pairs[name].set(value)

    def get_emotion_description(self, name):
        if name in self.pairs:
            return self.pairs[name].describe()
        return "неизвестная эмоция"

    def describe_all(self):
        return {name: pair.describe() for name, pair in self.pairs.items()}
