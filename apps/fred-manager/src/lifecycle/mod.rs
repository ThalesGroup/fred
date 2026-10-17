// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Retirement acceptance, durable receipts and bounded Temporal cleanup.
pub mod policy;
pub mod store;
pub use store::{Lifecycle, Receipt, Status};
pub mod cleanup;
pub mod worker;
