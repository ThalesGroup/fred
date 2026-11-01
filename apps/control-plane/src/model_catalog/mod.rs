// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Platform observations, explicit organization assignments and model policy.
//! Deployment initializes once; admissions read current SQL facts.

pub mod config;
mod discovery;
pub(crate) mod http;
pub mod initialization;
pub(crate) mod instance;
mod policy;
mod store;

pub use discovery::{ChatProvenance, DiscoveryFailure, ModelMetadata};
pub use store::{
    ModelInventory, ModelObservation, RefreshResult, StoredModelOffer, configure_sources,
    inventory, refresh,
};
