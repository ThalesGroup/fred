// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use sqlx::{AssertSqlSafe, PgPool};
use uuid::Uuid;

#[path = "support/database.rs"]
mod database;
use database::database;

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
    let pool = database().await;
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
    let pool = database().await;
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
async fn document_publication_updates_both_storage_counters() {
    let pool = database().await;
    let [org, _, _, _] = spaces(&pool).await;
    sqlx::query("select fixture_document(p_id=>$1,p_space_id=>$1,p_name=>'existing.txt',p_mime=>'text/plain',p_size=>400,p_sha256=>repeat('a',64),p_created_by=>'alice',p_object_key=>$1::text,p_quota_owner=>$1)")
        .bind(org).execute(&pool).await.unwrap();
    let accounts: i64 = sqlx::query_scalar("select count(*) from storage_budget")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(accounts, 2);
    let usage: i64 = sqlx::query_scalar(
        "select sum(size)::bigint from document_current where quota_owner=$1 and deletion_id is null",
    )
    .bind(org)
    .fetch_one(&pool)
    .await
    .unwrap();
    assert_eq!(usage, 400);
    let counters: Vec<i64> = sqlx::query_scalar("select used_bytes from storage_budget")
        .fetch_all(&pool)
        .await
        .unwrap();
    assert_eq!(counters, vec![400, 400]);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn budgets_follow_space_purge_without_deleting_other_accounts() {
    let pool = database().await;
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
