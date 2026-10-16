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
//! interleave between check and write. Placement is read from OpenFGA links.

use std::collections::{BTreeMap, BTreeSet};

use sqlx::{PgPool, Postgres, Transaction};
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
const OWNER_ON_ORGANIZATIONS: &str = "only an organization has owners";
const PERSONAL_FIXED: &str = "a personal space has a fixed single member";
const CHILDREN_FIRST: &str = "remove dependent child roles and personal-space eligibility first";

async fn require(fga: &Fga, user: &str, permission: Permission, space: Uuid) -> AppResult<()> {
    if fga.check(user, permission, space).await? {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

/// A space with its placement. Links are immutable, so reading them before locking is safe:
/// a project costs two `parent` Reads, a team or personal space one, an organization none.
pub async fn load(pool: &PgPool, fga: &Fga, id: Uuid) -> AppResult<Space> {
    place(fga, db::space(pool, id).await?).await
}

pub async fn place(fga: &Fga, row: SpaceRow) -> AppResult<Space> {
    let missing = || anyhow::anyhow!("space {} has no placement link", row.id);
    Ok(match (row.kind, row.personal_owner.is_some()) {
        (SpaceKind::Organization, _) => Space::placed(row, &[], None),
        (_, true) => {
            let org = fga.link_of(row.id, true).await?.ok_or_else(missing)?;
            Space::placed(row, &[], Some(org))
        }
        (kind, false) => {
            let parent = fga.link_of(row.id, false).await?.ok_or_else(missing)?;
            let mut ancestors = vec![parent];
            if kind == SpaceKind::Project {
                let org = fga.link_of(parent, false).await?.ok_or_else(missing)?;
                ancestors.insert(0, org);
            }
            Space::placed(row, &ancestors, None)
        }
    })
}

/// I23: attachment is derived from direct roles on committed spaces, including
/// governance-only roles. SQL stores no duplicate membership or permission matrix.
/// Read every page and placement; stale tuples on uncommitted spaces grant nothing.
pub async fn organization<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    fga: &Fga,
    user: &str,
) -> AppResult<Option<Uuid>> {
    let roles = fga.roles_of(user).await?;
    let ids: Vec<_> = roles.iter().map(|(id, _)| *id).collect();
    let rows = db::spaces(ex, &ids).await?;
    let mut organization = None;
    let mut pending = tokio::task::JoinSet::new();
    let mut rows = rows.into_iter();
    // Independent placements overlap, with a fixed per-resolution concurrency cap.
    // place() still resolves a project's parent before its organization.
    loop {
        while pending.len() < 32 {
            let Some(row) = rows.next() else { break };
            let fga = fga.clone();
            pending.spawn(async move { place(&fga, row).await });
        }
        let Some(result) = pending.join_next().await else {
            break;
        };
        let space = result.map_err(anyhow::Error::from)??;
        if organization.is_some_and(|id| id != space.organization) {
            return Err(AppError::Conflict(
                "multiple organization attachments".into(),
            ));
        }
        organization = Some(space.organization);
    }
    Ok(organization)
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
    let space = load(pool, fga, space_id).await?;
    require_context(pool, fga, user, space.organization).await?;
    require(fga, user, Permission::Read, space.id).await?;
    let kinds: &[SpaceKind] = if space.personal_owner.is_some() {
        &[SpaceKind::Team]
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
    let ids: Vec<Uuid> = direct.iter().map(|(id, _)| *id).collect();
    let mut rows: BTreeMap<Uuid, SpaceRow> = db::spaces(pool, &ids)
        .await?
        .into_iter()
        .map(|r| (r.id, r))
        .collect();
    let mut parent = BTreeMap::new();
    let mut organization = BTreeMap::new();
    for personal in [false, true] {
        let placed: Vec<Uuid> = rows
            .values()
            .filter(|r| r.kind != SpaceKind::Organization && r.personal_owner.is_some() == personal)
            .map(|r| r.id)
            .collect();
        let links = fga.links_of(&placed, personal).await?;
        let target = if personal {
            &mut organization
        } else {
            &mut parent
        };
        target.extend(links.into_iter().filter_map(|(id, link)| Some((id, link?))));
    }
    // Resolve missing project ancestors too, including inconsistent legacy grants.
    let mut context = None;
    for row in rows.values() {
        let mut id = row.id;
        let org = if row.personal_owner.is_some() {
            *organization
                .get(&id)
                .ok_or_else(|| anyhow::anyhow!("missing organization link"))?
        } else {
            if row.kind != SpaceKind::Organization && !parent.contains_key(&id) {
                return Err(anyhow::anyhow!("missing parent link").into());
            }
            for _ in 0..2 {
                if let Some(up) = parent.get(&id).copied() {
                    id = up;
                } else if row.kind == SpaceKind::Project && id != row.id {
                    let up = fga
                        .link_of(id, false)
                        .await?
                        .ok_or_else(|| anyhow::anyhow!("missing parent link"))?;
                    parent.insert(id, up);
                    id = up;
                } else {
                    break;
                }
            }
            id
        };
        if context.is_some_and(|previous| previous != org) {
            return Err(AppError::Conflict(
                "multiple organization attachments".into(),
            ));
        }
        context = Some(org);
    }
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
            .filter(|r| r.kind == kind && r.personal_owner.is_none())
            .map(|r| r.id)
            .filter(|id| !descending(*id, &inherited).is_empty())
            .collect();
        let children = fga.children_of(&frontier).await?;
        let found: Vec<Uuid> = children
            .iter()
            .flat_map(|(_, c)| c.iter().copied())
            .collect();
        let found: BTreeMap<Uuid, SpaceRow> = db::spaces(pool, &found)
            .await?
            .into_iter()
            .map(|r| (r.id, r))
            .collect();
        for (up, kids) in children {
            let carried = descending(up, &inherited);
            for kid in kids.iter().filter(|k| found.contains_key(k)) {
                parent.insert(*kid, up);
                inherited.entry(*kid).or_default().extend(&carried);
                rows.insert(*kid, found[kid].clone());
            }
        }
    }
    let mut out: Vec<Membership> = rows
        .into_values()
        .map(|row| {
            let mut ancestors = Vec::new();
            let mut cursor = row.id;
            while let Some(&up) = parent.get(&cursor) {
                ancestors.insert(0, up);
                cursor = up;
            }
            let own: BTreeSet<Role> = direct
                .iter()
                .filter(|(s, _)| *s == row.id)
                .map(|(_, r)| *r)
                .collect();
            let reached = inherited.remove(&row.id).unwrap_or_default();
            let org = organization.get(&row.id).copied();
            Membership {
                roles: own.union(&reached).copied().collect(),
                inherited_roles: reached.difference(&own).copied().collect(),
                space: Space::placed(row, &ancestors, org),
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
    Ok(db::spaces(&mut **tx, &ids).await?)
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
        (Role::Owner, SpaceKind::Organization) => fga.is_platform_owner(caller).await?,
        (Role::Owner, _) => return Err(AppError::Conflict(OWNER_ON_ORGANIZATIONS.into())),
        (Role::Admin, SpaceKind::Organization) => {
            fga.check(caller, Permission::Manage, space.id).await?
                || fga
                    .check_space(caller, SpacePermission::Own, space.id)
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
async fn lock_for(
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
    let org = space.organization.as_bytes();
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

/// Organizations are created by an operator; the first person must be unattached.
/// The first person becomes owner, admin and member: technical and business roles may be
/// held by the same person.
pub async fn create_organization(
    pool: &PgPool,
    fga: &Fga,
    name: &str,
    admin: &str,
) -> AppResult<Space> {
    let id = Uuid::new_v4();
    let org = Space::placed(
        SpaceRow {
            id,
            kind: SpaceKind::Organization,
            name: name.to_string(),
            personal_owner: None,
        },
        &[],
        None,
    );
    let tuples = [
        Tuple {
            user: admin,
            role: Role::Admin,
            space: id,
        },
        Tuple {
            user: admin,
            role: Role::Member,
            space: id,
        },
        Tuple {
            user: admin,
            role: Role::Owner,
            space: id,
        },
    ];
    let mut tx = bootstrap::locked(pool).await?;
    fga.initialize_guard(Scope::Organization(id)).await?;
    let mut guard = fga
        .guard(&[Scope::Platform, Scope::Organization(id)])
        .await?;
    may_attach(&mut *tx, fga, admin, id).await?;
    persist(tx, fga, &mut guard, &org, &[], &tuples, None).await?;
    Ok(org)
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
    let parent = load(pool, fga, parent_id).await?;
    domain::check_parent(kind, Some(&parent))?;
    let mut tx = pool.begin().await?;
    lock_organization(&mut tx, &parent).await?;
    let mut guard = fga
        .guard(&[Scope::Organization(parent.organization)])
        .await?;
    require_context(&mut *tx, fga, caller, parent.organization).await?;
    require(fga, caller, Permission::Manage, parent.id).await?;
    if !holds_parent_content(fga, admin, parent.id).await? {
        return Err(AppError::Conflict(PARENT_REQUIRED.into()));
    }
    require_context(&mut *tx, fga, admin, parent.organization).await?;
    if children(&mut tx, fga, parent.id)
        .await?
        .iter()
        .any(|c| c.name == name)
    {
        return Err(AppError::Conflict(SIBLING_NAME.into()));
    }
    let id = Uuid::new_v4();
    let space = Space::placed(
        SpaceRow {
            id,
            kind,
            name,
            personal_owner: None,
        },
        &parent.path,
        None,
    );
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
    let org = load(pool, fga, organization_id).await?;
    domain::check_parent(SpaceKind::Team, Some(&org))?;
    let mut tx = pool.begin().await?;
    lock_organization(&mut tx, &org).await?;
    let mut guard = fga.guard(&[Scope::Organization(org.id)]).await?;
    require_context(&mut *tx, fga, caller, org.id).await?;
    require(fga, caller, Permission::Read, org.id).await?;
    let personal = fga.linked_to(org.id, true).await?;
    if let Some(row) = db::spaces(&mut *tx, &personal)
        .await?
        .into_iter()
        .find(|s| s.personal_owner.as_deref() == Some(caller))
    {
        require(fga, caller, Permission::Read, row.id).await?;
        return Ok((Space::placed(row, &[], Some(org.id)), false));
    }
    if !fga
        .check_space(caller, SpacePermission::CreatePersonalSpace, org.id)
        .await?
    {
        return Err(AppError::Forbidden);
    }
    let id = Uuid::new_v4();
    let space = Space::placed(
        SpaceRow {
            id,
            kind: SpaceKind::Team,
            name: caller.to_string(),
            personal_owner: Some(caller.to_string()),
        },
        &[],
        Some(org.id),
    );
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

pub async fn grant(
    pool: &PgPool,
    fga: &Fga,
    directory: Option<&crate::keycloak::Directory>,
    caller: &str,
    space_id: Uuid,
    role: Role,
    target: &str,
) -> AppResult<()> {
    let space = load(pool, fga, space_id).await?;
    if space.personal_owner.is_some() {
        return Err(AppError::Conflict(PERSONAL_FIXED.into()));
    }
    let (mut tx, mut guard) = lock_for(pool, fga, &space).await?;
    if role != Role::Owner {
        require_context(&mut *tx, fga, caller, space.organization).await?;
    }
    may_change(fga, caller, &space, role).await?;
    if role == Role::Owner {
        let directory = directory
            .ok_or_else(|| AppError::Unavailable("Keycloak directory is not configured".into()))?;
        if !directory.exists(target).await? {
            return Err(AppError::NotFound);
        }
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
    tracing::info!(actor_uid = caller, subject = target, ?role, space_id = %space.id, outcome = "granted", "authz.relation.granted");
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
    let space = load(pool, fga, space_id).await?;
    let (mut tx, mut guard) = lock_for(pool, fga, &space).await?;
    if role != Role::Owner {
        require_context(&mut *tx, fga, caller, space.organization).await?;
    }
    if space.personal_owner.is_some() {
        require(fga, caller, Permission::Manage, space.organization).await?;
    } else {
        may_change(fga, caller, &space, role).await?;
    }
    let held = fga.roles_of(target).await?;
    let on_space: Vec<Role> = held
        .iter()
        .filter(|(s, _)| *s == space.id)
        .map(|(_, r)| *r)
        .collect();
    if matches!(role, Role::Admin | Role::Owner)
        && space.personal_owner.is_none()
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
    fga.write(
        &mut guard,
        &[],
        &if on_space.contains(&role) {
            vec![Tuple {
                user: target,
                role,
                space: space.id,
            }]
        } else {
            vec![]
        },
    )
    .await?;
    crate::logging::audit_relation(
        Some(caller),
        target,
        role.as_str(),
        &format!("space:{}", space.id),
        false,
    );
    tx.commit().await?;
    tracing::info!(actor_uid = caller, subject = target, ?role, space_id = %space.id, outcome = "revoked", "authz.relation.revoked");
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
    let space = load(pool, fga, space_id).await?;
    let mut tx = pool.begin().await?;
    lock_organization(&mut tx, &space).await?;
    let mut guard = fga
        .guard(&[Scope::Organization(space.organization)])
        .await?;
    require_context(&mut *tx, fga, caller, space.organization).await?;
    require(fga, caller, Permission::Write, space_id).await?;
    fga.fence(&mut guard).await?;
    Ok(tx)
}

/// Folder creation uses the held connection for placement lookup and insertion, so
/// lock waiters cannot starve its transaction by consuming the rest of the pool.
pub async fn create_folder(
    pool: &PgPool,
    fga: &Fga,
    caller: &str,
    space_id: Uuid,
    parent_id: Option<Uuid>,
    name: String,
) -> AppResult<Folder> {
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
    let id = Uuid::new_v4();
    let folder = Folder {
        id,
        space_id,
        parent_id,
        name,
        path: domain::folder_path(parent.as_ref(), id),
    };
    db::insert_folder(&mut *tx, &folder).await?;
    tx.commit().await?;
    Ok(folder)
}
