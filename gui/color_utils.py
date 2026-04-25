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
        'sadness_joy': ((255, 255, 0), (0, 0, 255)),       # Желтый / Синий
        'fear_calm': ((0, 128, 0), (173, 216, 230)),       # Зеленый / Свелта-голубой
        'anger_humility': ((32, 178, 170), (255, 0, 0)),   # Бирюзовый / Красный
        'disgust_acceptance': ((144, 238, 144), (128, 0, 128)), # Салатовый / Пурпурный
        'habit_surprise': ((255, 165, 0), (139, 69, 19)),  # Оранжевый / Коричневый
        'shame_confidence': ((255, 215, 0), (128, 128, 128)), # Золотой / Серый
        'alienation_openness': ((255, 20, 147), (47, 79, 79))  # Розовый / Темно-серый
    }

    if emotion_name not in COLOR_MAP:
        return "#FFFFFF"

    pos_color, neg_color = COLOR_MAP[emotion_name]
    target_color = pos_color if value > 0 else neg_color
    
    # Сила эмоции (линейный градиент для шкалы x10)
    intensity = min(abs(value) / 30.0, 1.0)
    
    # Интерполяция между белым (255,255,255) и целевым цветом
    r = int(255 + (target_color[0] - 255) * intensity)
    g = int(255 + (target_color[1] - 255) * intensity)
    b = int(255 + (target_color[2] - 255) * intensity)
    
    return f"#{r:02x}{g:02x}{b:02x}"
