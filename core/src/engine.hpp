#ifndef ENGINE_HPP
#define ENGINE_HPP

#include <vector>
#include <string>
#include <map>
#include "logger.hpp"

namespace core_engine {

struct Relation {
    float utility;
    float affinity;
    float trust;
    float responsiveness;
};

struct Interaction {
    int from_idx;
    int to_idx;
    int type; // 0: refusal, 1: success, 2: fail
};

struct ArchetypeConfig {
    float refusal_chance;
    float decay_rate;
    float temperature;
    float emotion_decay;
    std::vector<float> emotion_coefficients; // Matches NUM_AXES
    std::string scoring_affinity;       // "linear", "log", "exp", "sigmoid", "periodic"
    std::string scoring_utility;
    std::string scoring_trust;
    std::string scoring_responsiveness;
};

// Плоская структура для быстрого доступа к данным в памяти
struct SimulationState {
    int num_agents;
    std::vector<float> emotions; // Matrix N x 7
    std::vector<float> relations; // Matrix N x N x 4 (utility, affinity, trust, responsiveness)
    std::vector<float> sensitivities; // Vector N
    // Матрица влияния эмоций на отношения (из Archetype.emotion_effects)
    // Размер: N_agents x 7_axes x 4_relations (U, A, T, R)
    std::vector<float> emission_weights;
    
    // Новые поля для v5.1
    std::vector<int> agent_archetypes; // Индекс архетипа для каждого агента
    std::vector<ArchetypeConfig> archetype_configs; 
    
    // Параметры осей эмоций (индексы)
    static constexpr int NUM_AXES = 7;
};

class Engine {
public:
    Engine(int n) : num_agents(n) {
        state.num_agents = n;
        state.emotions.assign(n * SimulationState::NUM_AXES, 0.0f);
        state.relations.assign(n * n * 4, 0.0f);
        state.sensitivities.assign(n, 1.0f);
        state.emission_weights.assign(n * SimulationState::NUM_AXES * 4, 0.0f);
        state.agent_archetypes.assign(n, 0);
    }

    void set_emotion(int agent_idx, int axis_idx, float value) {
        state.emotions[agent_idx * SimulationState::NUM_AXES + axis_idx] = value;
    }

    void set_emission_weight(int agent_idx, int axis_idx, float du, float da, float dt, float dr) {
        int base = (agent_idx * SimulationState::NUM_AXES + axis_idx) * 4;
        state.emission_weights[base + 0] = du;
        state.emission_weights[base + 1] = da;
        state.emission_weights[base + 2] = dt;
        state.emission_weights[base + 3] = dr;
    }

    void set_relation(int from_idx, int to_idx, float u, float a, float t, float r) {
        int base = (from_idx * num_agents + to_idx) * 4;
        state.relations[base + 0] = u;
        state.relations[base + 1] = a;
        state.relations[base + 2] = t;
        state.relations[base + 3] = r;
    }

    void set_archetype_config(int arch_idx, float refusal, float decay, float temp, 
                             float e_decay, const std::vector<float>& e_coeffs,
                             const std::string& sa, const std::string& su, 
                             const std::string& st, const std::string& sr) {
        if (arch_idx >= (int)state.archetype_configs.size()) {
            state.archetype_configs.resize(arch_idx + 1);
        }
        state.archetype_configs[arch_idx] = {refusal, decay, temp, e_decay, e_coeffs, sa, su, st, sr};
    }

    void set_agent_archetype(int agent_idx, int arch_idx) {
        state.agent_archetypes[agent_idx] = arch_idx;
    }

    // Тот самый N^2 метод
    void influence_emotions();

    // Новые методы для ускорения шага
    float calculate_priority_score(int from_idx, int to_idx);
    int choose_target(int agent_idx);
    void process_interaction(int from_idx, int to_idx, bool success);
    void process_refusal(int from_idx, int to_idx);
    bool should_refuse(int agent_idx, int target_idx);

    // V5.2: Методы полного цикла
    void apply_relation_decay();
    void react_to_relations();
    void react_to_emotions();
    void apply_emotion_decay();
    void perform_daily_cycle(int interactions_per_day);
    void seed(int s);

    void set_agent_names(const std::vector<std::string>& names) {
        agent_names = names;
    }

    void save_states_csv(const std::string& filepath, const std::string& date_str, bool is_first_run) {
        CSVLogger::log_agent_states(filepath, date_str, agent_names, state.emotions, state.relations, num_agents, is_first_run);
    }

    void save_interactions_csv(const std::string& filepath, const std::string& date_str, bool is_first_run) {
        std::vector<InteractionLogEntry> logs;
        for (const auto& inter : last_day_interactions) {
            logs.push_back({inter.from_idx, inter.to_idx, inter.type});
        }
        CSVLogger::log_interactions(filepath, date_str, agent_names, logs, is_first_run);
    }

    SimulationState state;
    std::vector<Interaction> last_day_interactions;
private:
    int num_agents;
    std::vector<std::string> agent_names;
};

} // namespace core_engine

#endif
