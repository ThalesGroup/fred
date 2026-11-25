// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use axum::{
    Json, Router,
    body::{Body, to_bytes},
    http::{HeaderMap, Request},
    routing::{get, post},
};
use control_plane::{
    agents::{PlatformConfig, RuntimeCatalogSource, template_id},
    api::{AppState, routes},
    auth::Authenticator,
    config::Configuration,
    model_catalog,
    organization_prompt_settings::{self, PatchCreationAssistant},
};
use serde_json::{Value, json};
use std::sync::Arc;
use tokio::sync::Mutex;
use tower::ServiceExt;
use uuid::Uuid;

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn creation_draft_is_authorized_isolated_and_never_creates_an_instance() {
    let pool = super::environment::database::database().await;
    control_plane::bootstrap::grant_root(&pool, "root")
        .await
        .unwrap();
    let (org, other, team) = (Uuid::new_v4(), Uuid::new_v4(), Uuid::new_v4());
    sqlx::query("insert into space(id,kind,name,organization_id,parent_id) values($1,'organization','Draft A',$1,null),($2,'organization','Draft B',$2,null),($3,'team','Draft team',$1,$1)").bind(org).bind(other).bind(team).execute(&pool).await.unwrap();
    sqlx::query("insert into space_role_grant(space_id,subject,role) values($1,'owner','owner'),($2,'editor','editor'),($2,'reader','member')").bind(org).bind(team).execute(&pool).await.unwrap();
    let template = template_id(org, "fixture", "template");
    control_plane::authorization::set_agent_default_on(
        &mut pool.acquire().await.unwrap(),
        org,
        template,
        true,
    )
    .await
    .unwrap();
    sqlx::query("insert into runtime_catalog(runtime_id,reachable) values('fixture',true)")
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("insert into capability_offer(source_id,capability_id,version,descriptor,advertised) values('fixture','allowed','1','{}',true),('fixture','forbidden','1','{}',true)").execute(&pool).await.unwrap();
    sqlx::query("insert into organization_capability(organization_id,source_id,capability_id,enabled_by) values($1,'fixture','allowed','owner')").bind(org).execute(&pool).await.unwrap();
    let source: model_catalog::config::ModelSource = serde_json::from_value(json!({"source_id":"model-source","revision":1,"enabled":true,"visibility_scope":"fixture-account", "inventory":{"kind":"declared","models":[{"id":"chat","reasoning":true},{"id":"dedicated","reasoning":true}]},"inference":{"credential_binding":"fixture","api_root":"https://inference.invalid/v1","wire":"openai_chat","route":"standard","dialect":"openai","auth":{"kind":"api_key"}}})).unwrap();
    model_catalog::configure_sources(&pool, std::slice::from_ref(&source))
        .await
        .unwrap();
    model_catalog::refresh(&pool, &source).await.unwrap(); // declared inventory: no provider call
    sqlx::query("insert into organization_model_source(organization_id,source_id) values($1,'model-source')").bind(org).execute(&pool).await.unwrap();
    sqlx::query("insert into organization_model_policy(organization_id,revision,created_by,updated_by) values($1,1,'owner','owner')").bind(org).execute(&pool).await.unwrap();
    sqlx::query("insert into organization_model_permission(organization_id,source_id,upstream_model_id,reasoning_enabled) values($1,'model-source','chat',true),($1,'model-source','dedicated',true)").bind(org).execute(&pool).await.unwrap();
    sqlx::query("update organization_model_policy set default_source_id='model-source',default_upstream_model_id='chat' where organization_id=$1").bind(org).execute(&pool).await.unwrap();
    let patch: PatchCreationAssistant=serde_json::from_value(json!({"text":"Organization A meta prompt in {language}","model":{"source_id":"model-source","upstream_model_id":"dedicated"},"reasoning":true})).unwrap();
    organization_prompt_settings::save_creation(
        &mut pool.acquire().await.unwrap(),
        org,
        "owner",
        &patch,
    )
    .await
    .unwrap();
    let fields = Arc::new(Mutex::new(
        json!([{"key":"prompts.system","type":"prompt"}]),
    ));
    let received = Arc::new(Mutex::new(Vec::<(HeaderMap, Value)>::new()));
    let catalog_fields = fields.clone();
    let captured = received.clone();
    let pod = Router::new()
        .route("/agents/templates", get(move || {
            let fields = catalog_fields.clone();
            async move {
                Json(json!([{
                    "template_agent_id": "template", "title": "Template",
                    "description": "Draftable", "kind": "react",
                    "default_tuning": {"fields": fields.lock().await.clone()},
                    "available_capabilities": [{"id":"allowed"}, {"id":"forbidden"}],
                    "supports_capabilities": true
                }]))
            }
        }))
        .route("/agents/creation-assistant/draft", post(move |headers: HeaderMap, Json(body): Json<Value>| {
            let captured = captured.clone();
            async move {
                captured.lock().await.push((headers, body));
                Json(json!({"name":"Draft", "role":"Role", "description":"Description",
                    "system_prompt":"Draft instructions", "capability_ids":["allowed","forbidden","injected"]}))
            }
        }));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    let task = tokio::spawn(async move { axum::serve(listener, pod).await.unwrap() });
    let identity = super::support::IdentityServer::start().await;
    let mut config: Configuration =
        serde_yaml_ng::from_str(include_str!("../../config/configuration.yaml")).unwrap();
    config.security.user.realm_url = identity.realm.clone();
    config.security.delegation.accept_delegated_calls = true;
    config.security.delegation.service_accounts_only = true;
    let app = routes(AppState {
        pool: pool.clone(),
        auth: Arc::new(
            Authenticator::start(config.security().unwrap())
                .await
                .unwrap(),
        ),
        agent_catalog: PlatformConfig {
            runtime_catalog_sources: vec![RuntimeCatalogSource {
                runtime_id: "fixture".into(),
                base_url: base,
                public_base_url: None,
                enabled: true,
            }],
            ..Default::default()
        },
        history: None,
        directory: None,
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    });
    let path = format!("/spaces/{team}/agent-templates/{template}/creation-assistant/draft");
    let body = json!({"description":"Help me", "language":"fr", "capabilities":[{"id":"allowed","name":"Allowed"},{"id":"forbidden","name":"Forbidden"},{"id":"injected","name":"Injected"}]});
    for user in ["reader", "owner", "stranger"] {
        assert_eq!(
            super::support::request(&app, &identity, Some(user), "POST", &path, body.clone())
                .await
                .0,
            403
        );
    }
    for field in ["model", "reasoning", "creation_prompt", "inference"] {
        let mut injected = body.clone();
        injected[field] = json!("injected");
        assert_eq!(
            super::support::request(&app, &identity, Some("editor"), "POST", &path, injected)
                .await
                .0,
            422
        );
    }
    let (status, result) =
        super::support::request(&app, &identity, Some("editor"), "POST", &path, body.clone()).await;
    assert_eq!(status, 200, "{result}");
    assert_eq!(result["capability_ids"], json!(["allowed"]));
    assert!(result.get("inference").is_none());
    let requests = received.lock().await;
    assert_eq!(requests.len(), 1);
    assert!(requests[0].0.get("authorization").is_some());
    assert_eq!(requests[0].1["space_id"], json!(team));
    assert_eq!(requests[0].1["template_id"], json!(template));
    assert_eq!(requests[0].1["capabilities"].as_array().unwrap().len(), 1);
    drop(requests);
    let runtime = format!("/spaces/{team}/agent-templates/{template}/creation-assistant/runtime");
    assert_eq!(
        super::support::request(
            &app,
            &identity,
            Some("editor"),
            "POST",
            &runtime,
            Value::Null
        )
        .await
        .0,
        403
    );
    let now = chrono::Utc::now().timestamp();
    let workload=identity.sign(json!({"sub":"service-account-pod","preferred_username":"service-account-pod","azp":"pod","client_id":"pod","iss":identity.realm,"aud":"fred-delegation","iat":now,"exp":now+300,"resource_access":{"fred-delegation":{"roles":["delegation_caller"]}}}));
    let call = |path: String| {
        let app = app.clone();
        let workload = workload.clone();
        async move {
            let response = app
                .oneshot(
                    Request::builder()
                        .method("POST")
                        .uri(path)
                        .header("authorization", format!("Bearer {workload}"))
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            let status = response.status().as_u16();
            let value: Value =
                serde_json::from_slice(&to_bytes(response.into_body(), 1024 * 1024).await.unwrap())
                    .unwrap();
            (status, value)
        }
    };
    let delegated = format!("{runtime}?person=editor&run=draft&agent={template}");
    let (status, admission) = call(delegated.clone()).await;
    assert_eq!(status, 200, "{admission}");
    assert_eq!(admission["space"]["organization_id"], json!(org));
    assert_eq!(
        admission["creation_prompt"],
        "Organization A meta prompt in {language}"
    );
    assert_eq!(admission["capability_ids"], json!(["allowed"]));
    assert_eq!(
        admission["inference"]["selection"]["key"]["upstream_model_id"],
        "dedicated"
    );
    assert_eq!(
        admission["inference"]["selection"]["options"]["reasoning_effort"],
        "high"
    );
    assert_eq!(admission["prompt_key"], "prompts.system");
    assert_eq!(
        call(format!(
            "{runtime}?person=editor&run=draft&agent={}",
            Uuid::new_v4()
        ))
        .await
        .0,
        403
    );
    let other_template = template_id(other, "fixture", "template");
    assert_eq!(call(format!("/spaces/{team}/agent-templates/{other_template}/creation-assistant/runtime?person=editor&run=draft&agent={other_template}")).await.0,404);
    sqlx::query(
        "update model_offer set metadata=jsonb_set(metadata, '{reasoning}', 'false') where source_id='model-source' and upstream_model_id='dedicated'",
    )
    .execute(&pool)
    .await
    .unwrap();
    assert!(
        call(delegated.clone()).await.1["inference"]["selection"]["options"]["reasoning_effort"]
            .is_null()
    );
    // Without a prompt-settings override, use the catalogue's dedicated model;
    // only an unset dedicated choice follows the space default.
    sqlx::query("update organization_prompt_settings set creation_model_source_id=null, creation_model_upstream_id=null where organization_id=$1")
        .bind(org).execute(&pool).await.unwrap();
    sqlx::query("update organization_model_policy set creation_assistant_source_id='model-source', creation_assistant_upstream_model_id='dedicated' where organization_id=$1")
        .bind(org).execute(&pool).await.unwrap();
    let (status, admission) = call(delegated.clone()).await;
    assert_eq!(status, 200, "{admission}");
    assert_eq!(
        admission["inference"]["selection"]["key"]["upstream_model_id"],
        "dedicated"
    );
    sqlx::query("update organization_model_policy set creation_assistant_source_id=null, creation_assistant_upstream_model_id=null where organization_id=$1")
        .bind(org).execute(&pool).await.unwrap();
    let (status, admission) = call(delegated.clone()).await;
    assert_eq!(status, 200, "{admission}");
    assert_eq!(
        admission["inference"]["selection"]["key"]["upstream_model_id"],
        "chat"
    );
    sqlx::query("update organization_model_policy set creation_assistant_source_id='model-source', creation_assistant_upstream_model_id='dedicated' where organization_id=$1")
        .bind(org).execute(&pool).await.unwrap();
    sqlx::query(
        "insert into space_model_policy(space_id,revision,updated_by) values($1,1,'owner')",
    )
    .bind(team)
    .execute(&pool)
    .await
    .unwrap();
    sqlx::query("insert into space_model_setting(space_id,source_id,upstream_model_id,disabled,reasoning_default_on) values($1,'model-source','dedicated',true,false)").bind(team).execute(&pool).await.unwrap();
    let (status, error) = call(delegated.clone()).await;
    assert_eq!(status, 409, "{error}");
    assert_eq!(error["code"], "model_offer_forbidden");
    sqlx::query("delete from space_model_setting where space_id=$1")
        .bind(team)
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("update model_offer set advertised=false,withdrawn_at=now() where source_id='model-source' and upstream_model_id='dedicated'").execute(&pool).await.unwrap();
    assert_eq!(call(delegated.clone()).await.0, 409);
    *fields.lock().await = json!([{"key":"prompts.system","type":"prompt","ui":{"hide":true}}]);
    assert_eq!(
        super::support::request(&app, &identity, Some("editor"), "POST", &path, body.clone())
            .await
            .0,
        409
    );
    let native = template_id(org, "control-plane", fred_rust_agent::AGENT_ID);
    control_plane::authorization::set_agent_default_on(
        &mut pool.acquire().await.unwrap(),
        org,
        native,
        true,
    )
    .await
    .unwrap();
    assert_eq!(
        super::support::request(
            &app,
            &identity,
            Some("editor"),
            "POST",
            &format!("/spaces/{team}/agent-templates/{native}/creation-assistant/draft"),
            body
        )
        .await
        .0,
        409
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from agent_instance")
            .fetch_one(&pool)
            .await
            .unwrap(),
        0
    );
    task.abort();
}
