class EmotionPair:
    def __init__(self, name, min_value=-3, max_value=3):
        self.name = name
        self.value = 0
        self.min_value = min_value
        self.max_value = max_value

    def adjust(self, delta):
        self.value = max(self.min_value, min(self.max_value, self.value + delta))

    def set(self, value):
        self.value = max(self.min_value, min(self.max_value, value))

    def describe(self):
        descriptions = {
            -3: "очень негативно",
            -2: "негативно",
            -1: "немного негативно",
             0: "нейтрально",
             1: "немного позитивно",
             2: "позитивно",
             3: "очень позитивно"
        }
        return descriptions.get(self.value, "неопределённо")
