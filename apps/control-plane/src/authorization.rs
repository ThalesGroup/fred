// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Direct role storage and the bounded organization/team/project permission matrix.
use crate::{
    domain::{Permission, Role, Space, SpaceKind, SpaceRow},
    error::{AppError, AppResult},
    roles::{PlatformPermission, PlatformRole, SpacePermission},
};
use sqlx::PgConnection;
use uuid::Uuid;

/// Direct roles on the requested space grant permissions through this shared matrix.
pub fn grants(role: Role, permission: SpacePermission) -> bool {
    use Role::*;
    use SpacePermission::*;
    match permission {
        Read => matches!(role, Member | Editor | Analyst),
        Write => role == Editor,
        Manage => role == Owner,
        RunEvaluations | ManageEvaluationCorpus => matches!(role, Analyst | Owner),
        ReadConversationsForEvaluation => role == Analyst,
        AdministerOrganization => role == OrganizationAdmin,
        CreatePersonalSpace => role == Owner || role.grants_content(),
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

/// SQL facts shared by single-space decisions and set-based navigation. $1 is
/// the subject, $2 the business roles derived from the Rust permission matrix.
/// This contains no permission implication and never follows a parent grant.
macro_rules! subject_spaces {
    () => {
        "with subject_spaces as (
            select s.*, array_agg(r.role) as direct_roles,
                s.deletion_id is null and o.deletion_id is null
                and (p.id is null or p.deletion_id is null) as active
            from space_role_grant r join space s on s.id=r.space_id
            join space o on o.id=s.organization_id
            left join space p on p.id=s.parent_id
            where r.subject=$1
            group by s.id, o.deletion_id, p.id, p.deletion_id
        ), organization_participants as (
            select distinct organization_id from subject_spaces
            where active and kind <> 'personal' and direct_roles && $2::text[]
        ) "
    };
}
pub(crate) use subject_spaces;

/// Existing grants admit a person to Weaver; a leftover personal space is not admission.
pub async fn is_admitted<'e>(ex: impl sqlx::PgExecutor<'e>, subject: &str) -> AppResult<bool> {
    Ok(sqlx::query_scalar(concat!(
        subject_spaces!(),
        "
        select exists(select 1 from platform_role_grant where subject=$1)
            or exists(select 1 from subject_spaces where active and kind <> 'personal')"
    ))
    .bind(subject)
    .bind(roles_granting(SpacePermission::CreatePersonalSpace))
    .fetch_one(ex)
    .await?)
}

/// SQL consumers bind these roles instead of maintaining another role matrix.
pub fn roles_granting(permission: SpacePermission) -> Vec<&'static str> {
    Role::ALL
        .into_iter()
        .filter(|role| grants(*role, permission))
        .map(Role::as_str)
        .collect()
}

#[derive(Debug, sqlx::FromRow)]
pub struct SpaceFacts {
    #[sqlx(flatten)]
    pub space: SpaceRow,
    pub active: bool,
    pub in_organization: bool,
    pub organization_participant: bool,
    pub direct_roles: Vec<String>,
}

/// One coherent statement for a pool or an already locked transaction connection.
/// Organization context includes retired/governance grants; participation does not.
pub async fn load_facts<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
    id: Uuid,
) -> AppResult<SpaceFacts> {
    Ok(sqlx::query_as(concat!(subject_spaces!(), "
        select s.id, s.kind, s.name, s.personal_owner, s.parent_id, s.organization_id,
            s.deletion_id is null and o.deletion_id is null
                and (p.id is null or p.deletion_id is null) as active,
            exists(select 1 from subject_spaces a where a.organization_id=s.organization_id) as in_organization,
            exists(select 1 from organization_participants a where a.organization_id=s.organization_id) as organization_participant,
            coalesce((select a.direct_roles from subject_spaces a where a.id=s.id), array[]::text[]) as direct_roles
        from space s join space o on o.id=s.organization_id
        left join space p on p.id=s.parent_id where s.id=$3"))
        .bind(subject)
        .bind(roles_granting(SpacePermission::CreatePersonalSpace))
        .bind(id)
        .fetch_one(ex)
        .await?)
}

impl SpaceFacts {
    /// Retirement also applies to explicit platform governance of an organization.
    pub(crate) fn require_active(&self) -> AppResult<()> {
        if !self.active {
            return Err(AppError::problem(
                axum::http::StatusCode::CONFLICT,
                crate::lifecycle::store::PENDING_DELETION,
                "space is pending deletion",
            ));
        }
        Ok(())
    }
}

/// Preserve the business error precedence: outside context, retired, then denied.
/// Parent placement affects activity only, never the subject's direct permissions.
pub fn decide(facts: &SpaceFacts, permission: SpacePermission) -> AppResult<()> {
    if !facts.in_organization {
        return Err(AppError::NotFound);
    }
    facts.require_active()?;
    if (facts.space.kind == SpaceKind::Personal
        || permission == SpacePermission::CreatePersonalSpace)
        && !facts.organization_participant
    {
        return Err(AppError::Forbidden);
    }
    if permission != SpacePermission::CreatePersonalSpace
        && !facts
            .direct_roles
            .iter()
            .any(|role| Role::parse(role).is_some_and(|role| grants(role, permission)))
    {
        return Err(AppError::Forbidden);
    }
    Ok(())
}

pub async fn authorize<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
    id: Uuid,
    permission: impl Into<SpacePermission>,
) -> AppResult<Space> {
    let facts = load_facts(ex, subject, id).await?;
    decide(&facts, permission.into())?;
    Ok(facts.space.into())
}

/// An organization identifier is checked before context, lifecycle or permission.
pub async fn authorize_organization<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
    id: Uuid,
    permission: impl Into<SpacePermission>,
) -> AppResult<Space> {
    let facts = load_facts(ex, subject, id).await?;
    if facts.space.kind != SpaceKind::Organization {
        return Err(AppError::NotFound);
    }
    decide(&facts, permission.into())?;
    Ok(facts.space.into())
}

pub async fn require_platform<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
    permission: PlatformPermission,
) -> AppResult<()> {
    if check_platform(ex, subject, permission).await? {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

/// Context alone is used for grant recipients and governance, including retired roles.
pub async fn in_organization<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    user: &str,
    organization: Uuid,
) -> AppResult<bool> {
    Ok(sqlx::query_scalar("select exists(select 1 from space s join space_role_grant r on r.space_id=s.id where r.subject=$1 and s.organization_id=$2)")
        .bind(user).bind(organization).fetch_one(ex).await?)
}

pub async fn readable_path<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
    path: &[Uuid],
    levels: Option<&[SpaceKind]>,
) -> sqlx::Result<Vec<Uuid>> {
    sqlx::query_scalar("select s.id from space s where s.id=any($1) and s.deletion_id is null
        and ($3::space_kind[] is null or s.kind=any($3))
        and exists(select 1 from space_role_grant r where r.space_id=s.id and r.subject=$2 and r.role=any($4))
        order by array_position($1, s.id)")
        .bind(path).bind(subject).bind(levels).bind(roles_granting(SpacePermission::Read))
        .fetch_all(ex).await
}

pub async fn memberships<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
) -> sqlx::Result<Vec<(SpaceRow, Vec<Role>)>> {
    #[derive(sqlx::FromRow)]
    struct MembershipRow {
        #[sqlx(flatten)]
        space: SpaceRow,
        direct_roles: Vec<String>,
    }
    let rows: Vec<MembershipRow> = sqlx::query_as(concat!(subject_spaces!(), "
        select s.* from subject_spaces s where active and
        (kind <> 'personal' or exists(select 1 from organization_participants a where a.organization_id=s.organization_id))"))
        .bind(subject).bind(roles_granting(SpacePermission::CreatePersonalSpace))
        .fetch_all(ex).await?;
    Ok(rows
        .into_iter()
        .map(|row| {
            let mut roles: Vec<_> = row
                .direct_roles
                .iter()
                .filter_map(|r| Role::parse(r))
                .collect();
            roles.sort();
            (row.space, roles)
        })
        .collect())
}

pub use fred_rust_sdk::security::platform::{is_platform_admin, platform_roles};

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
pub async fn check_platform<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    user: &str,
    p: PlatformPermission,
) -> sqlx::Result<bool> {
    let required = match p {
        PlatformPermission::ListAllTeams | PlatformPermission::ManageCapabilities => {
            PlatformRole::FeatureManager
        }
        PlatformPermission::ObservePlatform => PlatformRole::PlatformObserver,
        PlatformPermission::EditPlatformPrompt => PlatformRole::PromptEditor,
        _ => PlatformRole::PlatformAdmin,
    };
    Ok(platform_roles(ex, user).await?.contains(&required))
}

pub async fn direct_roles_on<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    user: &str,
    id: Uuid,
) -> sqlx::Result<Vec<Role>> {
    let roles: Vec<String> =
        sqlx::query_scalar("select role from space_role_grant where space_id=$1 and subject=$2")
            .bind(id)
            .bind(user)
            .fetch_all(ex)
            .await?;
    Ok(roles.iter().filter_map(|role| Role::parse(role)).collect())
}

pub async fn grants_on<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    ids: &[Uuid],
) -> sqlx::Result<Vec<(Uuid, Vec<(String, Role)>)>> {
    let rows: Vec<(Uuid, String, String)> =
        sqlx::query_as("select space_id,subject,role from space_role_grant where space_id=any($1)")
            .bind(ids)
            .fetch_all(ex)
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

pub async fn agent_default_on<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    organization: Uuid,
    template: Uuid,
) -> sqlx::Result<bool> {
    sqlx::query_scalar("select exists(select 1 from agent_template_policy where organization_id=$1 and template_id=$2)").bind(organization).bind(template).fetch_one(ex).await
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

/// Decision endpoints admit a workload assertion; ordinary user APIs retain their extractor.
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
/// Preserve the verified workload identity separately from its asserted person.
pub(crate) struct RuntimeCaller(pub crate::auth::CurrentUser);
impl axum::extract::FromRequestParts<crate::api::AppState> for RuntimeCaller {
    type Rejection = axum::response::Response;
    async fn from_request_parts(
        parts: &mut axum::http::request::Parts,
        state: &crate::api::AppState,
    ) -> Result<Self, Self::Rejection> {
        use axum::response::IntoResponse;
        state
            .auth
            .authenticate_runtime(crate::auth::bearer(parts))
            .await
            .map(Self)
            .map_err(IntoResponse::into_response)
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
        let RuntimeCaller(caller) = RuntimeCaller::from_request_parts(parts, state).await?;
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
    agent_default_on(ex, space.organization, template).await
}
