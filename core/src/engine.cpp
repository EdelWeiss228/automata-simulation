#include "engine.hpp"
#include <cmath>
#include <algorithm>

namespace core_engine {

void Engine::influence_emotions() {
    // Предрасчёт основных эмоций агентов. Это только чтение состояния,
    // поэтому выполняется последовательно и одинаково при любом числе потоков.
    std::vector<int> primary_axis(num_agents, -1);
    std::vector<float> weight_primary(num_agents, 0.0f);
    std::vector<float> weight_secondary(num_agents, 0.0f);
    std::vector<bool> active(num_agents, false);

    for (int i = 0; i < num_agents; ++i) {
        int offset_i = i * SimulationState::NUM_AXES;
        float max_val = 0.0f;
        float total_intensity = 0.0f;
        for (int a = 0; a < SimulationState::NUM_AXES; ++a) {
            float val = (float)state.emotions[offset_i + a];
            float abs_val = std::abs(val);
            total_intensity += abs_val;
            if (abs_val > std::abs(max_val)) {
                max_val = val;
                primary_axis[i] = a;
            }
        }
        if (max_val == 0.0f || total_intensity == 0.0f) {
            continue;
        }
        active[i] = true;
        weight_primary[i] = std::abs(max_val) / total_intensity;
        weight_secondary[i] =
            (1.0f - weight_primary[i]) / (SimulationState::NUM_AXES - 1);
    }

    std::vector<int> new_emotions = state.emotions;
    // Снимок отношений на начало шага. Потоки читают только его, поэтому
    // обновление строки i другим потоком не влияет на расчёт.
    const std::vector<int> relations_snapshot = state.relations;

    // Параллелим по получателю влияния j. Поток j пишет только строку j
    // матрицы отношений и локальный буфер эмоций, поэтому гонки нет.
    #pragma omp parallel for schedule(static)
    for (int j = 0; j < num_agents; ++j) {
        float delta_emotions[SimulationState::NUM_AXES] = {0.0f};

        // Влияют только те, с кем уже есть связь. Нулевая строка — это
        // tabula rasa; глобальное усреднение по всем N превращало любую
        // случайную флуктуацию в общий дрейф всего коллектива.
        int active_count = 0;
        for (int i = 0; i < num_agents; ++i) {
            if (i == j) continue;
            int base_ij = (i * num_agents + j) * 3;
            if (relations_snapshot[base_ij + 0] != 0 ||
                relations_snapshot[base_ij + 1] != 0 ||
                relations_snapshot[base_ij + 2] != 0) {
                ++active_count;
            }
        }
        if (active_count == 0) {
            continue;
        }

        for (int i = 0; i < num_agents; ++i) {
            if (i == j || !active[i]) continue;

            int base_ji = (j * num_agents + i) * 3;
            int base_ij = (i * num_agents + j) * 3;
            float u_ij = (float)relations_snapshot[base_ij + 0];
            float a_ij = (float)relations_snapshot[base_ij + 1];
            float t_ij = (float)relations_snapshot[base_ij + 2];
            if (u_ij == 0.0f && a_ij == 0.0f && t_ij == 0.0f) continue;

            float effect_strength = (a_ij + t_ij + u_ij) / 3.0f;
            // Знак связи важен: при положительном отношении агент
            // сближается с эмоцией партнёра, при отрицательном —
            // отталкивается. Раньше abs() превращал любую связь в
            // imitation и усреднял весь коллектив в ноль.
            float common_factor =
                (effect_strength / 100.0f) * state.sensitivities[j] * 0.2f /
                std::max(1, active_count);

            int offset_i = i * SimulationState::NUM_AXES;
            float r_sens = state.sensitivities[j];
            // Разные эмоциональные оси могут писать в одну и ту же
            // реляционную функцию. Суммируем вклад осей локально, иначе
            // последняя ось перезаписывала бы предыдущие.
            float rel_delta[3] = {0.0f, 0.0f, 0.0f};

            for (int a = 0; a < SimulationState::NUM_AXES; ++a) {
                float val_i = (float)state.emotions[offset_i + a];
                float weight = (a == primary_axis[i])
                                   ? weight_primary[i]
                                   : weight_secondary[i];
                float delta = val_i * common_factor * weight;
                delta_emotions[a] += delta;

                int weight_base = (i * SimulationState::NUM_AXES + a) * 3;
                rel_delta[0] += delta * state.emission_weights[weight_base + 0] *
                                r_sens * 10.0f;
                rel_delta[1] += delta * state.emission_weights[weight_base + 1] *
                                r_sens * 10.0f;
                rel_delta[2] += delta * state.emission_weights[weight_base + 2] *
                                r_sens * 10.0f;
            }

            for (int k = 0; k < 3; ++k) {
                state.relations[base_ji + k] = std::max(
                    -100, std::min(100,
                        (int)std::round(relations_snapshot[base_ji + k] +
                                        rel_delta[k])));
            }
        }

        int offset_j = j * SimulationState::NUM_AXES;
        for (int a = 0; a < SimulationState::NUM_AXES; ++a) {
            new_emotions[offset_j + a] = std::max(
                -30, std::min(30,
                    (int)std::round(state.emotions[offset_j + a] + delta_emotions[a])));
        }
    }

    state.emotions.swap(new_emotions);
}

// Вспомогательная функция для трансформаций
float apply_transformation(float val, const std::string& type) {
    if (type == "log") {
        return std::log(std::abs(val) + 1.0f) * (val >= 0 ? 1.0f : -1.0f);
    } else if (type == "exp") {
        return std::exp(val / 5.0f);
    } else if (type == "sigmoid") {
        return 10.0f / (1.0f + std::exp(-val));
    } else if (type == "periodic") {
        return std::sin(val) * 5.0f;
    }
    return val; // linear
}

float Engine::calculate_priority_score(int from_idx, int to_idx) {
    int arch_idx = state.agent_archetypes[from_idx];
    const auto& conf = state.archetype_configs[arch_idx];
    
    int base_ij = (from_idx * num_agents + to_idx) * 3;
    float u = (float)state.relations[base_ij + 0];
    float a = (float)state.relations[base_ij + 1];
    float t = (float)state.relations[base_ij + 2];
    
    float a_score = apply_transformation(a / 10.0f, conf.scoring_affinity);
    float u_score = apply_transformation(u / 10.0f, conf.scoring_utility);
    float t_score = apply_transformation(t / 10.0f, conf.scoring_trust);

    return a_score + u_score + t_score;
}

bool Engine::should_refuse(int agent_idx, int target_idx) {
    // Отказ определяет цель, а не инициатор. Её базовый шанс корректируется
    // текущим отношением к инициатору: плохое отношение повышает вероятность,
    // хорошее — понижает.
    int arch_idx = state.agent_archetypes[target_idx];
    float base_factor = state.archetype_configs[arch_idx].refusal_chance;

    int base_ta = (target_idx * num_agents + agent_idx) * 3;
    float mean = (state.relations[base_ta + 0] +
                  state.relations[base_ta + 1] +
                  state.relations[base_ta + 2]) / 3.0f;
    float relation_factor = 2.0f / (1.0f + std::exp(mean / 25.0f));

    float final_prob = base_factor * relation_factor;
    final_prob = std::max(0.01f, std::min(0.95f, final_prob));

    return random_unit() < final_prob;
}

int Engine::choose_target(int agent_idx) {
    // Никакой классификации mandatory/optional/avoid: выбор идёт softmax
    // по всем доступным кандидатам.
    std::vector<int> candidates;
    candidates.reserve(num_agents - 1);
    for (int j = 0; j < num_agents; ++j) {
        if (agent_idx != j) candidates.push_back(j);
    }

    if (candidates.empty()) return -1;
    if (candidates.size() == 1) return candidates[0];

    int arch_idx = state.agent_archetypes[agent_idx];
    float temp = std::max(0.01f, state.archetype_configs[arch_idx].temperature);

    std::vector<float> scores;
    scores.reserve(candidates.size());
    float max_score = -1e9f;
    for (int cand : candidates) {
        float s = calculate_priority_score(agent_idx, cand);
        scores.push_back(s);
        if (s > max_score) max_score = s;
    }

    float sum_exp = 0.0f;
    std::vector<float> exp_scores;
    exp_scores.reserve(scores.size());
    for (float s : scores) {
        float e = std::exp((s - max_score) / temp);
        exp_scores.push_back(e);
        sum_exp += e;
    }

    float r = random_unit() * sum_exp;
    float current_sum = 0.0f;
    for (size_t i = 0; i < exp_scores.size(); ++i) {
        current_sum += exp_scores[i];
        if (r <= current_sum) return candidates[i];
    }

    return candidates.back();
}

void Engine::process_interaction(int from_idx, int to_idx, int sigma) {
    if (sigma == 0) {
        process_refusal(from_idx, to_idx);
        return;
    }

    float s_i = state.sensitivities[from_idx];
    float s_t = state.sensitivities[to_idx];

    auto primary_emotion_value = [&](int idx) {
        int primary_axis = 0;
        int max_val = -1;
        for (int a = 0; a < SimulationState::NUM_AXES; ++a) {
            int v = std::abs(state.emotions[idx * SimulationState::NUM_AXES + a]);
            if (v > max_val) {
                max_val = v;
                primary_axis = a;
            }
        }
        return state.emotions[idx * SimulationState::NUM_AXES + primary_axis];
    };

    int e_i = primary_emotion_value(from_idx);
    int e_t = primary_emotion_value(to_idx);

    // По тексту положительный исход масштабируется эмоциональным
    // состоянием партнёра: для i -> j это E_j, для j -> i это E_i.
    auto multiplier_for = [&](int partner_e) {
        if (sigma == 1) return (partner_e >= 0) ? 2.0f : 0.5f;
        if (sigma == -1) return (partner_e >= 0) ? 0.5f : 2.0f;
        return 1.0f;
    };

    auto apply_side = [&](int actor, int other, float sensitivity, float multiplier) {
        float base_affinity = 15.0f * multiplier;
        float base_trust = 10.0f * multiplier;
        if (sigma == -1) {
            base_trust = -20.0f * multiplier;
            base_affinity = -5.0f * multiplier;
        }

        int base = (actor * num_agents + other) * 3;
        state.relations[base + 0] = std::max(-100, std::min(100,
            (int)(state.relations[base + 0] + base_affinity * sensitivity)));
        state.relations[base + 1] = std::max(-100, std::min(100,
            (int)(state.relations[base + 1] + base_affinity * sensitivity)));
        state.relations[base + 2] = std::max(-100, std::min(100,
            (int)(state.relations[base + 2] + base_trust * sensitivity)));
    };

    apply_side(from_idx, to_idx, s_i, multiplier_for(e_t));
    apply_side(to_idx, from_idx, s_t, multiplier_for(e_i));
}

void Engine::process_refusal(int from_idx, int to_idx) {
    // По тексту отказ ухудшает все три функции у обоих участников.
    // Главная ось архетипа получает полный вес, остальные — половинный.
    const int actors[2] = {from_idx, to_idx};
    const int others[2] = {to_idx, from_idx};

    for (int side = 0; side < 2; ++side) {
        int actor = actors[side];
        int other = others[side];
        float sensitivity = state.sensitivities[actor];
        float penalty = 20.0f * sensitivity;

        int arch_idx = state.agent_archetypes[actor];
        int vuln = state.archetype_configs[arch_idx].refusal_vulnerability;
        if (vuln < 0 || vuln > 2) vuln = 0;

        int base = (actor * num_agents + other) * 3;
        for (int k = 0; k < 3; ++k) {
            float impact = (k == vuln) ? 1.0f : 0.5f;
            state.relations[base + k] = std::max(
                -100,
                std::min(100,
                    (int)(state.relations[base + k] - penalty * impact)));
        }
    }
}

void Engine::apply_relation_decay() {
    #pragma omp parallel for
    for (int i = 0; i < num_agents; ++i) {
        int arch_idx = state.agent_archetypes[i];
        float decay_rate = state.archetype_configs[arch_idx].decay_rate;
        float s_i = state.sensitivities[i];
        float step = decay_rate * s_i;

        for (int j = 0; j < num_agents; ++j) {
            if (i == j) continue;
            int base = (i * num_agents + j) * 3;
            
            // A, T, U decay
            for (int k = 0; k < 3; ++k) {
                int val = state.relations[base + k];
                if (val > 0) state.relations[base + k] = std::max(0, (int)(val - step * 0.5f));
                else if (val < 0) state.relations[base + k] = std::min(0, (int)(val + step)); // Режим прощения 1.0x
            }
        }
    }
}

void Engine::react_to_relations() {
    #pragma omp parallel for
    for (int i = 0; i < num_agents; ++i) {
        float avg_u = 0.0f;
        float avg_a = 0.0f;
        float avg_t = 0.0f;
        int count = 0;

        for (int j = 0; j < num_agents; ++j) {
            if (i == j) continue;
            int base = (i * num_agents + j) * 3;
            int u = state.relations[base + 0];
            int a = state.relations[base + 1];
            int t = state.relations[base + 2];
            // Среднее только по реально существующим связям: нули — это
            // отсутствие отношения, а не «нейтральное отношение».
            if (u == 0 && a == 0 && t == 0) continue;
            avg_u += (float)u;
            avg_a += (float)a;
            avg_t += (float)t;
            count++;
        }
        
        if (count > 0) {
            avg_u /= count;
            avg_a /= count;
            avg_t /= count;
        } else {
            continue;
        }

        float effect = (avg_a + avg_t + avg_u) / 3.0f; // Scale is now (100+100+100)/3 = 100 max.
        int arch_idx = state.agent_archetypes[i];
        const auto& coeffs = state.archetype_configs[arch_idx].emotion_coefficients;
        float s_i = state.sensitivities[i];

        for (int axis = 0; axis < SimulationState::NUM_AXES; ++axis) {
            if (axis < (int)coeffs.size()) {
                // effect в [-100,100], coeff ~10: деление на 1000 даёт
                // не больше ~1 единицы эмоции за такт, как в Python-версии.
                float delta = (effect * coeffs[axis] * 0.005f) * s_i;
                state.emotions[i * SimulationState::NUM_AXES + axis] = 
                    std::max(-30, std::min(30, (int)(state.emotions[i * SimulationState::NUM_AXES + axis] + delta)));
            }
        }
    }
}

void Engine::react_to_emotions() {
    #pragma omp parallel for
    for (int i = 0; i < num_agents; ++i) {
        float s_i = state.sensitivities[i];
        // Эмоция меняет только уже существующую связь. Коэффициент снижен
        // с 0.3 до 0.03: при x10-шкале прежний давал до ±9 за такт на каждую
        // пару и за несколько тактов загонял всю матрицу в ±100.
        float k_factor = 0.05f;

        for (int axis = 0; axis < SimulationState::NUM_AXES; ++axis) {
            float val = (float)state.emotions[i * SimulationState::NUM_AXES + axis];
            if (std::abs(val) < 1.0f) continue;

            for (int j = 0; j < num_agents; ++j) {
                if (i == j) continue;
                int base = (i * num_agents + j) * 3;
                if (state.relations[base + 0] == 0 &&
                    state.relations[base + 1] == 0 &&
                    state.relations[base + 2] == 0) {
                    continue;
                }
                
                // 0: SADNESS_JOY -> Affinity
                if (axis == 0) {
                    state.relations[base + 1] = std::max(-100, std::min(100, (int)(state.relations[base + 1] + val * k_factor * s_i)));
                }
                // 1: FEAR_CALM -> Trust
                else if (axis == 1) {
                    state.relations[base + 2] = std::max(-100, std::min(100, (int)(state.relations[base + 2] + val * k_factor * s_i)));
                }
                // 2: ANGER_HUMILITY -> Trust (2.0x weight for Anger)
                else if (axis == 2) {
                    float factor = (val < 0) ? 2.0f : 1.0f;
                    state.relations[base + 2] = std::max(-100, std::min(100, (int)(state.relations[base + 2] + val * k_factor * factor * s_i)));
                }
                // 3: DISGUST_ACCEPTANCE -> Utility & Affinity
                else if (axis == 3) {
                    state.relations[base + 1] = std::max(-100, std::min(100, (int)(state.relations[base + 1] + val * k_factor * s_i)));
                    state.relations[base + 0] = std::max(-100, std::min(100, (int)(state.relations[base + 0] + val * k_factor * s_i)));
                }
                // 4: HABIT_SURPRISE -> Utility
                else if (axis == 4) {
                    state.relations[base + 0] = std::max(-100, std::min(100, (int)(state.relations[base + 0] + val * k_factor * s_i)));
                }
                // 5: SHAME_CONFIDENCE -> Trust
                else if (axis == 5) {
                    state.relations[base + 2] = std::max(-100, std::min(100, (int)(state.relations[base + 2] + val * k_factor * s_i)));
                }
                // 6: ALIENATION_OPENNESS -> Trust & Affinity
                else if (axis == 6) {
                    state.relations[base + 2] = std::max(-100, std::min(100, (int)(state.relations[base + 2] + val * k_factor * s_i)));
                    state.relations[base + 1] = std::max(-100, std::min(100, (int)(state.relations[base + 1] + val * k_factor * s_i)));
                }
            }
        }
    }
}

void Engine::apply_emotion_decay() {
    #pragma omp parallel for
    for (int i = 0; i < num_agents; ++i) {
        int arch_idx = state.agent_archetypes[i];
        float decay_rate = state.archetype_configs[arch_idx].emotion_decay;
        float s_i = state.sensitivities[i];
        float step = decay_rate * s_i;

        for (int axis = 0; axis < SimulationState::NUM_AXES; ++axis) {
            int& val = state.emotions[i * SimulationState::NUM_AXES + axis];
            if (val > 0) val = std::max(0, (int)(val - step));
            else if (val < 0) val = std::min(0, (int)(val + step));
        }
    }
}

void Engine::perform_daily_cycle(int interactions_per_day) {
    last_day_interactions.clear();
    
// Затухание отношений
    apply_relation_decay();
    
// Реакция на текущие отношения
    react_to_relations();
    
// 1 Затухание эмоций
    apply_emotion_decay();
    
// 2 Влияние эмоций на отношения
    react_to_emotions();
    
// Групповое влияние
    influence_emotions();
    
// Взаимодействия
    for (int iter = 0; iter < interactions_per_day; ++iter) {
        for (int i = 0; i < num_agents; ++i) {
            int target = choose_target(i);
            if (target != -1) {
                if (should_refuse(i, target)) {
                    process_refusal(i, target);
                    last_day_interactions.push_back({i, target, 0}); // 0: refusal
                } else {
                    int sigma = (random_percent() < 50) ? 1 : -1;
                    process_interaction(i, target, sigma);
                    last_day_interactions.push_back({i, target, sigma}); // 1: success, -1: fail
                }
            }
            // Нет цели — это отсутствие контакта, а не отказ. Штрафовать
            // всех агентов за это нельзя.
        }
    }
}

float Engine::random_unit() {
    // 24 старших бита mt19937 -> [0, 1), без зависимости от STL-распределений.
    return (float)(rng() >> 8) * (1.0f / 16777216.0f);
}

int Engine::random_percent() {
    return (int)(rng() % 100);
}

void Engine::seed(int s) {
    rng.seed((uint32_t)s);
}

} // namespace core_engine
