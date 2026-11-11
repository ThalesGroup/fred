// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Organization authorization of capability offers: deny by default.

use std::collections::{BTreeSet, HashMap, HashSet};

use axum::http::StatusCode;
use sqlx::PgConnection;
use uuid::Uuid;

use crate::{
    domain::Space,
    error::{AppError, AppResult},
};

/// One organization's authorization of offers, read in one query.
#[derive(Clone)]
pub struct Policy {
    /// Capability ids enabled for every space, by source_id.
    enabled: HashMap<String, HashSet<String>>,
    local: HashMap<Uuid, HashMap<String, HashSet<String>>>,
}

impl Policy {
    /// A shared application is available when at least one authorized pod offers it.
    pub fn any_usable(&self, space: &Space, capability_id: &str) -> bool {
        self.enabled
            .keys()
            .any(|runtime| usable(self, space, runtime, capability_id))
    }

    pub async fn load<'e>(
        ex: impl sqlx::PgExecutor<'e>,
        organization_id: Uuid,
    ) -> sqlx::Result<Self> {
        Self::load_scoped(ex, organization_id, None).await
    }

    /// Admission needs only its own ancestors, never every team's restrictions.
    pub async fn load_for_space<'e>(
        ex: impl sqlx::PgExecutor<'e>,
        space: &Space,
    ) -> sqlx::Result<Self> {
        Self::load_scoped(ex, space.organization, Some(&space.path)).await
    }

    async fn load_scoped<'e>(
        ex: impl sqlx::PgExecutor<'e>,
        organization_id: Uuid,
        path: Option<&[Uuid]>,
    ) -> sqlx::Result<Self> {
        let rows: Vec<(String, Option<String>, Option<Uuid>)> = sqlx::query_as(
            "select source_id, capability_id, null::uuid as space_id
             from organization_capability where organization_id = $1
             union all
             select p.source_id, a.capability_id, p.space_id
             from space_capability_policy p join space s on s.id=p.space_id
             left join space_capability_permission a using (space_id, source_id)
             where s.organization_id=$1 and p.restricted and ($2::uuid[] is null or p.space_id=any($2))",
        )
        .bind(organization_id)
        .bind(path)
        .fetch_all(ex)
        .await?;
        let mut enabled: HashMap<String, HashSet<String>> = HashMap::new();
        let mut local: HashMap<Uuid, HashMap<String, HashSet<String>>> = HashMap::new();
        for (runtime, capability, space) in rows {
            let entries = match space {
                Some(space) => local.entry(space).or_default().entry(runtime).or_default(),
                None => enabled.entry(runtime).or_default(),
            };
            if let Some(capability) = capability {
                entries.insert(capability);
            }
        }
        Ok(Self { enabled, local })
    }

    /// The organization's "enabled for all" decision, as stored.
    pub fn default_on(&self, source_id: &str, capability_id: &str) -> bool {
        self.enabled
            .get(source_id)
            .is_some_and(|ids| ids.contains(capability_id))
    }

    /// This policy with one offer disabled, to preview its revocation.
    pub fn without(&self, source_id: &str, capability_id: &str) -> Self {
        let mut policy = self.clone();
        if let Some(ids) = policy.enabled.get_mut(source_id) {
            ids.remove(capability_id);
        }
        policy
    }
}

/// The single rule deciding whether `space` may use an offer. Team exceptions
/// and the personal-space class belong here and in `Policy`, nowhere else.
pub fn usable(policy: &Policy, space: &Space, source_id: &str, capability_id: &str) -> bool {
    policy.default_on(source_id, capability_id)
        && space.path.iter().all(|id| {
            policy
                .local
                .get(id)
                .and_then(|runtimes| runtimes.get(source_id))
                .is_none_or(|allowed| allowed.contains(capability_id))
        })
}

/// The first selected capability `space` may no longer use.
pub fn first_unusable<'a>(
    policy: &Policy,
    space: &Space,
    source_id: &str,
    selected: &'a [String],
) -> Option<&'a str> {
    selected
        .iter()
        .map(String::as_str)
        .find(|id| !usable(policy, space, selection_source(source_id, id), id))
}

pub fn require_usable(
    policy: &Policy,
    space: &Space,
    source_id: &str,
    selected: &[String],
) -> AppResult<()> {
    first_unusable(policy, space, source_id, selected).map_or(Ok(()), |id| Err(not_enabled(id)))
}

pub fn not_enabled(capability_id: &str) -> AppError {
    AppError::problem(
        StatusCode::UNPROCESSABLE_ENTITY,
        "agent_capability_unavailable",
        format!("Capability {capability_id} is not enabled for this space."),
    )
}

/// Offers of `source_id` that `space` may select.
pub async fn usable_capability_ids<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space: &Space,
    source_id: &str,
) -> AppResult<BTreeSet<String>> {
    let policy = Policy::load(ex, space.organization).await?;
    Ok([source_id, crate::mcp_connections::SOURCE_ID]
        .into_iter()
        .flat_map(|source| policy.enabled.get(source).into_iter().flatten())
        .filter(|id| usable(&policy, space, selection_source(source_id, id), id))
        .cloned()
        .collect())
}

/// Returns whether the stored decision changed. Caller holds the organization lock.
pub(super) async fn set_default_on(
    conn: &mut PgConnection,
    organization_id: Uuid,
    source_id: &str,
    capability_id: &str,
    default_on: bool,
    actor: &str,
) -> AppResult<bool> {
    // Shared row lock: a concurrent refresh cannot withdraw the offer before we write.
    let advertised: bool = sqlx::query_scalar(
        "select advertised from capability_offer
         where source_id = $1 and capability_id = $2 for share",
    )
    .bind(source_id)
    .bind(capability_id)
    .fetch_optional(&mut *conn)
    .await?
    .ok_or(AppError::NotFound)?;
    let result = if default_on {
        if !advertised {
            return Err(AppError::Conflict(
                "This offer is unavailable; it cannot be enabled.".into(),
            ));
        }
        sqlx::query(
            "insert into organization_capability (organization_id, source_id, capability_id, enabled_by)
             values ($1, $2, $3, $4) on conflict do nothing",
        )
        .bind(organization_id)
        .bind(source_id)
        .bind(capability_id)
        .bind(actor)
        .execute(&mut *conn)
        .await?
    } else {
        sqlx::query(
            "delete from organization_capability
             where organization_id = $1 and source_id = $2 and capability_id = $3",
        )
        .bind(organization_id)
        .bind(source_id)
        .bind(capability_id)
        .execute(&mut *conn)
        .await?
    };
    Ok(result.rows_affected() == 1)
}

/// Selection provenance is independent of the executing pod. Native IDs retain their pod.
pub fn selection_source<'a>(runtime: &'a str, id: &str) -> &'a str {
    if id.starts_with("managed-mcp:") {
        crate::mcp_connections::SOURCE_ID
    } else {
        runtime
    }
}
