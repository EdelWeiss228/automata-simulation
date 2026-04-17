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
        Рассчитывает вероятность отказа на основе базового шанса архетипа.
        """
        base_factor = getattr(agent.archetype, "refusal_chance", 0.3)
        return min(0.95, base_factor)

    @staticmethod
    def handle_player_interaction(agent, player):
        """
        Обрабатывает инициативу агента по отношению к игроку.
        """
        emotion_name, emotion_value = agent.get_primary_emotion()
        # Игрок отвечает на эмоцию
        player.respond_to_agent(agent.name, emotion_name, emotion_value)
        
        # Агент обновляет отношение к игроку (delta теперь в x10)
        s_i = getattr(agent, 'sensitivity', 1.0)
        delta_scaled = emotion_value * s_i # emotion_value уже до 30
        
        # При успехе контакта с игроком (инициатива агента)
        agent.relations[player.name]['affinity'] = agent.limit_predicate_value(
            agent.relations[player.name].get('affinity', 0) + int(delta_scaled * 2.0)
        )
        agent.relations[player.name]['utility'] = agent.limit_predicate_value(
            agent.relations[player.name].get('utility', 0) + int(delta_scaled * 2.0)
        )
        agent.relations[player.name]['trust'] = agent.limit_predicate_value(
            agent.relations[player.name].get('trust', 0) + int(delta_scaled)
        )

    @staticmethod
    def _apply_transformation(val, transform_type):
        """Применяет математическую трансформацию к значению (scaled input)."""
        val_orig = val / 10.0 # Ожидаем логарифм/экспоненту в шкале 0..10
        if transform_type == "log":
            return math.log(abs(val_orig) + 1) * (1 if val_orig >= 0 else -1)
        elif transform_type == "exp":
            return math.exp(val_orig / 5.0)
        elif transform_type == "sigmoid":
            return 10 / (1 + math.exp(-val_orig))
        elif transform_type == "periodic":
            return math.sin(val_orig) * 5.0
        return val_orig # linear по умолчанию

    @classmethod
    def priority_score(cls, agent, target_name, metrics):
        """
        Расчет приоритета цели на основе реляционных метрик.
        """
        config = getattr(agent.archetype, 'scoring_config', {})
        
        affinity = metrics.get('affinity', 0)
        utility = metrics.get('utility', 0)
        trust = metrics.get('trust', 0)

        # Применяем трансформации
        a_score = cls._apply_transformation(affinity, config.get("affinity", "linear"))
        u_score = cls._apply_transformation(utility, config.get("utility", "linear"))
        t_score = cls._apply_transformation(trust, config.get("trust", "linear"))

        alpha = 1.5
        
        return a_score + u_score + alpha * t_score

    @staticmethod
    def categorize_relationships(agent):
        """Классифицировать отношения агента."""
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
        """Выбрать цель взаимодействия на основе Softmax-распределения."""
        candidates = mandatory if mandatory else optional
        if not candidates:
            return None
            
        if len(candidates) == 1:
            return candidates[0]

        temp = getattr(agent.archetype, 'temperature', 1.0)
        temp = max(0.01, temp)
        
        scores = []
        for target_name, metrics in candidates:
            score = cls.priority_score(agent, target_name, metrics)
            scores.append(score)
            
        max_score = max(scores)
        exp_scores = [math.exp((s - max_score) / temp) for s in scores]
        
        chosen_idx = random.choices(range(len(candidates)), weights=exp_scores, k=1)[0]
        return candidates[chosen_idx]

    @staticmethod
    def process_refusal(agent, target_agent):
        """
        Обработать отказ взаимодействия между агентами.
        Штраф получает только инициатор (agent), так как его чаяния не оправдались.
        Тот, кто отказал (target_agent), не меняет своего мнения об инициаторе.
        """
        s_i = getattr(agent, 'sensitivity', 1.0)

        if target_agent.name not in agent.relations:
            from core.agent_factory import AgentFactory
            AgentFactory.initialize_agent_relations(agent, [target_agent.name])

        vuln_i = getattr(agent.archetype, 'refusal_vulnerability', 0)
        penalty = 20 * s_i # Умеренный штраф (-2.0 в старой шкале)

        if vuln_i == 0:
            agent.relations[target_agent.name]['utility'] = agent.limit_predicate_value(
                agent.relations[target_agent.name].get('utility', 0) - penalty
            )
        elif vuln_i == 1:
            agent.relations[target_agent.name]['affinity'] = agent.limit_predicate_value(
                agent.relations[target_agent.name].get('affinity', 0) - penalty
            )
        else:
            agent.relations[target_agent.name]['trust'] = agent.limit_predicate_value(
                agent.relations[target_agent.name].get('trust', 0) - penalty
            )

        # Тот, кто отказал, не меняет мнения. Логика изменений убрана.

    @staticmethod
    def process_interaction_result(agent, target_agent, sigma):
        """
        Обработать результат взаимодействия (Sigma) и обновить отношения.
        Влияние зависит от знака первичной эмоции:
        - Успех (1) усиливает позитив (x2.0) и гасит негатив (x0.5)
        - Неудача (-1) гасит позитив (x0.5) и раздувает негатив (x2.0)
        """
        s_i = getattr(agent, "sensitivity", 1.0)
        s_t = getattr(target_agent, "sensitivity", 1.0)
        
        # Получаем знак и силу первичной эмоции инициатора
        _, e_val = agent.get_primary_emotion()
        
        # Определяем множитель на основе Сигма-модели
        multiplier = 1.0
        if sigma == 1: # Успех
            multiplier = 2.0 if e_val >= 0 else 0.5
        elif sigma == -1: # Неудача
            multiplier = 0.5 if e_val >= 0 else 2.0

        # Базовые дельты в x10
        base_affinity = 15 * multiplier
        base_trust = 10 * multiplier
        
        # При неудаче (-1) доверие всегда падает сильнее, а аффинити страдает от 'шума'
        if sigma == -1:
            base_trust = -20 * multiplier
            base_affinity = -5 * multiplier

        for a, t_obj, s in [(agent, target_agent, s_i), (target_agent, agent, s_t)]:
            t_name = t_obj.name
            if t_name not in a.relations:
                from core.agent_factory import AgentFactory
                AgentFactory.initialize_agent_relations(a, [t_name])
            
            # Применяем изменения
            a.relations[t_name]['affinity'] = a.limit_predicate_value(
                a.relations[t_name].get('affinity', 0) + int(base_affinity * s)
            )
            a.relations[t_name]['utility'] = a.limit_predicate_value(
                a.relations[t_name].get('utility', 0) + int(base_affinity * s)
            )
            a.relations[t_name]['trust'] = a.limit_predicate_value(
                a.relations[t_name].get('trust', 0) + int(base_trust * s)
            )
