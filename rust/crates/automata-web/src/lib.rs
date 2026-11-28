//! HTTP/JSON API and static dashboard for v3 simulation runs.
//!
//! The web layer is deliberately read-only and stateless: manifests and run
//! directories are the source of truth, and long simulations stay in
//! `automata-cli`/systemd rather than HTTP handlers.

#![forbid(unsafe_code)]

pub mod http;
pub mod json;
pub mod runs;
pub mod server;

pub use server::{SERVICE_VERSION, WebConfig, serve};
