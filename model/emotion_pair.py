"""Модуль содержит класс EmotionPair, представляющий пару противоположных эмоций."""

class EmotionPair:
    """Класс для представления и управления значением пары противоположных эмоций."""
    def __init__(self, name, min_value=-3.0, max_value=3.0):
        self.name = name
        self.value = 0.0
        self.min_value = float(min_value)
        self.max_value = float(max_value)

    def adjust(self, delta):
        """Изменяет значение эмоции на заданное смещение (float), соблюдая границы."""
        self.value = max(self.min_value, min(self.max_value, self.value + float(delta)))

    def set(self, value):
        """Устанавливает конкретное значение эмоции (float) в пределах допустимого диапазона."""
        self.value = max(self.min_value, min(self.max_value, float(value)))

    def describe(self):
        """Возвращает текстовое описание текущего значения эмоции на основе диапазонов."""
        val = self.value
        if val <= -2.5: return "очень негативно"
        if val <= -1.5: return "негативно"
        if val <= -0.5: return "немного негативно"
        if val >= 2.5: return "очень позитивно"
        if val >= 1.5: return "позитивно"
        if val >= 0.5: return "немного позитивно"
        return "нейтрально"
