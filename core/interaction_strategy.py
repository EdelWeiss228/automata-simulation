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
        Рассчитывает вероятность отказа на основе Softmax от отзывчивости (Responsiveness).
        """
        r_ij = agent.get_relation_vector(target_agent.name).get("responsiveness", 0)
        
        # Используем экспоненциальную функцию для Softmax-подобного поведения
        # Температура T определяет крутизну кривой. Чем ниже T, тем жестче отказ при R < 0.
        temp = 2.0
        # Шанс отказа = 1 / (1 + exp(R / T))
        # Если R = 0, шанс 0.5. Если R = 10, шанс ~0.006. Если R = -10, шанс ~0.993.
        refusal_prob = 1.0 / (1.0 + math.exp(r_ij / temp))
        
        # Архетипичный базовый шанс как множитель
        base_factor = getattr(agent.archetype, "refusal_chance", 0.3)
        return min(0.95, refusal_prob * (base_factor / 0.3))

    @staticmethod
    def handle_player_interaction(agent, player):
        """
        Обрабатывает инициативу агента по отношению к игроку.
        """
        emotion_name, emotion_value = agent.get_primary_emotion()
        # Игрок отвечает на эмоцию
        player.respond_to_agent(agent.name, emotion_name, emotion_value)
        
        # Агент обновляет отношение к игроку
        s_i = getattr(agent, 'sensitivity', 1.0)
        delta = emotion_value * s_i
        
        # При успехе контакта с игроком (инициатива агента)
        agent.relations[player.name]['affinity'] = agent.limit_predicate_value(
            agent.relations[player.name].get('affinity', 0) + delta * 2.0 # Усиленный рост
        )
        agent.relations[player.name]['utility'] = agent.limit_predicate_value(
            agent.relations[player.name].get('utility', 0) + delta * 2.0 # Усиленный рост
        )
        agent.relations[player.name]['trust'] = agent.limit_predicate_value(
            agent.relations[player.name].get('trust', 0) + delta
        )
        agent.relations[player.name]['responsiveness'] = agent.limit_predicate_value(
            agent.relations[player.name].get('responsiveness', 0) + s_i
        )

    @staticmethod
    def _apply_transformation(val, transform_type):
        """Применяет математическую трансформацию к значению."""
        if transform_type == "log":
            return math.log(abs(val) + 1) * (1 if val >= 0 else -1)
        elif transform_type == "exp":
            return math.exp(val / 5.0)
        elif transform_type == "sigmoid":
            return 10 / (1 + math.exp(-val))
        elif transform_type == "periodic":
            return math.sin(val) * 5.0
        return val # linear по умолчанию

    @classmethod
    def priority_score(cls, agent, target_name, metrics):
        """
        Расчет приоритета цели на основе реляционных метрик.
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
        """
        s_i = getattr(agent, 'sensitivity', 1.0)
        s_target = getattr(target_agent, 'sensitivity', 1.0)

        # Инициатор (agent) расстроен отказом
        agent.relations[target_agent.name]['responsiveness'] = agent.limit_predicate_value(
            agent.relations[target_agent.name].get('responsiveness', 0) - 2.0 * s_i # Сильное падение R
        )
        agent.relations[target_agent.name]['affinity'] = agent.limit_predicate_value(
            agent.relations[target_agent.name].get('affinity', 0) - 1.5 * s_i # Существенное падение A
        )
        agent.relations[target_agent.name]['utility'] = agent.limit_predicate_value(
            agent.relations[target_agent.name].get('utility', 0) - 0.5 * s_i # Легкое падение U
        )

        # Целевой агент (target_agent) тоже охладевает, если отказал
        target_agent.relations[agent.name]['responsiveness'] = target_agent.limit_predicate_value(
            target_agent.relations[agent.name].get('responsiveness', 0) - 1.0 * s_target
        )
        target_agent.relations[agent.name]['affinity'] = target_agent.limit_predicate_value(
            target_agent.relations[agent.name].get('affinity', 0) - 0.5 * s_target
        )

    @staticmethod
    def process_interaction_result(agent, target_agent, success):
        """
        Обработать результат взаимодействия и обновить отношения.
        """
        s_i = getattr(agent, "sensitivity", 1.0)
        s_t = getattr(target_agent, "sensitivity", 1.0)
        
        if success:
            # УСПЕХ: Приоритетный рост Affinity и Utility (с двойным коэффициентом)
            delta_primary = 2.0 * s_i
            delta_trust = 1.0 * s_i
            delta_resp = 1.0 * s_i
            
            for a, t_obj, s in [(agent, target_agent, s_i), (target_agent, agent, s_t)]:
                t_name = t_obj.name
                a.relations[t_name]['affinity'] = a.limit_predicate_value(a.relations[t_name].get('affinity', 0) + delta_primary)
                a.relations[t_name]['utility'] = a.limit_predicate_value(a.relations[t_name].get('utility', 0) + delta_primary)
                a.relations[t_name]['trust'] = a.limit_predicate_value(a.relations[t_name].get('trust', 0) + delta_trust)
                a.relations[t_name]['responsiveness'] = a.limit_predicate_value(a.relations[t_name].get('responsiveness', 0) + delta_resp)
        else:
            # НЕУДАЧА: Основной удар по Trust
            delta_trust_fail = 2.0 * s_i
            delta_others_fail = 0.5 * s_i
            delta_resp_fail = 0.5 * s_i # Контакт был, R все равно растет, но слабее
            
            for a, t_obj, s in [(agent, target_agent, s_i), (target_agent, agent, s_t)]:
                t_name = t_obj.name
                a.relations[t_name]['trust'] = a.limit_predicate_value(a.relations[t_name].get('trust', 0) - delta_trust_fail)
                a.relations[t_name]['affinity'] = a.limit_predicate_value(a.relations[t_name].get('affinity', 0) - delta_others_fail)
                a.relations[t_name]['utility'] = a.limit_predicate_value(a.relations[t_name].get('utility', 0) - delta_others_fail)
                a.relations[t_name]['responsiveness'] = a.limit_predicate_value(a.relations[t_name].get('responsiveness', 0) + delta_resp_fail)
