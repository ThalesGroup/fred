// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Platform model inventory and organization administration, without runtime enforcement.
//! Configuration is applied on serve startup; refresh is an explicit internal operation.

pub mod config;
mod discovery;
pub(crate) mod http;
pub(crate) mod instance;
mod policy;
mod store;

pub use discovery::{ChatProvenance, DiscoveryFailure, ModelMetadata};
pub use store::{
    ModelInventory, ModelObservation, RefreshResult, StoredModelOffer, configure_sources,
    inventory, refresh,
};
