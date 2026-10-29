// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Organization authorization of pod capability offers: deny by default.

use std::collections::{BTreeSet, HashMap, HashSet};

use axum::http::StatusCode;
use sqlx::PgConnection;
use uuid::Uuid;

use crate::{
    domain::Space,
    error::{AppError, AppResult},
};

/// One organization's authorization of pod offers, read in one query.
#[derive(Clone)]
pub struct Policy {
    /// Capability ids enabled for every space, by runtime_id.
    enabled: HashMap<String, HashSet<String>>,
}

impl Policy {
    pub async fn load<'e>(
        ex: impl sqlx::PgExecutor<'e>,
        organization_id: Uuid,
    ) -> sqlx::Result<Self> {
        let rows: Vec<(String, String)> = sqlx::query_as(
            "select runtime_id, capability_id from organization_capability where organization_id = $1",
        )
        .bind(organization_id)
        .fetch_all(ex)
        .await?;
        let mut enabled: HashMap<String, HashSet<String>> = HashMap::new();
        for (runtime_id, capability_id) in rows {
            enabled.entry(runtime_id).or_default().insert(capability_id);
        }
        Ok(Self { enabled })
    }

    /// The organization's "enabled for all" decision, as stored.
    pub fn default_on(&self, runtime_id: &str, capability_id: &str) -> bool {
        self.enabled
            .get(runtime_id)
            .is_some_and(|ids| ids.contains(capability_id))
    }

    /// This policy with one offer disabled, to preview its revocation.
    pub fn without(&self, runtime_id: &str, capability_id: &str) -> Self {
        let mut policy = self.clone();
        if let Some(ids) = policy.enabled.get_mut(runtime_id) {
            ids.remove(capability_id);
        }
        policy
    }
}

/// The single rule deciding whether `space` may use an offer. Team exceptions
/// and the personal-space class belong here and in `Policy`, nowhere else.
pub fn usable(policy: &Policy, _space: &Space, runtime_id: &str, capability_id: &str) -> bool {
    policy.default_on(runtime_id, capability_id)
}

/// The first selected capability `space` may no longer use.
pub fn first_unusable<'a>(
    policy: &Policy,
    space: &Space,
    runtime_id: &str,
    selected: &'a [String],
) -> Option<&'a str> {
    selected
        .iter()
        .map(String::as_str)
        .find(|id| !usable(policy, space, runtime_id, id))
}

pub fn require_usable(
    policy: &Policy,
    space: &Space,
    runtime_id: &str,
    selected: &[String],
) -> AppResult<()> {
    first_unusable(policy, space, runtime_id, selected).map_or(Ok(()), |id| Err(not_enabled(id)))
}

pub fn not_enabled(capability_id: &str) -> AppError {
    AppError::problem(
        StatusCode::UNPROCESSABLE_ENTITY,
        "agent_capability_unavailable",
        format!("Capability {capability_id} is not enabled for this space."),
    )
}

/// Offers of `runtime_id` that `space` may select.
pub async fn usable_capability_ids<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space: &Space,
    runtime_id: &str,
) -> AppResult<BTreeSet<String>> {
    let policy = Policy::load(ex, space.organization).await?;
    Ok(policy
        .enabled
        .get(runtime_id)
        .into_iter()
        .flatten()
        .filter(|id| usable(&policy, space, runtime_id, id))
        .cloned()
        .collect())
}

/// Returns whether the stored decision changed. Caller holds the organization lock.
pub(super) async fn set_default_on(
    conn: &mut PgConnection,
    organization_id: Uuid,
    runtime_id: &str,
    capability_id: &str,
    default_on: bool,
    actor: &str,
) -> AppResult<bool> {
    // Shared row lock: a concurrent refresh cannot withdraw the offer before we write.
    let advertised: bool = sqlx::query_scalar(
        "select advertised from runtime_capability
         where runtime_id = $1 and capability_id = $2 for share",
    )
    .bind(runtime_id)
    .bind(capability_id)
    .fetch_optional(&mut *conn)
    .await?
    .ok_or(AppError::NotFound)?;
    let result = if default_on {
        if !advertised {
            return Err(AppError::Conflict(
                "The pod no longer advertises this capability; it cannot be enabled.".into(),
            ));
        }
        sqlx::query(
            "insert into organization_capability (organization_id, runtime_id, capability_id, enabled_by)
             values ($1, $2, $3, $4) on conflict do nothing",
        )
        .bind(organization_id)
        .bind(runtime_id)
        .bind(capability_id)
        .bind(actor)
        .execute(&mut *conn)
        .await?
    } else {
        sqlx::query(
            "delete from organization_capability
             where organization_id = $1 and runtime_id = $2 and capability_id = $3",
        )
        .bind(organization_id)
        .bind(runtime_id)
        .bind(capability_id)
        .execute(&mut *conn)
        .await?
    };
    Ok(result.rows_affected() == 1)
}
