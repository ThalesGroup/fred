// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Ralph, the embedded Rust agent. The host owns HTTP, identity and admission.

pub mod answer;
pub mod demo;
mod events;
mod request;
pub mod search;
#[cfg(test)]
mod testing;
pub mod turn;

pub use events::RuntimeEvent;
pub use request::{ExecuteError, ExecuteRequest, RequestedTarget};
pub use rig_core::completion::Usage;

pub const AGENT_ID: &str = "fred.github.ralph";

/// Descriptive metadata, independent of the host's discovery wire format.
pub struct AgentDefinition {
    pub id: &'static str,
    pub title: &'static str,
    pub version: &'static str,
    pub provider: &'static str,
    pub description: &'static str,
}

pub const DEFINITION: AgentDefinition = AgentDefinition {
    id: AGENT_ID,
    title: "Ralph",
    version: env!("CARGO_PKG_VERSION"),
    provider: "control-plane",
    description: "Rust chat agent with optional document search. Each message is independent; no saved history.",
};
