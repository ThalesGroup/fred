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

async fn document(pool: &PgPool, space: Uuid) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query("insert into document(id,space_id,name,mime,size,sha256,created_by,object_key,quota_owner) values($1,$2,$1::text || '.txt','text/plain',10,repeat('a',64),'alice',$1::text,$2)")
        .bind(id).bind(space).execute(pool).await.unwrap();
    id
}

async fn folder(pool: &PgPool, space: Uuid) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query(
        "insert into folder(id,space_id,name,path) values($1,$2,$1::text,'/' || $1::text || '/')",
    )
    .bind(id)
    .bind(space)
    .execute(pool)
    .await
    .unwrap();
    id
}

async fn request(
    pool: &PgPool,
    document: Uuid,
    space: Uuid,
    folder: Option<Uuid>,
) -> Result<Uuid, sqlx::Error> {
    let id = Uuid::new_v4();
    sqlx::query("insert into document_move(id,document_id,actor,destination_space_id,destination_folder_id) values($1,$2,'alice',$3,$4)")
        .bind(id).bind(document).bind(space).bind(folder).execute(pool).await?;
    Ok(id)
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn move_request_captures_source_and_checks_destination() {
    let pool = database(None).await;
    let [org, team, project, personal] = spaces(&pool).await;
    let other = spaces(&pool).await[0];
    let target = folder(&pool, project).await;
    let doc = document(&pool, team).await;
    violation(request(&pool, doc, team, None).await.unwrap_err(), "23514");
    violation(request(&pool, doc, other, None).await.unwrap_err(), "23514");
    violation(
        request(&pool, doc, team, Some(target)).await.unwrap_err(),
        "23503",
    );
    violation(
        request(&pool, doc, project, Some(Uuid::new_v4()))
            .await
            .unwrap_err(),
        "23503",
    );
    violation(
        request(&pool, doc, Uuid::new_v4(), None).await.unwrap_err(),
        "23503",
    );
    violation(
        request(&pool, Uuid::new_v4(), project, None)
            .await
            .unwrap_err(),
        "23503",
    );
    let operation = request(&pool, doc, project, Some(target)).await.unwrap();
    let stored: (Uuid, Option<Uuid>, Uuid, Option<Uuid>, Option<Uuid>) = sqlx::query_as("select source_space_id,source_folder_id,destination_space_id,destination_folder_id,generation_id from document_move where id=$1")
        .bind(operation).fetch_one(&pool).await.unwrap();
    assert_eq!(stored, (team, None, project, Some(target), None));
    for destination in [org, personal] {
        let doc = document(&pool, project).await;
        request(&pool, doc, destination, None).await.unwrap();
    }
    let doc = document(&pool, team).await;
    let same_space_folder = folder(&pool, team).await;
    request(&pool, doc, team, Some(same_space_folder))
        .await
        .unwrap();
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn move_identity_single_active_request_and_terminal_outcome_are_protected() {
    let pool = database(None).await;
    let [org, team, project, _] = spaces(&pool).await;
    let doc = document(&pool, team).await;
    let first = request(&pool, doc, project, None).await.unwrap();
    violation(request(&pool, doc, org, None).await.unwrap_err(), "23505");
    for statement in [
        "update document_move set id=gen_random_uuid() where id=$1",
        "update document_move set document_id=gen_random_uuid() where id=$1",
        "update document_move set actor='bob' where id=$1",
        "update document_move set destination_space_id=gen_random_uuid() where id=$1",
        "update document_move set destination_folder_id=gen_random_uuid() where id=$1",
        "update document_move set source_space_id=gen_random_uuid() where id=$1",
        "update document_move set source_folder_id=gen_random_uuid() where id=$1",
        "update document_move set generation_id=gen_random_uuid() where id=$1",
        "update document_move set created_at=created_at-interval '1 day' where id=$1",
        "update document_move set phase='completed' where id=$1",
        "update document_move set phase='projecting' where id=$1",
        "update document_move set finished_at=clock_timestamp() where id=$1",
    ] {
        violation(
            sqlx::query(AssertSqlSafe(statement))
                .bind(first)
                .execute(&pool)
                .await
                .unwrap_err(),
            "23514",
        );
    }
    sqlx::query("update document_move set phase='cancelled' where id=$1")
        .bind(first)
        .execute(&pool)
        .await
        .unwrap();
    assert!(
        sqlx::query_scalar::<_, bool>(
            "select finished_at >= created_at from document_move where id=$1"
        )
        .bind(first)
        .fetch_one(&pool)
        .await
        .unwrap()
    );
    let second = request(&pool, doc, org, None).await.unwrap();
    violation(
        sqlx::query("update document_move set phase='requested',finished_at=null where id=$1")
            .bind(first)
            .execute(&pool)
            .await
            .unwrap_err(),
        "23514",
    );
    let stale = sqlx::query(
        "update document_move set phase='completed' where id=$1 and phase='projecting'",
    )
    .bind(first)
    .execute(&pool)
    .await
    .unwrap();
    assert_eq!(stale.rows_affected(), 0);
    assert_eq!(
        sqlx::query_scalar::<_, String>("select phase from document_move where id=$1")
            .bind(second)
            .fetch_one(&pool)
            .await
            .unwrap(),
        "requested"
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn requests_reject_existing_processing_and_inclusion_work() {
    let pool = database(None).await;
    let [org, team, _, _] = spaces(&pool).await;
    let processing_doc = document(&pool, team).await;
    sqlx::query("insert into document_processing(id,request_key,actor,document_id,profile,workflow_id,submission,deadline_at,profile_settings,preparation_seconds,extraction_seconds,indexing_seconds) values($1,$1,'alice',$2,'fast',$1::text,'{}',now()+interval '1 hour','{}',1,1,1)")
        .bind(Uuid::new_v4()).bind(processing_doc).execute(&pool).await.unwrap();
    violation(
        request(&pool, processing_doc, org, None).await.unwrap_err(),
        "23514",
    );
    let inclusion_doc = document(&pool, team).await;
    sqlx::query("update document set retrieval_id=id,retrieval_actor='alice',retrieval_target=true,retrieval_phase='ready',retrieval_confirmed=false where id=$1")
        .bind(inclusion_doc).execute(&pool).await.unwrap();
    violation(
        request(&pool, inclusion_doc, org, None).await.unwrap_err(),
        "23514",
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn schema_preparation_does_not_move_existing_documents_or_weaken_immutability() {
    let pool = database(Some(8)).await;
    let [org, team, _, _] = spaces(&pool).await;
    let doc = document(&pool, team).await;
    let before: serde_json::Value =
        sqlx::query_scalar("select to_jsonb(d) from document d where id=$1")
            .bind(doc)
            .fetch_one(&pool)
            .await
            .unwrap();
    sqlx::migrate!().run(&pool).await.unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from document_move")
            .fetch_one(&pool)
            .await
            .unwrap(),
        0
    );
    request(&pool, doc, org, None).await.unwrap();
    let after: serde_json::Value =
        sqlx::query_scalar("select to_jsonb(d) from document d where id=$1")
            .bind(doc)
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(before, after);
    violation(
        sqlx::query("update document set space_id=$2 where id=$1")
            .bind(doc)
            .bind(org)
            .execute(&pool)
            .await
            .unwrap_err(),
        "P0001",
    );
    sqlx::query("delete from document where id=$1")
        .bind(doc)
        .execute(&pool)
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from document_move")
            .fetch_one(&pool)
            .await
            .unwrap(),
        0
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn request_provenance_is_canonical_and_destination_history_does_not_block_purge() {
    let pool = database(None).await;
    let [org, team, project, _] = spaces(&pool).await;
    let doc = document(&pool, org).await;
    let target = folder(&pool, project).await;
    let id = Uuid::new_v4();
    sqlx::query("insert into document_move(id,document_id,actor,source_space_id,source_folder_id,generation_id,destination_space_id,destination_folder_id) values($1,$2,'alice',$3,$3,$3,$4,$5)")
        .bind(id).bind(doc).bind(team).bind(project).bind(target).execute(&pool).await.unwrap();
    let source: (Uuid, Option<Uuid>, Option<Uuid>) = sqlx::query_as(
        "select source_space_id,source_folder_id,generation_id from document_move where id=$1",
    )
    .bind(id)
    .fetch_one(&pool)
    .await
    .unwrap();
    assert_eq!(source, (org, None, None));
    sqlx::query("delete from folder where id=$1")
        .bind(target)
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("delete from space where id=$1")
        .bind(project)
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("update document_move set phase='cancelled' where id=$1")
        .bind(id)
        .execute(&pool)
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, Uuid>("select destination_space_id from document_move where id=$1")
            .bind(id)
            .fetch_one(&pool)
            .await
            .unwrap(),
        project
    );
}
