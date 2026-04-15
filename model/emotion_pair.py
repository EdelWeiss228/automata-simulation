"""Модуль содержит класс EmotionPair, представляющий пару противоположных эмоций."""

class EmotionPair:
    """Класс для представления и управления значением пары противоположных эмоций."""
    def __init__(self, name, min_value=-30, max_value=30):
        self.name = name
        self.value = 0
        self.min_value = int(min_value)
        self.max_value = int(max_value)

    def adjust(self, delta):
        """Изменяет значение эмоции на заданное смещение (int), соблюдая границы."""
        self.value = max(self.min_value, min(self.max_value, int(self.value + delta)))

    def set(self, value):
        """Устанавливает конкретное значение эмоции (int) в пределах допустимого диапазона."""
        self.value = max(self.min_value, min(self.max_value, int(value)))

    def describe(self):
        """Возвращает текстовое описание текущего значения эмоции на основе диапазонов (x10)."""
        val = self.value
        if val <= -25: return "очень негативно"
        if val <= -15: return "негативно"
        if val <= -5: return "немного негативно"
        if val >= 25: return "очень позитивно"
        if val >= 15: return "позитивно"
        if val >= 5: return "немного позитивно"
        return "нейтрально"
