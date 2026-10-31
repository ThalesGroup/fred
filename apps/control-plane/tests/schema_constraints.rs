// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use serde_json::json;
use sqlx::{AssertSqlSafe, PgPool};
use uuid::Uuid;

async fn database() -> PgPool {
    database_at(None).await
}

async fn database_at(version: Option<i64>) -> PgPool {
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

fn check_violation(error: sqlx::Error) {
    violation(error, "23514");
}

fn violation(error: sqlx::Error, code: &str) {
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some(code)
    );
}

async fn organization(pool: &PgPool, name: &str) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query("insert into space(id,kind,name,organization_id) values ($1,'organization',$2,$1)")
        .bind(id)
        .bind(name)
        .execute(pool)
        .await
        .unwrap();
    id
}

async fn insert_space(
    pool: &PgPool,
    kind: &str,
    organization: Uuid,
    parent: Option<Uuid>,
    name: &str,
    owner: Option<&str>,
) -> Result<Uuid, sqlx::Error> {
    let id = Uuid::new_v4();
    sqlx::query("insert into space(id,kind,name,organization_id,parent_id,personal_owner) values ($1,$2::text::space_kind,$3,$4,$5,$6)")
        .bind(id).bind(kind).bind(name).bind(organization).bind(parent).bind(owner)
        .execute(pool).await?;
    Ok(id)
}

// Proves: I1
#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn space_hierarchy_rejects_wrong_roots_parents_and_cross_organization_projects() {
    let pool = database().await;
    let org = organization(&pool, "A").await;
    let other = organization(&pool, "B").await;
    let team = insert_space(&pool, "team", org, Some(org), "Team", None)
        .await
        .unwrap();
    let project = insert_space(&pool, "project", org, Some(team), "Project", None)
        .await
        .unwrap();
    let personal = insert_space(&pool, "personal", org, None, "Personal", Some("alice"))
        .await
        .unwrap();

    for (kind, root, parent, owner) in [
        ("organization", org, None, None),
        ("team", org, None, None),
        ("team", org, Some(team), None),
        ("project", org, None, None),
        ("project", org, Some(org), None),
        ("project", org, Some(project), None),
        ("project", org, Some(personal), None),
        ("personal", team, None, Some("alice")),
    ] {
        check_violation(
            insert_space(&pool, kind, root, parent, "Invalid", owner)
                .await
                .unwrap_err(),
        );
    }
    violation(
        insert_space(&pool, "project", other, Some(team), "Foreign", None)
            .await
            .unwrap_err(),
        "23503",
    );
    let id = Uuid::new_v4();
    check_violation(
        sqlx::query("insert into space(id,kind,name,organization_id,parent_id) values ($1,'project','Self',$2,$1)")
            .bind(id).bind(org).execute(&pool).await.unwrap_err(),
    );
}

// Proves: I1
#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn hierarchy_accepts_a_tree_inserted_in_one_statement() {
    let pool = database().await;
    let org = Uuid::new_v4();
    let team = Uuid::new_v4();
    let project = Uuid::new_v4();
    sqlx::query("insert into space(id,kind,name,organization_id,parent_id) values
        ($1,'project','Project',$3,$2), ($2,'team','Team',$3,$3), ($3,'organization','Org',$3,null)")
        .bind(project).bind(team).bind(org).execute(&pool).await.unwrap();
}

// Proves: I1
#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn sibling_names_are_unique_on_insert_and_rename_but_local_to_the_parent() {
    let pool = database().await;
    let org = organization(&pool, "A").await;
    let other = organization(&pool, "B").await;
    let team = insert_space(&pool, "team", org, Some(org), "Team", None)
        .await
        .unwrap();
    insert_space(&pool, "team", other, Some(other), "Team", None)
        .await
        .unwrap();
    violation(
        insert_space(&pool, "team", org, Some(org), "Team", None)
            .await
            .unwrap_err(),
        "23505",
    );
    insert_space(&pool, "project", org, Some(team), "Project", None)
        .await
        .unwrap();
    let second = insert_space(&pool, "project", org, Some(team), "Other", None)
        .await
        .unwrap();
    violation(
        sqlx::query("update space set name='Project' where id=$1")
            .bind(second)
            .execute(&pool)
            .await
            .unwrap_err(),
        "23505",
    );
}

// Proves: I6
#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn personal_grants_reject_other_subjects_on_insert_and_update() {
    let pool = database().await;
    let org = organization(&pool, "A").await;
    let other = organization(&pool, "B").await;
    let personal = insert_space(&pool, "personal", org, None, "Personal", Some("alice"))
        .await
        .unwrap();
    sqlx::query("insert into space_role_grant(space_id,subject,role) values ($1,'alice','member'),($1,'alice','editor')")
        .bind(personal).execute(&pool).await.unwrap();
    check_violation(
        sqlx::query(
            "insert into space_role_grant(space_id,subject,role) values ($1,'bob','editor')",
        )
        .bind(personal)
        .execute(&pool)
        .await
        .unwrap_err(),
    );
    check_violation(
        sqlx::query(
            "update space_role_grant set subject='bob' where space_id=$1 and role='editor'",
        )
        .bind(personal)
        .execute(&pool)
        .await
        .unwrap_err(),
    );
    // Placement integrity must not impose a single organization per subject.
    sqlx::query("insert into space_role_grant(space_id,subject,role) values ($1,'alice','member'),($2,'alice','member'),($1,'bob','member')")
        .bind(org).bind(other).execute(&pool).await.unwrap();
    check_violation(
        sqlx::query("update space_role_grant set space_id=$1 where space_id=$2 and subject='bob'")
            .bind(personal)
            .bind(org)
            .execute(&pool)
            .await
            .unwrap_err(),
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn model_source_configuration_requires_non_null_identity_and_revision() {
    let pool = database().await;
    for configuration in [
        json!({}),
        json!({"source_id": "source"}),
        json!({"revision": 1}),
        json!({"source_id": null, "revision": 1}),
        json!({"source_id": "source", "revision": null}),
        json!({"source_id": "other", "revision": 1}),
        json!({"source_id": "source", "revision": 0}),
    ] {
        check_violation(
            sqlx::query("insert into model_source(source_id,configuration) values ('source',$1)")
                .bind(configuration)
                .execute(&pool)
                .await
                .unwrap_err(),
        );
    }
    sqlx::query("insert into model_source(source_id,configuration) values ('source',$1)")
        .bind(json!({"source_id": "source", "revision": 1}))
        .execute(&pool)
        .await
        .unwrap();
    check_violation(
        sqlx::query("update model_source set configuration = '{}' where source_id = 'source'")
            .execute(&pool)
            .await
            .unwrap_err(),
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn agent_template_policies_only_reference_organizations() {
    let pool = database().await;
    let organization = Uuid::new_v4();
    sqlx::query(
        "insert into space(id,kind,name,organization_id) values ($1,'organization','Org',$1)",
    )
    .bind(organization)
    .execute(&pool)
    .await
    .unwrap();
    let team = Uuid::new_v4();
    sqlx::query(
        "insert into space(id,kind,name,organization_id,parent_id) values ($1,'team','Team',$2,$2)",
    )
    .bind(team)
    .bind(organization)
    .execute(&pool)
    .await
    .unwrap();
    let template = Uuid::new_v4();
    check_violation(
        sqlx::query(
            "insert into agent_template_policy(organization_id,template_id) values ($1,$2)",
        )
        .bind(team)
        .bind(template)
        .execute(&pool)
        .await
        .unwrap_err(),
    );
    sqlx::query("insert into agent_template_policy(organization_id,template_id) values ($1,$2)")
        .bind(organization)
        .bind(template)
        .execute(&pool)
        .await
        .unwrap();
    check_violation(
        sqlx::query("update agent_template_policy set organization_id=$1 where organization_id=$2")
            .bind(team)
            .bind(organization)
            .execute(&pool)
            .await
            .unwrap_err(),
    );
}

// Proves: I21
#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn organization_admin_scope_is_checked_on_insert_and_role_or_space_update() {
    let pool = database().await;
    let org = organization(&pool, "Org").await;
    let team = insert_space(&pool, "team", org, Some(org), "Team", None)
        .await
        .unwrap();
    let project = insert_space(&pool, "project", org, Some(team), "Project", None)
        .await
        .unwrap();
    let personal = insert_space(&pool, "personal", org, None, "Personal", Some("alice"))
        .await
        .unwrap();
    for space in [team, project, personal] {
        check_violation(
            sqlx::query("insert into space_role_grant(space_id,subject,role) values ($1,'alice','organization_admin')")
                .bind(space).execute(&pool).await.unwrap_err(),
        );
    }
    sqlx::query("insert into space_role_grant(space_id,subject,role) values ($1,'alice','organization_admin'),($2,'alice','owner')")
        .bind(org).bind(team).execute(&pool).await.unwrap();
    check_violation(
        sqlx::query("update space_role_grant set role='organization_admin' where space_id=$1")
            .bind(team)
            .execute(&pool)
            .await
            .unwrap_err(),
    );
    check_violation(
        sqlx::query("update space_role_grant set space_id=$1 where space_id=$2")
            .bind(team)
            .bind(org)
            .execute(&pool)
            .await
            .unwrap_err(),
    );
}

// Document and processing share a UUID only to keep these SQL fixtures small.
async fn processing_document(pool: &PgPool, space: Uuid) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query(
        "insert into document(id,space_id,name,mime,size,sha256,created_by,object_key,quota_owner)
        values($1,$2,$1::text,'text/plain',1,repeat('a',64),'alice',$1::text,$2)",
    )
    .bind(id)
    .bind(space)
    .execute(pool)
    .await
    .unwrap();
    sqlx::query("insert into document_processing(id,request_key,actor,document_id,profile,workflow_id,submission,deadline_at,profile_settings,preparation_seconds,extraction_seconds,indexing_seconds)
        values($1,$1,'alice',$1,'fast',$1::text,'{}',now()+interval '1 hour','{}',60,60,60)")
        .bind(id).execute(pool).await.unwrap();
    id
}

async fn generation(pool: &PgPool, processing: Uuid, document: Uuid) -> Result<Uuid, sqlx::Error> {
    let id = Uuid::new_v4();
    sqlx::query("insert into generation(id,processing_id,document_id,stage,execution_id,activity_id,attempt,expires_at,prefix,cleanup_after)
        values($1,$2,$3,'indexing',$1,$1,1,now()+interval '1 hour',$1::text,now()+interval '2 hours')")
        .bind(id).bind(processing).bind(document).execute(pool).await?;
    Ok(id)
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn publication_and_generation_cannot_cross_document_boundaries() {
    let pool = database().await;
    let org = organization(&pool, "Org").await;
    let a = processing_document(&pool, org).await;
    let b = processing_document(&pool, org).await;
    let first = generation(&pool, a, a).await.unwrap();
    violation(generation(&pool, a, b).await.unwrap_err(), "23503");
    violation(
        sqlx::query("update generation set processing_id=$1 where id=$2")
            .bind(b)
            .bind(first)
            .execute(&pool)
            .await
            .unwrap_err(),
        "23503",
    );
    let mut tx = pool.begin().await.unwrap();
    sqlx::query("update document set published_generation=$1 where id=$2")
        .bind(first)
        .bind(b)
        .execute(&mut *tx)
        .await
        .unwrap();
    violation(tx.commit().await.unwrap_err(), "23503");

    sqlx::query("update document set published_generation=$1 where id=$2")
        .bind(first)
        .bind(a)
        .execute(&pool)
        .await
        .unwrap();
    // Even a consistent reparenting of the generation cannot invalidate publication.
    let mut tx = pool.begin().await.unwrap();
    sqlx::query("update generation set processing_id=$1,document_id=$1 where id=$2")
        .bind(b)
        .bind(first)
        .execute(&mut *tx)
        .await
        .unwrap();
    violation(tx.commit().await.unwrap_err(), "23503");

    let second = generation(&pool, a, a).await.unwrap();
    sqlx::query("update document set published_generation=$1 where id=$2")
        .bind(second)
        .bind(a)
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("update document set published_generation=null where id=$1")
        .bind(a)
        .execute(&pool)
        .await
        .unwrap();
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn publication_allows_atomic_purge_but_rejects_dangling_references() {
    let pool = database().await;
    let org = organization(&pool, "Org").await;
    let doc = processing_document(&pool, org).await;
    let published = generation(&pool, doc, doc).await.unwrap();
    sqlx::query("update document set published_generation=$1 where id=$2")
        .bind(published)
        .bind(doc)
        .execute(&pool)
        .await
        .unwrap();
    let mut tx = pool.begin().await.unwrap();
    sqlx::query("delete from document_processing where id=$1")
        .bind(doc)
        .execute(&mut *tx)
        .await
        .unwrap();
    violation(tx.commit().await.unwrap_err(), "23503");

    let mut tx = pool.begin().await.unwrap();
    sqlx::query("delete from document_processing where id=$1")
        .bind(doc)
        .execute(&mut *tx)
        .await
        .unwrap();
    sqlx::query("delete from document where id=$1")
        .bind(doc)
        .execute(&mut *tx)
        .await
        .unwrap();
    tx.commit().await.unwrap();
    let remaining: i64 = sqlx::query_scalar("select count(*) from generation where id=$1")
        .bind(published)
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(remaining, 0);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn publication_migration_backfills_identity_and_rejects_existing_mismatch() {
    for mismatch in [false, true] {
        let pool = database_at(Some(4)).await;
        let org = organization(&pool, "Org").await;
        let a = processing_document(&pool, org).await;
        let b = processing_document(&pool, org).await;
        sqlx::query("insert into generation(id,processing_id,stage,execution_id,activity_id,attempt,expires_at,prefix,cleanup_after)
            values($1,$1,'indexing',$1,$1,1,now()+interval '1 hour',$1::text,now()+interval '2 hours')")
            .bind(a).execute(&pool).await.unwrap();
        sqlx::query("update document set published_generation=$1 where id=$2")
            .bind(a)
            .bind(if mismatch { b } else { a })
            .execute(&pool)
            .await
            .unwrap();
        let result = sqlx::migrate!().run(&pool).await;
        if mismatch {
            match result.unwrap_err() {
                sqlx::migrate::MigrateError::ExecuteMigration(error, 5) => {
                    violation(error, "23503")
                }
                other => panic!("unexpected migration failure: {other}"),
            }
        } else {
            result.unwrap();
            let document: Uuid =
                sqlx::query_scalar("select document_id from generation where id=$1")
                    .bind(a)
                    .fetch_one(&pool)
                    .await
                    .unwrap();
            assert_eq!(document, a);
        }
    }
}
