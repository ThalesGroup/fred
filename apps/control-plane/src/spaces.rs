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

//! Space and role mutations. Each one checks the caller's right and "a role on a space
//! requires a direct content role on its parent", then writes, all under one
//! transaction-scoped advisory lock per organization: no concurrent mutation can
//! interleave between check and write. Placement and direct grants commit atomically in PostgreSQL.

use std::{
    collections::{BTreeMap, BTreeSet},
    time::Duration,
};

use sqlx::{PgConnection, PgPool, Postgres, Transaction};
use uuid::Uuid;

use crate::{
    authorization::{self, Authorization},
    bootstrap, db,
    domain::{self, Folder, Permission, Role, Space, SpaceKind, SpaceRow},
    error::{AppError, AppResult},
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

async fn require(
    authorization: &Authorization,
    user: &str,
    permission: Permission,
    space: Uuid,
) -> AppResult<()> {
    if authorization.check(user, permission, space).await? {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

/// The space row only: retirement is reported after authorization, never before.
pub async fn load(pool: &PgPool, id: Uuid) -> AppResult<Space> {
    Ok(db::space(pool, id).await?.into())
}

/// The business authorization of every route: a missing space, or one outside the
/// caller's organization, is 404; then a retired space is 409; then a missing
/// permission is 403. Full rule: 03-security.md.
pub async fn authorize(
    pool: &PgPool,
    authorization: &Authorization,
    caller: &str,
    id: Uuid,
    permission: Permission,
) -> AppResult<Space> {
    let space = load(pool, id).await?;
    in_context(in_organization(pool, caller, space.organization).await?)?;
    crate::lifecycle::store::require_active(pool, id).await?;
    require_personal_access(pool, caller, &space).await?;
    require(authorization, caller, permission, id).await?;
    Ok(space)
}

/// The same rule on the connection that already holds the organization lock.
pub(crate) async fn authorize_locked(
    conn: &mut PgConnection,
    caller: &str,
    id: Uuid,
    permission: Permission,
) -> AppResult<Space> {
    let space: Space = db::space(&mut *conn, id).await?.into();
    in_context(in_organization(&mut *conn, caller, space.organization).await?)?;
    crate::lifecycle::store::require_active(&mut *conn, id).await?;
    require_personal_access(&mut *conn, caller, &space).await?;
    if !authorization::check_space(&mut *conn, caller, permission.into(), id).await? {
        return Err(AppError::Forbidden);
    }
    Ok(space)
}

/// Any current business role on an active collective space admits its holder to
/// their personal space. Technical administration alone grants no business access.
pub async fn can_open_personal<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    user: &str,
    organization: Uuid,
) -> AppResult<bool> {
    let eligible: bool = sqlx::query_scalar("select exists(select 1 from space_role_grant r join space s on s.id=r.space_id where r.subject=$1 and r.role in ('owner','member','editor','analyst') and s.organization_id=$2 and s.kind <> 'personal' and s.deletion_id is null)").bind(user).bind(organization).fetch_one(ex).await?;
    Ok(eligible)
}

async fn require_personal_access<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    user: &str,
    space: &Space,
) -> AppResult<()> {
    if space.kind == SpaceKind::Personal && !can_open_personal(ex, user, space.organization).await?
    {
        return Err(AppError::Forbidden);
    }
    Ok(())
}

/// Outside the caller's organization, a space does not exist for them.
fn in_context(inside: bool) -> AppResult<()> {
    if inside {
        Ok(())
    } else {
        Err(AppError::NotFound)
    }
}

/// I23: all direct roles count, including governance and roles on retired spaces.
/// Foreign keys keep every direct grant attached to its existing space.
pub async fn organization<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    user: &str,
) -> AppResult<Option<Uuid>> {
    let organizations: Vec<Uuid> = sqlx::query_scalar("select distinct s.organization_id from space s join space_role_grant r on r.space_id=s.id where r.subject=$1").bind(user).fetch_all(ex).await?;
    if organizations.len() > 1 {
        return Err(AppError::Conflict(
            "multiple organization attachments".into(),
        ));
    }
    Ok(organizations.first().copied())
}

async fn context<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    roles: &[(Uuid, Role)],
) -> AppResult<Option<Uuid>> {
    let ids: Vec<_> = roles.iter().map(|(id, _)| *id).collect();
    let organizations: Vec<Uuid> =
        sqlx::query_scalar("select distinct organization_id from space where id = any($1)")
            .bind(&ids)
            .fetch_all(ex)
            .await?;
    if organizations.len() > 1 {
        return Err(AppError::Conflict(
            "multiple organization attachments".into(),
        ));
    }
    Ok(organizations.first().copied())
}

/// Call under the platform lock before granting a role.
/// The same check is usable with the importer's transaction-local rows.
pub(crate) async fn may_attach<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    user: &str,
    target: Uuid,
) -> AppResult<()> {
    if organization(ex, user).await?.is_some_and(|id| id != target) {
        return Err(AppError::Conflict(
            "the user already belongs to another organization".into(),
        ));
    }
    Ok(())
}

/// Organization context is independent of the requested permission.
pub async fn in_organization<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    user: &str,
    target: Uuid,
) -> AppResult<bool> {
    Ok(organization(ex, user).await? == Some(target))
}

pub async fn require_context<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    user: &str,
    target: Uuid,
) -> AppResult<()> {
    if in_organization(ex, user, target).await? {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

/// Search scope: the space and its ancestors, organization first, never descendants;
/// a personal space's scope is itself. `levels` only removes spaces.
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
    let space = authorize_locked(&mut tx, user, space_id, Permission::Read).await?;
    let rows: Vec<(Uuid, SpaceKind, String, bool)> = sqlx::query_as("select s.id,s.kind,r.role,r.space_id=s.id from space s join space_role_grant r on r.space_id=s.id or (s.kind <> 'personal' and r.space_id in (s.parent_id,s.organization_id)) where s.id=any($1) and s.deletion_id is null and r.subject=$2")
        .bind(&space.path).bind(user).fetch_all(&mut *tx).await?;
    let result = space
        .path
        .iter()
        .copied()
        .filter(|id| {
            rows.iter().any(|(candidate, kind, role, direct)| {
                candidate == id
                    && levels.is_none_or(|levels| levels.contains(kind))
                    && Role::parse(role).is_some_and(|role| {
                        authorization::grants(role, *direct, SpacePermission::Read)
                    })
            })
        })
        .collect();
    tx.commit().await?;
    Ok(result)
}

pub struct Membership {
    pub space: Space,
    /// Effective roles: direct ones and those descending from an ancestor.
    pub roles: Vec<Role>,
    /// Roles held only through an ancestor.
    pub inherited_roles: Vec<Role>,
}

/// Display memberships include direct roles and descending roles; access checks remain separate.
pub async fn memberships(
    pool: &PgPool,
    authorization: &Authorization,
    user: &str,
) -> AppResult<Vec<Membership>> {
    let direct = authorization.roles_of(user).await?;
    context(pool, &direct).await?;
    let ids: Vec<Uuid> = direct.iter().map(|(id, _)| *id).collect();
    let mut rows: BTreeMap<Uuid, SpaceRow> = db::active_spaces(pool, &ids)
        .await?
        .into_iter()
        .map(|r| (r.id, r))
        .collect();
    let personal_organizations: BTreeSet<_> = direct
        .iter()
        .filter(|(_, role)| *role == Role::Owner || role.grants_content())
        .filter_map(|(id, _)| rows.get(id))
        .filter(|row| row.kind != SpaceKind::Personal)
        .map(|row| row.organization_id)
        .collect();
    rows.retain(|_, row| {
        row.kind != SpaceKind::Personal || personal_organizations.contains(&row.organization_id)
    });
    let mut inherited: BTreeMap<Uuid, BTreeSet<Role>> = BTreeMap::new();
    let descending = |id: Uuid, inherited: &BTreeMap<Uuid, BTreeSet<Role>>| -> BTreeSet<Role> {
        direct
            .iter()
            .filter(|(s, r)| *s == id && r.descends())
            .map(|(_, r)| *r)
            .chain(inherited.get(&id).into_iter().flatten().copied())
            .collect()
    };
    // Organizations reach teams, then teams reach projects; projects have no children.
    for kind in [SpaceKind::Organization, SpaceKind::Team] {
        let frontier: Vec<Uuid> = rows
            .values()
            .filter(|r| r.kind == kind)
            .map(|r| r.id)
            .filter(|id| !descending(*id, &inherited).is_empty())
            .collect();
        let children = authorization.children_of(&frontier).await?;
        let found: Vec<Uuid> = children
            .iter()
            .flat_map(|(_, c)| c.iter().copied())
            .collect();
        let found: BTreeMap<Uuid, SpaceRow> = db::active_spaces(pool, &found)
            .await?
            .into_iter()
            .map(|r| (r.id, r))
            .collect();
        for (up, kids) in children {
            let carried = descending(up, &inherited);
            for kid in kids.iter().filter(|k| found.contains_key(k)) {
                inherited.entry(*kid).or_default().extend(&carried);
                rows.insert(*kid, found[kid].clone());
            }
        }
    }
    let mut out: Vec<Membership> = rows
        .into_values()
        .map(|row| {
            let own: BTreeSet<Role> = direct
                .iter()
                .filter(|(s, _)| *s == row.id)
                .map(|(_, r)| *r)
                .collect();
            let reached = inherited.remove(&row.id).unwrap_or_default();
            Membership {
                roles: own.union(&reached).copied().collect(),
                inherited_roles: reached.difference(&own).copied().collect(),
                space: row.into(),
            }
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

/// A role below the root requires a direct content role on the parent: inherited access
/// would let an ancestor's revocation orphan this role unnoticed.
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
/// owners, every other role by the space's owners.
async fn may_change(
    conn: &mut PgConnection,
    caller: &str,
    space: &Space,
    role: Role,
) -> AppResult<()> {
    let allowed = match (role, space.kind) {
        (Role::OrganizationAdmin, SpaceKind::Organization) => {
            authorization::platform_roles(&mut *conn, caller)
                .await?
                .contains(&crate::roles::PlatformRole::PlatformAdmin)
        }
        (Role::OrganizationAdmin, _) => {
            return Err(AppError::Conflict(ADMIN_ON_ORGANIZATIONS.into()));
        }
        (Role::Owner, SpaceKind::Organization) => {
            authorization::check_space(&mut *conn, caller, SpacePermission::Manage, space.id)
                .await?
                || authorization::check_space(
                    &mut *conn,
                    caller,
                    SpacePermission::AdministerOrganization,
                    space.id,
                )
                .await?
        }
        _ => {
            authorization::check_space(&mut *conn, caller, SpacePermission::Manage, space.id)
                .await?
        }
    };
    if allowed {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

/// Role mutations serialize with import and organization creation across organizations.
/// Lock order is always platform, then organization.
pub(crate) async fn lock_for(
    pool: &PgPool,
    space: &Space,
) -> AppResult<Transaction<'static, Postgres>> {
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

fn validate_username(username: &str) -> AppResult<()> {
    if username.is_empty()
        || username.chars().count() > 255
        || username.chars().any(char::is_control)
    {
        return Err(AppError::Unprocessable(
            "an existing username is required (1..255 characters)".into(),
        ));
    }
    Ok(())
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
pub async fn load_organization(pool: &PgPool, id: Uuid) -> AppResult<Space> {
    let space = load(pool, id).await?;
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
    authorization: &Authorization,
    directory: &crate::users::Directory<'_>,
    caller: &str,
    name: &str,
    admin_username: &str,
    owner_username: &str,
) -> AppResult<Space> {
    crate::platform::require_admin(authorization, caller).await?;
    let name = &validate_space_name(name)?;
    for username in [admin_username, owner_username] {
        validate_username(username)?;
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
    crate::platform::require_admin_locked(&mut tx, caller).await?;
    let targets: BTreeSet<_> = initial_roles.iter().map(|(user, _)| *user).collect();
    for target in targets {
        may_attach(&mut *tx, target, id).await?;
    }
    persist(tx, &org, &grants, Some(caller)).await?;
    Ok(org)
}

/// Renames an organization and/or makes each named account the sole direct holder of
/// its role, with the same authority, validation and locking as creation. Roles and
/// the renamed row commit together in the same SQL transaction.
pub async fn update_managed_organization(
    pool: &PgPool,
    authorization: &Authorization,
    directory: &crate::users::Directory<'_>,
    caller: &str,
    id: Uuid,
    change: OrganizationChange<'_>,
) -> AppResult<OrganizationGovernance> {
    crate::platform::require_admin(authorization, caller).await?;
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
        validate_username(username)?;
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
    crate::platform::require_admin_locked(&mut tx, caller).await?;
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
            may_attach(&mut *tx, target, id).await?;
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

/// A team or project, administered by `owner`; the caller gets nothing on it.
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
    let mut tx = pool.begin().await?;
    lock_organization(&mut tx, &parent).await?;
    authorize_locked(&mut tx, caller, parent.id, Permission::Manage).await?;
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
    let org = load(pool, organization_id).await?;
    if org.kind != SpaceKind::Organization {
        return Err(AppError::BadRequest(
            "a personal space must belong to an organization".into(),
        ));
    }
    let mut tx = pool.begin().await?;
    lock_organization(&mut tx, &org).await?;
    let direct = authorization::roles_of(&mut *tx, caller).await?;
    in_context(context(&mut *tx, &direct).await? == Some(org.id))?;
    crate::lifecycle::store::require_active(&mut *tx, org.id).await?;
    if !can_open_personal(&mut *tx, caller, org.id).await? {
        return Err(AppError::Forbidden);
    }
    if let Some(row) = db::personal_space(&mut *tx, org.id, caller).await? {
        if !authorization::check_space(&mut *tx, caller, SpacePermission::Read, row.id).await? {
            return Err(AppError::Forbidden);
        }
        return Ok((Space::from(row), false));
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
    if space.kind == SpaceKind::Personal {
        return Err(AppError::Conflict(PERSONAL_FIXED.into()));
    }
    let mut tx = lock_for(pool, &space).await?;
    if role != Role::OrganizationAdmin {
        require_context(&mut *tx, caller, space.organization).await?;
    }
    may_change(&mut tx, caller, &space, role).await?;
    // Retirement is reported only once the caller is authorized.
    crate::lifecycle::store::require_active(&mut *tx, space.id).await?;
    if !directory.exists(target).await? {
        return Err(AppError::Unprocessable(UNKNOWN_SUBJECT.into()));
    }
    if let Some(parent) = space.parent_id
        && !holds_parent_content(&mut tx, target, parent).await?
    {
        return Err(AppError::Conflict(PARENT_REQUIRED.into()));
    }
    may_attach(&mut *tx, target, space.organization).await?;
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
    if role != Role::OrganizationAdmin {
        require_context(&mut *tx, caller, space.organization).await?;
    }
    if space.kind == SpaceKind::Personal {
        if !authorization::check_space(
            &mut *tx,
            caller,
            SpacePermission::Manage,
            space.organization,
        )
        .await?
        {
            return Err(AppError::Forbidden);
        }
    } else {
        may_change(&mut tx, caller, &space, role).await?;
    }
    crate::lifecycle::store::require_active(&mut *tx, space.id).await?;
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

/// Authorize a local SQL mutation or external dispatch while retaining the organization
/// lock. The caller commits its SQL changes before releasing this transaction.
pub async fn authorized_write(
    pool: &PgPool,
    caller: &str,
    space_id: Uuid,
) -> AppResult<Transaction<'static, Postgres>> {
    authorized_mutation(pool, caller, space_id, Permission::Write).await
}

/// The same bounded organization lock for a mutation that `permission` authorizes,
/// such as a reader's conversation attachment.
pub(crate) async fn authorized_mutation(
    pool: &PgPool,
    caller: &str,
    space_id: Uuid,
    permission: Permission,
) -> AppResult<Transaction<'static, Postgres>> {
    let space = load(pool, space_id).await?;
    let mut tx = tokio::time::timeout(Duration::from_secs(5), async {
        let key = i64::from_be_bytes(space.organization.as_bytes()[..8].try_into().unwrap());
        loop {
            let mut tx = pool.begin().await?;
            let acquired: bool = sqlx::query_scalar("select pg_try_advisory_xact_lock($1)")
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
    authorize_locked(&mut tx, caller, space_id, permission).await?;
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
    let mut tx = authorized_write(pool, caller, space_id).await?;
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
