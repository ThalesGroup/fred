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

//! SQL access. Placement columns are only ever written by inserts.

use sqlx::{PgPool, Postgres, Transaction};
use uuid::Uuid;

use crate::domain::{Document, Folder, Space, SpaceRow};

// Macros rather than consts: sqlx only accepts compile-time SQL strings.
macro_rules! space {
    () => {
        "select id, kind, name, personal_owner, parent_id, organization_id from space"
    };
}
macro_rules! folder {
    () => {
        "select id, space_id, parent_id, name, path, created_at from folder"
    };
}
macro_rules! document {
    () => {
        "select id, space_id, folder_id, name, mime, size, sha256, created_by, created_at, retrievable, retrievable_pending from document"
    };
}

/// Read-only migration verification for API startup and CLI commands.
/// Only the explicit migration command applies schema changes.
pub async fn require_initialized(pool: &PgPool) -> anyhow::Result<()> {
    use sqlx::migrate::Migrate;
    let mut connection = pool.acquire().await?;
    let applied = connection
        .list_applied_migrations("_sqlx_migrations")
        .await?;
    let migrator = sqlx::migrate!();
    anyhow::ensure!(
        connection
            .dirty_version("_sqlx_migrations")
            .await?
            .is_none(),
        "incomplete schema migration"
    );
    anyhow::ensure!(
        applied.len() == migrator.iter().count(),
        "incompatible schema"
    );
    for migration in migrator.iter() {
        anyhow::ensure!(
            applied
                .iter()
                .any(|m| m.version == migration.version && m.checksum == migration.checksum),
            "incompatible schema"
        );
    }
    Ok(())
}

/// The caller's active personal space in one organization, unique by index.
pub async fn personal_space<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    organization: Uuid,
    owner: &str,
) -> sqlx::Result<Option<SpaceRow>> {
    sqlx::query_as(concat!(
        space!(),
        " where organization_id = $1 and kind = 'personal' and personal_owner = $2 and deletion_id is null"
    ))
    .bind(organization)
    .bind(owner)
    .fetch_optional(ex)
    .await
}

/// Organizations are the only spaces resolved by name alone.
pub async fn organization_named<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    name: &str,
) -> sqlx::Result<Option<SpaceRow>> {
    sqlx::query_as(concat!(
        space!(),
        " where kind = 'organization' and name = $1"
    ))
    .bind(name)
    .fetch_optional(ex)
    .await
}

pub async fn space<'e>(ex: impl sqlx::PgExecutor<'e>, id: Uuid) -> sqlx::Result<SpaceRow> {
    sqlx::query_as(concat!(space!(), " where id = $1"))
        .bind(id)
        .fetch_one(ex)
        .await
}

/// The requested space rows.
pub async fn spaces<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    ids: &[Uuid],
) -> sqlx::Result<Vec<SpaceRow>> {
    sqlx::query_as(concat!(space!(), " where id = any($1) order by id"))
        .bind(ids)
        .fetch_all(ex)
        .await
}

/// Active business listings omit retired rows without changing operational lookups.
pub async fn active_spaces<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    ids: &[Uuid],
) -> sqlx::Result<Vec<SpaceRow>> {
    sqlx::query_as(concat!(
        space!(),
        " where id = any($1) and deletion_id is null order by id"
    ))
    .bind(ids)
    .fetch_all(ex)
    .await
}

pub async fn insert_space(tx: &mut Transaction<'_, Postgres>, s: &Space) -> sqlx::Result<()> {
    sqlx::query("insert into space (id, kind, name, personal_owner, parent_id, organization_id) values ($1, $2, $3, $4, $5, $6)")
        .bind(s.id)
        .bind(s.kind)
        .bind(&s.name)
        .bind(&s.personal_owner)
        .bind(s.parent_id)
        .bind(s.organization)
        .execute(&mut **tx)
        .await?;
    Ok(())
}

pub async fn folder<'e>(pool: impl sqlx::PgExecutor<'e>, id: Uuid) -> sqlx::Result<Folder> {
    sqlx::query_as(concat!(folder!(), " where id = $1 and deletion_id is null"))
        .bind(id)
        .fetch_one(pool)
        .await
}

pub async fn folder_ancestors<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space: Uuid,
    parent: Option<Uuid>,
) -> sqlx::Result<Vec<Folder>> {
    if let Some(parent) = parent {
        let rows = sqlx::query_as::<_, Folder>(
            "with recursive ancestors as (
                select f.*, 1 as depth from folder f where id = $1 and space_id = $2 and deletion_id is null
                union all
                select p.*, a.depth + 1 from folder p join ancestors a
                    on p.id = a.parent_id and p.space_id = a.space_id where a.depth < 15
            ) select id, space_id, parent_id, name, path, created_at from ancestors order by depth desc"
        ).bind(parent).bind(space).fetch_all(ex).await?;
        if rows.is_empty() {
            return Err(sqlx::Error::RowNotFound);
        }
        Ok(rows)
    } else {
        Ok(Vec::new())
    }
}

pub async fn insert_folder<'e>(
    pool: impl sqlx::PgExecutor<'e>,
    f: &Folder,
) -> sqlx::Result<Folder> {
    sqlx::query_as(
        "insert into folder (id, space_id, parent_id, name, path, created_at) values ($1, $2, $3, $4, $5, $6) returning id, space_id, parent_id, name, path, created_at",
    )
    .bind(f.id)
    .bind(f.space_id)
    .bind(f.parent_id)
    .bind(&f.name)
    .bind(&f.path)
    .bind(f.created_at)
    .fetch_one(pool)
    .await
}

pub async fn rename_folder<'e>(
    pool: impl sqlx::PgExecutor<'e>,
    id: Uuid,
    name: &str,
) -> sqlx::Result<()> {
    sqlx::query("update folder set name = $2 where id = $1")
        .bind(id)
        .bind(name)
        .execute(pool)
        .await?;
    Ok(())
}

/// One SQL statement removes the whole subtree or fails its document foreign key.
/// The caller holds the owning organization lock through commit.
pub async fn delete_folder<'e>(pool: impl sqlx::PgExecutor<'e>, id: Uuid) -> sqlx::Result<()> {
    sqlx::query(
        "with recursive subtree as (
        select id, space_id from folder where id = $1
        union all
        select f.id, f.space_id from folder f join subtree p
            on f.space_id = p.space_id and f.parent_id = p.id
    ) delete from folder f using subtree s where f.id = s.id",
    )
    .bind(id)
    .execute(pool)
    .await?;
    Ok(())
}

/// A live drive document. An attachment is absent here: only its conversation routes reach it.
pub async fn document<'e>(ex: impl sqlx::PgExecutor<'e>, id: Uuid) -> sqlx::Result<Document> {
    sqlx::query_as(concat!(
        document!(),
        " where id = $1 and deletion_id is null and session_id is null"
    ))
    .bind(id)
    .fetch_one(ex)
    .await
}

/// Any live document, attachments included, for processing paths that never serve a user route.
pub async fn pipeline_document<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    id: Uuid,
) -> sqlx::Result<Document> {
    sqlx::query_as(concat!(
        document!(),
        " where id = $1 and deletion_id is null"
    ))
    .bind(id)
    .fetch_one(ex)
    .await
}
