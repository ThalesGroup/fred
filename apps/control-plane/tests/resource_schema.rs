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

async fn prompt(pool: &PgPool, space: Uuid, name: &str) -> Result<Uuid, sqlx::Error> {
    let id = Uuid::new_v4();
    sqlx::query("insert into prompt(prompt_id,space_id,logical_name,display_name,text,created_by) values($1,$2,$3,'Summary','Original {{unknown}}','alice')")
        .bind(id).bind(space).bind(name).execute(pool).await?;
    Ok(id)
}

async fn agent(pool: &PgPool, space: Uuid) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by) values($1,$2,$1,'native','assistant',$1::text,'{}','alice')")
        .bind(id).bind(space).execute(pool).await.unwrap();
    id
}

async fn session(
    pool: &PgPool,
    space: Uuid,
    agent: Uuid,
    deployment: Option<Uuid>,
) -> Result<Uuid, sqlx::Error> {
    let id = Uuid::new_v4();
    sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,agent_space_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,'alice',$2,$3,$4,$3,'native','Assistant',1)")
        .bind(id).bind(space).bind(agent).bind(deployment).execute(pool).await?;
    Ok(id)
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn prompt_names_and_promotions_are_local_and_independent() {
    let pool = database(None).await;
    let spaces = spaces(&pool).await;
    let source = prompt(&pool, spaces[0], "resume").await.unwrap();
    for space in &spaces[1..] {
        prompt(&pool, *space, "resume").await.unwrap();
    }
    violation(
        prompt(&pool, spaces[0], "resume").await.unwrap_err(),
        "23505",
    );
    for invalid in [
        "",
        "skill",
        "Resume",
        " resume",
        "a b",
        "résumé",
        "/resume",
        &"a".repeat(65),
    ] {
        violation(
            prompt(&pool, spaces[0], invalid).await.unwrap_err(),
            "23514",
        );
    }
    prompt(&pool, spaces[0], &"a".repeat(64)).await.unwrap();
    sqlx::query("update prompt set text='Edited',updated_by='bob' where prompt_id=$1")
        .bind(source)
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("delete from prompt where prompt_id=$1")
        .bind(source)
        .execute(&pool)
        .await
        .unwrap();
    let texts: Vec<String> =
        sqlx::query_scalar("select text from prompt where logical_name='resume'")
            .fetch_all(&pool)
            .await
            .unwrap();
    assert_eq!(texts, vec!["Original {{unknown}}"; 3]);
    // Resource purge follows definitive space purge, not deletion of its source copy.
    sqlx::query("delete from space where id=$1")
        .bind(spaces[2])
        .execute(&pool)
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from prompt where logical_name='resume'")
            .fetch_one(&pool)
            .await
            .unwrap(),
        2
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn prompt_identity_and_edit_metadata_are_protected() {
    let pool = database(None).await;
    let [org, _, _, _] = spaces(&pool).await;
    let id = prompt(&pool, org, "resume").await.unwrap();
    let initial: (String, String, bool) = sqlx::query_as(
        "select created_by,updated_by,created_at=updated_at from prompt where prompt_id=$1",
    )
    .bind(id)
    .fetch_one(&pool)
    .await
    .unwrap();
    assert_eq!(initial, ("alice".into(), "alice".into(), true));
    for statement in [
        "update prompt set logical_name='other' where prompt_id=$1",
        "update prompt set prompt_id=gen_random_uuid() where prompt_id=$1",
        "update prompt set space_id=gen_random_uuid() where prompt_id=$1",
        "update prompt set created_by='bob' where prompt_id=$1",
        "update prompt set created_at=clock_timestamp() where prompt_id=$1",
    ] {
        violation(
            sqlx::query(AssertSqlSafe(statement))
                .bind(id)
                .execute(&pool)
                .await
                .unwrap_err(),
            "23514",
        );
    }
    sqlx::query("update prompt set updated_at='2000-01-01',updated_by='bob' where prompt_id=$1")
        .bind(id)
        .execute(&pool)
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, String>("select updated_by from prompt where prompt_id=$1")
            .bind(id)
            .fetch_one(&pool)
            .await
            .unwrap(),
        "alice"
    );
    sqlx::query("update prompt set text='New text',updated_by='bob',updated_at='2000-01-01' where prompt_id=$1")
        .bind(id).execute(&pool).await.unwrap();
    let edited: (String, bool) =
        sqlx::query_as("select updated_by,updated_at>created_at from prompt where prompt_id=$1")
            .bind(id)
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(edited, ("bob".into(), true));
    violation(
        sqlx::query("update prompt set text='Other',updated_by=null where prompt_id=$1")
            .bind(id)
            .execute(&pool)
            .await
            .unwrap_err(),
        "23502",
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn chat_space_survives_agent_deletion_and_owns_attachments() {
    let pool = database(None).await;
    let [org, team, project, _] = spaces(&pool).await;
    let instance = agent(&pool, org).await;
    let chat = session(&pool, project, instance, Some(org)).await.unwrap();
    let placement: (Uuid, Uuid) =
        sqlx::query_as("select space_id,agent_space_id from session_metadata where session_id=$1")
            .bind(chat)
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(placement, (project, org));
    for statement in [
        "update session_metadata set space_id=gen_random_uuid() where session_id=$1",
        "update session_metadata set user_id='bob' where session_id=$1",
        "update session_metadata set agent_instance_id=gen_random_uuid() where session_id=$1",
        "update session_metadata set agent_space_id=null where session_id=$1",
        "update session_metadata set template_id=gen_random_uuid() where session_id=$1",
        "update session_metadata set runtime_id='other' where session_id=$1",
        "update session_metadata set session_id=gen_random_uuid() where session_id=$1",
    ] {
        violation(
            sqlx::query(AssertSqlSafe(statement))
                .bind(chat)
                .execute(&pool)
                .await
                .unwrap_err(),
            "23514",
        );
    }
    for (space, expected) in [(org, false), (project, true)] {
        let result = sqlx::query("insert into document(id,space_id,session_id,name,mime,size,sha256,created_by,object_key,quota_owner) values($1,$2,$3,'file.txt','text/plain',1,repeat('a',64),'alice',$1::text,$4)")
            .bind(Uuid::new_v4()).bind(space).bind(chat).bind(team).execute(&pool).await;
        if expected {
            result.unwrap();
        } else {
            violation(result.unwrap_err(), "23503");
        }
    }
    sqlx::query("delete from agent_instance where agent_instance_id=$1")
        .bind(instance)
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("update session_metadata set title='History' where session_id=$1")
        .bind(chat)
        .execute(&pool)
        .await
        .unwrap();
    let retained: (Uuid, Uuid, Uuid) = sqlx::query_as("select s.agent_instance_id,s.agent_space_id,d.space_id from session_metadata s join document d on d.session_id=s.session_id where s.session_id=$1")
        .bind(chat).fetch_one(&pool).await.unwrap();
    assert_eq!(retained, (instance, org, project));
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn session_requires_real_same_organization_association() {
    let pool = database(None).await;
    let [org, _, project, _] = spaces(&pool).await;
    let other = spaces(&pool).await[0];
    let instance = agent(&pool, org).await;
    violation(
        session(&pool, project, instance, Some(other))
            .await
            .unwrap_err(),
        "23514",
    );
    violation(
        session(&pool, other, instance, Some(org))
            .await
            .unwrap_err(),
        "23514",
    );
    violation(
        session(&pool, project, Uuid::new_v4(), None)
            .await
            .unwrap_err(),
        "23503",
    );
    violation(
        session(&pool, Uuid::new_v4(), instance, None)
            .await
            .unwrap_err(),
        "23503",
    );
    let chat = session(&pool, project, instance, None).await.unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, Uuid>(
            "select agent_space_id from session_metadata where session_id=$1"
        )
        .bind(chat)
        .fetch_one(&pool)
        .await
        .unwrap(),
        org
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn migration_recovers_known_deployment_without_inventing_deleted_agents() {
    let pool = database(Some(7)).await;
    let [org, _, project, _] = spaces(&pool).await;
    let instance = agent(&pool, org).await;
    let missing = Uuid::new_v4();
    for agent in [instance, missing] {
        sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,'alice',$2,$1,$1,'native','Assistant',1)")
            .bind(agent).bind(project).execute(&pool).await.unwrap();
    }
    sqlx::migrate!().run(&pool).await.unwrap();
    for (id, expected) in [(instance, Some(org)), (missing, None)] {
        assert_eq!(
            sqlx::query_scalar::<_, Option<Uuid>>(
                "select agent_space_id from session_metadata where session_id=$1"
            )
            .bind(id)
            .fetch_one(&pool)
            .await
            .unwrap(),
            expected
        );
        sqlx::query("update session_metadata set title='History' where session_id=$1")
            .bind(id)
            .execute(&pool)
            .await
            .unwrap();
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn agent_metadata_preserves_unknown_history_and_requires_future_authors() {
    let pool = database(Some(7)).await;
    let [org, _, _, _] = spaces(&pool).await;
    let old = agent(&pool, org).await;
    sqlx::query(
        "update agent_instance set created_by=null,updated_by=null where agent_instance_id=$1",
    )
    .bind(old)
    .execute(&pool)
    .await
    .unwrap();
    sqlx::migrate!().run(&pool).await.unwrap();
    let history: (Option<String>, Option<String>) = sqlx::query_as(
        "select created_by,updated_by from agent_instance where agent_instance_id=$1",
    )
    .bind(old)
    .fetch_one(&pool)
    .await
    .unwrap();
    assert_eq!(history, (None, None));
    violation(
        sqlx::query("update agent_instance set tuning='{\"x\":1}' where agent_instance_id=$1")
            .bind(old)
            .execute(&pool)
            .await
            .unwrap_err(),
        "23514",
    );
    sqlx::query(
        "update agent_instance set tuning='{\"x\":1}',updated_by='bob' where agent_instance_id=$1",
    )
    .bind(old)
    .execute(&pool)
    .await
    .unwrap();
    let edited: (Option<String>, String, bool) = sqlx::query_as("select created_by,updated_by,updated_at>created_at from agent_instance where agent_instance_id=$1")
        .bind(old).fetch_one(&pool).await.unwrap();
    assert_eq!(edited, (None, "bob".into(), true));
    let new = agent(&pool, org).await;
    assert!(sqlx::query_scalar::<_, bool>("select created_by=updated_by and created_at=updated_at from agent_instance where agent_instance_id=$1").bind(new).fetch_one(&pool).await.unwrap());
    for statement in [
        "update agent_instance set space_id=gen_random_uuid() where agent_instance_id=$1",
        "update agent_instance set agent_instance_id=gen_random_uuid() where agent_instance_id=$1",
        "update agent_instance set template_id=gen_random_uuid() where agent_instance_id=$1",
        "update agent_instance set source_runtime_id='other' where agent_instance_id=$1",
        "update agent_instance set source_agent_id='other' where agent_instance_id=$1",
        "update agent_instance set created_by='bob' where agent_instance_id=$1",
    ] {
        violation(
            sqlx::query(AssertSqlSafe(statement))
                .bind(new)
                .execute(&pool)
                .await
                .unwrap_err(),
            "23514",
        );
    }
    sqlx::query("update agent_instance set updated_by='bob',updated_at='2000-01-01' where agent_instance_id=$1")
        .bind(new).execute(&pool).await.unwrap();
    assert!(sqlx::query_scalar::<_, bool>("select created_by=updated_by and created_at=updated_at from agent_instance where agent_instance_id=$1").bind(new).fetch_one(&pool).await.unwrap());
    violation(sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning) values($1,$2,$1,'native','assistant',$1::text,'{}')")
        .bind(Uuid::new_v4()).bind(org).execute(&pool).await.unwrap_err(), "23514");
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn association_creation_holds_agent_until_commit_but_not_afterward() {
    let pool = database(None).await;
    let [org, _, project, _] = spaces(&pool).await;
    let instance = agent(&pool, org).await;
    let mut creation = pool.begin().await.unwrap();
    sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,'alice',$2,$1,$1,'native','Assistant',1)")
        .bind(instance).bind(project).execute(&mut *creation).await.unwrap();
    let mut deletion = pool.begin().await.unwrap();
    sqlx::query("set local lock_timeout='100ms'")
        .execute(&mut *deletion)
        .await
        .unwrap();
    violation(
        sqlx::query("delete from agent_instance where agent_instance_id=$1")
            .bind(instance)
            .execute(&mut *deletion)
            .await
            .unwrap_err(),
        "55P03",
    );
    deletion.rollback().await.unwrap();
    creation.commit().await.unwrap();
    sqlx::query("delete from agent_instance where agent_instance_id=$1")
        .bind(instance)
        .execute(&pool)
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, Uuid>(
            "select agent_space_id from session_metadata where session_id=$1"
        )
        .bind(instance)
        .fetch_one(&pool)
        .await
        .unwrap(),
        org
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
async fn assigned_agent_names_are_canonical_local_and_immutable() {
    let pool = database(None).await;
    let [org, team, _, _] = spaces(&pool).await;
    let source = agent(&pool, org).await;
    let promoted = agent(&pool, team).await;
    let duplicate = agent(&pool, org).await;
    for instance in [source, promoted] {
        sqlx::query("update agent_instance set logical_name='resume' where agent_instance_id=$1")
            .bind(instance)
            .execute(&pool)
            .await
            .unwrap();
    }
    // Types have separate namespaces in the same space.
    prompt(&pool, org, "resume").await.unwrap();
    violation(
        sqlx::query("update agent_instance set logical_name='resume' where agent_instance_id=$1")
            .bind(duplicate)
            .execute(&pool)
            .await
            .unwrap_err(),
        "23505",
    );
    for invalid in [
        "",
        "Resume",
        "/resume",
        "a b",
        "résumé",
        "resume\n",
        &"a".repeat(65),
    ] {
        violation(
            sqlx::query("update agent_instance set logical_name=$2 where agent_instance_id=$1")
                .bind(duplicate)
                .bind(invalid)
                .execute(&pool)
                .await
                .unwrap_err(),
            "23514",
        );
    }
    for name in [Some("other"), None] {
        violation(
            sqlx::query("update agent_instance set logical_name=$2 where agent_instance_id=$1")
                .bind(source)
                .bind(name)
                .execute(&pool)
                .await
                .unwrap_err(),
            "23514",
        );
    }
    sqlx::query("update agent_instance set tuning='{\"edited\":true}',updated_by='bob',display_name='New label' where agent_instance_id=$1")
        .bind(source).execute(&pool).await.unwrap();
    sqlx::query("delete from agent_instance where agent_instance_id=$1")
        .bind(source)
        .execute(&pool)
        .await
        .unwrap();
    let independent: (String, serde_json::Value) =
        sqlx::query_as("select logical_name,tuning from agent_instance where agent_instance_id=$1")
            .bind(promoted)
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(independent, ("resume".into(), serde_json::json!({})));
}
