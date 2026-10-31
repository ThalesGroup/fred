// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use sqlx::{AssertSqlSafe, PgPool};
use uuid::Uuid;

async fn database(version: Option<i64>) -> PgPool {
    let postgres = std::env::var("CONTROL_PLANE_IT_POSTGRES")
        .expect("needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES");
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
    let migrator = sqlx::migrate!();
    if let Some(version) = version {
        migrator.run_to(version, &pool).await.unwrap();
    } else {
        migrator.run(&pool).await.unwrap();
    }
    pool
}

fn violation(error: sqlx::Error, code: &str) {
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some(code)
    );
}

async fn spaces(pool: &PgPool) -> [Uuid; 4] {
    let ids = std::array::from_fn(|_| Uuid::new_v4());
    sqlx::query(
        "insert into space(id,kind,name,organization_id,parent_id,personal_owner) values
        ($1,'organization',$1::text,$1,null,null),
        ($2,'team','Team',$1,$1,null),
        ($3,'project','Project',$1,$2,null),
        ($4,'personal','Personal',$1,null,'alice')",
    )
    .bind(ids[0])
    .bind(ids[1])
    .bind(ids[2])
    .bind(ids[3])
    .execute(pool)
    .await
    .unwrap();
    ids
}

async fn budget(pool: &PgPool, space: Uuid, scope: &str) -> Result<(), sqlx::Error> {
    sqlx::query("insert into storage_budget(space_id,scope,limit_bytes,used_bytes,reserved_bytes) values($1,$2,1000,0,0)")
        .bind(space).bind(scope).execute(pool).await?;
    Ok(())
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn budgets_distinguish_local_and_total_and_exclude_project_accounts() {
    let pool = database(None).await;
    let [org, team, project, personal] = spaces(&pool).await;
    for space in [org, team, personal] {
        budget(&pool, space, "local").await.unwrap();
        violation(budget(&pool, space, "local").await.unwrap_err(), "23505");
    }
    budget(&pool, org, "organization_total").await.unwrap();
    for space in [team, personal, project] {
        violation(
            budget(&pool, space, "organization_total")
                .await
                .unwrap_err(),
            "23514",
        );
    }
    violation(budget(&pool, project, "local").await.unwrap_err(), "23514");
    violation(budget(&pool, org, "other").await.unwrap_err(), "23514");
    violation(
        budget(&pool, Uuid::new_v4(), "local").await.unwrap_err(),
        "23503",
    );
    violation(
        sqlx::query("update storage_budget set space_id=$1 where space_id=$2")
            .bind(project)
            .bind(team)
            .execute(&pool)
            .await
            .unwrap_err(),
        "23514",
    );
    violation(
        sqlx::query("update storage_budget set scope='organization_total' where space_id=$1")
            .bind(team)
            .execute(&pool)
            .await
            .unwrap_err(),
        "23514",
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn budget_numbers_are_required_and_nonnegative_without_forcing_usage_below_limit() {
    let pool = database(None).await;
    let [org, _, _, _] = spaces(&pool).await;
    for (limit, used, reserved, code) in [
        (None, Some(0), Some(0), "23502"),
        (Some(1), None, Some(0), "23502"),
        (Some(1), Some(0), None, "23502"),
        (Some(0), Some(0), Some(0), "23514"),
        (Some(-1), Some(0), Some(0), "23514"),
        (Some(1), Some(-1), Some(0), "23514"),
        (Some(1), Some(0), Some(-1), "23514"),
    ] {
        violation(sqlx::query("insert into storage_budget(space_id,scope,limit_bytes,used_bytes,reserved_bytes) values($1,'local',$2,$3,$4)")
            .bind(org).bind(limit.map(i64::from)).bind(used.map(i64::from)).bind(reserved.map(i64::from))
            .execute(&pool).await.unwrap_err(), code);
    }
    violation(
        sqlx::query(
            "insert into storage_budget(space_id,scope,limit_bytes) values($1,'local',1000)",
        )
        .bind(org)
        .execute(&pool)
        .await
        .unwrap_err(),
        "23502",
    );
    budget(&pool, org, "local").await.unwrap();
    sqlx::query("update storage_budget set used_bytes=800,reserved_bytes=100,limit_bytes=500 where space_id=$1")
        .bind(org).execute(&pool).await.unwrap();
    for statement in [
        "update storage_budget set used_bytes=-1 where space_id=$1",
        "update storage_budget set reserved_bytes=-1 where space_id=$1",
        "update storage_budget set limit_bytes=0 where space_id=$1",
    ] {
        violation(
            sqlx::query(AssertSqlSafe(statement))
                .bind(org)
                .execute(&pool)
                .await
                .unwrap_err(),
            "23514",
        );
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn migration_does_not_create_zero_counters_for_existing_documents() {
    let pool = database(Some(6)).await;
    let [org, _, _, _] = spaces(&pool).await;
    sqlx::query("insert into document(id,space_id,name,mime,size,sha256,created_by,object_key,quota_owner) values($1,$1,'existing.txt','text/plain',400,repeat('a',64),'alice',$1::text,$1)")
        .bind(org).execute(&pool).await.unwrap();
    sqlx::migrate!().run(&pool).await.unwrap();
    let accounts: i64 = sqlx::query_scalar("select count(*) from storage_budget")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(accounts, 0);
    let usage: i64 = sqlx::query_scalar(
        "select sum(size)::bigint from document where quota_owner=$1 and deletion_id is null",
    )
    .bind(org)
    .fetch_one(&pool)
    .await
    .unwrap();
    assert_eq!(usage, 400);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn budgets_follow_space_purge_without_deleting_other_accounts() {
    let pool = database(None).await;
    let [org, team, project, _] = spaces(&pool).await;
    for (space, scope) in [(org, "local"), (org, "organization_total"), (team, "local")] {
        budget(&pool, space, scope).await.unwrap();
    }
    sqlx::query("delete from space where id=$1")
        .bind(project)
        .execute(&pool)
        .await
        .unwrap();
    let count: i64 = sqlx::query_scalar("select count(*) from storage_budget")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(count, 3);
    sqlx::query("delete from space where id=$1")
        .bind(team)
        .execute(&pool)
        .await
        .unwrap();
    let ids: Vec<Uuid> = sqlx::query_scalar("select space_id from storage_budget")
        .fetch_all(&pool)
        .await
        .unwrap();
    assert_eq!(ids, vec![org, org]);
}
