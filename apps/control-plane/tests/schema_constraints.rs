// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use serde_json::json;
use sqlx::PgPool;
use uuid::Uuid;

#[path = "support/database.rs"]
mod database;
use database::database;

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
        "select fixture_document(p_id=>$1,p_space_id=>$2,p_name=>$1::text,p_mime=>'text/plain',p_size=>1,p_sha256=>repeat('a',64),p_created_by=>'alice',p_object_key=>$1::text,p_quota_owner=>$2)",
    )
    .bind(id)
    .bind(space)
    .execute(pool)
    .await
    .unwrap();
    sqlx::query("insert into document_processing(id,request_key,actor,document_id,content_id,expected_content_id,expected_generation_id,profile,workflow_id,submission,deadline_at,profile_settings,preparation_seconds,extraction_seconds,indexing_seconds)
        values($1,$1,'alice',$1,$1,$1,null,'fast',$1::text,'{}',now()+interval '1 hour','{}',60,60,60)")
        .bind(id).execute(pool).await.unwrap();
    id
}

async fn generation(pool: &PgPool, processing: Uuid, document: Uuid) -> Result<Uuid, sqlx::Error> {
    let id = Uuid::new_v4();
    sqlx::query("insert into generation(id,processing_id,document_id,stage,execution_id,activity_id,attempt,expires_at,prefix,cleanup_after)
        values($1,$2,$3,'indexing',$1,$1,1,now()+interval '1 hour',$1::text,now()+interval '2 hours')")
        .bind(id).bind(processing).bind(document).execute(pool).await?;
    sqlx::query("update generation set committed_at=now(),vector_ordinals='{}' where id=$1")
        .bind(id)
        .execute(pool)
        .await?;
    sqlx::query("update document_processing set status='succeeded',stage='done',completed_at=now() where id=$1")
        .bind(processing).execute(pool).await?;
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
    violation(
        sqlx::query("update document set published_generation=$1 where id=$2")
            .bind(first)
            .bind(b)
            .execute(&pool)
            .await
            .unwrap_err(),
        "23514",
    );

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

    // Clearing a live publication would discard a usable result without a successor.
    violation(
        sqlx::query("update document set published_generation=null where id=$1")
            .bind(a)
            .execute(&pool)
            .await
            .unwrap_err(),
        "23514",
    );
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
async fn agent_display_names_are_unique_from_creation_and_on_rename() {
    let pool = database().await;
    let org = organization(&pool, "Org").await;
    let first = Uuid::new_v4();
    let second = Uuid::new_v4();
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values
        ($1,$3,$1,'native','assistant','Simon','{}','alice','simon-reference'),
        ($2,$3,$2,'native','assistant','Eva','{}','alice','eva-reference')")
        .bind(first).bind(second).bind(org).execute(&pool).await.unwrap();
    violation(sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values
        ($1,$2,$1,'native','assistant','simon','{}','alice','another-reference')")
        .bind(Uuid::new_v4()).bind(org).execute(&pool).await.unwrap_err(), "23505");
    violation(sqlx::query("update agent_instance set display_name='SIMON',updated_by='alice' where agent_instance_id=$1")
        .bind(second).execute(&pool).await.unwrap_err(), "23505");
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn initialization_replays_without_data_changes_and_refuses_incompatible_history() {
    let pool = database().await;
    let org = organization(&pool, "Keep this organization").await;
    let name: String = sqlx::query_scalar("select current_database()")
        .fetch_one(&pool)
        .await
        .unwrap();
    let url = format!(
        "{}/{name}",
        std::env::var("CONTROL_PLANE_IT_POSTGRES").unwrap()
    );
    let initialize = || {
        std::process::Command::new(env!("CARGO_BIN_EXE_control-plane"))
            .arg("initialize-schema")
            .env("DATABASE_URL", &url)
            .env("CONFIG_FILE", "/nonexistent/config")
            .output()
            .unwrap()
    };
    assert!(initialize().status.success());
    control_plane::db::require_initialized(&pool).await.unwrap();
    let versions: Vec<i64> =
        sqlx::query_scalar("select version from _sqlx_migrations order by version")
            .fetch_all(&pool)
            .await
            .unwrap();
    assert_eq!(
        versions,
        sqlx::migrate!()
            .iter()
            .map(|m| m.version)
            .collect::<Vec<_>>()
    );

    // Simulate a draft installation's obsolete history only in this disposable fixture.
    sqlx::query("insert into _sqlx_migrations(version,description,success,checksum,execution_time) values(99,'obsolete draft',true,decode('00','hex'),0)")
        .execute(&pool).await.unwrap();
    let rejected = initialize();
    assert!(!rejected.status.success());
    assert!(String::from_utf8_lossy(&rejected.stdout).contains("do not rewrite SQLx history"));
    assert!(control_plane::db::require_initialized(&pool).await.is_err());
    let retained: String = sqlx::query_scalar("select name from space where id=$1")
        .bind(org)
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(retained, "Keep this organization");
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn cp_read_document_tree_is_granted_to_its_reader_only() {
    let pool = database().await;
    let org = organization(&pool, "Visible organization").await;
    // The real consumer role can read the contract, including empty result sets.
    let reader = PgPool::connect_with(
        pool.connect_options()
            .as_ref()
            .clone()
            .username("fred_kf")
            .password("it"),
    )
    .await
    .unwrap();
    sqlx::query("select mime,created_at from cp_read.document_visibility limit 1")
        .fetch_all(&reader)
        .await
        .unwrap();
    sqlx::query("select name from cp_read.folder_path limit 1")
        .fetch_all(&reader)
        .await
        .unwrap();
    sqlx::query("select name from cp_read.space_state where id=$1")
        .bind(org)
        .fetch_one(&reader)
        .await
        .unwrap();
    reader.close().await;
    let forbidden: bool = sqlx::query_scalar(
        "select has_table_privilege('fred_runtime_reader','cp_read.document_visibility','select')",
    )
    .fetch_one(&pool)
    .await
    .unwrap();
    assert!(!forbidden);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn model_usage_constrains_facts_without_foreign_keys() {
    async fn insert(
        pool: &PgPool,
        report: Uuid,
        session: Uuid,
        exchange: &str,
        offer: (&str, &str),
        tokens: [i64; 4],
    ) -> Result<sqlx::postgres::PgQueryResult, sqlx::Error> {
        sqlx::query("insert into model_usage(session_id,exchange_id,occurred_at,space_id,user_id,agent_instance_id,model_source_id,upstream_model_id,input_tokens,output_tokens,cache_read_tokens,cache_creation_tokens,report_id) values($1,$2,now(),$3,'alice',$4,$5,$6,$7,$8,$9,$10,$11)")
            .bind(session).bind(exchange).bind(Uuid::new_v4()).bind(Uuid::new_v4())
            .bind(offer.0).bind(offer.1).bind(tokens[0]).bind(tokens[1]).bind(tokens[2]).bind(tokens[3]).bind(report).execute(pool).await
    }
    let pool = database().await;
    let session = Uuid::new_v4();
    let report = Uuid::new_v4();
    // No referenced session, space, person, agent or catalogue offer is required.
    insert(
        &pool,
        report,
        session,
        "turn",
        ("source", "model"),
        [0, 0, 0, 0],
    )
    .await
    .unwrap();
    violation(
        insert(
            &pool,
            report,
            session,
            "turn",
            ("source", "model"),
            [0, 0, 0, 0],
        )
        .await
        .unwrap_err(),
        "23505",
    );
    // Each component of the offer identity participates in the primary key.
    for offer in [("other-source", "model"), ("source", "other-model")] {
        insert(&pool, report, session, "turn", offer, [0, 0, 0, 0])
            .await
            .unwrap();
    }
    for source in [
        "".into(),
        " leading".into(),
        "trailing ".into(),
        "-source".into(),
        "_source".into(),
        ".source".into(),
        "source/name".into(),
        "é".into(),
        "s".repeat(65),
    ] {
        check_violation(
            insert(
                &pool,
                report,
                session,
                "invalid",
                (&source, "model"),
                [0, 0, 0, 0],
            )
            .await
            .unwrap_err(),
        );
    }
    insert(
        &pool,
        report,
        session,
        "source-boundary",
        (&format!("A{}", "._-".repeat(21)), "model"),
        [0, 0, 0, 0],
    )
    .await
    .unwrap();
    for exchange in [
        "".into(),
        " leading".into(),
        "trailing ".into(),
        "control\ninside".into(),
        "control\u{7f}".into(),
        "x".repeat(257),
    ] {
        check_violation(
            insert(
                &pool,
                report,
                session,
                &exchange,
                ("source", "model"),
                [0, 0, 0, 0],
            )
            .await
            .unwrap_err(),
        );
    }
    for model in [
        "".into(),
        " leading".into(),
        "trailing ".into(),
        "x".repeat(257),
        "é".repeat(129),
    ] {
        check_violation(
            insert(
                &pool,
                report,
                session,
                "invalid",
                ("source", &model),
                [0, 0, 0, 0],
            )
            .await
            .unwrap_err(),
        );
    }
    for tokens in [[-1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 0], [0, 0, 0, -1]] {
        check_violation(
            insert(
                &pool,
                report,
                session,
                "invalid",
                ("source", "model"),
                tokens,
            )
            .await
            .unwrap_err(),
        );
    }
    for column in [
        "report_id",
        "session_id",
        "exchange_id",
        "occurred_at",
        "space_id",
        "user_id",
        "agent_instance_id",
        "model_source_id",
        "upstream_model_id",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
    ] {
        violation(
            sqlx::query(sqlx::AssertSqlSafe(format!(
                "update model_usage set {column}=null"
            )))
            .execute(&pool)
            .await
            .unwrap_err(),
            "23502",
        );
    }
    insert(
        &pool,
        report,
        session,
        &"é".repeat(256),
        ("source", &"é".repeat(128)),
        [i64::MAX; 4],
    )
    .await
    .unwrap();
    // Changing session/exchange cannot reuse a report's offer key.
    violation(
        insert(
            &pool,
            report,
            Uuid::new_v4(),
            "different",
            ("source", "model"),
            [0; 4],
        )
        .await
        .unwrap_err(),
        "23505",
    );
    // A new report may consume the same offer for the same session and exchange.
    insert(
        &pool,
        Uuid::new_v4(),
        session,
        "turn",
        ("source", "model"),
        [0; 4],
    )
    .await
    .unwrap();
    let collations: Vec<(String, String)> = sqlx::query_as(
        "select attname::text, collname::text from pg_attribute a
         join pg_collation c on c.oid=a.attcollation
         where a.attrelid='model_usage'::regclass
           and a.attname in ('model_source_id','upstream_model_id') order by attname",
    )
    .fetch_all(&pool)
    .await
    .unwrap();
    assert_eq!(
        collations,
        vec![
            ("model_source_id".into(), "C".into()),
            ("upstream_model_id".into(), "C".into()),
        ]
    );
    let foreign_keys: i64 = sqlx::query_scalar(
        "select count(*) from pg_constraint where conrelid='model_usage'::regclass and contype='f'",
    )
    .fetch_one(&pool)
    .await
    .unwrap();
    assert_eq!(foreign_keys, 0);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn organization_title_policy_checks_its_membership() {
    let pool = database().await;
    let org = organization(&pool, "Title organization").await;
    sqlx::query("insert into organization_model_policy(organization_id,revision,created_by,updated_by) values($1,1,'alice','alice')")
        .bind(org).execute(&pool).await.unwrap();
    check_violation(sqlx::query("update organization_model_policy set title_source_id='missing' where organization_id=$1").bind(org).execute(&pool).await.unwrap_err());
    violation(sqlx::query("update organization_model_policy set title_source_id='missing', title_upstream_model_id='model' where organization_id=$1").bind(org).execute(&pool).await.unwrap_err(), "23503");
}

async fn wiki_steps(pool: &PgPool, statements: &[&'static str]) -> Result<(), sqlx::Error> {
    let mut tx = pool.begin().await?;
    for statement in statements {
        sqlx::raw_sql(*statement).execute(&mut *tx).await?;
    }
    tx.commit().await
}

async fn used(pool: &PgPool) -> i64 {
    sqlx::query_scalar("select used_bytes from storage_budget where scope='local'")
        .fetch_one(pool)
        .await
        .unwrap()
}

/// A conversation output of 40 bytes copied into a Wiki document of the same bytes.
const WIKI_COPY: [&str; 3] = [
    "insert into document(id,space_id,name,created_by,quota_owner,purpose) values ('00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-00000000000b','report.pdf','alice','00000000-0000-0000-0000-00000000000b','wiki')",
    "insert into document_content(id,document_id,kind,object_key,mime,size,sha256,published_at) values ('00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-0000000000f1','primary','k/f1','application/pdf',40,repeat('a',64),now())",
    "update document set current_content_id='00000000-0000-0000-0000-0000000000f1' where id='00000000-0000-0000-0000-0000000000f1'",
];

// One arbitration for pages and files; drafts only from a live conversation of
// their author, with its agent snapshot; file bytes copy one of its outputs; refusal,
// entry deletion and conversation purge retire copies and release quota.
#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn wiki_drafts_files_and_arbitration_keep_provenance_shape_and_quota() {
    let pool = database().await;
    wiki_steps(&pool, &[
        "insert into space(id,kind,name,organization_id) values ('00000000-0000-0000-0000-00000000000a','organization','O','00000000-0000-0000-0000-00000000000a')",
        "insert into space(id,kind,name,organization_id,parent_id) values ('00000000-0000-0000-0000-00000000000b','team','T','00000000-0000-0000-0000-00000000000a','00000000-0000-0000-0000-00000000000a')",
        "insert into storage_budget values ('00000000-0000-0000-0000-00000000000a','organization_total',1000,0,0),('00000000-0000-0000-0000-00000000000b','local',500,0,0)",
        "insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,created_by,updated_by,tuning,logical_name) values ('00000000-0000-0000-0000-0000000000a1','00000000-0000-0000-0000-00000000000b','00000000-0000-0000-0000-0000000000a2','rt','ag','Helper','x','x','{}','helper')",
        "insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values ('00000000-0000-0000-0000-0000000000c1','alice','00000000-0000-0000-0000-00000000000b','00000000-0000-0000-0000-0000000000a1','00000000-0000-0000-0000-0000000000a2','rt','Helper',1)",
        "insert into document(id,space_id,session_id,name,purpose,created_by,quota_owner) values ('00000000-0000-0000-0000-0000000000b1','00000000-0000-0000-0000-00000000000b','00000000-0000-0000-0000-0000000000c1','report.pdf','output','alice','00000000-0000-0000-0000-00000000000b')",
        "insert into document_content(id,document_id,kind,object_key,mime,size,sha256,published_at) values ('00000000-0000-0000-0000-0000000000b1','00000000-0000-0000-0000-0000000000b1','primary','k/b1','application/pdf',40,repeat('a',64),now())",
        "update document set current_content_id='00000000-0000-0000-0000-0000000000b1' where id='00000000-0000-0000-0000-0000000000b1'",
    ]).await.unwrap();
    let draft = "insert into wiki_revision(revision_id,space_id,entry_kind,content_md,status,author_user_id,agent_instance_id,agent_name,session_id,proposed_title) values ('00000000-0000-0000-0000-0000000000d1','00000000-0000-0000-0000-00000000000b','page','hello','proposed','alice','00000000-0000-0000-0000-0000000000a1','Helper','00000000-0000-0000-0000-0000000000c1','Guide')";
    // The agent name is the one the person saw; provenance never exists without a conversation.
    for refused in [
        "insert into wiki_revision(revision_id,space_id,entry_kind,content_md,status,author_user_id,agent_instance_id,agent_name,session_id,proposed_title) values (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','page','x','proposed','alice','00000000-0000-0000-0000-0000000000a1','Other','00000000-0000-0000-0000-0000000000c1','P')",
        "insert into wiki_revision(revision_id,space_id,entry_kind,content_md,status,author_user_id,agent_instance_id,agent_name,session_id,proposed_title) values (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','page','x','proposed','bob','00000000-0000-0000-0000-0000000000a1','Helper','00000000-0000-0000-0000-0000000000c1','P')",
        "insert into wiki_revision(revision_id,space_id,entry_kind,content_md,status,author_user_id,agent_instance_id,agent_name,proposed_title) values (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','page','x','proposed','alice','00000000-0000-0000-0000-0000000000a1','Helper','P')",
        "insert into wiki_revision(revision_id,space_id,entry_kind,content_md,status,author_user_id,proposed_title) values (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','rules','r','proposed','bob','Rules')",
    ] {
        check_violation(wiki_steps(&pool, &[refused]).await.unwrap_err());
    }
    wiki_steps(&pool, &[draft]).await.unwrap();
    // A decided revision belongs to no conversation; confirmation only detaches it.
    check_violation(wiki_steps(&pool, &[
        "insert into wiki_page(page_id,space_id,slug,title,kind,updated_by) values ('00000000-0000-0000-0000-0000000000e1','00000000-0000-0000-0000-00000000000b','e1','Guide','page','bob')",
        "update wiki_revision set status='published',page_id='00000000-0000-0000-0000-0000000000e1',reviewed_at=now(),reviewed_by='bob' where revision_id='00000000-0000-0000-0000-0000000000d1'",
    ]).await.unwrap_err());
    wiki_steps(&pool, &["update wiki_revision set session_id=null where revision_id='00000000-0000-0000-0000-0000000000d1'"]).await.unwrap();
    check_violation(wiki_steps(&pool, &["update wiki_revision set session_id='00000000-0000-0000-0000-0000000000c1' where revision_id='00000000-0000-0000-0000-0000000000d1'"]).await.unwrap_err());
    wiki_steps(&pool, &[
        "insert into wiki_page(page_id,space_id,slug,title,kind,updated_by,current_revision_id) values ('00000000-0000-0000-0000-0000000000e1','00000000-0000-0000-0000-00000000000b','e1','Guide','page','bob','00000000-0000-0000-0000-0000000000d1')",
        "update wiki_revision set status='published',page_id='00000000-0000-0000-0000-0000000000e1',reviewed_at=now(),reviewed_by='bob' where revision_id='00000000-0000-0000-0000-0000000000d1'",
    ]).await.unwrap();
    violation(wiki_steps(&pool, &["insert into wiki_page(page_id,space_id,slug,title,kind,updated_by) values (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','x2','  guide ','page','bob')"]).await.unwrap_err(), "23505");
    // File bytes come from a draft of the conversation holding exactly those bytes.
    let file = "insert into wiki_revision(revision_id,space_id,entry_kind,content_md,document_id,status,author_user_id,agent_instance_id,agent_name,session_id,proposed_title,proposed_parent_page_id) values ('00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-00000000000b','file','','00000000-0000-0000-0000-0000000000f1','proposed','alice','00000000-0000-0000-0000-0000000000a1','Helper','00000000-0000-0000-0000-0000000000c1','report.pdf','00000000-0000-0000-0000-0000000000e1')";
    let no_session = "insert into wiki_revision(revision_id,space_id,entry_kind,content_md,document_id,status,author_user_id,proposed_title) values ('00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-00000000000b','file','','00000000-0000-0000-0000-0000000000f1','proposed','alice','report.pdf')";
    check_violation(
        wiki_steps(
            &pool,
            &[WIKI_COPY[0], WIKI_COPY[1], WIKI_COPY[2], no_session],
        )
        .await
        .unwrap_err(),
    );
    let tampered = [
        "insert into document(id,space_id,name,created_by,quota_owner,purpose) values ('00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-00000000000b','report.pdf','alice','00000000-0000-0000-0000-00000000000b','wiki')",
        "insert into document_content(id,document_id,kind,object_key,mime,size,sha256,published_at) values ('00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-0000000000f1','primary','k/f1','application/pdf',40,repeat('b',64),now())",
        WIKI_COPY[2],
        file,
    ];
    check_violation(wiki_steps(&pool, &tampered).await.unwrap_err());
    // A person's own proposal from the conversation is detached in the same transaction.
    wiki_steps(&pool, &[WIKI_COPY[0], WIKI_COPY[1], WIKI_COPY[2], file,
        "update wiki_revision set session_id=null where revision_id='00000000-0000-0000-0000-0000000000f1'"]).await.unwrap();
    assert_eq!(
        used(&pool).await,
        80,
        "the pending copy counts in the space quota"
    );
    // Two proposals for one new name are allowed; only one can be accepted (D18).
    wiki_steps(&pool, &[
        "insert into document(id,space_id,name,created_by,quota_owner,purpose) values ('00000000-0000-0000-0000-0000000000f2','00000000-0000-0000-0000-00000000000b','report.pdf','alice','00000000-0000-0000-0000-00000000000b','wiki')",
        "insert into document_content(id,document_id,kind,object_key,mime,size,sha256,published_at) values ('00000000-0000-0000-0000-0000000000f2','00000000-0000-0000-0000-0000000000f2','primary','k/f2','application/pdf',40,repeat('a',64),now())",
        "update document set current_content_id='00000000-0000-0000-0000-0000000000f2' where id='00000000-0000-0000-0000-0000000000f2'",
        "insert into wiki_revision(revision_id,space_id,entry_kind,content_md,document_id,status,author_user_id,agent_instance_id,agent_name,session_id,proposed_title) values ('00000000-0000-0000-0000-0000000000f2','00000000-0000-0000-0000-00000000000b','file','','00000000-0000-0000-0000-0000000000f2','proposed','alice','00000000-0000-0000-0000-0000000000a1','Helper','00000000-0000-0000-0000-0000000000c1','report.pdf')",
        "update wiki_revision set session_id=null where revision_id='00000000-0000-0000-0000-0000000000f2'",
    ]).await.unwrap();
    // A file revision owns the copy named by its own id.
    check_violation(wiki_steps(&pool, &["insert into wiki_revision(revision_id,space_id,entry_kind,content_md,document_id,status,author_user_id,agent_instance_id,agent_name,session_id,proposed_title) values (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','file','','00000000-0000-0000-0000-0000000000f2','proposed','alice','00000000-0000-0000-0000-0000000000a1','Helper','00000000-0000-0000-0000-0000000000c1','x.pdf')"]).await.unwrap_err());
    wiki_steps(&pool, &[
        "insert into wiki_page(page_id,space_id,slug,title,kind,parent_page_id,updated_by,current_revision_id) values ('00000000-0000-0000-0000-0000000000e2','00000000-0000-0000-0000-00000000000b','e2','report.pdf','file','00000000-0000-0000-0000-0000000000e1','bob','00000000-0000-0000-0000-0000000000f1')",
        "update wiki_revision set status='published',page_id='00000000-0000-0000-0000-0000000000e2',proposed_parent_page_id=null,reviewed_at=now(),reviewed_by='bob' where revision_id='00000000-0000-0000-0000-0000000000f1'",
    ]).await.unwrap();
    // A file is a leaf born with its revision, carries no page text and has no history.
    violation(wiki_steps(&pool, &["insert into wiki_page(page_id,space_id,slug,title,kind,parent_page_id,updated_by) values (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','x3','Child','page','00000000-0000-0000-0000-0000000000e2','bob')"]).await.unwrap_err(), "23503");
    check_violation(wiki_steps(&pool, &["insert into wiki_page(page_id,space_id,slug,title,kind,updated_by) values (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','x4','a.txt','file','bob')"]).await.unwrap_err());
    violation(wiki_steps(&pool, &["insert into wiki_revision(revision_id,space_id,page_id,entry_kind,content_md,status,author_user_id) values (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','00000000-0000-0000-0000-0000000000e2','page','t','published','bob')"]).await.unwrap_err(), "23503");
    check_violation(wiki_steps(&pool, &["update wiki_revision set status='superseded' where revision_id='00000000-0000-0000-0000-0000000000f1'"]).await.unwrap_err());
    // A published Wiki copy is frozen: its bytes are never replaced, only retired.
    check_violation(wiki_steps(&pool, &[
        "insert into document_content(id,document_id,kind,object_key,mime,size,sha256,published_at) values ('00000000-0000-0000-0000-0000000000f9','00000000-0000-0000-0000-0000000000f1','primary','k/f9','application/pdf',40,repeat('c',64),now())",
        "update document set current_content_id='00000000-0000-0000-0000-0000000000f9' where id='00000000-0000-0000-0000-0000000000f1'",
    ]).await.unwrap_err());
    // A refusal deletes the proposal; SQL retires its copy and releases its quota.
    wiki_steps(
        &pool,
        &["delete from wiki_revision where revision_id='00000000-0000-0000-0000-0000000000f2'"],
    )
    .await
    .unwrap();
    let retired: Option<Uuid> = sqlx::query_scalar(
        "select current_content_id from document where id='00000000-0000-0000-0000-0000000000f2'",
    )
    .fetch_one(&pool)
    .await
    .unwrap();
    assert_eq!((retired, used(&pool).await), (None, 80));
    let scheduled: bool = sqlx::query_scalar("select cleanup_after is not null from document_content where id='00000000-0000-0000-0000-0000000000f2'")
        .fetch_one(&pool).await.unwrap();
    assert!(scheduled);
    // Deleting entries deletes their proposals and those creating entries under them (D21).
    wiki_steps(&pool, &["insert into wiki_revision(revision_id,space_id,entry_kind,content_md,status,author_user_id,proposed_title,proposed_parent_page_id) values ('00000000-0000-0000-0000-0000000000d2','00000000-0000-0000-0000-00000000000b','page','child','proposed','carol','Sub','00000000-0000-0000-0000-0000000000e1')"]).await.unwrap();
    wiki_steps(
        &pool,
        &["delete from wiki_page where page_id='00000000-0000-0000-0000-0000000000e2'"],
    )
    .await
    .unwrap();
    assert_eq!(
        used(&pool).await,
        40,
        "only the conversation output remains counted"
    );
    wiki_steps(
        &pool,
        &["delete from wiki_page where page_id='00000000-0000-0000-0000-0000000000e1'"],
    )
    .await
    .unwrap();
    let left: i64 = sqlx::query_scalar("select count(*) from wiki_revision")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(left, 0);
    // A Wiki copy has no destination; its journal rows name none either.
    check_violation(wiki_steps(&pool, &["insert into document(id,space_id,session_id,name,created_by,quota_owner,purpose) values (gen_random_uuid(),'00000000-0000-0000-0000-00000000000b','00000000-0000-0000-0000-0000000000c1','x','a','00000000-0000-0000-0000-00000000000b','wiki')"]).await.unwrap_err());
    wiki_steps(&pool, &[
        "insert into document_upload(id,request_key,actor,organization_id,space_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,purpose,reserved_bytes,request_fingerprint) values (gen_random_uuid(),gen_random_uuid(),'alice','00000000-0000-0000-0000-00000000000a','00000000-0000-0000-0000-00000000000b','00000000-0000-0000-0000-00000000000b','r.pdf','application/pdf',10,repeat('a',64),'u1','pending',now()+interval '1h','wiki',10,repeat('b',64))",
        "insert into document_upload(id,request_key,actor,organization_id,space_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,purpose,reserved_bytes,request_fingerprint) values (gen_random_uuid(),gen_random_uuid(),'bob','00000000-0000-0000-0000-00000000000a','00000000-0000-0000-0000-00000000000b','00000000-0000-0000-0000-00000000000b','r.pdf','application/pdf',10,repeat('a',64),'u2','pending',now()+interval '1h','wiki',10,repeat('b',64))",
    ]).await.unwrap();
    check_violation(wiki_steps(&pool, &["insert into document_upload(id,request_key,actor,organization_id,space_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,purpose,reserved_bytes) values (gen_random_uuid(),gen_random_uuid(),'bob','00000000-0000-0000-0000-00000000000a','00000000-0000-0000-0000-00000000000b','00000000-0000-0000-0000-00000000000b','r.pdf','application/pdf',10,repeat('a',64),'u3','pending',now()+interval '1h','output',10)"]).await.unwrap_err());
    // Request identity is mandatory for Wiki receipts and cannot change or vanish.
    for statement in [
        "update document_upload set request_fingerprint=repeat('c',64) where object_key='u1'",
        "update document_upload set request_fingerprint=null where object_key='u1'",
        "insert into document_upload(id,request_key,actor,organization_id,space_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,purpose,reserved_bytes) select gen_random_uuid(),gen_random_uuid(),actor,organization_id,space_id,quota_owner,name,mime,size,sha256,'missing-identity',status,expires_at,purpose,reserved_bytes from document_upload where object_key='u1'",
    ] {
        check_violation(wiki_steps(&pool, &[statement]).await.unwrap_err());
    }
    // A draft and its copy go with their conversation.
    wiki_steps(&pool, &["insert into wiki_revision(revision_id,space_id,entry_kind,content_md,status,author_user_id,agent_instance_id,agent_name,session_id,proposed_title) values ('00000000-0000-0000-0000-0000000000d3','00000000-0000-0000-0000-00000000000b','page','z','proposed','alice','00000000-0000-0000-0000-0000000000a1','Helper','00000000-0000-0000-0000-0000000000c1','Z')"]).await.unwrap();
    wiki_steps(
        &pool,
        &[
            "delete from document_content where document_id='00000000-0000-0000-0000-0000000000b1'",
            "delete from document where id='00000000-0000-0000-0000-0000000000b1'",
            "delete from session_metadata where session_id='00000000-0000-0000-0000-0000000000c1'",
        ],
    )
    .await
    .unwrap();
    let drafts: i64 = sqlx::query_scalar("select count(*) from wiki_revision")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(drafts, 0);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn wiki_parent_detaches_only_on_acceptance_without_mutating_content_or_provenance() {
    let pool = database().await;
    let space = organization(&pool, "Wiki parent lifecycle").await;
    let parent = Uuid::new_v4();
    let page = Uuid::new_v4();
    let revision = Uuid::new_v4();
    for id in [parent, page] {
        sqlx::query("insert into wiki_page(page_id,space_id,slug,title,kind,updated_by) values ($1,$2,$1::text,$1::text,'page','author')")
            .bind(id).bind(space).execute(&pool).await.unwrap();
    }
    sqlx::query("insert into wiki_revision(revision_id,space_id,entry_kind,content_md,status,author_user_id,proposed_title,proposed_parent_page_id) values ($1,$2,'page','original','proposed','author','Child',$3)")
        .bind(revision).bind(space).bind(parent).execute(&pool).await.unwrap();
    // Every failed attempt must leave the same proposal, including its destination.
    for patch in [
        "proposed_parent_page_id=null",
        "proposed_parent_page_id=$2", // another existing destination, without acceptance
        "proposed_parent_page_id=revision_id", // another destination, even if nonexistent
        "proposed_parent_page_id=revision_id,status='published',page_id=$2",
        "status='published',page_id=$2", // acceptance cannot retain the dependency
        "proposed_parent_page_id=null,status='superseded',page_id=$2",
        "proposed_parent_page_id=null,status='published',page_id=$2,content_md='changed'",
        "proposed_parent_page_id=null,status='published',page_id=$2,author_user_id='other'",
        "proposed_parent_page_id=null,status='published',page_id=$2,agent_instance_id=revision_id,agent_name='Other'",
        "proposed_parent_page_id=null,status='published',page_id=$2,created_at=created_at+interval '1s'",
        "proposed_parent_page_id=null,status='published',page_id=$2,base_revision_id=revision_id",
        "proposed_parent_page_id=null,status='published',page_id=$2,proposed_title='Changed'",
    ] {
        let sql = sqlx::AssertSqlSafe(format!(
            "update wiki_revision set {patch} where revision_id=$1 and $2::uuid is not null"
        ));
        check_violation(
            sqlx::query(sql)
                .bind(revision)
                .bind(page)
                .execute(&pool)
                .await
                .unwrap_err(),
        );
    }
    // Direct insertion of accepted content cannot recreate an old-parent dependency.
    check_violation(sqlx::query("insert into wiki_revision(revision_id,space_id,page_id,entry_kind,content_md,status,author_user_id,proposed_title,proposed_parent_page_id) values (gen_random_uuid(),$1,$2,'page','text','published','author','Child',$3)")
        .bind(space).bind(page).bind(parent).execute(&pool).await.unwrap_err());
    let original: serde_json::Value = sqlx::query_scalar("select to_jsonb(r) - array['status','page_id','proposed_parent_page_id','reviewed_at','reviewed_by'] from wiki_revision r where revision_id=$1")
        .bind(revision).fetch_one(&pool).await.unwrap();
    sqlx::query("update wiki_revision set proposed_parent_page_id=null,status='published',page_id=$2,reviewed_at=clock_timestamp(),reviewed_by='editor' where revision_id=$1")
        .bind(revision).bind(page).execute(&pool).await.unwrap();
    let accepted: serde_json::Value = sqlx::query_scalar("select to_jsonb(r) - array['status','page_id','proposed_parent_page_id','reviewed_at','reviewed_by'] from wiki_revision r where revision_id=$1")
        .bind(revision).fetch_one(&pool).await.unwrap();
    assert_eq!(accepted, original);
    for patch in [
        "proposed_parent_page_id=$2",
        "content_md='changed'",
        "author_user_id='other'",
        "agent_instance_id=revision_id,agent_name='Other'",
        "reviewed_by='other'",
        "reviewed_at=reviewed_at+interval '1s'",
    ] {
        let sql = sqlx::AssertSqlSafe(format!(
            "update wiki_revision set {patch} where revision_id=$1 and $2::uuid is not null"
        ));
        check_violation(
            sqlx::query(sql)
                .bind(revision)
                .bind(parent)
                .execute(&pool)
                .await
                .unwrap_err(),
        );
    }
    sqlx::query("update wiki_revision set status='superseded' where revision_id=$1")
        .bind(revision)
        .execute(&pool)
        .await
        .unwrap();
    check_violation(
        sqlx::query("update wiki_revision set proposed_parent_page_id=$2 where revision_id=$1")
            .bind(revision)
            .bind(parent)
            .execute(&pool)
            .await
            .unwrap_err(),
    );
}
