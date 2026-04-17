#include "engine.hpp"
#include <cmath>
#include <algorithm>

namespace core_engine {

void Engine::influence_emotions() {
    // Временный буфер для изменений, чтобы расчет был атомарным для всего шага
    std::vector<float> delta_emotions(state.emotions.size(), 0.0f);

    #pragma omp parallel for
    for (int i = 0; i < num_agents; ++i) {
        // 1. Находим основную эмоцию агента i
        int primary_axis = -1;
        float max_val = 0.0f;
        float total_intensity = 0.0f;
        
        int offset_i = i * SimulationState::NUM_AXES;
        for (int a = 0; a < SimulationState::NUM_AXES; ++a) {
            float val = (float)state.emotions[offset_i + a];
            float abs_val = std::abs(val);
            total_intensity += abs_val;
            if (abs_val > std::abs(max_val)) {
                max_val = val;
                primary_axis = a;
            }
        }

        if (max_val == 0.0f || total_intensity == 0.0f) continue;

        // 2. Рассчитываем веса
        float weight_primary = std::abs(max_val) / total_intensity;
        float weight_secondary = (1.0f - weight_primary) / (SimulationState::NUM_AXES - 1);

        // 3. Влияем на каждого агента j
        for (int j = 0; j < num_agents; ++j) {
            if (i == j) continue;

            int base_ji = (j * num_agents + i) * 3;
            int u_ji = state.relations[base_ji + 0];
            int a_ji = state.relations[base_ji + 1];
            int t_ji = state.relations[base_ji + 2];

            int arch_j = state.agent_archetypes[j];
            int vuln_j = state.archetype_configs[arch_j].refusal_vulnerability;
            int vuln_val = (vuln_j == 0) ? u_ji : (vuln_j == 1 ? a_ji : t_ji);

            bool avoid = false;
            if (vuln_val < -50) avoid = true;
            else if (t_ji >= 50 && a_ji >= 50) {} 
            else if (t_ji >= 0 || a_ji >= 0) {} 
            else avoid = true;

            if (avoid) continue;

            int base_ij = (i * num_agents + j) * 3;
            float u_ij = (float)state.relations[base_ij + 0];
            float a_ij = (float)state.relations[base_ij + 1];
            float t_ij = (float)state.relations[base_ij + 2];
            
            float effect_strength = (a_ij + t_ij + u_ij) / 3.0f;
            // Уменьшаем common_factor, т.к. значения выросли в 10 раз
            float common_factor = std::abs(effect_strength) * state.sensitivities[j] * 0.001f;

            int offset_j = j * SimulationState::NUM_AXES;
            for (int a = 0; a < SimulationState::NUM_AXES; ++a) {
                float val_i = (float)state.emotions[offset_i + a];
                float weight = (a == primary_axis) ? weight_primary : weight_secondary;
                float delta = val_i * common_factor * weight;
                delta_emotions[offset_j + a] += delta;

                int base_ji_rel = (j * num_agents + i) * 3;
                int weight_base = (i * SimulationState::NUM_AXES + a) * 3;
                
                float r_sens = state.sensitivities[j];
                // delta здесь - плавающее изменение, прибавляем к целому
                state.relations[base_ji_rel + 0] = std::max(-100, std::min(100, (int)(state.relations[base_ji_rel + 0] + delta * state.emission_weights[weight_base + 0] * r_sens * 10.0f)));
                state.relations[base_ji_rel + 1] = std::max(-100, std::min(100, (int)(state.relations[base_ji_rel + 1] + delta * state.emission_weights[weight_base + 1] * r_sens * 10.0f)));
                state.relations[base_ji_rel + 2] = std::max(-100, std::min(100, (int)(state.relations[base_ji_rel + 2] + delta * state.emission_weights[weight_base + 2] * r_sens * 10.0f)));
            }

        }
    }

    for (size_t k = 0; k < state.emotions.size(); ++k) {
        state.emotions[k] = std::max(-30, std::min(30, (int)(state.emotions[k] + delta_emotions[k])));
    }
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
    
    float alpha = 1.5f;
    return a_score + u_score + alpha * t_score;
}

bool Engine::should_refuse(int agent_idx, int target_idx) {
    int arch_idx = state.agent_archetypes[target_idx];
    float base_factor = state.archetype_configs[arch_idx].refusal_chance;
    float final_prob = std::min(0.95f, base_factor);
    
    return ((float)rand() / (float)RAND_MAX) < final_prob;
}

int Engine::choose_target(int agent_idx) {
    std::vector<int> mandatory;
    std::vector<int> optional;
    
    for (int j = 0; j < num_agents; ++j) {
        if (agent_idx == j) continue;
        
        int base_ij = (agent_idx * num_agents + j) * 3;
        int u = state.relations[base_ij + 0];
        int a = state.relations[base_ij + 1];
        int t = state.relations[base_ij + 2];
        
        int arch_idx = state.agent_archetypes[agent_idx];
        int vuln_i = state.archetype_configs[arch_idx].refusal_vulnerability;
        int vuln_val = (vuln_i == 0) ? u : (vuln_i == 1 ? a : t);
        
        if (vuln_val < -50) continue; // avoid
        if (t >= 50 && a >= 50) mandatory.push_back(j);
        else if (t >= 0 || a >= 0) optional.push_back(j);
    }
    
    const auto& candidates = mandatory.empty() ? optional : mandatory;
    if (candidates.empty()) return -1;
    if (candidates.size() == 1) return candidates[0];
    
    int arch_idx = state.agent_archetypes[agent_idx];
    float temp = std::max(0.01f, state.archetype_configs[arch_idx].temperature);
    
    std::vector<float> scores;
    float max_score = -1e9f;
    for (int cand : candidates) {
        float s = calculate_priority_score(agent_idx, cand);
        scores.push_back(s);
        if (s > max_score) max_score = s;
    }
    
    float sum_exp = 0.0f;
    std::vector<float> exp_scores;
    for (float s : scores) {
        float e = std::exp((s - max_score) / temp);
        exp_scores.push_back(e);
        sum_exp += e;
    }
    
    float r = ((float)rand() / (float)RAND_MAX) * sum_exp;
    float current_sum = 0.0f;
    for (size_t i = 0; i < exp_scores.size(); ++i) {
        current_sum += exp_scores[i];
        if (r <= current_sum) return candidates[i];
    }
    
    return candidates.back();
}

void Engine::process_interaction(int from_idx, int to_idx, int sigma) {
    float s_i = state.sensitivities[from_idx];
    float s_t = state.sensitivities[to_idx];
    
    // 1. Находим первичную эмоцию инициатора
    int primary_axis = 0;
    int max_val = -1;
    for (int a = 0; a < SimulationState::NUM_AXES; ++a) {
        int v = std::abs(state.emotions[from_idx * SimulationState::NUM_AXES + a]);
        if (v > max_val) {
            max_val = v;
            primary_axis = a;
        }
    }
    int e_val = state.emotions[from_idx * SimulationState::NUM_AXES + primary_axis];

    // 2. Рассчитываем множитель (Sigma Model v6.2)
    float multiplier = 1.0f;
    if (sigma == 1) { // Успех
        multiplier = (e_val >= 0) ? 2.0f : 0.5f;
    } else if (sigma == -1) { // Неудача
        multiplier = (e_val >= 0) ? 0.5f : 2.0f;
    }

    // 3. Базовые дельты (scale x10)
    float base_affinity = 15.0f * multiplier;
    float base_trust = 10.0f * multiplier;
    
    if (sigma == -1) {
        base_trust = -20.0f * multiplier;
        base_affinity = -5.0f * multiplier;
    }

    // Применяем к инициатору (i -> target)
    int base_it = (from_idx * num_agents + to_idx) * 3;
    state.relations[base_it + 0] = std::max(-100, std::min(100, (int)(state.relations[base_it + 0] + base_affinity * s_i)));
    state.relations[base_it + 1] = std::max(-100, std::min(100, (int)(state.relations[base_it + 1] + base_affinity * s_i)));
    state.relations[base_it + 2] = std::max(-100, std::min(100, (int)(state.relations[base_it + 2] + base_trust * s_i)));

    // Применяем к цели (target -> i)
    int base_ti = (to_idx * num_agents + from_idx) * 3;
    state.relations[base_ti + 0] = std::max(-100, std::min(100, (int)(state.relations[base_ti + 0] + base_affinity * s_t)));
    state.relations[base_ti + 1] = std::max(-100, std::min(100, (int)(state.relations[base_ti + 1] + base_affinity * s_t)));
    state.relations[base_ti + 2] = std::max(-100, std::min(100, (int)(state.relations[base_ti + 2] + base_trust * s_t)));
}

void Engine::process_refusal(int from_idx, int to_idx) {
    float s_i = state.sensitivities[from_idx];
    
    // Штраф получает только инициатор (from_idx)
    int arch_idx = state.agent_archetypes[from_idx];
    int vuln_i = state.archetype_configs[arch_idx].refusal_vulnerability;
    int base_it = (from_idx * num_agents + to_idx) * 3;
    float penalty = 20.0f * s_i;

    if (vuln_i == 0) state.relations[base_it + 0] = std::max(-100, std::min(100, (int)(state.relations[base_it + 0] - penalty)));
    else if (vuln_i == 1) state.relations[base_it + 1] = std::max(-100, std::min(100, (int)(state.relations[base_it + 1] - penalty)));
    else state.relations[base_it + 2] = std::max(-100, std::min(100, (int)(state.relations[base_it + 2] - penalty)));

    // Тот, кто отказал (to_idx), не меняет своего мнения об инициаторе.
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
            avg_u += (float)state.relations[base + 0];
            avg_a += (float)state.relations[base + 1];
            avg_t += (float)state.relations[base + 2];
            count++;
        }
        
        if (count > 0) {
            avg_u /= count;
            avg_a /= count;
            avg_t /= count;
        }

        float effect = (avg_a + avg_t + avg_u) / 3.0f; // Scale is now (100+100+100)/3 = 100 max.
        int arch_idx = state.agent_archetypes[i];
        const auto& coeffs = state.archetype_configs[arch_idx].emotion_coefficients;
        float s_i = state.sensitivities[i];

        for (int axis = 0; axis < SimulationState::NUM_AXES; ++axis) {
            if (axis < (int)coeffs.size()) {
                float delta = (effect * coeffs[axis] * 0.05f) * s_i;
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
        float k_factor = 0.3f;

        for (int axis = 0; axis < SimulationState::NUM_AXES; ++axis) {
            float val = (float)state.emotions[i * SimulationState::NUM_AXES + axis];
            if (std::abs(val) < 1.0f) continue;

            for (int j = 0; j < num_agents; ++j) {
                if (i == j) continue;
                int base = (i * num_agents + j) * 3;
                
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
    
    // 0. Затухание отношений
    apply_relation_decay();
    
    // 1. Реакция на текущие отношения
    react_to_relations();
    
    // 1.1 Затухание эмоций
    apply_emotion_decay();
    
    // 1.2 Влияние эмоций на отношения
    react_to_emotions();
    
    // 2. Групповое влияние
    influence_emotions();
    
    // 3. Взаимодействия
    for (int iter = 0; iter < interactions_per_day; ++iter) {
        for (int i = 0; i < num_agents; ++i) {
            int target = choose_target(i);
            if (target != -1) {
                if (should_refuse(i, target)) {
                    process_refusal(i, target);
                    last_day_interactions.push_back({i, target, 0}); // 0: refusal
                } else {
                    int sigma = ((rand() % 100) < 50) ? 1 : -1;
                    process_interaction(i, target, sigma);
                    last_day_interactions.push_back({i, target, sigma}); // 1: success, -1: fail
                }
            } else {
                // Decay for all when no target chosen (as in Collective.py)
                for (int j = 0; j < num_agents; ++j) {
                    if (i == j) continue;
                    process_refusal(i, j);
                    last_day_interactions.push_back({i, j, 0});
                }
            }
        }
    }
}

void Engine::seed(int s) {
    srand(s);
}

} // namespace core_engine
