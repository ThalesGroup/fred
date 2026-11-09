// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! Content writes share the transaction-scoped organization advisory lock; governance
//! takes it exclusively. Authorization is checked under that lock and retained through
//! commit, ordering content with revocation without serializing independent writers.
//! Governance also protects cross-row placement and direct-role invariants.

use std::time::Duration;

use sqlx::{PgConnection, PgPool, Postgres, Transaction};
use uuid::Uuid;

use crate::{
    authorization, bootstrap, db,
    domain::{self, Folder, Permission, Role, Space, SpaceKind, SpaceRow},
    error::{AppError, AppResult},
    roles::PlatformPermission,
    roles::SpacePermission,
};

struct RoleGrant<'a> {
    user: &'a str,
    role: Role,
    space: Uuid,
}
async fn write_grants(
    conn: &mut PgConnection,
    writes: &[RoleGrant<'_>],
    deletes: &[RoleGrant<'_>],
) -> AppResult<()> {
    for (grants, enabled) in [(deletes, false), (writes, true)] {
        for grant in grants {
            authorization::write_role(&mut *conn, grant.user, grant.role, grant.space, enabled)
                .await?;
        }
    }
    Ok(())
}

const PARENT_REQUIRED: &str = "the user must first be a member of the parent space";
const SIBLING_NAME: &str = "a space with this name already exists here";
const INVALID_SUBJECT: &str =
    "the subject must contain 1..255 characters without whitespace, ':' or '#'";
const UNKNOWN_SUBJECT: &str = "the subject is not a known identity of the user directory";
const ADMIN_ON_ORGANIZATIONS: &str = "only an organization has admins";
const PERSONAL_FIXED: &str = "a personal space has a fixed single member";
const CHILDREN_FIRST: &str = "remove dependent child roles first";
const ADMIN_NOT_FOUND: &str = "organization admin account was not found";
const OWNER_NOT_FOUND: &str = "organization owner account was not found";

/// The space row only: retirement is reported after authorization, never before.
pub async fn load(pool: &PgPool, id: Uuid) -> AppResult<Space> {
    Ok(db::space(pool, id).await?.into())
}

pub async fn require_context<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    user: &str,
    target: Uuid,
) -> AppResult<()> {
    if authorization::in_organization(ex, user, target).await? {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

/// Search scope: the space and its ancestors, organization first, never descendants;
/// each requires a direct reading role. A personal scope is itself; `levels` only narrows it.
pub async fn scope(
    pool: &PgPool,
    user: &str,
    space_id: Uuid,
    levels: Option<&[SpaceKind]>,
) -> AppResult<Vec<Uuid>> {
    let mut tx = pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let space = authorization::authorize(&mut *tx, user, space_id, Permission::Read).await?;
    let result = authorization::readable_path(&mut *tx, user, &space.path, levels).await?;
    tx.commit().await?;
    Ok(result)
}

pub struct Membership {
    pub space: Space,
    /// Roles held directly on this space.
    pub roles: Vec<Role>,
}

/// Display active spaces with direct roles; access checks remain separate.
pub async fn memberships(pool: &PgPool, user: &str) -> AppResult<Vec<Membership>> {
    let mut out: Vec<Membership> = authorization::memberships(pool, user)
        .await?
        .into_iter()
        .map(|(row, roles)| Membership {
            space: row.into(),
            roles,
        })
        .collect();
    out.sort_by(|a, b| a.space.path.cmp(&b.space.path));
    Ok(out)
}

/// Committed children only: a rolled-back creation leaves links to an id SQL never had.
async fn children(tx: &mut Transaction<'_, Postgres>, parent: Uuid) -> AppResult<Vec<SpaceRow>> {
    let ids: Vec<Uuid> = sqlx::query_scalar("select id from space where parent_id=$1")
        .bind(parent)
        .fetch_all(&mut **tx)
        .await?;
    Ok(db::spaces(&mut **tx, &ids).await?)
}

/// Spaces whose roles require a content role here: children, and for an organization
/// the personal spaces it manages, so a member leaves only after their personal space.
async fn dependents(tx: &mut Transaction<'_, Postgres>, space: &Space) -> AppResult<Vec<SpaceRow>> {
    let ids: Vec<Uuid> = sqlx::query_scalar(
        "select id from space where parent_id=$1 or (kind='personal' and organization_id=$1)",
    )
    .bind(space.id)
    .fetch_all(&mut **tx)
    .await?;
    let mut rows = db::spaces(&mut **tx, &ids).await?;
    let pending: Vec<SpaceRow> = sqlx::query_as(concat!("select s.id, s.kind, s.name, s.personal_owner, s.parent_id, s.organization_id from space s join deletion d on d.target_id = s.id where ", space_target!(), " and d.status <> 'completed' and d.target_parent_id = $1"))
        .bind(space.id).fetch_all(&mut **tx).await?;
    for row in pending {
        if !rows.iter().any(|r| r.id == row.id) {
            rows.push(row);
        }
    }
    Ok(rows)
}

/// A role below the root requires a direct content role on the parent.
async fn holds_parent_content(
    conn: &mut PgConnection,
    user: &str,
    parent: Uuid,
) -> AppResult<bool> {
    Ok(authorization::roles_of(conn, user)
        .await?
        .iter()
        .any(|(id, role)| *id == parent && role.grants_content()))
}

/// Admins of an organization are named by platform admins, its owners by its admins or
/// direct owners, every other role by the space's direct owners.
async fn may_change(
    conn: &mut PgConnection,
    caller: &str,
    space: &Space,
    role: Role,
    granting: bool,
) -> AppResult<()> {
    let facts = authorization::load_facts(&mut *conn, caller, space.id).await?;
    if role == Role::OrganizationAdmin && space.kind != SpaceKind::Personal {
        facts.require_active()?;
        if space.kind != SpaceKind::Organization {
            return Err(AppError::Conflict(ADMIN_ON_ORGANIZATIONS.into()));
        }
        return authorization::require_platform(conn, caller, PlatformPermission::ManagePlatform)
            .await;
    }
    let decision = authorization::decide(&facts, SpacePermission::Manage);
    if space.kind == SpaceKind::Personal && granting {
        return match decision {
            Ok(()) | Err(AppError::Forbidden) => Err(AppError::Conflict(PERSONAL_FIXED.into())),
            Err(error) => Err(error),
        };
    }
    match decision {
        Err(AppError::Forbidden) if space.kind == SpaceKind::Personal => {
            authorization::authorize_organization(
                conn,
                caller,
                space.organization,
                Permission::Manage,
            )
            .await?;
            Ok(())
        }
        Err(AppError::Forbidden)
            if role == Role::Owner && space.kind == SpaceKind::Organization =>
        {
            authorization::decide(&facts, SpacePermission::AdministerOrganization)
        }
        decision => decision,
    }
}

/// Role mutations serialize with import and organization creation across organizations.
/// Lock order is always platform, then organization.
async fn lock_for(pool: &PgPool, space: &Space) -> AppResult<Transaction<'static, Postgres>> {
    let mut tx = bootstrap::locked(pool).await?;
    lock_organization(&mut tx, space).await?;
    Ok(tx)
}

/// Locks the organization `space` belongs to, until the transaction ends.
pub(crate) async fn lock_organization(
    tx: &mut Transaction<'_, Postgres>,
    space: &Space,
) -> AppResult<()> {
    lock_organization_id(tx, space.organization)
        .await
        .map_err(Into::into)
}

/// The durable cleanup journal retains the organization ID after retirement.
pub(crate) async fn lock_organization_id(
    tx: &mut Transaction<'_, Postgres>,
    organization: Uuid,
) -> sqlx::Result<()> {
    let org = organization.as_bytes();
    let key = i64::from_be_bytes(org[..8].try_into().expect("a uuid has 16 bytes"));
    sqlx::query("select pg_advisory_xact_lock($1)")
        .bind(key)
        .execute(&mut **tx)
        .await?;
    Ok(())
}

/// Placement and initial roles commit together or roll back together.
async fn persist(
    mut tx: Transaction<'_, Postgres>,
    space: &Space,
    grants: &[RoleGrant<'_>],
    caller: Option<&str>,
) -> AppResult<()> {
    db::insert_space(&mut tx, space).await?;
    write_grants(&mut tx, grants, &[]).await?;
    for grant in grants {
        crate::logging::audit_relation(
            caller,
            grant.user,
            grant.role.as_str(),
            &format!("space:{}", grant.space),
            true,
        );
    }
    tx.commit().await?;
    Ok(())
}

fn validate_space_name(name: &str) -> AppResult<String> {
    domain::space_name(name).ok_or_else(|| {
        AppError::Unprocessable(
            "space name must contain 1..180 characters, be nonblank and contain no control characters".into(),
        )
    })
}

/// The subject of an existing account, looked up by exact username.
async fn resolve_account(
    directory: &crate::users::Directory<'_>,
    username: &str,
    missing: &str,
) -> AppResult<String> {
    Ok(directory
        .find_username(username)
        .await?
        .ok_or_else(|| AppError::Unprocessable(missing.into()))?
        .id)
}

/// An active or retired organization row; any other space id does not exist here.
pub async fn load_organization<'e>(ex: impl sqlx::PgExecutor<'e>, id: Uuid) -> AppResult<Space> {
    let space = Space::from(db::space(ex, id).await?);
    if space.kind != SpaceKind::Organization {
        return Err(AppError::NotFound);
    }
    Ok(space)
}

/// An organization and the subjects directly holding its governance roles.
pub struct OrganizationGovernance {
    pub organization: Space,
    pub admins: Vec<String>,
    pub owners: Vec<String>,
}

/// Requested changes to a managed organization; absent fields stay unchanged.
pub struct OrganizationChange<'a> {
    pub name: Option<&'a str>,
    pub admin_username: Option<&'a str>,
    pub owner_username: Option<&'a str>,
}

/// HTTP governance creates only the two explicitly selected roles, never content access.
pub async fn create_managed_organization(
    pool: &PgPool,
    directory: &crate::users::Directory<'_>,
    caller: &str,
    name: &str,
    admin_username: &str,
    owner_username: &str,
) -> AppResult<Space> {
    authorization::require_platform(pool, caller, PlatformPermission::ManagePlatform).await?;
    let name = &validate_space_name(name)?;
    for username in [admin_username, owner_username] {
        crate::users::validate_username(username)?;
    }
    // Resolve before taking the global mutation lock. No directory write is performed.
    let admin = resolve_account(directory, admin_username, ADMIN_NOT_FOUND).await?;
    let owner = if owner_username == admin_username {
        admin.clone()
    } else {
        resolve_account(directory, owner_username, OWNER_NOT_FOUND).await?
    };
    let initial_roles = [
        (admin.as_str(), Role::OrganizationAdmin),
        (owner.as_str(), Role::Owner),
    ];
    let id = Uuid::new_v4();
    let org = Space::from(SpaceRow {
        id,
        kind: SpaceKind::Organization,
        name: name.to_string(),
        personal_owner: None,
        parent_id: None,
        organization_id: id,
    });
    let grants: Vec<_> = initial_roles
        .iter()
        .map(|(user, role)| RoleGrant {
            user,
            role: *role,
            space: id,
        })
        .collect();
    let mut tx = bootstrap::locked(pool).await?;
    // Retired names remain reserved until their normal deletion completes.
    if db::organization_named(&mut *tx, name).await?.is_some() {
        return Err(AppError::Conflict(SIBLING_NAME.into()));
    }
    authorization::require_platform(&mut *tx, caller, PlatformPermission::ManagePlatform).await?;
    persist(tx, &org, &grants, Some(caller)).await?;
    Ok(org)
}

/// Renames an organization and/or makes each named account the sole direct holder of
/// its role, with the same authority, validation and locking as creation. Roles and
/// the renamed row commit together in the same SQL transaction.
pub async fn update_managed_organization(
    pool: &PgPool,
    directory: &crate::users::Directory<'_>,
    caller: &str,
    id: Uuid,
    change: OrganizationChange<'_>,
) -> AppResult<OrganizationGovernance> {
    authorization::require_platform(pool, caller, PlatformPermission::ManagePlatform).await?;
    let name = change.name.map(validate_space_name).transpose()?;
    if name.is_none() && change.admin_username.is_none() && change.owner_username.is_none() {
        return Err(AppError::Unprocessable(
            "no organization change requested".into(),
        ));
    }
    for username in [change.admin_username, change.owner_username]
        .into_iter()
        .flatten()
    {
        crate::users::validate_username(username)?;
    }
    let admin = match change.admin_username {
        Some(username) => Some(resolve_account(directory, username, ADMIN_NOT_FOUND).await?),
        None => None,
    };
    let owner = match change.owner_username {
        Some(username) if change.admin_username == Some(username) => admin.clone(),
        Some(username) => Some(resolve_account(directory, username, OWNER_NOT_FOUND).await?),
        None => None,
    };
    let mut tx = lock_for(pool, &load_organization(pool, id).await?).await?;
    authorization::require_platform(&mut *tx, caller, PlatformPermission::ManagePlatform).await?;
    // Re-read under the lock: a concurrent rename may have committed meanwhile.
    let mut organization: Space = db::space(&mut *tx, id).await?.into();
    crate::lifecycle::store::require_active(&mut *tx, id).await?;
    if let Some(name) = &name
        && db::organization_named(&mut *tx, name)
            .await?
            .is_some_and(|other| other.id != id)
    {
        return Err(AppError::Conflict(SIBLING_NAME.into()));
    }
    // Both rosters are read under the lock, so the response describes what is committed.
    let admins = authorization::space_holders(&mut *tx, id, Role::OrganizationAdmin).await?;
    let owners = authorization::space_holders(&mut *tx, id, Role::Owner).await?;
    let mut holders = Vec::new();
    for (target, role, current) in [
        (&admin, Role::OrganizationAdmin, &admins),
        (&owner, Role::Owner, &owners),
    ] {
        if let Some(target) = target {
            holders.push((target.as_str(), role, current));
        }
    }
    let (mut writes, mut deletes) = (Vec::new(), Vec::new());
    for (target, role, current) in &holders {
        if !current.iter().any(|holder| holder == target) {
            writes.push(RoleGrant {
                user: target,
                role: *role,
                space: id,
            });
        }
        deletes.extend(
            current
                .iter()
                .filter(|holder| holder != target)
                .map(|holder| RoleGrant {
                    user: holder,
                    role: *role,
                    space: id,
                }),
        );
    }
    if let Some(name) = name {
        sqlx::query("update space set name = $1 where id = $2")
            .bind(&name)
            .bind(id)
            .execute(&mut *tx)
            .await?;
        organization.name = name;
    }
    write_grants(&mut tx, &writes, &deletes).await?;
    for (grant, granted) in writes
        .iter()
        .map(|t| (t, true))
        .chain(deletes.iter().map(|t| (t, false)))
    {
        crate::logging::audit_relation(
            Some(caller),
            grant.user,
            grant.role.as_str(),
            &format!("space:{id}"),
            granted,
        );
    }
    tx.commit().await?;
    Ok(OrganizationGovernance {
        organization,
        admins: admin.map_or(admins, |admin| vec![admin]),
        owners: owner.map_or(owners, |owner| vec![owner]),
    })
}

/// The direct parent owner creates a team or project and names its owner; the caller gets nothing.
pub async fn create_space(
    pool: &PgPool,
    caller: &str,
    kind: SpaceKind,
    parent_id: Uuid,
    name: String,
    owner: &str,
) -> AppResult<Space> {
    let name = validate_space_name(&name)?;
    let parent = load(pool, parent_id).await?;
    domain::check_parent(kind, Some(&parent))?;
    let (mut tx, parent) = governance_mutation(pool, caller, parent.id, Permission::Manage).await?;
    if !holds_parent_content(&mut tx, owner, parent.id).await? {
        return Err(AppError::Conflict(PARENT_REQUIRED.into()));
    }
    require_context(&mut *tx, owner, parent.organization).await?;
    if crate::lifecycle::store::reserved(&mut *tx, parent.id, &name).await?
        || children(&mut tx, parent.id)
            .await?
            .iter()
            .any(|c| c.name == name)
    {
        return Err(AppError::Conflict(SIBLING_NAME.into()));
    }
    let id = Uuid::new_v4();
    let space = Space::from(SpaceRow {
        id,
        kind,
        name,
        personal_owner: None,
        parent_id: Some(parent.id),
        organization_id: parent.organization,
    });
    persist(
        tx,
        &space,
        &[RoleGrant {
            user: owner,
            role: Role::Owner,
            space: id,
        }],
        Some(caller),
    )
    .await?;
    Ok(space)
}

pub async fn create_personal_space(
    pool: &PgPool,
    caller: &str,
    organization_id: Uuid,
) -> AppResult<(Space, bool)> {
    let (mut tx, org) = governance_mutation(
        pool,
        caller,
        MutationTarget::Organization(organization_id),
        SpacePermission::CreatePersonalSpace,
    )
    .await?;
    if let Some(row) = db::personal_space(&mut *tx, org.id, caller).await? {
        let space = authorization::authorize(&mut *tx, caller, row.id, Permission::Read).await?;
        return Ok((space, false));
    }
    let id = Uuid::new_v4();
    let space = Space::from(SpaceRow {
        id,
        kind: SpaceKind::Personal,
        name: caller.to_string(),
        personal_owner: Some(caller.to_string()),
        parent_id: None,
        organization_id: org.id,
    });
    let grants = [
        RoleGrant {
            user: caller,
            role: Role::Member,
            space: id,
        },
        RoleGrant {
            user: caller,
            role: Role::Editor,
            space: id,
        },
    ];
    persist(tx, &space, &grants, Some(caller)).await?;
    Ok((space, true))
}

/// The target must be a known identity of the configured directory, checked after
/// authorization so that an unauthorized caller cannot probe which subjects exist.
pub async fn grant(
    pool: &PgPool,
    directory: &crate::users::Directory<'_>,
    caller: &str,
    space_id: Uuid,
    role: Role,
    target: &str,
) -> AppResult<()> {
    if !domain::valid_subject(target) {
        return Err(AppError::Unprocessable(INVALID_SUBJECT.into()));
    }
    let space = load(pool, space_id).await?;
    let mut tx = lock_for(pool, &space).await?;
    may_change(&mut tx, caller, &space, role, true).await?;
    if !directory.exists(target).await? {
        return Err(AppError::Unprocessable(UNKNOWN_SUBJECT.into()));
    }
    if let Some(parent) = space.parent_id
        && !holds_parent_content(&mut tx, target, parent).await?
    {
        return Err(AppError::Conflict(PARENT_REQUIRED.into()));
    }
    write_grants(
        &mut tx,
        &[RoleGrant {
            user: target,
            role,
            space: space.id,
        }],
        &[],
    )
    .await?;
    crate::logging::audit_relation(
        Some(caller),
        target,
        role.as_str(),
        &format!("space:{}", space.id),
        true,
    );
    tx.commit().await?;
    Ok(())
}

/// Revoke access without deleting space-owned resources or their publications.
/// A personal space is managed from its organization: its owner's roles can be removed
/// there, never added, so an organization can always let a member go.
pub async fn revoke(
    pool: &PgPool,
    caller: &str,
    space_id: Uuid,
    role: Role,
    target: &str,
) -> AppResult<()> {
    let space = load(pool, space_id).await?;
    let mut tx = lock_for(pool, &space).await?;
    may_change(&mut tx, caller, &space, role, false).await?;
    let held = authorization::roles_of(&mut *tx, target).await?;
    let on_space: Vec<Role> = held
        .iter()
        .filter(|(s, _)| *s == space.id)
        .map(|(_, r)| *r)
        .collect();
    if matches!(role, Role::Owner | Role::OrganizationAdmin)
        && space.kind != SpaceKind::Personal
        && on_space.contains(&role)
    {
        let holders = authorization::space_holders(&mut *tx, space.id, role).await?;
        if !holders.iter().any(|holder| holder != target) {
            return Err(AppError::Conflict(format!(
                "a non-personal space must retain an {}",
                if role == Role::Owner {
                    "owner"
                } else {
                    "admin"
                }
            )));
        }
    }
    let dependents = dependents(&mut tx, &space).await?;
    let in_child = held
        .iter()
        .any(|(s, _)| dependents.iter().any(|c| c.id == *s));
    if domain::revocation_blocked(role, &on_space, in_child) {
        return Err(AppError::Conflict(CHILDREN_FIRST.into()));
    }
    // An absent role is an idempotent no-op.
    let removes = on_space.contains(&role);
    let deletes: &[RoleGrant] = if removes {
        &[RoleGrant {
            user: target,
            role,
            space: space.id,
        }]
    } else {
        &[]
    };
    write_grants(&mut tx, &[], deletes).await?;
    if removes {
        crate::logging::audit_relation(
            Some(caller),
            target,
            role.as_str(),
            &format!("space:{}", space.id),
            false,
        );
    }
    tx.commit().await?;
    Ok(())
}

/// Organization routes reject another space kind before deciding access.
pub enum MutationTarget {
    Space(Uuid),
    Organization(Uuid),
}

impl From<Uuid> for MutationTarget {
    fn from(id: Uuid) -> Self {
        Self::Space(id)
    }
}

/// Acquire the bounded shared content guard, then decide against current facts.
pub async fn authorized_mutation(
    pool: &PgPool,
    caller: &str,
    target: impl Into<MutationTarget>,
    permission: impl Into<SpacePermission>,
) -> AppResult<(Transaction<'static, Postgres>, Space)> {
    let target = target.into();
    let tx = storage_transaction(pool, target.id(), true).await?;
    authorize_mutation(tx, caller, target, permission.into()).await
}

/// Governance queues exclusively behind content already admitted.
pub async fn governance_mutation(
    pool: &PgPool,
    caller: &str,
    target: impl Into<MutationTarget>,
    permission: impl Into<SpacePermission>,
) -> AppResult<(Transaction<'static, Postgres>, Space)> {
    let target = target.into();
    let space = load(pool, target.id()).await?;
    let mut tx = pool.begin().await?;
    sqlx::query("set local lock_timeout = '5s'")
        .execute(&mut *tx)
        .await?;
    sqlx::query("set local statement_timeout = '15s'")
        .execute(&mut *tx)
        .await?;
    // Rare governance holds a connection while queued, so new shared writers cannot starve it.
    lock_organization_id(&mut tx, space.organization).await?;
    authorize_mutation(tx, caller, target, permission.into()).await
}

impl MutationTarget {
    fn id(&self) -> Uuid {
        match *self {
            Self::Space(id) | Self::Organization(id) => id,
        }
    }
}

async fn authorize_mutation(
    mut tx: Transaction<'static, Postgres>,
    caller: &str,
    target: MutationTarget,
    permission: SpacePermission,
) -> AppResult<(Transaction<'static, Postgres>, Space)> {
    let space = match target {
        MutationTarget::Space(id) => {
            authorization::authorize(&mut *tx, caller, id, permission).await?
        }
        MutationTarget::Organization(id) => {
            authorization::authorize_organization(&mut *tx, caller, id, permission).await?
        }
    };
    Ok((tx, space))
}

/// Shared organization guard for file writes; exclusive governance still fences retirement.
pub(crate) async fn storage_transaction(
    pool: &PgPool,
    space_id: Uuid,
    shared: bool,
) -> AppResult<Transaction<'static, Postgres>> {
    let space = load(pool, space_id).await?;
    let mut tx = tokio::time::timeout(Duration::from_secs(5), async {
        let key = i64::from_be_bytes(space.organization.as_bytes()[..8].try_into().unwrap());
        loop {
            let mut tx = pool.begin().await?;
            let acquired: bool = sqlx::query_scalar(if shared {
                "select pg_try_advisory_xact_lock_shared($1)"
            } else {
                "select pg_try_advisory_xact_lock($1)"
            })
            .bind(key)
            .fetch_one(&mut *tx)
            .await?;
            if acquired {
                return Ok::<_, sqlx::Error>(tx);
            }
            // Finish rollback before sleeping so contenders return their connection.
            tx.rollback().await?;
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
    })
    .await
    .map_err(|_| AppError::Unavailable("database temporarily busy".into()))??;
    sqlx::query("set local lock_timeout = '5s'")
        .execute(&mut *tx)
        .await?;
    sqlx::query("set local statement_timeout = '15s'")
        .execute(&mut *tx)
        .await?;
    Ok(tx)
}

pub(crate) fn folder_name(name: &str) -> AppResult<String> {
    domain::canonical_name(name, 255)
        .filter(|name| !name.contains(['/', '\\']))
        .ok_or_else(|| {
            AppError::Unprocessable(
                "folder name must contain 1..255 characters without slashes or control characters"
                    .into(),
            )
        })
}

/// Folder placement lookup and insertion reuse the authorized transaction's connection.
pub async fn create_folder(
    pool: &PgPool,
    caller: &str,
    space_id: Uuid,
    parent_id: Option<Uuid>,
    name: String,
) -> AppResult<Folder> {
    let name = folder_name(&name)?;
    let (mut tx, _) = authorized_mutation(pool, caller, space_id, Permission::Write).await?;
    let parent = match parent_id {
        Some(id) => Some(db::folder(&mut *tx, id).await?),
        None => None,
    };
    if parent.as_ref().is_some_and(|p| p.space_id != space_id) {
        return Err(AppError::BadRequest(
            "the parent folder belongs to another space".into(),
        ));
    }
    if parent
        .as_ref()
        .is_some_and(|p| p.path.split('/').filter(|s| !s.is_empty()).count() >= 15)
    {
        return Err(AppError::Unprocessable(
            "at most 15 folder levels are allowed".into(),
        ));
    }
    let id = Uuid::new_v4();
    let folder = Folder {
        id,
        space_id,
        parent_id,
        name: name.to_owned(),
        path: domain::folder_path(parent.as_ref(), id),
        created_at: chrono::Utc::now(),
    };
    let folder = db::insert_folder(&mut *tx, &folder).await?;
    tx.commit().await?;
    Ok(folder)
}
