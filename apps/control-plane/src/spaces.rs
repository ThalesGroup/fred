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
//! interleave between check and write. Immutable placement is recorded in SQL alongside publication of OpenFGA links.

use std::{
    collections::{BTreeMap, BTreeSet},
    time::Duration,
};

use sqlx::{PgConnection, PgPool, Postgres, Transaction};
use uuid::Uuid;

use crate::{
    bootstrap, db,
    domain::{self, Folder, Permission, Role, Space, SpaceKind, SpaceRow},
    error::{AppError, AppResult},
    fga::{Fga, Guard, Link, Scope, Tuple},
    roles::SpacePermission,
};

const PARENT_REQUIRED: &str = "the user must first be a member of the parent space";
const SIBLING_NAME: &str = "a space with this name already exists here";
const INVALID_SUBJECT: &str =
    "the subject must contain 1..255 characters without whitespace, ':' or '#'";
const UNKNOWN_SUBJECT: &str = "the subject is not a known identity of the user directory";
const OWNER_ON_ORGANIZATIONS: &str = "only an organization has owners";
const PERSONAL_FIXED: &str = "a personal space has a fixed single member";
const CHILDREN_FIRST: &str = "remove dependent child roles and personal-space eligibility first";
const OWNER_NOT_FOUND: &str = "organization owner account was not found";
const ADMIN_NOT_FOUND: &str = "organization administrator account was not found";
/// Bounds the request entries, hence the directory lookups made before locking.
pub const MAX_ORGANIZATION_ADMINS: usize = 50;
/// Role grants and revocations one edit can publish: one Write takes 100 tuple
/// operations, four of which fence the platform and organization guards.
const MAX_ROLE_CHANGES: usize = 96;

async fn require(fga: &Fga, user: &str, permission: Permission, space: Uuid) -> AppResult<()> {
    if fga.check(user, permission, space).await? {
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
    fga: &Fga,
    caller: &str,
    id: Uuid,
    permission: Permission,
) -> AppResult<Space> {
    let space = load(pool, id).await?;
    in_context(in_organization(pool, fga, caller, space.organization).await?)?;
    crate::lifecycle::store::require_active(pool, id).await?;
    require(fga, caller, permission, id).await?;
    Ok(space)
}

/// The same rule on the connection that already holds the organization lock.
pub(crate) async fn authorize_locked(
    conn: &mut PgConnection,
    fga: &Fga,
    caller: &str,
    id: Uuid,
    permission: Permission,
) -> AppResult<Space> {
    let space: Space = db::space(&mut *conn, id).await?.into();
    in_context(in_organization(&mut *conn, fga, caller, space.organization).await?)?;
    crate::lifecycle::store::require_active(&mut *conn, id).await?;
    require(fga, caller, permission, id).await?;
    Ok(space)
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
/// Missing SQL rows are uncommitted/orphan tuples and confer no attachment.
pub async fn organization<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    fga: &Fga,
    user: &str,
) -> AppResult<Option<Uuid>> {
    context(ex, &fga.roles_of(user).await?).await
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

/// Call under the platform lock and after capturing its guard before a grant.
/// The same check is usable with the importer's transaction-local rows.
pub(crate) async fn may_attach<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    fga: &Fga,
    user: &str,
    target: Uuid,
) -> AppResult<()> {
    if organization(ex, fga, user)
        .await?
        .is_some_and(|id| id != target)
    {
        return Err(AppError::Conflict(
            "the user already belongs to another organization".into(),
        ));
    }
    Ok(())
}

/// Context limits the organization, while OpenFGA still evaluates all permissions.
pub async fn in_organization<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    fga: &Fga,
    user: &str,
    target: Uuid,
) -> AppResult<bool> {
    Ok(organization(ex, fga, user).await? == Some(target))
}

pub async fn require_context<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    fga: &Fga,
    user: &str,
    target: Uuid,
) -> AppResult<()> {
    if in_organization(ex, fga, user, target).await? {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

/// Search scope: the space and its ancestors, organization first, never descendants;
/// a personal space's scope is itself. `levels` only removes spaces.
pub async fn scope(
    pool: &PgPool,
    fga: &Fga,
    user: &str,
    space_id: Uuid,
    levels: Option<&[SpaceKind]>,
) -> AppResult<Vec<Uuid>> {
    let space = authorize(pool, fga, user, space_id, Permission::Read).await?;
    let kinds: &[SpaceKind] = if space.kind == SpaceKind::Personal {
        &[SpaceKind::Personal]
    } else {
        &[SpaceKind::Organization, SpaceKind::Team, SpaceKind::Project]
    };
    Ok(space
        .path
        .iter()
        .zip(kinds)
        .filter(|(_, kind)| levels.is_none_or(|l| l.contains(kind)))
        .map(|(id, _)| *id)
        .collect())
}

pub struct Membership {
    pub space: Space,
    /// Effective roles: direct ones and those descending from an ancestor.
    pub roles: Vec<Role>,
    /// Roles held only through an ancestor.
    pub inherited_roles: Vec<Role>,
}

/// Spaces where `user` holds a direct role or a descending one, for display only: every
/// decision remains an OpenFGA Check. Walks down from descending roles instead of
/// `ListObjects`, whose server-side result limit truncates silently.
pub async fn memberships(pool: &PgPool, fga: &Fga, user: &str) -> AppResult<Vec<Membership>> {
    let direct = fga.roles_of(user).await?;
    context(pool, &direct).await?;
    let ids: Vec<Uuid> = direct.iter().map(|(id, _)| *id).collect();
    let mut rows: BTreeMap<Uuid, SpaceRow> = db::active_spaces(pool, &ids)
        .await?
        .into_iter()
        .map(|r| (r.id, r))
        .collect();
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
        let children = fga.children_of(&frontier).await?;
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
async fn children(
    tx: &mut Transaction<'_, Postgres>,
    fga: &Fga,
    parent: Uuid,
) -> AppResult<Vec<SpaceRow>> {
    let ids = fga.linked_to(parent, false).await?;
    Ok(db::spaces(&mut **tx, &ids).await?)
}

/// Spaces whose roles require a content role here: children, and for an organization
/// the personal spaces it manages, so a member leaves only after their personal space.
async fn dependents(
    tx: &mut Transaction<'_, Postgres>,
    fga: &Fga,
    space: &Space,
) -> AppResult<Vec<SpaceRow>> {
    let mut ids = fga.linked_to(space.id, false).await?;
    if space.kind == SpaceKind::Organization {
        ids.extend(fga.linked_to(space.id, true).await?);
    }
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
async fn holds_parent_content(fga: &Fga, user: &str, parent: Uuid) -> AppResult<bool> {
    Ok(fga
        .direct_roles_on(user, parent)
        .await?
        .iter()
        .any(|r| r.grants_content()))
}

/// Owners of an organization are named by platform owners, its admins by its owners or
/// admins, every other role by the space's admins.
async fn may_change(fga: &Fga, caller: &str, space: &Space, role: Role) -> AppResult<()> {
    let allowed = match (role, space.kind) {
        (Role::OrganizationOwner, SpaceKind::Organization) => fga.is_platform_owner(caller).await?,
        (Role::OrganizationOwner, _) => {
            return Err(AppError::Conflict(OWNER_ON_ORGANIZATIONS.into()));
        }
        (Role::Admin, SpaceKind::Organization) => {
            fga.check(caller, Permission::Manage, space.id).await?
                || fga
                    .check_space(caller, SpacePermission::OwnOrganization, space.id)
                    .await?
        }
        _ => fga.check(caller, Permission::Manage, space.id).await?,
    };
    if allowed {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

/// Role mutations serialize with import and organization creation across organizations.
/// Lock order is always platform, then organization; both guards fence late writes.
pub(crate) async fn lock_for(
    pool: &PgPool,
    fga: &Fga,
    space: &Space,
) -> AppResult<(Transaction<'static, Postgres>, Guard)> {
    let mut tx = bootstrap::locked(pool).await?;
    lock_organization(&mut tx, space).await?;
    let scopes = vec![Scope::Platform, Scope::Organization(space.organization)];
    let guard = fga.guard(&scopes).await?;
    Ok((tx, guard))
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

/// Row and initial roles land together: the row commits only after OpenFGA accepted the
/// tuples. A failed commit leaves roles on a space id that never existed, which grant nothing.
async fn persist(
    mut tx: Transaction<'_, Postgres>,
    fga: &Fga,
    guard: &mut Guard,
    space: &Space,
    links: &[Link],
    tuples: &[Tuple<'_>],
    caller: Option<&str>,
) -> AppResult<()> {
    db::insert_space(&mut tx, space).await?;
    fga.write_created(guard, links, tuples).await?;
    for tuple in tuples {
        crate::logging::audit_relation(
            caller,
            tuple.user,
            tuple.role.as_str(),
            &format!("space:{}", tuple.space),
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
    pub owners: Vec<String>,
    pub admins: Vec<String>,
}

/// Requested changes to a managed organization; absent fields stay unchanged.
pub struct OrganizationChange<'a> {
    pub name: Option<&'a str>,
    pub owner_username: Option<&'a str>,
    /// The complete set of direct administrators.
    pub admin_usernames: Option<&'a [String]>,
}

fn validate_admins(usernames: &[String]) -> AppResult<()> {
    if usernames.is_empty() || usernames.len() > MAX_ORGANIZATION_ADMINS {
        return Err(AppError::Unprocessable(format!(
            "an organization needs 1..{MAX_ORGANIZATION_ADMINS} administrator entries"
        )));
    }
    usernames
        .iter()
        .try_for_each(|username| validate_username(username))
}

/// Distinct administrator subjects in request order; an owner named again, with its
/// subject, is not looked up twice.
async fn resolve_admins(
    directory: &crate::users::Directory<'_>,
    usernames: &[String],
    owner: Option<(&str, &str)>,
) -> AppResult<Vec<String>> {
    let mut admins: Vec<String> = Vec::new();
    let mut seen = BTreeSet::new();
    for username in usernames {
        if !seen.insert(username.as_str()) {
            continue;
        }
        let subject = match owner {
            Some((name, subject)) if name == username => subject.to_owned(),
            _ => resolve_account(directory, username, ADMIN_NOT_FOUND).await?,
        };
        if !admins.contains(&subject) {
            admins.push(subject);
        }
    }
    Ok(admins)
}

/// HTTP governance creates only the explicitly selected roles, never content access.
pub async fn create_managed_organization(
    pool: &PgPool,
    fga: &Fga,
    directory: &crate::users::Directory<'_>,
    caller: &str,
    name: &str,
    owner_username: &str,
    admin_usernames: &[String],
) -> AppResult<Space> {
    crate::platform::require_owner(fga, caller).await?;
    let name = &validate_space_name(name)?;
    validate_username(owner_username)?;
    validate_admins(admin_usernames)?;
    // Resolve before taking the global mutation lock. No directory write is performed.
    let owner = resolve_account(directory, owner_username, OWNER_NOT_FOUND).await?;
    let admins = resolve_admins(
        directory,
        admin_usernames,
        Some((owner_username, owner.as_str())),
    )
    .await?;
    let initial_roles: Vec<_> = std::iter::once((owner.as_str(), Role::OrganizationOwner))
        .chain(admins.iter().map(|admin| (admin.as_str(), Role::Admin)))
        .collect();
    let id = Uuid::new_v4();
    let org = Space::from(SpaceRow {
        id,
        kind: SpaceKind::Organization,
        name: name.to_string(),
        personal_owner: None,
        parent_id: None,
        organization_id: id,
    });
    let tuples: Vec<_> = initial_roles
        .iter()
        .map(|(user, role)| Tuple {
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
    fga.initialize_guard(Scope::Organization(id)).await?;
    let mut guard = fga
        .guard(&[Scope::Platform, Scope::Organization(id)])
        .await?;
    crate::platform::require_owner(fga, caller).await?;
    let targets: BTreeSet<_> = initial_roles.iter().map(|(user, _)| *user).collect();
    for target in targets {
        may_attach(&mut *tx, fga, target, id).await?;
    }
    persist(tx, fga, &mut guard, &org, &[], &tuples, Some(caller)).await?;
    Ok(org)
}

/// Renames an organization, makes the named owner its sole direct owner and/or makes
/// the named administrators its exact set of direct admins, with the same authority,
/// validation and locking as creation. SQL commits only after OpenFGA accepted the delta.
pub async fn update_managed_organization(
    pool: &PgPool,
    fga: &Fga,
    directory: &crate::users::Directory<'_>,
    caller: &str,
    id: Uuid,
    change: OrganizationChange<'_>,
) -> AppResult<OrganizationGovernance> {
    crate::platform::require_owner(fga, caller).await?;
    let name = change.name.map(validate_space_name).transpose()?;
    if name.is_none() && change.owner_username.is_none() && change.admin_usernames.is_none() {
        return Err(AppError::Unprocessable(
            "no organization change requested".into(),
        ));
    }
    if let Some(username) = change.owner_username {
        validate_username(username)?;
    }
    if let Some(usernames) = change.admin_usernames {
        validate_admins(usernames)?;
    }
    let new_owner = match change.owner_username {
        Some(username) => Some(resolve_account(directory, username, OWNER_NOT_FOUND).await?),
        None => None,
    };
    let new_admins = match change.admin_usernames {
        Some(usernames) => {
            let owner = change.owner_username.zip(new_owner.as_deref());
            Some(resolve_admins(directory, usernames, owner).await?)
        }
        None => None,
    };
    let (mut tx, mut guard) = lock_for(pool, fga, &load_organization(pool, id).await?).await?;
    crate::platform::require_owner(fga, caller).await?;
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
    let (owners, admins) = tokio::try_join!(
        fga.space_holders(id, Role::OrganizationOwner),
        fga.space_holders(id, Role::Admin),
    )?;
    let mut desired = Vec::new();
    if let Some(owner) = &new_owner {
        desired.push((
            Role::OrganizationOwner,
            std::slice::from_ref(owner),
            &owners,
        ));
    }
    if let Some(targets) = &new_admins {
        desired.push((Role::Admin, targets.as_slice(), &admins));
    }
    let (mut writes, mut deletes, mut attached) = (Vec::new(), Vec::new(), BTreeSet::new());
    for (role, targets, current) in &desired {
        for target in targets.iter() {
            if !current.contains(target) {
                if attached.insert(target) {
                    may_attach(&mut *tx, fga, target, id).await?;
                }
                writes.push(Tuple {
                    user: target,
                    role: *role,
                    space: id,
                });
            }
        }
        deletes.extend(
            current
                .iter()
                .filter(|holder| !targets.contains(holder))
                .map(|holder| Tuple {
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
    if writes.len() + deletes.len() > MAX_ROLE_CHANGES {
        return Err(AppError::Unprocessable(format!(
            "an edit can grant or revoke at most {MAX_ROLE_CHANGES} roles"
        )));
    }
    fga.write(&mut guard, &writes, &deletes).await?;
    for (tuple, granted) in writes
        .iter()
        .map(|t| (t, true))
        .chain(deletes.iter().map(|t| (t, false)))
    {
        crate::logging::audit_relation(
            Some(caller),
            tuple.user,
            tuple.role.as_str(),
            &format!("space:{id}"),
            granted,
        );
    }
    tx.commit().await?;
    Ok(OrganizationGovernance {
        organization,
        owners: new_owner.map_or(owners, |owner| vec![owner]),
        admins: new_admins.unwrap_or(admins),
    })
}

/// A team or project, administered by `admin`; the caller gets nothing on it.
pub async fn create_space(
    pool: &PgPool,
    fga: &Fga,
    caller: &str,
    kind: SpaceKind,
    parent_id: Uuid,
    name: String,
    admin: &str,
) -> AppResult<Space> {
    let name = validate_space_name(&name)?;
    let parent = load(pool, parent_id).await?;
    domain::check_parent(kind, Some(&parent))?;
    let mut tx = pool.begin().await?;
    lock_organization(&mut tx, &parent).await?;
    let mut guard = fga
        .guard(&[Scope::Organization(parent.organization)])
        .await?;
    authorize_locked(&mut tx, fga, caller, parent.id, Permission::Manage).await?;
    if !holds_parent_content(fga, admin, parent.id).await? {
        return Err(AppError::Conflict(PARENT_REQUIRED.into()));
    }
    require_context(&mut *tx, fga, admin, parent.organization).await?;
    if crate::lifecycle::store::reserved(&mut *tx, parent.id, &name).await?
        || children(&mut tx, fga, parent.id)
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
        fga,
        &mut guard,
        &space,
        &[Link::Parent {
            child: id,
            parent: parent.id,
        }],
        &[Tuple {
            user: admin,
            role: Role::Admin,
            space: id,
        }],
        Some(caller),
    )
    .await?;
    Ok(space)
}

pub async fn create_personal_space(
    pool: &PgPool,
    fga: &Fga,
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
    let mut guard = fga.guard(&[Scope::Organization(org.id)]).await?;
    authorize_locked(&mut tx, fga, caller, org.id, Permission::Read).await?;
    // SQL finds the one candidate; its OpenFGA link must still place it in this organization.
    if let Some(row) = db::personal_space(&mut *tx, org.id, caller).await? {
        if fga.link_of(row.id, true).await? != Some(org.id) {
            return Err(AppError::Conflict(
                "the personal space has no organization link; repair it before reuse".into(),
            ));
        }
        require(fga, caller, Permission::Read, row.id).await?;
        return Ok((Space::from(row), false));
    }
    if !fga
        .check_space(caller, SpacePermission::CreatePersonalSpace, org.id)
        .await?
    {
        return Err(AppError::Forbidden);
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
    let tuples = [
        Tuple {
            user: caller,
            role: Role::Member,
            space: id,
        },
        Tuple {
            user: caller,
            role: Role::Editor,
            space: id,
        },
    ];
    let links = [Link::Organization {
        personal: id,
        organization: org.id,
    }];
    persist(tx, fga, &mut guard, &space, &links, &tuples, Some(caller)).await?;
    Ok((space, true))
}

/// The target must be a known identity of the configured directory, checked after
/// authorization so that an unauthorized caller cannot probe which subjects exist.
pub async fn grant(
    pool: &PgPool,
    fga: &Fga,
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
    let (mut tx, mut guard) = lock_for(pool, fga, &space).await?;
    if role != Role::OrganizationOwner {
        require_context(&mut *tx, fga, caller, space.organization).await?;
    }
    may_change(fga, caller, &space, role).await?;
    // Retirement is reported only once the caller is authorized.
    crate::lifecycle::store::require_active(&mut *tx, space.id).await?;
    if !directory.exists(target).await? {
        return Err(AppError::Unprocessable(UNKNOWN_SUBJECT.into()));
    }
    if let Some(parent) = space.parent_id
        && !holds_parent_content(fga, target, parent).await?
    {
        return Err(AppError::Conflict(PARENT_REQUIRED.into()));
    }
    if role == Role::PersonalSpaceCreator {
        if space.kind != SpaceKind::Organization {
            return Err(AppError::BadRequest(
                "personal-space eligibility belongs to an organization".into(),
            ));
        }
        if !holds_parent_content(fga, target, space.id).await? {
            return Err(AppError::Conflict(
                "personal-space eligibility requires direct organization content membership".into(),
            ));
        }
    }
    may_attach(&mut *tx, fga, target, space.organization).await?;
    fga.write(
        &mut guard,
        &[Tuple {
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
    fga: &Fga,
    caller: &str,
    space_id: Uuid,
    role: Role,
    target: &str,
) -> AppResult<()> {
    let space = load(pool, space_id).await?;
    let (mut tx, mut guard) = lock_for(pool, fga, &space).await?;
    if role != Role::OrganizationOwner {
        require_context(&mut *tx, fga, caller, space.organization).await?;
    }
    if space.kind == SpaceKind::Personal {
        require(fga, caller, Permission::Manage, space.organization).await?;
    } else {
        may_change(fga, caller, &space, role).await?;
    }
    crate::lifecycle::store::require_active(&mut *tx, space.id).await?;
    let held = fga.roles_of(target).await?;
    let on_space: Vec<Role> = held
        .iter()
        .filter(|(s, _)| *s == space.id)
        .map(|(_, r)| *r)
        .collect();
    if matches!(role, Role::Admin | Role::OrganizationOwner)
        && space.kind != SpaceKind::Personal
        && on_space.contains(&role)
    {
        let holders = fga.space_holders(space.id, role).await?;
        if !holders.iter().any(|holder| holder != target) {
            return Err(AppError::Conflict(format!(
                "a non-personal space must retain an {}",
                if role == Role::Admin {
                    "administrator"
                } else {
                    "owner"
                }
            )));
        }
    }
    let dependents = dependents(&mut tx, fga, &space).await?;
    let in_child = held
        .iter()
        .any(|(s, _)| dependents.iter().any(|c| c.id == *s));
    if domain::revocation_blocked(role, &on_space, in_child) {
        return Err(AppError::Conflict(CHILDREN_FIRST.into()));
    }
    // A role that is not held still consumes the guard, but nothing is revoked or audited.
    let removes = on_space.contains(&role);
    let deletes: &[Tuple] = if removes {
        &[Tuple {
            user: target,
            role,
            space: space.id,
        }]
    } else {
        &[]
    };
    fga.write(&mut guard, &[], deletes).await?;
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

/// Fence a local SQL mutation or external dispatch while retaining the organization
/// lock. The caller commits its SQL changes before releasing this transaction.
pub async fn authorized_write(
    pool: &PgPool,
    fga: &Fga,
    caller: &str,
    space_id: Uuid,
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
    let mut guard = fga
        .guard(&[Scope::Organization(space.organization)])
        .await?;
    authorize_locked(&mut tx, fga, caller, space_id, Permission::Write).await?;
    fga.fence(&mut guard).await?;
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
    fga: &Fga,
    caller: &str,
    space_id: Uuid,
    parent_id: Option<Uuid>,
    name: String,
) -> AppResult<Folder> {
    let name = folder_name(&name)?;
    let mut tx = authorized_write(pool, fga, caller, space_id).await?;
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
