#ifndef LOGGER_HPP
#define LOGGER_HPP

#include <string>
#include <vector>
#include <fstream>
#include <iomanip>

namespace core_engine {

struct InteractionLogEntry {
    int from_idx;
    int to_idx;
    int type; // 0: refusal, 1: success, 2: fail
};

class CSVLogger {
public:
    static void log_agent_states(
        const std::string& filepath,
        const std::string& date_str,
        const std::vector<std::string>& agent_names,
        const std::vector<float>& emotions,
        const std::vector<float>& relations,
        int num_agents,
        bool is_first_run
    );

    static void log_interactions(
        const std::string& filepath,
        const std::string& date_str,
        const std::vector<std::string>& agent_names,
        const std::vector<InteractionLogEntry>& interactions,
        bool is_first_run
    );
};

} // namespace core_engine

#endif // LOGGER_HPP
