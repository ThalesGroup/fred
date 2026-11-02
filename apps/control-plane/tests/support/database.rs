// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use sqlx::{AssertSqlSafe, PgPool, postgres::PgConnectOptions};
use uuid::Uuid;

pub async fn database() -> PgPool {
    let postgres = std::env::var("CONTROL_PLANE_IT_POSTGRES")
        .expect("needs disposable admin Postgres with pgvector and psql: make test-integration");
    let name = format!("t_{}", Uuid::new_v4().simple());
    let admin = PgPool::connect(&format!("{postgres}/postgres"))
        .await
        .unwrap();
    // Roles are cluster-wide: serialize bootstrap across databases and test binaries.
    let mut guard = admin.begin().await.unwrap();
    sqlx::query("select pg_advisory_xact_lock(66723001)")
        .execute(&mut *guard)
        .await
        .unwrap();
    sqlx::query(AssertSqlSafe(format!("create database {name}")))
        .execute(&admin)
        .await
        .unwrap();
    let url = format!("{postgres}/{name}");
    let bootstrap_url = url.clone();
    let bootstrap_name = name.clone();
    let status = tokio::task::spawn_blocking(move || {
        std::process::Command::new("psql")
            .args(["-X", "-q", "-v", "ON_ERROR_STOP=1", "-v"])
            .arg(format!("database={bootstrap_name}"))
            .args([
                "-f",
                concat!(
                    env!("CARGO_MANIFEST_DIR"),
                    "/../../deploy/postgres/bootstrap.sql"
                ),
            ])
            .env("PGDATABASE", bootstrap_url)
            .output()
            .expect("psql is required for the canonical deployment bootstrap")
            .status
    })
    .await
    .unwrap();
    assert!(
        status.success(),
        "bootstrap failed: tests require an administrator and the vector extension; no privilege fallback is allowed"
    );
    // Synthetic password, only inside disposable fixtures. Consumer tests use real logins.
    sqlx::raw_sql("ALTER ROLE fred_cp PASSWORD 'it'; ALTER ROLE fred_kf PASSWORD 'it'; ALTER ROLE fred_runtime PASSWORD 'it'; ALTER ROLE fred_monitor PASSWORD 'it';")
        .execute(&admin).await.unwrap();
    guard.commit().await.unwrap();
    admin.close().await;
    let options = url
        .parse::<PgConnectOptions>()
        .unwrap()
        .username("fred_cp")
        .password("it")
        .options([("search_path", "control_plane")]);
    let pool = PgPool::connect_with(options).await.unwrap();
    sqlx::migrate!().run(&pool).await.unwrap();
    pool
}
