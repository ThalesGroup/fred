// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Direct role storage and the bounded organization/team/project permission matrix.
use crate::{
    domain::{Permission, Role, Space, SpaceKind},
    roles::{PlatformPermission, PlatformRole, SpacePermission},
};
use sqlx::{PgConnection, PgPool};
use uuid::Uuid;

#[derive(Clone)]
pub struct Authorization {
    pub pool: PgPool,
}
pub const READ_CONCURRENCY: usize = 8;

/// The role matrix is shared by probes and mutation checks, never copied by consumers.
pub fn grants(role: Role, direct: bool, permission: SpacePermission) -> bool {
    use Role::*;
    use SpacePermission::*;
    if !direct && !role.descends() {
        return false;
    }
    match permission {
        Read => matches!(role, Member | Editor | Analyst),
        Write => role == Editor,
        Manage => role == Owner,
        RunEvaluations | ManageEvaluationCorpus => matches!(role, Analyst | Owner),
        ReadConversationsForEvaluation => role == Analyst,
        AdministerOrganization => direct && role == OrganizationAdmin,
        CreatePersonalSpace => direct && (role == Owner || role.grants_content()),
    }
}
impl From<Permission> for SpacePermission {
    fn from(value: Permission) -> Self {
        match value {
            Permission::Read => Self::Read,
            Permission::Write => Self::Write,
            Permission::Manage => Self::Manage,
        }
    }
}

pub async fn check_space<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
    permission: SpacePermission,
    space: Uuid,
) -> sqlx::Result<bool> {
    let roles: Vec<(String,bool)> = sqlx::query_as("select r.role, r.space_id = s.id from space s join space_role_grant r on r.space_id = s.id or (s.kind <> 'personal' and r.space_id in (s.parent_id,s.organization_id)) where s.id = $1 and r.subject = $2")
        .bind(space).bind(subject).fetch_all(ex).await?;
    Ok(roles
        .iter()
        .any(|(role, direct)| Role::parse(role).is_some_and(|r| grants(r, *direct, permission))))
}
pub async fn platform_roles<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
) -> sqlx::Result<Vec<PlatformRole>> {
    let roles: Vec<String> =
        sqlx::query_scalar("select role from platform_role_grant where subject=$1")
            .bind(subject)
            .fetch_all(ex)
            .await?;
    Ok(roles
        .iter()
        .filter_map(|r| PlatformRole::parse(r))
        .collect())
}
pub async fn write_role(
    conn: &mut PgConnection,
    subject: &str,
    role: Role,
    space: Uuid,
    grant: bool,
) -> sqlx::Result<()> {
    let query = if grant {
        "insert into space_role_grant(space_id,subject,role) values($1,$2,$3) on conflict do nothing"
    } else {
        "delete from space_role_grant where space_id=$1 and subject=$2 and role=$3"
    };
    sqlx::query(query)
        .bind(space)
        .bind(subject)
        .bind(role.as_str())
        .execute(conn)
        .await?;
    Ok(())
}
pub async fn write_platform(
    conn: &mut PgConnection,
    subject: &str,
    role: PlatformRole,
    grant: bool,
) -> sqlx::Result<()> {
    let query = if grant {
        "insert into platform_role_grant(subject,role) values($1,$2) on conflict do nothing"
    } else {
        "delete from platform_role_grant where subject=$1 and role=$2"
    };
    sqlx::query(query)
        .bind(subject)
        .bind(role.relation())
        .execute(conn)
        .await?;
    Ok(())
}
pub async fn roles_of<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
) -> sqlx::Result<Vec<(Uuid, Role)>> {
    let rows: Vec<(Uuid, String)> =
        sqlx::query_as("select space_id,role from space_role_grant where subject=$1")
            .bind(subject)
            .fetch_all(ex)
            .await?;
    Ok(rows
        .into_iter()
        .filter_map(|(id, r)| Role::parse(&r).map(|r| (id, r)))
        .collect())
}
impl Authorization {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
    pub async fn check(&self, user: &str, p: Permission, id: Uuid) -> sqlx::Result<bool> {
        self.check_space(user, p.into(), id).await
    }
    pub async fn check_space(
        &self,
        user: &str,
        p: SpacePermission,
        id: Uuid,
    ) -> sqlx::Result<bool> {
        check_space(&self.pool, user, p, id).await
    }
    pub async fn is_platform_admin(&self, user: &str) -> sqlx::Result<bool> {
        Ok(platform_roles(&self.pool, user)
            .await?
            .contains(&PlatformRole::PlatformAdmin))
    }
    pub async fn effective_platform_roles(&self, user: &str) -> sqlx::Result<Vec<PlatformRole>> {
        // Platform governance never implies delegated business or observer roles.
        platform_roles(&self.pool, user).await
    }
    pub async fn check_platform(&self, user: &str, p: PlatformPermission) -> sqlx::Result<bool> {
        let required = match p {
            PlatformPermission::ListAllTeams | PlatformPermission::ManageCapabilities => {
                PlatformRole::FeatureManager
            }
            PlatformPermission::ObservePlatform => PlatformRole::PlatformObserver,
            PlatformPermission::EditPlatformPrompt => PlatformRole::PromptEditor,
            _ => PlatformRole::PlatformAdmin,
        };
        Ok(self
            .effective_platform_roles(user)
            .await?
            .contains(&required))
    }
    pub async fn platform_grants(&self) -> sqlx::Result<Vec<(String, PlatformRole)>> {
        platform_grants(&self.pool).await
    }
    pub async fn roles_of(&self, user: &str) -> sqlx::Result<Vec<(Uuid, Role)>> {
        roles_of(&self.pool, user).await
    }
    pub async fn direct_roles_on(&self, user: &str, id: Uuid) -> sqlx::Result<Vec<Role>> {
        Ok(self
            .roles_of(user)
            .await?
            .into_iter()
            .filter(|(s, _)| *s == id)
            .map(|(_, r)| r)
            .collect())
    }
    pub async fn space_holders(&self, id: Uuid, role: Role) -> sqlx::Result<Vec<String>> {
        sqlx::query_scalar(
            "select subject from space_role_grant where space_id=$1 and role=$2 order by subject",
        )
        .bind(id)
        .bind(role.as_str())
        .fetch_all(&self.pool)
        .await
    }
    pub async fn grants_on(&self, ids: &[Uuid]) -> sqlx::Result<Vec<(Uuid, Vec<(String, Role)>)>> {
        let rows: Vec<(Uuid, String, String)> = sqlx::query_as(
            "select space_id,subject,role from space_role_grant where space_id=any($1)",
        )
        .bind(ids)
        .fetch_all(&self.pool)
        .await?;
        Ok(ids
            .iter()
            .map(|id| {
                (
                    *id,
                    rows.iter()
                        .filter(|(s, _, _)| s == id)
                        .filter_map(|(_, u, r)| Role::parse(r).map(|r| (u.clone(), r)))
                        .collect(),
                )
            })
            .collect())
    }
    pub async fn linked_to(&self, parent: Uuid, personal: bool) -> sqlx::Result<Vec<Uuid>> {
        sqlx::query_scalar(if personal {
            "select id from space where organization_id=$1 and kind='personal'"
        } else {
            "select id from space where parent_id=$1"
        })
        .bind(parent)
        .fetch_all(&self.pool)
        .await
    }
    pub async fn children_of(&self, ids: &[Uuid]) -> sqlx::Result<Vec<(Uuid, Vec<Uuid>)>> {
        let rows: Vec<(Uuid, Uuid)> =
            sqlx::query_as("select parent_id,id from space where parent_id=any($1)")
                .bind(ids)
                .fetch_all(&self.pool)
                .await?;
        Ok(ids
            .iter()
            .map(|id| {
                (
                    *id,
                    rows.iter()
                        .filter(|(p, _)| p == id)
                        .map(|(_, c)| *c)
                        .collect(),
                )
            })
            .collect())
    }
    pub async fn agent_default_on(&self, organization: Uuid, template: Uuid) -> sqlx::Result<bool> {
        sqlx::query_scalar("select exists(select 1 from agent_template_policy where organization_id=$1 and template_id=$2)").bind(organization).bind(template).fetch_one(&self.pool).await
    }
    pub async fn can_use_agent(&self, template: Uuid, space: &Space) -> sqlx::Result<bool> {
        if !matches!(space.kind, SpaceKind::Team | SpaceKind::Personal) {
            return Ok(false);
        }
        self.agent_default_on(space.organization, template).await
    }
}
pub async fn set_agent_default_on(
    conn: &mut PgConnection,
    organization: Uuid,
    template: Uuid,
    on: bool,
) -> sqlx::Result<bool> {
    let query = if on {
        "insert into agent_template_policy(organization_id,template_id) values($1,$2) on conflict do nothing"
    } else {
        "delete from agent_template_policy where organization_id=$1 and template_id=$2"
    };
    Ok(sqlx::query(query)
        .bind(organization)
        .bind(template)
        .execute(conn)
        .await?
        .rows_affected()
        > 0)
}

/// Only decision endpoints admit a workload assertion; ordinary user APIs retain their extractor.
#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Delegation {
    pub person: Option<String>,
    pub run: Option<String>,
    pub agent: Option<String>,
}
impl Delegation {
    pub(crate) fn subject<'a>(
        &'a self,
        state: &crate::api::AppState,
        caller: &'a crate::auth::CurrentUser,
    ) -> crate::error::AppResult<&'a str> {
        use crate::error::AppError;
        use axum::http::StatusCode;
        let invalid = || {
            AppError::Unprocessable(
                "Expected a complete person/run/agent assertion with plain identifiers.".into(),
            )
        };
        if self.person.is_some() || self.run.is_some() || self.agent.is_some() {
            if !state.auth.accepts_runtime_delegation(caller) {
                return Err(AppError::problem(
                    StatusCode::FORBIDDEN,
                    "delegation_not_allowed",
                    "The authenticated caller cannot delegate.",
                ));
            }
            let (Some(person), Some(run), Some(agent)) = (&self.person, &self.run, &self.agent)
            else {
                return Err(invalid());
            };
            if !crate::domain::valid_subject(person)
                || person.contains('*')
                || ![run, agent].iter().all(|value| {
                    (1..=256).contains(&value.chars().count())
                        && !value.contains(['*', '#'])
                        && value.trim() == value.as_str()
                        && !value.chars().any(char::is_control)
                })
            {
                return Err(invalid());
            }
            Ok(person)
        } else {
            if caller.service_account
                || caller.delegation_caller
                || caller.roles.iter().any(|r| r == "service_agent")
            {
                return Err(AppError::problem(
                    StatusCode::FORBIDDEN,
                    "delegation_required",
                    "A workload must name the person, run and agent it acts for.",
                ));
            }
            if !crate::domain::valid_subject(&caller.uid) || caller.uid.contains('*') {
                return Err(invalid());
            }
            Ok(&caller.uid)
        }
    }
}
pub(crate) struct DecisionUser(pub String);
impl axum::extract::FromRequestParts<crate::api::AppState> for DecisionUser {
    type Rejection = axum::response::Response;
    async fn from_request_parts(
        parts: &mut axum::http::request::Parts,
        state: &crate::api::AppState,
    ) -> Result<Self, Self::Rejection> {
        use axum::response::IntoResponse;
        let caller = state
            .auth
            .authenticate_runtime(crate::auth::bearer(parts))
            .await
            .map_err(IntoResponse::into_response)?;
        let crate::extract::ApiQuery(query) =
            crate::extract::ApiQuery::<Delegation>::from_request_parts(parts, state)
                .await
                .map_err(IntoResponse::into_response)?;
        let subject = query
            .subject(state, &caller)
            .map_err(IntoResponse::into_response)?;
        crate::onboarding::require_accepted(
            &state.pool,
            state.onboarding.gcu_version.as_deref(),
            subject,
        )
        .await
        .map_err(IntoResponse::into_response)?;
        Ok(Self(subject.to_owned()))
    }
}

pub async fn space_holders<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space: Uuid,
    role: Role,
) -> sqlx::Result<Vec<String>> {
    sqlx::query_scalar(
        "select subject from space_role_grant where space_id=$1 and role=$2 order by subject",
    )
    .bind(space)
    .bind(role.as_str())
    .fetch_all(ex)
    .await
}

pub async fn platform_grants<'e>(
    ex: impl sqlx::PgExecutor<'e>,
) -> sqlx::Result<Vec<(String, PlatformRole)>> {
    let rows: Vec<(String, String)> =
        sqlx::query_as("select subject,role from platform_role_grant order by subject,role")
            .fetch_all(ex)
            .await?;
    Ok(rows
        .into_iter()
        .filter_map(|(u, r)| PlatformRole::parse(&r).map(|r| (u, r)))
        .collect())
}

pub async fn can_use_agent<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    template: Uuid,
    space: &Space,
) -> sqlx::Result<bool> {
    if !matches!(space.kind, SpaceKind::Team | SpaceKind::Personal) {
        return Ok(false);
    }
    sqlx::query_scalar("select exists(select 1 from agent_template_policy where organization_id=$1 and template_id=$2)").bind(space.organization).bind(template).fetch_one(ex).await
}
