// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::Receipt;

/// Called only after the transaction commits, with runtime provenance captured before purge.
pub(super) fn session(receipt: &Receipt, runtime: &str) {
    macro_rules! emit {
        ($event:literal $(, $field:ident = $value:expr)*) => {
            tracing::info!(target: "fred.security.audit",
                audit_event = $event, target_kind = "session",
                operation_id = %receipt.id, session_id = %receipt.target_id,
                space_id = %receipt.target_parent_id.map(|id| id.to_string()).unwrap_or_default(),
                organization_id = %receipt.organization_id, actor_uid = receipt.actor_subject,
                runtime_id = runtime, rule_id = ?receipt.rule_id,
                requested_at = %receipt.requested_at, due_at = %receipt.due_at,
                $($field = $value,)*
                "Session deletion"
            );
        };
    }
    if let Some(completed) = receipt.completed_at {
        emit!("deletion.completed", completed_at = completed.to_rfc3339());
    } else {
        emit!("deletion.accepted");
    }
}
