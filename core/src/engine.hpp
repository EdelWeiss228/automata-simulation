#ifndef ENGINE_HPP
#define ENGINE_HPP

#include <vector>
#include <string>
#include <map>

namespace core_engine {

struct Relation {
    float utility;
    float affinity;
    float trust;
    float responsiveness;
};

// Плоская структура для быстрого доступа к данным в памяти
struct SimulationState {
    int num_agents;
    std::vector<float> emotions; // Matrix N x 7
    std::vector<float> relations; // Matrix N x N x 4 (utility, affinity, trust, responsiveness)
    std::vector<float> sensitivities; // Vector N
    
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
    }

    void set_emotion(int agent_idx, int axis_idx, float value) {
        state.emotions[agent_idx * SimulationState::NUM_AXES + axis_idx] = value;
    }

    void set_relation(int from_idx, int to_idx, float u, float a, float t, float r) {
        int base = (from_idx * num_agents + to_idx) * 4;
        state.relations[base + 0] = u;
        state.relations[base + 1] = a;
        state.relations[base + 2] = t;
        state.relations[base + 3] = r;
    }

    // Тот самый N^2 метод
    void influence_emotions();

    SimulationState state;
private:
    int num_agents;
};

} // namespace core_engine

#endif
