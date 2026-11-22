// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{Result, invalid};
use crate::{
    api::AppState,
    auth::CurrentUser,
    authorization::{self, Delegation},
    domain::{Permission, Space},
    error::AppError,
    onboarding,
    roles::SpacePermission,
    spaces,
};
use axum::extract::FromRef;
use serde::Deserialize;
use sqlx::{Postgres, Transaction};
use uuid::Uuid;

#[derive(Deserialize)]
pub(super) struct Query {
    #[serde(flatten)]
    pub delegation: Delegation,
    pub session_id: Option<Uuid>,
    pub cursor: Option<String>,
}

pub(super) struct Access {
    pub(super) index: &'static dyn super::WikiIndex,
    pub tx: Transaction<'static, Postgres>,
    pub space: Space,
    pub person: String,
    /// The conversation a proposal comes from, once `own_session` checked it.
    pub session: Option<Uuid>,
    pub agent: Option<(Uuid, String)>,
    pub enabled: bool,
    /// The person arbitrates: a delegated turn never does.
    pub editor: bool,
    pub delegated: bool,
}

/// Reuse the organization retirement fence, then serialize tree mutations on
/// this space alone. No network call or human wait occurs inside this transaction.
pub(super) async fn open(
    state: &AppState,
    caller: &CurrentUser,
    query: &Query,
    space_id: Uuid,
    permission: Permission,
    mutation: bool,
) -> Result<Access> {
    let person = query.delegation.subject(state, caller)?.to_owned();
    let delegated = query.delegation.agent.is_some();
    if delegated && permission == Permission::Write {
        return Err(AppError::Forbidden.into());
    }
    if !delegated {
        let admission = onboarding::AdmissionState::from_ref(state);
        onboarding::require_admitted(&admission.pool, &admission.auth, &person).await?;
        if admission.auth.enabled() {
            onboarding::require_accepted(&admission.pool, admission.version.as_deref(), &person)
                .await?;
        }
        crate::users::snapshot(&admission, caller).await;
    }
    let mut tx = spaces::storage_transaction(&state.pool, space_id, true).await?;
    let (space, editor) = if delegated {
        (
            Space::from(crate::db::space(&mut *tx, space_id).await?),
            false,
        )
    } else {
        let facts = authorization::load_facts(&mut *tx, &person, space_id).await?;
        authorization::decide(&facts, permission.into())?;
        let editor = authorization::decide(&facts, SpacePermission::Write).is_ok();
        (Space::from(facts.space), editor)
    };
    crate::lifecycle::store::require_active(&mut *tx, space.id).await?;
    crate::lifecycle::store::require_active(&mut *tx, space.organization).await?;
    if mutation {
        // Serialize Wiki writers without blocking the space FK checks of a file
        // writer holding the conversation that own_session() will lock next.
        sqlx::query("select id from space where id=$1 for no key update")
            .bind(space_id)
            .execute(&mut *tx)
            .await?;
    }
    // Admission already checked the capability and direct space rights for a
    // delegated turn. Only the live resource association is checked again here.
    let enabled = if delegated {
        true
    } else {
        let policy = crate::agents::enablement::Policy::load_for_space(&mut *tx, &space).await?;
        policy.any_usable(&space, "team_wiki")
    };
    let mut access = Access {
        index: &super::index_pg::PostgresIndex,
        tx,
        space,
        person,
        session: None,
        agent: None,
        enabled,
        editor,
        delegated,
    };
    if delegated {
        let session = query
            .session_id
            .ok_or_else(|| invalid("The bound conversation is required."))?;
        let agent = query
            .delegation
            .agent
            .as_deref()
            .and_then(|id| Uuid::parse_str(id).ok())
            .ok_or_else(|| invalid("Invalid bound agent."))?;
        if access.own_session(session).await? != agent {
            return Err(AppError::NotFound.into());
        }
    }
    Ok(access)
}

impl Access {
    pub fn require_enabled(&self) -> Result<()> {
        if self.enabled {
            Ok(())
        } else {
            Err(AppError::NotFound.into())
        }
    }

    /// A proposal cannot name another user's conversation, nor change the bound
    /// conversation of a delegated turn. The share lock keeps the conversation, its
    /// agent snapshot and its outputs fixed until commit.
    pub async fn own_session(&mut self, session: Uuid) -> Result<Uuid> {
        if self.session.is_some_and(|bound| bound != session) {
            return Err(AppError::NotFound.into());
        }
        let (agent, name): (Uuid, String) = sqlx::query_as(
            "select agent_instance_id,agent_display_name from session_metadata where session_id=$1
             and space_id=$2 and user_id=$3 and deletion_id is null for share",
        )
        .bind(session)
        .bind(self.space.id)
        .bind(&self.person)
        .fetch_optional(&mut *self.tx)
        .await?
        .ok_or(AppError::NotFound)?;
        self.session = Some(session);
        self.agent = Some((agent, name));
        Ok(agent)
    }
}
