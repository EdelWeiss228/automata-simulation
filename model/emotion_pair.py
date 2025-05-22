"""Модуль содержит класс EmotionPair, представляющий пару противоположных эмоций."""

class EmotionPair:
    """Класс для представления и управления значением пары противоположных эмоций."""
    def __init__(self, name, min_value=-3, max_value=3):
        self.name = name
        self.value = 0
        self.min_value = min_value
        self.max_value = max_value

    def adjust(self, delta):
        """Изменяет значение эмоции на заданное смещение, соблюдая границы."""
        self.value = max(self.min_value, min(self.max_value, self.value + delta))

    def set(self, value):
        """Устанавливает конкретное значение эмоции в пределах допустимого диапазона."""
        self.value = max(self.min_value, min(self.max_value, value))

    def describe(self):
        """Возвращает текстовое описание текущего значения эмоции."""
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
