#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "engine.hpp"

namespace py = pybind11;

PYBIND11_MODULE(emotion_engine, m) {
    m.doc() = "High-performance C++ core for Agent Simulation";

    py::class_<core_engine::Engine>(m, "Engine")
        .def(py::init<int>())
        .def_property_readonly("num_agents", [](const core_engine::Engine &e) { return e.state.num_agents; })
        .def("set_emotion", &core_engine::Engine::set_emotion)
        .def("set_relation", &core_engine::Engine::set_relation)
        .def("influence_emotions", &core_engine::Engine::influence_emotions)
        .def_property_readonly("emotions", [](const core_engine::Engine &e) {
            return e.state.emotions;
        })
        .def_property_readonly("relations", [](const core_engine::Engine &e) {
            return e.state.relations;
        })
        .def_property("sensitivities", 
            [](const core_engine::Engine &e) { return e.state.sensitivities; },
            [](core_engine::Engine &e, const std::vector<float>& s) { e.state.sensitivities = s; }
        );
}
