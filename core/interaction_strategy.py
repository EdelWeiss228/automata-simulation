import random
import math

class InteractionStrategy:
    """
    Класс, инкапсулирующий стратегию выбора цели и обработки результатов взаимодействия.
    Вынесен из Collective для декомпозиции 'God Object'.
    """

    @staticmethod
    def calculate_refusal_chance(agent, target_agent) -> float:
        """
        Рассчитывает вероятность отказа в зависимости от отзывчивости и архетипа.
        """
        responsiveness = agent.relations.get(target_agent.name, {}).get("responsiveness", 0)
        base_chance = getattr(agent.archetype, "refusal_chance", 0.3)
        # Динамический модификатор: чем выше отзывчивость, тем ниже шанс отказа
        dynamic_modifier = max(0.1, 1 - responsiveness / 10)
        return min(1, base_chance * dynamic_modifier)

    @staticmethod
    def handle_player_interaction(agent, player):
        """
        Обрабатывает инициативу агента по отношению к игроку.
        ИСПРАВЛЕНО: Теперь обновление отношений взаимно.
        """
        emotion_name, emotion_value = agent.get_primary_emotion()
        print(
            f"\n{agent.name} выбирает взаимодействие с игроком. "
            f"Его примарная эмоция: {emotion_name} с силой {emotion_value}."
        )
        
        # Игрок отвечает на эмоцию (обновляет свои отношения)
        player.respond_to_agent(agent.name, emotion_name, emotion_value)
        
        # Агент тоже должен обновить свое отношение к игроку (Симметрия!)
        # Используем ту же логику, что и при взаимодействии с агентами
        s_i = getattr(agent, 'sensitivity', 1.0)
        delta = emotion_value * s_i
        
        agent.relations[player.name]['affinity'] = agent.limit_predicate_value(
            agent.relations[player.name].get('affinity', 0) + delta
        )
        agent.relations[player.name]['trust'] = agent.limit_predicate_value(
            agent.relations[player.name].get('trust', 0) + delta
        )
        agent.relations[player.name]['utility'] = agent.limit_predicate_value(
            agent.relations[player.name].get('utility', 0) + delta
        )

    @staticmethod
    def _apply_transformation(val, transform_type):
        """Применяет математическую трансформацию к значению."""
        if transform_type == "log":
            return math.log(abs(val) + 1) * (1 if val >= 0 else -1)
        elif transform_type == "exp":
            return math.exp(val / 5.0) # Масштабируем до разумных пределов
        elif transform_type == "sigmoid":
            return 10 / (1 + math.exp(-val)) # Масштабируем к диапазону 0..10
        elif transform_type == "periodic":
            return math.sin(val) * 5.0
        return val # linear по умолчанию

    @classmethod
    def priority_score(cls, agent, target_name, metrics):
        """
        Расчет приоритета цели на основе реляционных метрик с учетом нелинейности архетипа.
        """
        config = getattr(agent.archetype, 'scoring_config', {})
        
        affinity = metrics.get('affinity', 0)
        utility = metrics.get('utility', 0)
        trust = metrics.get('trust', 0)
        responsiveness = metrics.get('responsiveness', 0)

        # Применяем трансформации
        a_score = cls._apply_transformation(affinity, config.get("affinity", "linear"))
        u_score = cls._apply_transformation(utility, config.get("utility", "linear"))
        t_score = cls._apply_transformation(trust, config.get("trust", "linear"))
        r_score = cls._apply_transformation(responsiveness, config.get("responsiveness", "linear"))

        alpha = 1.5
        multiplier = 1.5 if responsiveness < 0 else 1.0
        
        return a_score + u_score + alpha * t_score + multiplier * r_score

    @staticmethod
    def categorize_relationships(agent):
        """Классифицировать отношения агента на обязательные, опциональные и избегаемые."""
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
        return mandatory, optional, avoid

    @classmethod
    def choose_target(cls, agent, mandatory, optional):
        """
        Выбрать цель взаимодействия на основе Softmax-распределения приоритетов.
        """
        candidates = mandatory if mandatory else optional
        if not candidates:
            return None
            
        # Если кандидат всего один - выбираем его сразу
        if len(candidates) == 1:
            return candidates[0]

        temp = getattr(agent.archetype, 'temperature', 1.0)
        # Ограничиваем температуру снизу, чтобы избежать деления на 0
        temp = max(0.01, temp)
        
        # 1. Считаем скоры для всех кандидатов
        scores = []
        for target_name, metrics in candidates:
            score = cls.priority_score(agent, target_name, metrics)
            scores.append(score)
            
        # 2. Вычисляем экспоненты (Softmax веса)
        # Вычитаем max(scores) для численной стабильности (предотвращение переполнения exp)
        max_score = max(scores)
        exp_scores = [math.exp((s - max_score) / temp) for s in scores]
        
        # 3. Взвешенный случайный выбор
        chosen_idx = random.choices(range(len(candidates)), weights=exp_scores, k=1)[0]
        return candidates[chosen_idx]

    @staticmethod
    def process_refusal(agent, target_agent):
        """
        Обработать отказ взаимодействия между агентами.
        """
        # Инициализация
        for a, t_name in [(agent, target_agent.name), (target_agent, agent.name)]:
            if t_name not in a.relations:
                a.relations[t_name] = {
                    'trust': 0, 'affinity': 0, 'utility': 0, 'responsiveness': 0
                }
            else:
                for key in ['trust', 'affinity', 'utility', 'responsiveness']:
                    a.relations[t_name].setdefault(key, 0)

        # Обновление responsiveness
        s_i = getattr(agent, 'sensitivity', 1.0)
        # Получаем текущую отзывчивость из КОРРЕКТНОГО места
        r_ij = agent.relations[target_agent.name].get('responsiveness', 0)
        
        # Если отзывчивость отрицательная, эффект сильнее
        r_factor = 1.5 if r_ij < 0 else 1.0
        decrement = 0.5 * s_i * r_factor
        
        agent.relations[target_agent.name]['responsiveness'] = max(
            -10, agent.relations[target_agent.name].get('responsiveness', 0) - decrement
        )
        target_agent.relations[agent.name]['responsiveness'] = max(
            -10, target_agent.relations[agent.name].get('responsiveness', 0) - decrement
        )

        # Понижаем trust и affinity
        agent.relations[target_agent.name]['trust'] = max(
            -10, agent.relations[target_agent.name].get('trust', 0) - 0.5 * s_i
        )
        agent.relations[target_agent.name]['affinity'] = max(
            -10, agent.relations[target_agent.name].get('affinity', 0) - 0.5 * s_i
        )
        target_agent.relations[agent.name]['trust'] = max(
            -10, target_agent.relations[agent.name].get('trust', 0) - 0.5 * s_i
        )
        target_agent.relations[agent.name]['affinity'] = max(
            -10, target_agent.relations[agent.name].get('affinity', 0) - 0.5 * s_i
        )

    @staticmethod
    def process_interaction_result(agent, target_agent, success):
        """
        Обработать результат взаимодействия и обновить отношения.
        """
        # Инициализация
        for a, t_name in [(agent, target_agent.name), (target_agent, agent.name)]:
            if t_name not in a.relations:
                a.relations[t_name] = {
                    'trust': 0, 'affinity': 0, 'utility': 0, 'responsiveness': 0
                }
            else:
                for key in ['trust', 'affinity', 'utility', 'responsiveness']:
                    a.relations[t_name].setdefault(key, 0)

        # Используем чувствительность инициатора для масштабирования
        s_i = getattr(agent, "sensitivity", 1.0)
        
        if success:
            delta_trust = 2 * s_i
            delta_other = 1 * s_i
            
            for a, t_name in [(agent, target_agent.name), (target_agent, agent.name)]:
                a.relations[t_name]['trust'] = min(
                    10, a.relations[t_name].get('trust', 0) + delta_trust
                )
                a.relations[t_name]['affinity'] = min(
                    10, a.relations[t_name].get('affinity', 0) + delta_other
                )
                a.relations[t_name]['utility'] = min(
                    10, a.relations[t_name].get('utility', 0) + delta_other
                )
                # Увеличиваем responsiveness
                a.relations[t_name]['responsiveness'] = min(
                    10, a.relations[t_name].get('responsiveness', 0) + s_i
                )
        else:
            delta_trust = 1 * s_i
            for a, t_name in [(agent, target_agent.name), (target_agent, agent.name)]:
                a.relations[t_name]['trust'] = max(
                    -10, a.relations[t_name].get('trust', 0) - delta_trust
                )
                # responsiveness всё равно растет при контакте
                a.relations[t_name]['responsiveness'] = min(
                    10, a.relations[t_name].get('responsiveness', 0) + s_i
                )
