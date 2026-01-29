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
            float val = state.emotions[offset_i + a];
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

            // Проверяем классификацию отношений j к i (избегание)
            // Важно: берем отношение j -> i
            int base_ji = (j * num_agents + i) * 4;
            float u_ji = state.relations[base_ji + 0];
            float a_ji = state.relations[base_ji + 1];
            float t_ji = state.relations[base_ji + 2];
            float r_ji = state.relations[base_ji + 3];

            bool avoid = false;
            if (r_ji < -5.0f) avoid = true;
            else if (t_ji >= 5.0f && a_ji >= 5.0f && r_ji >= 0.0f) {} // mandatory
            else if (t_ji >= 0.0f || a_ji >= 0.0f || r_ji > -5.0f) {} // optional
            else avoid = true;

            if (avoid) continue;

            // Рассчитываем силу влияния (i -> j)
            // Отношение i -> j определяет, насколько ИЗ i идет влияние
            int base_ij = (i * num_agents + j) * 4;
            float u_ij = state.relations[base_ij + 0];
            float a_ij = state.relations[base_ij + 1];
            float t_ij = state.relations[base_ij + 2];
            
            float effect_strength = (a_ij + t_ij + u_ij) / 3.0f;
            float common_factor = effect_strength * state.sensitivities[j] * 0.01f; // Дальнейшее демпфирование: 0.1 * 0.1 = 0.01

            // Применяем изменения к j
            int offset_j = j * SimulationState::NUM_AXES;
            for (int a = 0; a < SimulationState::NUM_AXES; ++a) {
                float val_i = state.emotions[offset_i + a];
                float weight = (a == primary_axis) ? weight_primary : weight_secondary;
                delta_emotions[offset_j + a] += val_i * common_factor * weight;
            }

            // Успешное влияние повышает отзывчивость i к j
            // В C++ версии мы можем обновить это сразу или накопить
            // В Python: self.update_responsiveness(target_name, 1) -> повышает отзывчивость SENDER к TARGET
            state.relations[base_ij + 3] = std::min(10.0f, state.relations[base_ij + 3] + 1.0f);
        }
    }

    // Применяем накопленные изменения эмоций + добавляем естественное затухание
    float decay_rate = 0.05f; // Базовая скорость затухания для C++ шага

    for (size_t k = 0; k < state.emotions.size(); ++k) {
        float current = state.emotions[k] + delta_emotions[k];
        
        // Эмоциональное затухание (стремление к 0)
        if (current > 0) {
            current = std::max(0.0f, current - decay_rate);
        } else if (current < 0) {
            current = std::min(0.0f, current + decay_rate);
        }

        state.emotions[k] = std::max(-3.0f, std::min(3.0f, current));
    }
}

} // namespace core_engine
