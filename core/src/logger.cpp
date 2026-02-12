#include "logger.hpp"
#include <iostream>

namespace core_engine {

void CSVLogger::log_agent_states(
    const std::string& filepath,
    const std::string& date_str,
    const std::vector<std::string>& agent_names,
    const std::vector<float>& emotions,
    const std::vector<float>& relations,
    int num_agents,
    bool is_first_run
) {
    std::ios_base::openmode mode = is_first_run ? std::ios::out : std::ios::app;
    std::ofstream f(filepath, mode);
    
    if (!f.is_open()) return;

    if (is_first_run) {
        f << "Дата,Имя агента,Эмоции,Предикаты\n";
    }

    const std::vector<std::string> emotion_axes = {
        "joy_sadness", "fear_calm", "anger_humility", 
        "disgust_acceptance", "surprise_habit", 
        "shame_confidence", "openness_alienation"
    };

    const std::vector<std::string> relation_types = {
        "utility", "affinity", "trust", "responsiveness"
    };

    // Date can be long (YYYY-MM-DD HH:MM:SS), we only want YYYY-MM-DD if matching isoformat() of date
    std::string short_date = date_str.substr(0, 10);

    for (int i = 0; i < num_agents; ++i) {
        f << short_date << "," << agent_names[i] << ",";
        
        // Эмоции: осе_1:значение; осе_2:значение...
        // Python logs them with full precision but we'll use a reasonable one or (int) if it matches
        for (int e = 0; e < 7; ++e) {
            f << emotion_axes[e] << ":" << emotions[i * 7 + e];
            if (e < 6) f << "; ";
        }
        f << ",";

        // Предикаты: "Target=utility:0,affinity:0... | Target2=..."
        f << "\""; 
        bool first_rel = true;
        for (int j = 0; j < num_agents; ++j) {
            if (i == j) continue;

            if (!first_rel) f << " | ";
            f << agent_names[j] << "=";
            
            int base = (i * num_agents + j) * 4;
            for (int r = 0; r < 4; ++r) {
                f << relation_types[r] << ":" << relations[base + r];
                if (r < 3) f << ",";
            }
            first_rel = false;
        }
        f << "\"\n";
    }
}

void CSVLogger::log_interactions(
    const std::string& filepath,
    const std::string& date_str,
    const std::vector<std::string>& agent_names,
    const std::vector<InteractionLogEntry>& interactions,
    bool is_first_run
) {
    std::ios_base::openmode mode = is_first_run ? std::ios::out : std::ios::app;
    std::ofstream f(filepath, mode);
    
    if (!f.is_open()) return;

    if (is_first_run) {
        f << "Дата,Источник,Цель,Успех\n";
    }

    const char* type_map[] = {"refusal", "success", "fail"};
    std::string short_date = date_str.substr(0, 10);

    for (const auto& inter : interactions) {
        if (inter.from_idx >= 0 && inter.from_idx < agent_names.size() &&
            inter.to_idx >= 0 && inter.to_idx < agent_names.size()) {
            f << short_date << "," << agent_names[inter.from_idx] << "," 
              << agent_names[inter.to_idx] << "," << type_map[inter.type] << "\n";
        }
    }
}

} // namespace core_engine
