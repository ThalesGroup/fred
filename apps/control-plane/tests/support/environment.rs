// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use control_plane::{db, domain::Space, fga::Fga};
use sqlx::{AssertSqlSafe, PgPool};
use std::time::Duration;
use uuid::Uuid;
const IGNORE: &str = "needs disposable Postgres and OpenFGA: make test-integration";

pub struct Env {
    pub pool: PgPool,
    pub fga: Fga,
    pub openfga: String,
    pub store: String,
}

pub async fn env() -> Env {
    let postgres = std::env::var("CONTROL_PLANE_IT_POSTGRES").expect(IGNORE);
    let openfga = std::env::var("CONTROL_PLANE_IT_OPENFGA").expect(IGNORE);
    let name = format!("t_{}", Uuid::new_v4().simple());
    let admin = PgPool::connect(&format!("{postgres}/postgres"))
        .await
        .unwrap();
    sqlx::query(AssertSqlSafe(format!("create database {name}")))
        .execute(&admin)
        .await
        .unwrap();
    let pool = PgPool::connect(&format!("{postgres}/{name}"))
        .await
        .unwrap();
    sqlx::migrate!().run(&pool).await.unwrap();
    let fga = Fga::connect(
        &openfga,
        &name,
        true,
        true,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap()
    .initialize(&pool)
    .await
    .unwrap();
    Env {
        pool,
        fga,
        openfga,
        store: name,
    }
}

/// Metadata-only fixtures exercise placement/lifecycle without fabricating production originals.
pub async fn insert_document(
    pool: &PgPool,
    d: &control_plane::domain::Document,
) -> sqlx::Result<()> {
    sqlx::query("insert into document (id,space_id,folder_id,name,mime,size,sha256,created_by,created_at,object_key,quota_owner) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$2)")
        .bind(d.id).bind(d.space_id).bind(d.folder_id).bind(&d.name).bind(&d.mime).bind(d.size).bind(&d.sha256).bind(&d.created_by).bind(d.created_at).bind(format!("fixture/{}",d.id))
        .execute(pool).await?;
    Ok(())
}

/// A space by parent and name, resolved as the importer does: organizations by name,
/// children among their parent's OpenFGA children.
pub async fn named_space(
    pool: &PgPool,
    fga: &Fga,
    parent: Option<Uuid>,
    name: &str,
) -> anyhow::Result<Option<Space>> {
    let row = match parent {
        None => db::organization_named(pool, name).await?,
        Some(parent) => {
            let ids = fga.linked_to(parent, false).await?;
            db::spaces(pool, &ids)
                .await?
                .into_iter()
                .find(|r| r.name == name)
        }
    };
    Ok(row.map(Space::from))
}
