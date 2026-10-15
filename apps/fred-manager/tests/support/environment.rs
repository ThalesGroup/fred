// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use fred_manager::fga::Fga;
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
    let postgres = std::env::var("FRED_MANAGER_IT_POSTGRES").expect(IGNORE);
    let openfga = std::env::var("FRED_MANAGER_IT_OPENFGA").expect(IGNORE);
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
    .initialize(&pool, false)
    .await
    .unwrap();
    Env {
        pool,
        fga,
        openfga,
        store: name,
    }
}
