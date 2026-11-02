// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use sqlx::{AssertSqlSafe, PgPool, postgres::PgConnectOptions};
use uuid::Uuid;

// Proves: I29
#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn consumers_only_read_their_cp_read_contract_and_visibility_tracks_publication() {
    let e = super::env().await;
    let name: String = sqlx::query_scalar("select current_database()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    let base = std::env::var("CONTROL_PLANE_IT_POSTGRES").unwrap();
    for (role, view, column) in [
        ("fred_kf", "space_state", "id"),
        ("fred_runtime", "terms_acceptance", "user_id"),
        ("fred_monitor", "platform_role_grant", "subject"),
    ] {
        let options = format!("{base}/{name}")
            .parse::<PgConnectOptions>()
            .unwrap()
            .username(role)
            .password("it");
        let consumer = PgPool::connect_with(options).await.unwrap();
        let mut connection = consumer.acquire().await.unwrap();
        // Prove ACL denial even if monitor disables its advisory read-only default.
        sqlx::query("set default_transaction_read_only = off")
            .execute(&mut *connection)
            .await
            .unwrap();
        let who: String = sqlx::query_scalar("select current_user")
            .fetch_one(&mut *connection)
            .await
            .unwrap();
        assert_eq!(who, role);
        sqlx::query(AssertSqlSafe(format!("select * from cp_read.{view}")))
            .execute(&mut *connection)
            .await
            .unwrap();
        let forbidden = [
            "select * from control_plane.document".to_string(),
            "select * from control_plane.space_role_grant".to_string(),
            format!("insert into cp_read.{view} default values"),
            format!("update cp_read.{view} set {column}={column} where false"),
            format!("delete from cp_read.{view} where false"),
            "create table public.forbidden(id int)".to_string(),
        ];
        for statement in forbidden {
            let error = sqlx::query(AssertSqlSafe(statement))
                .execute(&mut *connection)
                .await
                .unwrap_err();
            assert_eq!(
                error.as_database_error().unwrap().code().as_deref(),
                Some("42501")
            );
        }
        for other in ["space_state", "terms_acceptance", "platform_role_grant"] {
            if other != view {
                let error = sqlx::query(AssertSqlSafe(format!("select * from cp_read.{other}")))
                    .execute(&mut *connection)
                    .await
                    .unwrap_err();
                assert_eq!(
                    error.as_database_error().unwrap().code().as_deref(),
                    Some("42501")
                );
            }
        }
        drop(connection);
        consumer.close().await;
    }

    let org = Uuid::new_v4();
    let doc = Uuid::new_v4();
    let processing = Uuid::new_v4();
    let generation = Uuid::new_v4();
    let conversation = Uuid::new_v4();
    let deletion = Uuid::new_v4();
    sqlx::query("insert into space(id,kind,name,organization_id) values($1,'organization','SQL boundary',$1)")
        .bind(org).execute(&e.pool).await.unwrap();
    sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,'alice',$2,$1,$1,'fixture','Fixture',1)")
        .bind(conversation).bind(org).execute(&e.pool).await.unwrap();
    sqlx::query("insert into document(id,space_id,session_id,name,mime,size,sha256,created_by,object_key,quota_owner,retrievable) values($1,$2,$3,'fixture','text/plain',1,repeat('a',64),'alice','fixture',$2,true)")
        .bind(doc).bind(org).bind(conversation).execute(&e.pool).await.unwrap();
    assert!(!visible(&e.pool, doc).await);
    sqlx::query("insert into document_processing(id,document_id,actor,request_key,profile,workflow_id,submission,deadline_at,profile_settings,preparation_seconds,extraction_seconds,indexing_seconds) values($1,$2,'alice',$1,'fast','fixture','{}',now()+interval '1 hour','{}',60,60,60)")
        .bind(processing).bind(doc).execute(&e.pool).await.unwrap();
    sqlx::query("insert into generation(id,processing_id,document_id,stage,execution_id,activity_id,attempt,expires_at,prefix,committed_at,vector_ordinals,cleanup_after) values($1,$2,$3,'indexing',$1,$1,1,now()+interval '1 hour','fixture/',now(),array[0,2],now()+interval '2 hours')")
        .bind(generation).bind(processing).bind(doc).execute(&e.pool).await.unwrap();
    sqlx::query("update document set published_generation=$2 where id=$1")
        .bind(doc)
        .bind(generation)
        .execute(&e.pool)
        .await
        .unwrap();
    // A live processing run does not hide the previously published generation.
    assert!(visible(&e.pool, doc).await);
    sqlx::query("insert into deletion(id,target_id,target_kind,organization_id,actor_subject,requested_at,due_at) values($1,$2,'organization',$2,'alice',now(),now())")
        .bind(deletion).bind(org).execute(&e.pool).await.unwrap();
    for statement in [
        "update document set deletion_id=$2,purge_after=now() where id=$1",
        "update space set deletion_id=$2 where id=(select space_id from document where id=$1)",
        "update session_metadata set deletion_id=$2 where session_id=(select session_id from document where id=$1)",
    ] {
        let mut tx = e.pool.begin().await.unwrap();
        sqlx::query(AssertSqlSafe(statement))
            .bind(doc)
            .bind(deletion)
            .execute(&mut *tx)
            .await
            .unwrap();
        let value: bool = sqlx::query_scalar(
            "select visible from cp_read.document_visibility where document_id=$1",
        )
        .bind(doc)
        .fetch_one(&mut *tx)
        .await
        .unwrap();
        assert!(!value);
        tx.rollback().await.unwrap();
    }
    for statement in [
        "update document set retrievable=false where id=$1",
        "update document set retrieval_id=id,retrieval_actor='alice',retrieval_target=true,retrieval_phase='ready',retrieval_confirmed=false where id=$1",
        "update document set published_generation=null where id=$1",
    ] {
        let mut tx = e.pool.begin().await.unwrap();
        sqlx::query(AssertSqlSafe(statement))
            .bind(doc)
            .execute(&mut *tx)
            .await
            .unwrap();
        let value: bool = sqlx::query_scalar(
            "select visible from cp_read.document_visibility where document_id=$1",
        )
        .bind(doc)
        .fetch_one(&mut *tx)
        .await
        .unwrap();
        assert!(!value);
        tx.rollback().await.unwrap();
    }
    assert!(visible(&e.pool, doc).await);
}

async fn visible(pool: &PgPool, id: Uuid) -> bool {
    sqlx::query_scalar("select visible from cp_read.document_visibility where document_id=$1")
        .bind(id)
        .fetch_one(pool)
        .await
        .unwrap()
}
