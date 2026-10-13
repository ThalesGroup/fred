//! Space and role mutations. Each one checks "a role on a space requires read on its
//! parent" and writes under one transaction-scoped advisory lock per organization, so
//! no concurrent mutation can interleave between the check and the write.

use sqlx::{PgPool, Postgres, Transaction};
use uuid::Uuid;

use crate::{
    db,
    domain::{self, Permission, Role, Space, SpaceKind},
    error::{AppError, AppResult},
    fga::{Fga, Tuple},
};

const PARENT_REQUIRED: &str = "the user must first be able to read the parent space";
const PERSONAL_FIXED: &str = "a personal space has a fixed single member";
const CHILDREN_FIRST: &str = "remove the user from the child spaces first";

async fn require(fga: &Fga, user: &str, permission: Permission, space: Uuid) -> AppResult<()> {
    if fga.check(user, permission, space).await? {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

/// Locks the organization `space` belongs to, until the transaction ends.
async fn lock_organization(tx: &mut Transaction<'_, Postgres>, space: &Space) -> AppResult<()> {
    let org = space.path[0].as_bytes();
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
    space: &Space,
    tuples: &[Tuple<'_>],
) -> AppResult<()> {
    db::insert_space(&mut tx, space).await?;
    fga.write(tuples, &[]).await?;
    tx.commit().await?;
    Ok(())
}

/// Organizations are created by an operator: no parent, so no invariant to check.
pub async fn create_organization(
    pool: &PgPool,
    fga: &Fga,
    name: &str,
    admin: &str,
) -> AppResult<Space> {
    let id = Uuid::new_v4();
    let org = Space {
        id,
        kind: SpaceKind::Organization,
        name: name.to_string(),
        parent_id: None,
        personal_owner: None,
        path: vec![id],
    };
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
    ];
    persist(pool.begin().await?, fga, &org, &tuples).await?;
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
    let parent = db::space(pool, parent_id).await?;
    domain::check_parent(kind, Some(&parent))?;
    require(fga, caller, Permission::Manage, parent.id).await?;
    let mut tx = pool.begin().await?;
    lock_organization(&mut tx, &parent).await?;
    if !fga.check(admin, Permission::Read, parent.id).await? {
        return Err(AppError::Conflict(PARENT_REQUIRED.into()));
    }
    let id = Uuid::new_v4();
    let space = Space {
        id,
        kind,
        name,
        parent_id: Some(parent.id),
        personal_owner: None,
        path: domain::space_path(Some(&parent), id),
    };
    persist(
        tx,
        fga,
        &space,
        &[Tuple {
            user: admin,
            role: Role::Admin,
            space: id,
        }],
    )
    .await?;
    Ok(space)
}

pub async fn create_personal_space(
    pool: &PgPool,
    fga: &Fga,
    caller: &str,
    organization_id: Uuid,
) -> AppResult<Space> {
    let org = db::space(pool, organization_id).await?;
    domain::check_parent(SpaceKind::Team, Some(&org))?;
    let mut tx = pool.begin().await?;
    lock_organization(&mut tx, &org).await?;
    require(fga, caller, Permission::Read, org.id).await?;
    let id = Uuid::new_v4();
    let space = Space {
        id,
        kind: SpaceKind::Team,
        name: caller.to_string(),
        parent_id: Some(org.id),
        personal_owner: Some(caller.to_string()),
        path: domain::space_path(Some(&org), id),
    };
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
    persist(tx, fga, &space, &tuples).await?;
    Ok(space)
}

pub async fn grant(
    pool: &PgPool,
    fga: &Fga,
    caller: &str,
    space_id: Uuid,
    role: Role,
    target: &str,
) -> AppResult<()> {
    let space = db::space(pool, space_id).await?;
    if space.personal_owner.is_some() {
        return Err(AppError::Conflict(PERSONAL_FIXED.into()));
    }
    require(fga, caller, Permission::Manage, space.id).await?;
    let mut tx = pool.begin().await?;
    lock_organization(&mut tx, &space).await?;
    if let Some(parent) = space.parent_id
        && !fga.check(target, Permission::Read, parent).await?
    {
        return Err(AppError::Conflict(PARENT_REQUIRED.into()));
    }
    fga.write(
        &[Tuple {
            user: target,
            role,
            space: space.id,
        }],
        &[],
    )
    .await?;
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
    let space = db::space(pool, space_id).await?;
    let manager = match (&space.personal_owner, space.parent_id) {
        (Some(_), Some(org)) => org,
        _ => space.id,
    };
    require(fga, caller, Permission::Manage, manager).await?;
    let mut tx = pool.begin().await?;
    lock_organization(&mut tx, &space).await?;
    let held = fga.roles_of(target).await?;
    let on_space: Vec<Role> = held
        .iter()
        .filter(|(s, _)| *s == space.id)
        .map(|(_, r)| *r)
        .collect();
    let children = db::child_space_ids(&mut *tx, space.id).await?;
    let in_child = held.iter().any(|(s, _)| children.contains(s));
    if domain::revocation_blocked(role, &on_space, in_child) {
        return Err(AppError::Conflict(CHILDREN_FIRST.into()));
    }
    fga.write(
        &[],
        &[Tuple {
            user: target,
            role,
            space: space.id,
        }],
    )
    .await?;
    tx.commit().await?;
    Ok(())
}
