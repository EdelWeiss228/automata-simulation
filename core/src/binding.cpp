#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "engine.hpp"

namespace py = pybind11;

PYBIND11_MODULE(emotion_engine, m) {
    m.doc() = "High-performance C++ core for Agent Simulation";

    py::class_<core_engine::Interaction>(m, "Interaction")
        .def(py::init<>())
        .def_readwrite("from_idx", &core_engine::Interaction::from_idx)
        .def_readwrite("to_idx", &core_engine::Interaction::to_idx)
        .def_readwrite("type", &core_engine::Interaction::type);

    py::class_<core_engine::ArchetypeConfig>(m, "ArchetypeConfig")
        .def(py::init<>())
        .def_readwrite("refusal_chance", &core_engine::ArchetypeConfig::refusal_chance)
        .def_readwrite("decay_rate", &core_engine::ArchetypeConfig::decay_rate)
        .def_readwrite("temperature", &core_engine::ArchetypeConfig::temperature)
        .def_readwrite("emotion_decay", &core_engine::ArchetypeConfig::emotion_decay)
        .def_readwrite("emotion_coefficients", &core_engine::ArchetypeConfig::emotion_coefficients)
        .def_readwrite("scoring_affinity", &core_engine::ArchetypeConfig::scoring_affinity)
        .def_readwrite("scoring_utility", &core_engine::ArchetypeConfig::scoring_utility)
        .def_readwrite("scoring_trust", &core_engine::ArchetypeConfig::scoring_trust)
        .def_readwrite("scoring_responsiveness", &core_engine::ArchetypeConfig::scoring_responsiveness);

    py::class_<core_engine::SimulationState>(m, "SimulationState")
        .def_readwrite("num_agents", &core_engine::SimulationState::num_agents)
        .def_readwrite("emotions", &core_engine::SimulationState::emotions)
        .def_readwrite("relations", &core_engine::SimulationState::relations)
        .def_readwrite("sensitivities", &core_engine::SimulationState::sensitivities)
        .def_readwrite("emission_weights", &core_engine::SimulationState::emission_weights)
        .def_readwrite("agent_archetypes", &core_engine::SimulationState::agent_archetypes)
        .def_readwrite("archetype_configs", &core_engine::SimulationState::archetype_configs);

    py::class_<core_engine::Engine>(m, "Engine")
        .def(py::init<int>())
        .def_readwrite("state", &core_engine::Engine::state)
        .def("set_emotion", &core_engine::Engine::set_emotion)
        .def("set_relation", &core_engine::Engine::set_relation)
        .def("set_emission_weight", &core_engine::Engine::set_emission_weight)
        .def("set_archetype_config", &core_engine::Engine::set_archetype_config)
        .def("set_agent_archetype", &core_engine::Engine::set_agent_archetype)
        .def("influence_emotions", &core_engine::Engine::influence_emotions)
        .def("calculate_priority_score", &core_engine::Engine::calculate_priority_score)
        .def("choose_target", &core_engine::Engine::choose_target)
        .def("should_refuse", &core_engine::Engine::should_refuse)
        .def("process_interaction", &core_engine::Engine::process_interaction)
        .def("process_refusal", &core_engine::Engine::process_refusal)
        .def("perform_daily_cycle", &core_engine::Engine::perform_daily_cycle)
        .def("seed", &core_engine::Engine::seed)
        .def("set_agent_names", &core_engine::Engine::set_agent_names)
        .def("save_states_csv", &core_engine::Engine::save_states_csv)
        .def("save_interactions_csv", &core_engine::Engine::save_interactions_csv)
        .def_readwrite("last_day_interactions", &core_engine::Engine::last_day_interactions)
        .def_property_readonly("emotions", [](const core_engine::Engine &e) {
            return e.state.emotions;
        })
        .def_property_readonly("relations", [](const core_engine::Engine &e) {
            return e.state.relations;
        });
}
