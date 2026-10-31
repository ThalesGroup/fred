// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use control_plane::{authorization::Authorization, db, domain::Space};
use sqlx::{AssertSqlSafe, PgPool};
use uuid::Uuid;
const IGNORE: &str = "needs disposable Postgres: make test-integration";

pub struct Env {
    pub pool: PgPool,
    pub authorization: Authorization,
    subjects: OpenDirectory,
}

impl Env {
    /// A directory in which every fixture subject exists. Tests about unknown
    /// identities use their own strict identity server instead.
    pub fn subjects(&self) -> control_plane::users::Directory<'_> {
        control_plane::users::Directory::Keycloak(Some(&self.subjects.directory))
    }

    /// The same directory, owned, for spawned tasks.
    pub fn open_directory(&self) -> control_plane::keycloak::Directory {
        self.subjects.directory.clone()
    }
}

struct OpenDirectory {
    directory: control_plane::keycloak::Directory,
    task: tokio::task::JoinHandle<()>,
}
impl Drop for OpenDirectory {
    fn drop(&mut self) {
        self.task.abort();
    }
}

async fn open_directory() -> OpenDirectory {
    use axum::{
        Json, Router,
        extract::Path,
        routing::{get, post},
    };
    let app = Router::new()
        .route(
            "/realms/app/protocol/openid-connect/token",
            post(|| async {
                Json(serde_json::json!({"access_token":"fixture", "expires_in":300}))
            }),
        )
        .route(
            "/admin/realms/app/users/{id}",
            get(|Path(id): Path<String>| async move {
                Json(serde_json::json!({"id":id, "username":id}))
            }),
        );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let realm = format!("http://{}/realms/app", listener.local_addr().unwrap());
    let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    OpenDirectory {
        directory: control_plane::keycloak::Directory::new(
            &realm,
            "control-plane",
            "fixture".into(),
        )
        .unwrap(),
        task,
    }
}

pub async fn env() -> Env {
    let postgres = std::env::var("CONTROL_PLANE_IT_POSTGRES").expect(IGNORE);
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
    let authorization = Authorization::new(pool.clone());
    Env {
        pool,
        authorization,
        subjects: open_directory().await,
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
/// children among SQL placement.
pub async fn named_space(
    pool: &PgPool,
    authorization: &Authorization,
    parent: Option<Uuid>,
    name: &str,
) -> anyhow::Result<Option<Space>> {
    let row = match parent {
        None => db::organization_named(pool, name).await?,
        Some(parent) => {
            let ids = authorization.linked_to(parent, false).await?;
            db::spaces(pool, &ids)
                .await?
                .into_iter()
                .find(|r| r.name == name)
        }
    };
    Ok(row.map(Space::from))
}
