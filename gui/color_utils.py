def get_emotion_color(emotion_name, value):
    """
    Возвращает HEX-код цвета на основе примарной эмоции и её силы (-3..3).
    0 — белый. Крайние значения — насыщенные цвета.
    """
    if value == 0 or not emotion_name:
        return "#ADD8E6" # LightBlue для нейтрального состояния

    # Маппинг осей на цвета (Positive Color, Negative Color)
    # Порядок: (для value > 0, для value < 0)
    COLOR_MAP = {
        'joy_sadness': ((255, 255, 0), (0, 0, 255)),       # Желтый / Синий
        'fear_calm': ((0, 128, 0), (173, 216, 230)),       # Зеленый / Свелта-голубой
        'anger_humility': ((255, 0, 0), (32, 178, 170)),   # Красный / Бирюзовый
        'disgust_acceptance': ((128, 0, 128), (144, 238, 144)), # Пурпурный / Салатовый
        'surprise_habit': ((255, 165, 0), (139, 69, 19)),  # Оранжевый / Коричневый
        'shame_confidence': ((128, 128, 128), (255, 215, 0)), # Серый / Золотой
        'openness_alienation': ((255, 20, 147), (47, 79, 79))  # Розовый / Темно-серый
    }

    if emotion_name not in COLOR_MAP:
        return "#FFFFFF"

    pos_color, neg_color = COLOR_MAP[emotion_name]
    target_color = pos_color if value > 0 else neg_color
    
    # Сила эмоции от 0 до 1 (клиппинг для надежности)
    intensity = min(abs(value) / 3.0, 1.0)
    
    # Интерполяция между белым (255,255,255) и целевым цветом
    r = int(255 + (target_color[0] - 255) * intensity)
    g = int(255 + (target_color[1] - 255) * intensity)
    b = int(255 + (target_color[2] - 255) * intensity)
    
    return f"#{r:02x}{g:02x}{b:02x}"
