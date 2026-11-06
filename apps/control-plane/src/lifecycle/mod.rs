// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Retirement acceptance, durable receipts and bounded Temporal cleanup.
pub mod policy;
pub mod store;
pub use store::{Lifecycle, Receipt, Status, TargetKind};
pub mod cleanup;
pub mod runtime_storage;
pub mod worker;

mod audit;

#[derive(serde::Deserialize, utoipa::IntoParams)]
#[into_params(parameter_in = Query)]
pub(crate) struct DeleteQuery {
    /// Request immediate purge for an eligible resource as a platform administrator.
    #[serde(default)]
    pub immediate: bool,
}

pub(crate) async fn deletion_response(
    config: &policy::LifecycleConfig,
    receipt: Receipt,
    immediate: bool,
) -> (axum::http::StatusCode, axum::Json<Receipt>) {
    let status = if receipt.status == Status::Completed {
        axum::http::StatusCode::OK
    } else {
        // The receipt is durable even if this attempt to wake the worker fails.
        if immediate
            && config.enabled
            && receipt.due_at == receipt.requested_at
            && worker::start_immediate(config, receipt.id).await.is_err()
        {
            tracing::warn!(
                error_code = "deletion_dispatch_retry",
                "Deletion awaits its scheduled sweep"
            );
        }
        axum::http::StatusCode::ACCEPTED
    };
    (status, axum::Json(receipt))
}
