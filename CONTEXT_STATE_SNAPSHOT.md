# RECOVERY_CORE_SNAPSHOT_V4.9 (ANTIGRAVITY_HMM)
## TIMESTAMP: 2026-02-06

### 1. PROJECT_IDENTITY
- **DOMAIN**: Discrete Automaton Model / Social Simulation (Antigravity Project - MSU MechMath Level).
- **COLLECTIVE_ID**: Collective Automaton K = {A1, ..., An}.
- **VERSION**: 4.9 (Refined Relational Dynamics, Softmax Refusal, C++ Emission Weights).

### 2. FORMAL_MODEL_SPEC (SYSTEM_PROMPT_CONSTRAINTS)
- **EMOTIONS_VEC**: R_i(t) ∈ [-3, 3]^7 (Axes: Joy-Sadness, Fear-Calm, Anger-Humility, Disgust-Acceptance, Surprise-Habit, Shame-Confidence, Openness-Alienation).
- **RELATIONS_VEC**: U (Utility), A (Affinity), T (Trust), R (Responsiveness) ∈ [-10, 10].
- **LAWS**:
    - **RELATION_DECAY**: Law of Forgiveness (linear decay towards 0 based on archetype and sensitivity).
    - **EMOTION_DECAY**: Entropy control (damping extreme states).
    - **SIGMA_LOGIC**: σ_ij ∈ {-1, 0, 1} (Interaction Result). **v4.9**: Refusal chance via Softmax(R).
    - **RELATIONAL_SHIFT**: Success prioritizes Affinity/Utility (2.5x). Failure hits Trust.
    - **RESPONSIVENESS_AUTO**: Passive decay towards 0. Faster recovery if R < 0.
    - **COLLECTIVE_INFLUENCE**: O(N^2) Contagion in C++. **v4.9**: Archetype emission weights integration.

### 3. ARCHITECTURE_MAP
- **CORE_ENGINE** (C++17): `core/src/engine.cpp` (OpenMP parallel loops).
- **BINDINGS**: `pybind11` (Module: `emotion_engine`).
- **LOGIC_LAYER** (Python):
    - `model/agent.py`: Atomic automaton logic.
    - `model/collective.py`: High-level orchestration.
    - `model/university_collective.py`: V3.0 University hierarchy (1875 agents).
    - `core/interaction_strategy.py`: Softmax selection and Sigma updates.
    - `core/university_manager.py`: Spatial (Coord-based) and Schedule management.
- **GUI_LAYER**:
    - `gui/simulation_gui.py`: Basic graph-based UI.
    - `gui/university_gui.py`: Campus-map visualization (Primary emotion-based coloring).
    - `scripts/simulation_constructor.py`: Research UI (Archetype distribution, Gaussian/Uniform init).

### 4. BUILD_SYSTEM_STATE
- **SCRIPTS**: `build.sh` (Auto-detection Darwin/Linux/Windows), `run.sh` (Kernel check + auto-rebuild).
- **METADATA**: `core/.build_info` contains `OS | Kernel | Arch`.
- **DEPENDENCIES**: `libomp` (macOS/Darwin), `OpenMP` (Linux), `numpy`, `pandas`, `tkinter`.

### 5. RESEARCH_TOOLS
- **CONFIG**: `scenario.json` (Reproducibility anchor).
- **RUNNERS**:
    - `run_research_gui.py`: Visual simulation with pre-loaded scenarios.
    - `run_headless.py`: High-speed Silent Mode (No Tkinter bypass).

### 7. ARTIFACT_CONTEXT_RECOVERY
- **TASK_HISTORY**: [task.md](file:///Users/georgijtadziev/.gemini/antigravity/brain/f80644f3-59c1-40d2-8cb9-0417a648cda3/task.md) (Check for completed/pending phases).
- **PLANNING_HISTORY**: [implementation_plan.md](file:///Users/georgijtadziev/.gemini/antigravity/brain/f80644f3-59c1-40d2-8cb9-0417a648cda3/implementation_plan.md) (Deep dive into logic changes and bugs).
- **WALKTHROUGH_HISTORY**: [walkthrough.md](file:///Users/georgijtadziev/.gemini/antigravity/brain/f80644f3-59c1-40d2-8cb9-0417a648cda3/walkthrough.md) (Proof of work, screenshots, and verification results).

### 8. RECOVERY_QUERY_STRATEGY
"Check `CONTEXT_STATE_SNAPSHOT.md` for formal model R_i and R_ij definitions, verify `core/.build_info` for kernel compatibility, ensure `InteractionStrategy.process_interaction_result` aligns with σ_ij ∈ {-1, 0, 1}, and review ARTIFACTS in `.gemini/antigravity/brain/` for implementation history."

---

### 9. CORE_SYSTEM_JSON (FOR_MACHINE_PARSING)
```json
{
  "project_v": "4.9",
  "assistant_context": "Antigravity AI Assistant",
  "formal_model": {
    "emotion_axes": 7,
    "range": [-3.0, 3.0],
    "relations": ["utility", "affinity", "trust", "responsiveness"],
    "rel_range": [-10, 10],
    "sigma_logic": [-1, 0, 1],
    "softmax_refusal": true,
    "growth_priority": ["affinity", "utility"],
    "cpp_engine_v": "3.1"
  },
  "architecture": {
    "engine": "core/src/engine.cpp",
    "parallel": "OpenMP",
    "python_entry": "main.py",
    "research_entry": "scripts/simulation_constructor.py",
    "headless_entry": "scripts/run_headless.py"
  },
  "artifact_paths": {
    "task": "/Users/georgijtadziev/.gemini/antigravity/brain/f80644f3-59c1-40d2-8cb9-0417a648cda3/task.md",
    "plan": "/Users/georgijtadziev/.gemini/antigravity/brain/f80644f3-59c1-40d2-8cb9-0417a648cda3/implementation_plan.md",
    "walkthrough": "/Users/georgijtadziev/.gemini/antigravity/brain/f80644f3-59c1-40d2-8cb9-0417a648cda3/walkthrough.md"
  }
}
```
