// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use control_plane::{
    api::{AppState, routes},
    organization_prompt_settings::{self as settings, PatchCreationAssistant},
};
use serde_json::{Value, json};
use std::sync::Arc;
use uuid::Uuid;

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn organization_prompt_settings_permissions_isolation_and_atomic_writes() {
    let pool = super::environment::database::database().await;
    control_plane::bootstrap::grant_root(&pool, "root")
        .await
        .unwrap();
    let org = Uuid::new_v4();
    let other = Uuid::new_v4();
    let team = Uuid::new_v4();
    sqlx::query("insert into space(id,kind,name,organization_id,parent_id) values($1,'organization','A',$1,null),($2,'organization','B',$2,null),($3,'team','Team',$1,$1)")
        .bind(org).bind(other).bind(team).execute(&pool).await.unwrap();
    sqlx::query("insert into space_role_grant(space_id,subject,role) values($1,'owner','owner'),($1,'admin','organization_admin'),($1,'editor','editor'),($2,'other','owner'),($3,'team-owner','owner'),($1,'owner','member'),($1,'admin','member'),($1,'editor','member'),($2,'other','member'),($3,'team-owner','member')")
        .bind(org).bind(other).bind(team).execute(&pool).await.unwrap();
    sqlx::query(
        "insert into platform_role_grant(subject,role) values('prompt-editor','prompt_editor')",
    )
    .execute(&pool)
    .await
    .unwrap();
    // Published catalogue fixture: no provider or discovery endpoint is contacted.
    sqlx::query("insert into model_source(source_id,configuration,state,snapshot_revision,snapshot_source_revision) values('fixture','{\"source_id\":\"fixture\",\"revision\":1,\"enabled\":true}','ok',1,1)").execute(&pool).await.unwrap();
    sqlx::query("insert into model_offer(source_id,upstream_model_id,metadata,first_seen_at,last_seen_at,advertised) values('fixture','chat','{\"chat\":true,\"reasoning\":true}',now(),now(),true)").execute(&pool).await.unwrap();
    sqlx::query(
        "insert into organization_model_source(organization_id,source_id) values($1,'fixture')",
    )
    .bind(org)
    .execute(&pool)
    .await
    .unwrap();
    sqlx::query("insert into organization_model_policy(organization_id,revision,created_by,updated_by) values($1,1,'owner','owner')").bind(org).execute(&pool).await.unwrap();
    sqlx::query("insert into organization_model_permission(organization_id,source_id,upstream_model_id,reasoning_enabled) values($1,'fixture','chat',true)").bind(org).execute(&pool).await.unwrap();
    let identity = super::support::IdentityServer::start().await;
    let app = routes(AppState {
        pool: pool.clone(),
        auth: Arc::new(identity.auth().await),
        agent_catalog: Default::default(),
        history: None,
        directory: None,
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    });
    let common = format!("/spaces/{org}/prompt-settings/common");
    let creation = format!("/spaces/{org}/prompt-settings/creation-assistant");
    for actor in [
        "admin",
        "editor",
        "root",
        "prompt-editor",
        "team-owner",
        "other",
    ] {
        for (method, path, body) in [
            ("GET", &common, json!(null)),
            ("PUT", &common, json!({"text":"denied"})),
            ("GET", &creation, json!(null)),
            ("PATCH", &creation, json!({"reasoning":true})),
            ("DELETE", &creation, json!(null)),
        ] {
            let (status, body) =
                super::support::request(&app, &identity, Some(actor), method, path, body).await;
            assert!(
                [403, 404].contains(&status),
                "{actor} {method}: {status} {body}"
            );
        }
    }
    let (status, body) =
        super::support::request(&app, &identity, Some("owner"), "GET", &common, Value::Null).await;
    assert_eq!(status, 200, "{body}");
    assert!(body["text"].is_null());
    assert_eq!(body["defaults"][0]["runtime_id"], "control-plane");
    assert_eq!(
        super::support::request(
            &app,
            &identity,
            Some("owner"),
            "PUT",
            &common,
            json!({"text":""})
        )
        .await
        .0,
        204
    );
    assert_eq!(
        settings::read(&pool, org)
            .await
            .unwrap()
            .common_text
            .as_deref(),
        Some("")
    );
    assert!(
        settings::read(&pool, other)
            .await
            .unwrap()
            .common_text
            .is_none()
    );
    assert_eq!(
        super::support::request(
            &app,
            &identity,
            Some("owner"),
            "PATCH",
            &creation,
            json!({"text":"Write {language}","reasoning":true})
        )
        .await
        .0,
        204
    );
    let model = json!({"source_id":"fixture","upstream_model_id":"chat"});
    let response = super::support::request(
        &app,
        &identity,
        Some("owner"),
        "PATCH",
        &creation,
        json!({"model":model}),
    )
    .await;
    assert_eq!(response.0, 204, "{:?}", response.1);
    let date = settings::read(&pool, org)
        .await
        .unwrap()
        .creation_text_updated_at;
    assert_eq!(
        super::support::request(
            &app,
            &identity,
            Some("owner"),
            "PATCH",
            &creation,
            json!({"reasoning":false})
        )
        .await
        .0,
        204
    );
    assert_eq!(
        settings::read(&pool, org)
            .await
            .unwrap()
            .creation_text_updated_at,
        date
    );
    assert_eq!(
        super::support::request(
            &app,
            &identity,
            Some("owner"),
            "PATCH",
            &creation,
            json!({"text":"Write {language}"})
        )
        .await
        .0,
        204
    );
    assert!(
        settings::read(&pool, org)
            .await
            .unwrap()
            .creation_text_updated_at
            > date
    );
    assert_eq!(
        super::support::request(
            &app,
            &identity,
            Some("owner"),
            "PATCH",
            &creation,
            json!({"model":{"source_id":"missing","upstream_model_id":"unknown"}})
        )
        .await
        .0,
        422
    );
    for (path, body) in [
        (&common, json!({"text":"</platform_prompt>"})),
        (&creation, json!({"text":" \n"})),
        (&creation, json!({"text":"x".repeat(20001)})),
    ] {
        let method = if path == &common { "PUT" } else { "PATCH" };
        assert_eq!(
            super::support::request(&app, &identity, Some("owner"), method, path, body)
                .await
                .0,
            422
        );
    }
    // Two connections race without the HTTP lock: row updates preserve the other tab.
    let mut first = pool.acquire().await.unwrap();
    let mut second = pool.acquire().await.unwrap();
    let patch = PatchCreationAssistant {
        text: Some(Some("new draft".into())),
        reasoning: Some(true),
        ..Default::default()
    };
    let (a, b) = tokio::join!(
        settings::save_common(&mut first, org, "owner", "common"),
        settings::save_creation(&mut second, org, "owner", &patch)
    );
    a.unwrap();
    b.unwrap();
    let saved = settings::read(&pool, org).await.unwrap();
    assert_eq!(saved.common_text.as_deref(), Some("common"));
    assert_eq!(saved.creation_text.as_deref(), Some("new draft"));
    // Same-field writes are serialized by commit, including a writer already waiting.
    let mut tx = pool.begin().await.unwrap();
    settings::save_common(&mut tx, org, "first", "first")
        .await
        .unwrap();
    let pending_pool = pool.clone();
    let last = tokio::spawn(async move {
        settings::save_common(
            &mut pending_pool.acquire().await.unwrap(),
            org,
            "last",
            "last",
        )
        .await
        .unwrap();
    });
    tx.commit().await.unwrap();
    last.await.unwrap();
    assert_eq!(
        settings::read(&pool, org)
            .await
            .unwrap()
            .common_text
            .as_deref(),
        Some("last")
    );
    assert_eq!(
        super::support::request(
            &app,
            &identity,
            Some("owner"),
            "DELETE",
            &creation,
            Value::Null
        )
        .await
        .0,
        204
    );
    let saved = settings::read(&pool, org).await.unwrap();
    assert!(saved.creation_text.is_none());
    assert_eq!(
        serde_json::to_value(saved.creation_model.unwrap().0).unwrap(),
        model
    );
    assert!(saved.creation_reasoning);
    assert_eq!(saved.common_text.as_deref(), Some("last"));
    // Structural protections hold independently of routes; deletion purges settings.
    let err = sqlx::query("insert into organization_prompt_settings(organization_id) values($1)")
        .bind(team)
        .execute(&pool)
        .await
        .unwrap_err();
    assert_eq!(
        err.as_database_error().unwrap().code().as_deref(),
        Some("23514")
    );
    let err=sqlx::query("update organization_prompt_settings set creation_text=repeat('x',20001) where organization_id=$1").bind(org).execute(&pool).await.unwrap_err();
    assert_eq!(
        err.as_database_error().unwrap().code().as_deref(),
        Some("23514")
    );
    sqlx::query("delete from space where id=$1")
        .bind(team)
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("delete from space where id=$1")
        .bind(org)
        .execute(&pool)
        .await
        .unwrap();
    assert!(
        !sqlx::query_scalar::<_, bool>(
            "select exists(select 1 from organization_prompt_settings where organization_id=$1)"
        )
        .bind(org)
        .fetch_one(&pool)
        .await
        .unwrap()
    );
}
