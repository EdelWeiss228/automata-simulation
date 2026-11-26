//! Deterministic simulation core for the v3 social automata model.
//!
//! The crate deliberately has no dependencies and no I/O.  It is a vertical
//! slice of the future Rust kernel: typed state, explicit RNG, deterministic
//! iteration order, and data-parallel phases that produce the same result for
//! any thread count.
//!
//! The model is extracted from the corrected v2 implementation.  See
//! `docs/v3-rust-migration.md` for the exact mapping and for the differences
//! between the Python and C++ paths of v2 that this crate deliberately
//! resolves.

#![forbid(unsafe_code)]
#![deny(missing_debug_implementations)]

pub mod agent;
pub mod archetype;
pub mod emotion;
pub mod ids;
pub mod outcome;
pub mod parallel;
pub mod relation;
pub mod rng;
pub mod world;

pub use agent::{Agent, AgentSpec, Degree};
pub use archetype::{ArchetypeConfig, ArchetypeKind, Context, Scoring};
pub use emotion::{EMOTION_MAX, EMOTION_MIN, Emotion, EmotionAxis, EmotionVector, NUM_AXES};
pub use ids::AgentId;
pub use outcome::{Interaction, Outcome, SIGMA_RATE, sigma_rate_factor};
pub use relation::{RELATION_MAX, RELATION_MIN, Relation, RelationAxis};
pub use rng::DeterministicRng;
pub use world::{DayReport, InitMode, RunReport, World, WorldConfig};
