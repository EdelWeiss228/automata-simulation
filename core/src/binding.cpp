#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "engine.hpp"

namespace py = pybind11;

PYBIND11_MODULE(emotion_engine, m) {
    m.doc() = "High-performance C++ core for Agent Simulation";

    py::class_<core_engine::SimulationState>(m, "SimulationState")
        .def_readwrite("num_agents", &core_engine::SimulationState::num_agents)
        .def_readwrite("emotions", &core_engine::SimulationState::emotions)
        .def_readwrite("relations", &core_engine::SimulationState::relations)
        .def_readwrite("sensitivities", &core_engine::SimulationState::sensitivities)
        .def_readwrite("emission_weights", &core_engine::SimulationState::emission_weights);

    py::class_<core_engine::Engine>(m, "Engine")
        .def(py::init<int>())
        .def_readwrite("state", &core_engine::Engine::state)
        .def("set_emotion", &core_engine::Engine::set_emotion)
        .def("set_relation", &core_engine::Engine::set_relation)
        .def("set_emission_weight", &core_engine::Engine::set_emission_weight)
        .def("influence_emotions", &core_engine::Engine::influence_emotions)
        .def_property_readonly("emotions", [](const core_engine::Engine &e) {
            return e.state.emotions;
        })
        .def_property_readonly("relations", [](const core_engine::Engine &e) {
            return e.state.relations;
        });
}
