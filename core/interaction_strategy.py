import math
import random
from enum import IntEnum


class Outcome(IntEnum):
    """Дискретный исход взаимодействия (Sigma-модель)."""
    FAILURE = -1
    REFUSAL = 0
    SUCCESS = 1


def normalize_outcome(value) -> Outcome:
    """Приводит bool/str/int/Outcome к Outcome.

    Нужен на границах Python/C++, где исторически встречались и строки,
    и bool, и числа.
    """
    if isinstance(value, Outcome):
        return value
    if isinstance(value, bool):
        return Outcome.SUCCESS if value else Outcome.FAILURE
    if isinstance(value, str):
        key = value.strip().lower()
        if key in ("success", "ok", "1", "+1"):
            return Outcome.SUCCESS
        if key in ("fail", "failure", "error", "-1"):
            return Outcome.FAILURE
        if key in ("refusal", "refuse", "0"):
            return Outcome.REFUSAL
    if isinstance(value, (int, float)):
        if value > 0:
            return Outcome.SUCCESS
        if value < 0:
            return Outcome.FAILURE
        return Outcome.REFUSAL
    raise ValueError(f"Unknown interaction outcome: {value!r}")


class InteractionStrategy:
    """
    Класс, инкапсулирующий стратегию выбора цели и обработки результатов
    взаимодействия. Вынесен из Collective для декомпозиции 'God Object'.
    """

    @staticmethod
    def calculate_refusal_chance(target_agent, initiator_agent, context=None) -> float:
        """Вероятность отказа цели от контакта с инициатором.

        Базовая вероятность берётся у цели. Текущее отношение цели к
        инициатору сдвигает её: плохие отношения повышают шанс отказа,
        хорошие — понижают. Контекст тоже учитывается.
        """
        base_factor = float(getattr(target_agent.archetype, "refusal_chance", 0.3))

        metrics = target_agent.relations.get(initiator_agent.id, {}) or {}
        u = float(metrics.get("utility", 0))
        a = float(metrics.get("affinity", 0))
        t = float(metrics.get("trust", 0))
        relation_mean = (u + a + t) / 3.0

        # При нейтральных отношениях factor == 1.0.
        # При -100 -> почти 2.0, при +100 -> почти 0.0.
        relation_factor = 2.0 / (1.0 + math.exp(relation_mean / 25.0))

        context_factor = 1.0
        if context:
            adaptability = getattr(target_agent, "context_adaptability", {}) or {}
            context_factor = 1.0 / max(0.25, float(adaptability.get(context, 1.0)))

        chance = base_factor * relation_factor * context_factor
        return max(0.01, min(0.95, chance))

    @staticmethod
    def handle_player_interaction(agent, player):
        """
        Обрабатывает инициативу агента по отношению к игроку.
        """
        emotion_name, _, emotion_value = agent.get_primary_emotion()
        # Игрок отвечает на эмоцию
        player.respond_to_agent(agent.id, emotion_name, emotion_value)

        # Агент обновляет отношение к игроку (delta теперь в x10)
        s_i = getattr(agent, 'sensitivity', 1.0)
        delta_scaled = emotion_value * s_i  # emotion_value уже до 30

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
        val_orig = val / 10.0  # Ожидаем логарифм/экспоненту в шкале 0..10
        if transform_type == "log":
            return math.log(abs(val_orig) + 1) * (1 if val_orig >= 0 else -1)
        elif transform_type == "exp":
            return math.exp(val_orig / 5.0)
        elif transform_type == "sigmoid":
            return 10 / (1 + math.exp(-val_orig))
        elif transform_type == "periodic":
            return math.sin(val_orig) * 5.0
        return val_orig  # linear по умолчанию

    @classmethod
    def priority_score(cls, agent, target_name, metrics, context=None):
        """
        Расчет приоритета цели на основе реляционных метрик.
        Если отношений еще нет (первокурсник), возвращается 0.5 для равномерного
        Softmax-распределения.
        """
        if not metrics:
            return 0.5

        config = getattr(agent.archetype, 'scoring_config', {})

        affinity = metrics.get('affinity', 0)
        utility = metrics.get('utility', 0)
        trust = metrics.get('trust', 0)

        # Применяем трансформации
        a_score = cls._apply_transformation(affinity, config.get("affinity", "linear"))
        u_score = cls._apply_transformation(utility, config.get("utility", "linear"))
        t_score = cls._apply_transformation(trust, config.get("trust", "linear"))

        base_score = a_score + u_score + t_score

        # Влияние Среды: умножаем итоговый скор на коэффициент общительности
        if context and hasattr(agent, 'context_adaptability'):
            context_multiplier = agent.context_adaptability.get(context, 1.0)
            base_score *= context_multiplier

        return base_score

    @staticmethod
    def categorize_relationships(agent):
        """Классифицировать отношения агента (только для статистики).

        В управлении взаимодействием эта классификация больше не участвует.
        """
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
    def choose_target(cls, agent, candidates, context=None):
        """Выбрать цель взаимодействия на основе Softmax-распределения.

        Кандидаты — все доступные цели; никаких mandatory/optional/avoid
        в управлении. `candidates` может быть списком (name, metrics) или
        словарём name -> metrics.
        """
        if isinstance(candidates, dict):
            candidates = list(candidates.items())
        else:
            candidates = list(candidates)

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        temp = getattr(agent.archetype, 'temperature', 1.0)
        temp = max(0.01, temp)

        scores = []
        for target_name, metrics in candidates:
            score = cls.priority_score(agent, target_name, metrics, context)
            scores.append(score)

        max_score = max(scores)
        exp_scores = [math.exp((s - max_score) / temp) for s in scores]

        chosen_idx = random.choices(range(len(candidates)), weights=exp_scores, k=1)[0]
        return candidates[chosen_idx]

    @staticmethod
    def _ensure_relation(actor, other_id):
        if other_id not in actor.relations:
            # Отсутствие связи — это tabula rasa, а не случайная связь.
            # C++-ядро для новой пары тоже хранит нули.
            actor.relations[other_id] = {
                'utility': 0,
                'affinity': 0,
                'trust': 0,
            }

    @staticmethod
    def apply_emotional_reaction(actor, partner, outcome, context=None):
        """Обновить эмоции актора по исходу контакта и эмоции партнёра.

        Успех и неудача сближают эмоциональные профили (неудача — с меньшей
        дельтой), отказ — разводит. Это соответствует тексту: эмоция
        зависит от sigma и E_j, а отказ является единственным разрывающим
        исходом.
        """
        outcome = normalize_outcome(outcome)
        if outcome == Outcome.SUCCESS:
            strength = 1.0
        elif outcome == Outcome.FAILURE:
            strength = 0.5
        else:
            strength = -1.0

        sensitivity = float(getattr(actor, "sensitivity", 1.0))
        adaptability = getattr(actor, "context_adaptability", {}) or {}
        context_mod = adaptability.get(context, 1.0) if context else 1.0

        partner_emotions = partner.get_emotions()
        own_emotions = actor.get_emotions()
        for axis_name, partner_value in partner_emotions.items():
            own_value = own_emotions.get(axis_name, 0)
            delta = (strength * sensitivity * context_mod * 0.15 *
                     (float(partner_value) - float(own_value)))
            actor.automaton.adjust_emotion(axis_name, delta)

    @staticmethod
    def process_refusal(initiator, target_agent, context=None):
        """Обработать отказ.

        По тексту отказавший и инициатор оба ухудшают все три функции друг
        к другу. Главная ось архетипа получает больший вес, остальные —
        меньший. Контекст масштабирует силу реакции.
        """
        for actor, other in ((initiator, target_agent), (target_agent, initiator)):
            InteractionStrategy._ensure_relation(actor, other.id)

            impact = getattr(actor.archetype, 'refusal_impact', None)
            if not impact:
                impact = {'utility': 0.5, 'affinity': 0.5, 'trust': 0.5}

            adaptability = getattr(actor, 'context_adaptability', {}) or {}
            c_mod = adaptability.get(context, 1.0) if context else 1.0
            penalty = 20.0 * float(getattr(actor, 'sensitivity', 1.0)) * c_mod

            rel = actor.relations[other.id]
            rel['utility'] = actor.limit_predicate_value(
                rel.get('utility', 0) - penalty * float(impact.get('utility', 0.5))
            )
            rel['affinity'] = actor.limit_predicate_value(
                rel.get('affinity', 0) - penalty * float(impact.get('affinity', 0.5))
            )
            rel['trust'] = actor.limit_predicate_value(
                rel.get('trust', 0) - penalty * float(impact.get('trust', 0.5))
            )

    @staticmethod
    def process_interaction_result(agent, target_agent, sigma, context=None):
        """Обработать результат взаимодействия и обновить отношения.

        sigma принимает Outcome, int, bool или исторические строки.
        """
        outcome = normalize_outcome(sigma)
        if outcome == Outcome.REFUSAL:
            InteractionStrategy.process_refusal(agent, target_agent, context)
            InteractionStrategy.apply_emotional_reaction(
                agent, target_agent, outcome, context)
            InteractionStrategy.apply_emotional_reaction(
                target_agent, agent, outcome, context)
            return outcome

        s_i = float(getattr(agent, "sensitivity", 1.0))
        s_t = float(getattr(target_agent, "sensitivity", 1.0))

        # Влияние среды: динамический мультипликатор получения опыта.
        c_i = agent.context_adaptability.get(context, 1.0) if hasattr(agent, 'context_adaptability') and context else 1.0
        c_t = target_agent.context_adaptability.get(context, 1.0) if hasattr(target_agent, 'context_adaptability') and context else 1.0

        for a, t_obj, s, c_mod in ((agent, target_agent, s_i, c_i), (target_agent, agent, s_t, c_t)):
            t_id = t_obj.id
            InteractionStrategy._ensure_relation(a, t_id)

            # По тексту эмоциональное состояние обновляется не только
            # отношениями, но и исходом контакта sigma и эмоцией партнёра E_j.
            InteractionStrategy.apply_emotional_reaction(a, t_obj, outcome, context)

            # По тексту исход контакта масштабируется эмоциональным
            # состоянием партнёра E_j, то есть t_obj. Успех и неудача
            # повышают U/T/A, но неудача — с половинной дельтой; только
            # отказ понижает отношения.
            _, _, partner_e = t_obj.get_primary_emotion()
            multiplier = 2.0 if partner_e >= 0 else 0.5
            strength = 1.0 if outcome == Outcome.SUCCESS else 0.5

            base_affinity = 15 * multiplier * strength
            base_trust = 10 * multiplier * strength

            a.relations[t_id]['affinity'] = a.limit_predicate_value(
                a.relations[t_id].get('affinity', 0) + int(base_affinity * s * c_mod)
            )
            # В текущей модели utility исторически использует ту же базовую
            # дельту, что и affinity.
            a.relations[t_id]['utility'] = a.limit_predicate_value(
                a.relations[t_id].get('utility', 0) + int(base_affinity * s * c_mod)
            )
            a.relations[t_id]['trust'] = a.limit_predicate_value(
                a.relations[t_id].get('trust', 0) + int(base_trust * s * c_mod)
            )

        return outcome
