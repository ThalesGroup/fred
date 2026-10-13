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

use crate::domain::{Document, Folder, Space};

// Macros rather than consts: sqlx only accepts compile-time SQL strings.
macro_rules! space {
    () => {
        "select id, kind, name, parent_id, personal_owner, path from space"
    };
}
macro_rules! folder {
    () => {
        "select id, space_id, parent_id, name, path from folder"
    };
}
macro_rules! document {
    () => {
        "select id, space_id, folder_id, name, mime, size, sha256, created_by from document"
    };
}

pub async fn space(pool: &PgPool, id: Uuid) -> sqlx::Result<Space> {
    sqlx::query_as(concat!(space!(), " where id = $1"))
        .bind(id)
        .fetch_one(pool)
        .await
}

pub async fn spaces(pool: &PgPool, ids: &[Uuid]) -> sqlx::Result<Vec<Space>> {
    sqlx::query_as(concat!(space!(), " where id = any($1) order by path"))
        .bind(ids)
        .fetch_all(pool)
        .await
}

pub async fn child_space_ids<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    parent: Uuid,
) -> sqlx::Result<Vec<Uuid>> {
    sqlx::query_scalar("select id from space where parent_id = $1")
        .bind(parent)
        .fetch_all(ex)
        .await
}

pub async fn insert_space(tx: &mut Transaction<'_, Postgres>, s: &Space) -> sqlx::Result<()> {
    sqlx::query(
        "insert into space (id, kind, name, parent_id, personal_owner, path) values ($1, $2, $3, $4, $5, $6)",
    )
    .bind(s.id)
    .bind(s.kind)
    .bind(&s.name)
    .bind(s.parent_id)
    .bind(&s.personal_owner)
    .bind(&s.path)
    .execute(&mut **tx)
    .await?;
    Ok(())
}

pub async fn folder(pool: &PgPool, id: Uuid) -> sqlx::Result<Folder> {
    sqlx::query_as(concat!(folder!(), " where id = $1"))
        .bind(id)
        .fetch_one(pool)
        .await
}

pub async fn folders(
    pool: &PgPool,
    space: Uuid,
    parent: Option<Uuid>,
) -> sqlx::Result<Vec<Folder>> {
    sqlx::query_as(concat!(
        folder!(),
        " where space_id = $1 and parent_id is not distinct from $2 order by name"
    ))
    .bind(space)
    .bind(parent)
    .fetch_all(pool)
    .await
}

pub async fn insert_folder(pool: &PgPool, f: &Folder) -> sqlx::Result<()> {
    sqlx::query(
        "insert into folder (id, space_id, parent_id, name, path) values ($1, $2, $3, $4, $5)",
    )
    .bind(f.id)
    .bind(f.space_id)
    .bind(f.parent_id)
    .bind(&f.name)
    .bind(&f.path)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn rename_folder(pool: &PgPool, id: Uuid, name: &str) -> sqlx::Result<()> {
    sqlx::query("update folder set name = $2 where id = $1")
        .bind(id)
        .bind(name)
        .execute(pool)
        .await?;
    Ok(())
}

/// Fails with a foreign-key violation while the folder holds documents or sub-folders.
pub async fn delete_folder(pool: &PgPool, id: Uuid) -> sqlx::Result<()> {
    sqlx::query("delete from folder where id = $1")
        .bind(id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn document(pool: &PgPool, id: Uuid) -> sqlx::Result<Document> {
    sqlx::query_as(concat!(document!(), " where id = $1"))
        .bind(id)
        .fetch_one(pool)
        .await
}

/// One page of a folder (or of the space root when `folder` is None), keyset on (name, id).
/// The cursor carries the last row's sort values, so deleting that row changes nothing;
/// a document renamed across the cursor between two pages may be skipped or repeated.
pub async fn documents(
    pool: &PgPool,
    space: Uuid,
    folder: Option<Uuid>,
    after: Option<(&str, Uuid)>,
    limit: i64,
) -> sqlx::Result<Vec<Document>> {
    sqlx::query_as(concat!(
        document!(),
        " where space_id = $1 and folder_id is not distinct from $2
           and ($3::text is null or (name, id) > ($3, $4))
         order by name, id limit $5"
    ))
    .bind(space)
    .bind(folder)
    .bind(after.map(|(name, _)| name))
    .bind(after.map(|(_, id)| id))
    .bind(limit)
    .fetch_all(pool)
    .await
}

pub async fn insert_document(pool: &PgPool, d: &Document) -> sqlx::Result<()> {
    sqlx::query(
        "insert into document (id, space_id, folder_id, name, mime, size, sha256, created_by)
         values ($1, $2, $3, $4, $5, $6, $7, $8)",
    )
    .bind(d.id)
    .bind(d.space_id)
    .bind(d.folder_id)
    .bind(&d.name)
    .bind(&d.mime)
    .bind(d.size)
    .bind(&d.sha256)
    .bind(&d.created_by)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn rename_document(pool: &PgPool, id: Uuid, name: &str) -> sqlx::Result<()> {
    sqlx::query("update document set name = $2 where id = $1")
        .bind(id)
        .bind(name)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn delete_document(pool: &PgPool, id: Uuid) -> sqlx::Result<()> {
    sqlx::query("delete from document where id = $1")
        .bind(id)
        .execute(pool)
        .await?;
    Ok(())
}
