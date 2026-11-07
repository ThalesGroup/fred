// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use sqlx::PgPool;
use uuid::Uuid;
#[path = "support/database.rs"]
mod database;

async fn organization(pool: &PgPool, limit: i64) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query(
        "insert into space(id,kind,name,organization_id) values($1,'organization',$1::text,$1)",
    )
    .bind(id)
    .execute(pool)
    .await
    .unwrap();
    sqlx::query("insert into storage_budget(space_id,scope,limit_bytes,used_bytes,reserved_bytes) values($1,'local',$2,0,0),($1,'organization_total',$2,0,0)").bind(id).bind(limit).execute(pool).await.unwrap();
    id
}
async fn document(pool: &PgPool, org: Uuid, id: Uuid, size: i64) -> Result<(), sqlx::Error> {
    sqlx::query("select fixture_document($1,$2,$1::text,'text/plain',$3,repeat('a',64),'alice',$1::text,$2)")
        .bind(id).bind(org).bind(size).execute(pool).await?;
    Ok(())
}
fn constraint(error: sqlx::Error) {
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some("23514")
    );
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL"]
async fn concurrent_publications_cannot_overdraw_either_budget() {
    let pool = database::database().await;
    let org = organization(&pool, 100).await;
    let (a, b) = tokio::join!(
        document(&pool, org, Uuid::new_v4(), 60),
        document(&pool, org, Uuid::new_v4(), 60)
    );
    assert_ne!(a.is_ok(), b.is_ok(), "{a:?} {b:?}");
    let amounts: Vec<(i64, i64)> =
        sqlx::query_as("select used_bytes,reserved_bytes from storage_budget")
            .fetch_all(&pool)
            .await
            .unwrap();
    assert_eq!(amounts, vec![(60, 0), (60, 0)]);
    let count: i64 = sqlx::query_scalar("select count(*) from document_current")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(count, 1);
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL"]
async fn content_ownership_immutability_and_preview_source_are_enforced() {
    let pool = database::database().await;
    let org = organization(&pool, 1000).await;
    let a = Uuid::new_v4();
    let b = Uuid::new_v4();
    document(&pool, org, a, 10).await.unwrap();
    document(&pool, org, b, 20).await.unwrap();
    constraint(
        sqlx::query("update document set current_content_id=$2 where id=$1")
            .bind(a)
            .bind(b)
            .execute(&pool)
            .await
            .unwrap_err(),
    );
    constraint(
        sqlx::query("update document_content set size=99 where id=$1")
            .bind(a)
            .execute(&pool)
            .await
            .unwrap_err(),
    );
    constraint(
        sqlx::query("update document_content set cleaned_at=now() where id=$1")
            .bind(a)
            .execute(&pool)
            .await
            .unwrap_err(),
    );
    constraint(sqlx::query("insert into document_content(id,document_id,kind,source_content_id,object_key,mime,size,sha256,published_at) values(gen_random_uuid(),$1,'preview',$2,'wrong','application/pdf',3,repeat('a',64),now())").bind(a).bind(b).execute(&pool).await.unwrap_err());
    let preview = Uuid::new_v4();
    sqlx::query("insert into document_content(id,document_id,kind,source_content_id,object_key,mime,size,sha256,published_at) values($1,$2,'preview',$2,$1::text,'application/pdf',50,repeat('a',64),now())").bind(preview).bind(a).execute(&pool).await.unwrap();
    constraint(sqlx::query("insert into document_content(id,document_id,kind,source_content_id,object_key,mime,size,sha256,published_at) values(gen_random_uuid(),$1,'preview',$2,'recursive','application/pdf',1,repeat('a',64),now())").bind(a).bind(preview).execute(&pool).await.unwrap_err());
    let amounts: Vec<i64> = sqlx::query_scalar("select used_bytes from storage_budget")
        .fetch_all(&pool)
        .await
        .unwrap();
    assert_eq!(
        amounts,
        vec![30, 30],
        "technical previews are outside user quota"
    );
    // Internal hard deletion also accounts correctly before cascading content rows.
    sqlx::query("delete from document where id=$1")
        .bind(a)
        .execute(&pool)
        .await
        .unwrap();
    let amounts: Vec<i64> = sqlx::query_scalar("select used_bytes from storage_budget")
        .fetch_all(&pool)
        .await
        .unwrap();
    assert_eq!(amounts, vec![20, 20]);
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL"]
async fn bulk_retirement_updates_each_budget_once() {
    let pool = database::database().await;
    let org = organization(&pool, 1000).await;
    for _ in 0..32 {
        document(&pool, org, Uuid::new_v4(), 10).await.unwrap();
    }
    sqlx::raw_sql("create table budget_writes(scope text); create function trace_budget_write() returns trigger language plpgsql as $$ begin insert into budget_writes values(new.scope); return new; end $$; create trigger budget_write_trace after update on storage_budget for each row execute function trace_budget_write();")
        .execute(&pool).await.unwrap();
    let deletion = Uuid::new_v4();
    sqlx::query("insert into deletion(id,target_id,target_kind,organization_id,actor_subject,requested_at,due_at) values($1,$2,'organization',$2,'alice',now(),now())")
        .bind(deletion).bind(org).execute(&pool).await.unwrap();
    sqlx::query("update document set deletion_id=$1,purge_after=clock_timestamp()")
        .bind(deletion)
        .execute(&pool)
        .await
        .unwrap();
    let writes: i64 = sqlx::query_scalar("select count(*) from budget_writes")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(
        writes, 2,
        "one local and one total update, regardless of file count"
    );
    let amounts: Vec<i64> = sqlx::query_scalar("select used_bytes from storage_budget")
        .fetch_all(&pool)
        .await
        .unwrap();
    assert_eq!(amounts, vec![0, 0]);
    let queued: i64 =
        sqlx::query_scalar("select count(*) from document_content where cleanup_after is not null")
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(queued, 32);
}
