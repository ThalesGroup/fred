// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use axum::response::IntoResponse;
use control_plane::model_catalog::{
    self,
    config::ModelSource,
    initialization::{OrganizationModels, initialize},
};

struct Provider {
    url: String,
    response: Arc<Mutex<(u16, Value, usize)>>,
    inference: Arc<Mutex<Vec<(HeaderMap, Value)>>>,
    inference_status: Arc<Mutex<u16>>,
    next_message: Arc<Mutex<Option<Value>>>,
    searches: Arc<Mutex<Vec<Value>>>,
    search_response: Arc<Mutex<(u16, Value)>>,
    task: tokio::task::JoinHandle<()>,
}
impl Drop for Provider {
    fn drop(&mut self) {
        self.task.abort();
    }
}
impl Provider {
    async fn start() -> Self {
        let response = Arc::new(Mutex::new((
            200,
            json!({"data": [
                {"id":"chat", "capabilities":{"completion_chat":true,"reasoning":true}},
                {"id":"extra", "capabilities":{"completion_chat":true}}
            ]}),
            0,
        )));
        let inference = Arc::new(Mutex::new(Vec::new()));
        let completions = inference.clone();
        let inference_status = Arc::new(Mutex::new(200));
        let completion_status = inference_status.clone();
        let next_message = Arc::new(Mutex::new(None));
        let messages = next_message.clone();
        let searches = Arc::new(Mutex::new(Vec::new()));
        let captured_searches = searches.clone();
        let search_response = Arc::new(Mutex::new((200, json!([]))));
        let search_state = search_response.clone();
        let state = response.clone();
        let app = Router::new().route(
            "/models",
            get(move || {
                let state = state.clone();
                async move {
                    let mut state = state.lock().await;
                    state.2 += 1;
                    (
                        axum::http::StatusCode::from_u16(state.0).unwrap(),
                        Json(state.1.clone()),
                    )
                }
            }),
        );
        let app = app.route("/chat/completions", post(move |headers: HeaderMap, Json(body): Json<Value>| {
            let completions = completions.clone();
            let completion_status = completion_status.clone();
            let messages = messages.clone();
            async move {
                let streamed = body["stream"] == true;
                completions.lock().await.push((headers, body));
                let message = messages.lock().await.take().unwrap_or_else(|| json!({"role":"assistant","content":"managed simulated inference"}));
                let reason = if message.get("tool_calls").is_some() { "tool_calls" } else { "stop" };
                let status = axum::http::StatusCode::from_u16(*completion_status.lock().await).unwrap();
                let usage = json!({"prompt_tokens":2,"completion_tokens":2,"total_tokens":4});
                if streamed && status.is_success() {
                    let mut delta = message;
                    if let Some(calls) = delta["tool_calls"].as_array_mut() {
                        for (index, call) in calls.iter_mut().enumerate() {
                            call["index"] = json!(index);
                        }
                    }
                    let chunk = |delta: Value, reason: Value, usage: Value| {
                        json!({"id":"fixture", "object":"chat.completion.chunk", "created":0, "model":"chat",
                            "choices":[{"index":0,"delta":delta,"finish_reason":reason}], "usage":usage})
                    };
                    let body = format!(
                        "data: {}\n\ndata: {}\n\ndata: [DONE]\n\n",
                        chunk(delta, Value::Null, Value::Null),
                        chunk(json!({}), json!(reason), usage),
                    );
                    return (status, [("content-type", "text/event-stream")], body).into_response();
                }
                (status, Json(json!({"id":"fixture", "object":"chat.completion", "created":0, "model":"chat",
                    "choices":[{"index":0,"message":message,"finish_reason":reason}],
                    "usage":usage}))).into_response()
            }
        }));
        let app = app.route("/documents/search", post(move |headers: HeaderMap,
            axum::extract::Query(grant): axum::extract::Query<std::collections::BTreeMap<String, String>>,
            Json(body): Json<Value>| {
            let captured = captured_searches.clone();
            let state = search_state.clone();
            async move {
                captured.lock().await.push(json!({
                    "authorization":headers["authorization"].to_str().unwrap(),
                    "context":serde_json::from_str::<Value>(headers["x-fred-document-context"].to_str().unwrap()).unwrap(),
                    "grant":grant, "body":body,
                }));
                let state = state.lock().await;
                (axum::http::StatusCode::from_u16(state.0).unwrap(), Json(state.1.clone()))
            }
        }));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        Self {
            url,
            response,
            inference,
            inference_status,
            next_message,
            searches,
            search_response,
            task,
        }
    }
    fn source(&self, id: &str) -> ModelSource {
        serde_json::from_value(json!({"source_id":id,"revision":1,"enabled":true,
            "discovery_url":format!("{}/models",self.url),
            "inference":{"provider":"openai","api_root":self.url,"credential_binding":id},
            "visibility_scope":format!("account-{id}"),"authentication":{"mode":"public"},
            "qualification":"mixed_capabilities_v1","complete_inventory_guaranteed":true,
            "allow_insecure_http":true}))
        .unwrap()
    }
}
fn key(source: &str) -> Value {
    json!({"source_id":source,"upstream_model_id":"chat"})
}
fn declaration(name: &str, sources: &[&str]) -> OrganizationModels {
    serde_json::from_value(json!({"organization":name,"sources":sources,
        "permitted":sources.iter().map(|s| key(s)).collect::<Vec<_>>(),
        "default":sources.first().map(|s| key(s)), "fallback":null,
        "reasoning_enabled":sources.first().map(|s| vec![key(s)]).unwrap_or_default()}))
    .unwrap()
}
async fn model_app(
    e: &Env,
    identity: &support::IdentityServer,
    platform: PlatformConfig,
) -> Router {
    routes(AppState {
        pool: e.pool.clone(),
        agent_catalog: platform,
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    })
}
async fn inventory(app: &Router, identity: &support::IdentityServer, org: Uuid) -> Value {
    let (status, value) = request(
        app,
        identity,
        Some("alice"),
        "GET",
        &format!("/organizations/{org}/models"),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{value}");
    value
}
async fn completion(e: &Env, org: Uuid) -> bool {
    sqlx::query_scalar("select exists(select 1 from organization_model_initialization where organization_id=$1 and completed_at is not null)")
        .bind(org).fetch_one(&e.pool).await.unwrap()
}

#[test]
fn yaml_validation_rejects_invalid_policy_and_cli_redacts_input() {
    use std::io::Write;
    let yaml = "organization: Example\nsources: [account]\npermitted: []\ndefault: null\nfallback: null\nreasoning_enabled: []\n";
    let declaration: OrganizationModels = serde_yaml_ng::from_str(yaml).unwrap();
    control_plane::model_catalog::initialization::validate(std::slice::from_ref(&declaration))
        .unwrap();
    let mut invalid = declaration.clone();
    invalid.default = Some(serde_json::from_value(key("account")).unwrap());
    assert!(control_plane::model_catalog::initialization::validate(&[invalid]).is_err());
    let mut invalid = declaration.clone();
    invalid.reasoning_enabled = vec![serde_json::from_value(key("account")).unwrap()];
    assert!(control_plane::model_catalog::initialization::validate(&[invalid]).is_err());
    assert!(
        control_plane::model_catalog::initialization::validate(&[declaration.clone(), declaration])
            .is_err()
    );
    assert!(
        serde_yaml_ng::from_str::<OrganizationModels>(&format!(
            "{yaml}token: fixture-secret-must-not-escape\n"
        ))
        .is_err()
    );
    let mut file = tempfile::NamedTempFile::new().unwrap();
    file.write_all(b"app: fixture-secret-must-not-escape\n")
        .unwrap();
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .env_clear()
        .env("CONFIG_FILE", file.path())
        .env("ENV_FILE", "/nonexistent-fixture-env")
        .arg("initialize-models")
        .output()
        .unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(stderr.contains("invalid configuration YAML"), "{stderr}");
    assert!(!stderr.contains("fixture-secret"));
    assert!(
        !String::from_utf8(output.stdout)
            .unwrap()
            .contains("fixture-secret")
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn organization_provisioning_runs_the_pending_seed_without_model_ui_actions() {
    let e = env().await;
    let provider = Provider::start().await;
    let platform = PlatformConfig {
        model_sources: vec![provider.source("a")],
        organization_models: vec![declaration("New organization", &["a"])],
        ..Default::default()
    };
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    assert!(
        initialize(&e.pool, &platform, true)
            .await
            .unwrap_err()
            .to_string()
            .contains("organization_missing")
    );
    initialize(&e.pool, &platform, false).await.unwrap();
    assert_eq!(provider.response.lock().await.2, 0);
    let identity = support::IdentityServer::start().await;
    for user in ["owner", "admin"] {
        identity.users.lock().await.insert(user.into(), user.into());
    }
    control_plane::bootstrap::grant_root(&e.pool, "operator")
        .await
        .unwrap();
    let app = model_app(&e, &identity, platform).await;
    let (status, org) = request(
        &app,
        &identity,
        Some("operator"),
        "POST",
        "/admin/organizations",
        json!({"name":"New organization","admin_username":"admin","owner_username":"owner"}),
    )
    .await;
    assert_eq!(status, 201, "{org}");
    let org = Uuid::parse_str(org["id"].as_str().unwrap()).unwrap();
    assert!(completion(&e, org).await);
    let (status, policy) = request(
        &app,
        &identity,
        Some("owner"),
        "GET",
        &format!("/organizations/{org}/model-policy"),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{policy}");
    assert_eq!(policy["default"], key("a"));
    assert_eq!(policy["permitted"], json!([key("a")]));
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn sources_isolate_inventory_refresh_policy_recommendation_and_admission() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let other = support::member_organization(&e.pool, "Other", "bob")
        .await
        .unwrap();
    grant(&e, team.id, Role::Editor, "alice").await;
    let provider = Provider::start().await;
    let catalog = Catalog::start().await;
    let mut platform = catalog.config();
    platform.model_sources = vec![
        provider.source("a"),
        provider.source("b"),
        provider.source("c"),
    ];
    platform.organization_models = vec![
        declaration("TSN", &["a", "c"]),
        declaration("Other", &["b"]),
    ];
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, platform.clone()).await;
    let view = inventory(&app, &identity, org.id).await;
    assert_eq!(
        view["sources"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| s["observation"]["source_id"].as_str().unwrap())
            .collect::<Vec<_>>(),
        ["a", "c"]
    );
    assert_eq!(view["policy"]["permitted"], json!([key("a"), key("c")]));
    assert_eq!(view["policy"]["reasoning_enabled"], json!([key("a")]));
    let (status, view) = request(
        &app,
        &identity,
        Some("bob"),
        "GET",
        &format!("/organizations/{}/models", other.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(view["sources"].as_array().unwrap().len(), 1);
    assert_eq!(view["sources"][0]["observation"]["source_id"], "b");
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("/organizations/{}/models", other.id),
            Value::Null
        )
        .await
        .0,
        404
    );
    let calls = provider.response.lock().await.2;
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!("/organizations/{}/model-sources/b/refresh", org.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 403, "{body}");
    assert_eq!(body["code"], "model_source_not_assigned");
    assert_eq!(calls, provider.response.lock().await.2);
    let policy_path = format!("/organizations/{}/model-policy", org.id);
    let policy = json!({"expected_revision":1,"permitted":[key("b")],"reasoning_enabled":[],"default":key("b"),"fallback":null,"title":null});
    assert_eq!(
        request(&app, &identity, Some("alice"), "PUT", &policy_path, policy)
            .await
            .0,
        403
    );
    // The technical organization administrator does not acquire Manage.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice-owner"),
            "GET",
            &policy_path,
            Value::Null
        )
        .await
        .0,
        403
    );
    let template = enable(&e, org.id, "custom", true).await;
    let mut body = creation(template, "Forbidden recommendation");
    body["recommended_model"] = key("b");
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &collection(team.id),
            body
        )
        .await
        .0,
        422
    );
    let instance = create(
        &app,
        &identity,
        team.id,
        creation(template, "Allowed default"),
    )
    .await;
    // Retained legacy/tampered recommendations cannot import another account's facts.
    sqlx::query("update agent_instance set tuning=tuning || $1 where agent_instance_id=$2")
        .bind(sqlx::types::Json(json!({"recommended_model":key("b")})))
        .bind(Uuid::parse_str(instance["agent_instance_id"].as_str().unwrap()).unwrap())
        .execute(&e.pool)
        .await
        .unwrap();
    let base = item(team.id, &instance);
    let (status, facts) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("{base}/runtime"),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{facts}");
    let forbidden = facts["models"]["offers"]
        .as_array()
        .unwrap()
        .iter()
        .find(|o| o["key"]["source_id"] == "b")
        .unwrap();
    assert_eq!(forbidden["permitted"], false);
    assert_eq!(forbidden["candidate"], false);
    assert!(forbidden["metadata"].is_null() && forbidden["connection"].is_null());
    let (status, prep) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!("{base}/prepare-execution"),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{prep}");
    assert_eq!(prep["model_error"]["code"], "offer_forbidden");
    assert!(!prep.to_string().contains(&provider.url));
    // Same endpoint/account URL never merges distinct source identities.
    let mut changed = platform.model_sources.clone();
    changed[0].revision = 2;
    changed[0].visibility_scope = "other-account".into();
    assert!(
        model_catalog::configure_sources(&e.pool, &changed)
            .await
            .is_err()
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn seed_replay_preserves_ui_empty_deleted_policy_and_source_rotation() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let provider = Provider::start().await;
    let mut platform = PlatformConfig {
        model_sources: vec![provider.source("a")],
        organization_models: vec![declaration("TSN", &["a"])],
        ..Default::default()
    };
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, platform.clone()).await;
    let policy_path = format!("/organizations/{}/model-policy", org.id);
    let empty = json!({"expected_revision":1,"permitted":[],"reasoning_enabled":[],"default":null,"fallback":null,"title":null});
    assert_eq!(
        request(&app, &identity, Some("alice"), "PUT", &policy_path, empty)
            .await
            .0,
        200
    );
    let calls = provider.response.lock().await.2;
    initialize(&e.pool, &platform, true).await.unwrap();
    assert_eq!(
        inventory(&app, &identity, org.id).await["policy"]["permitted"],
        json!([])
    );
    assert_eq!(
        inventory(&app, &identity, org.id).await["policy"]["revision"],
        2
    );
    sqlx::query("delete from organization_model_policy where organization_id=$1")
        .bind(org.id)
        .execute(&e.pool)
        .await
        .unwrap();
    sqlx::query("delete from organization_model_source where organization_id=$1")
        .bind(org.id)
        .execute(&e.pool)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let view = inventory(&app, &identity, org.id).await;
    assert_eq!(view["policy"]["revision"], 0);
    assert_eq!(view["sources"], json!([]));
    assert_eq!(calls, provider.response.lock().await.2);
    platform.model_sources[0].revision = 2;
    platform.model_sources[0].enabled = false;
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    assert!(
        !model_catalog::inventory(&e.pool, "a")
            .await
            .unwrap()
            .unwrap()
            .observation
            .enabled
    );
    assert!(completion(&e, org.id).await);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn seed_failure_retry_validation_and_concurrent_replicas() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let provider = Provider::start().await;
    let mut platform = PlatformConfig {
        model_sources: vec![provider.source("a"), provider.source("b")],
        organization_models: vec![declaration("TSN", &["a", "b"])],
        ..Default::default()
    };
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    platform.organization_models[0].permitted[1].upstream_model_id = "missing".into();
    let error = initialize(&e.pool, &platform, true)
        .await
        .unwrap_err()
        .to_string();
    assert!(error.contains("unknown_model_offer"), "{error}");
    assert!(!completion(&e, org.id).await);
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from organization_model_source")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from organization_model_policy")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );
    platform.organization_models[0] = declaration("TSN", &["a", "b"]);
    provider.response.lock().await.0 = 503;
    provider.response.lock().await.1 = json!({"error":"fixture-secret-must-not-escape"});
    let error = initialize(&e.pool, &platform, true)
        .await
        .unwrap_err()
        .to_string();
    assert!(error.contains("model_discovery_failed") && !error.contains("fixture-secret"));
    assert!(!completion(&e, org.id).await);
    let retained = model_catalog::inventory(&e.pool, "a")
        .await
        .unwrap()
        .unwrap();
    assert_eq!(retained.offers.len(), 2);
    assert_eq!(retained.observation.snapshot_revision, 1);
    let calls = provider.response.lock().await.2;
    let duplicate = platform.organization_models[0].permitted[0].clone();
    platform.organization_models[0].permitted.push(duplicate);
    assert!(initialize(&e.pool, &platform, true).await.is_err());
    assert_eq!(calls, provider.response.lock().await.2);
    platform.organization_models[0] = declaration("TSN", &["a", "b"]);
    *provider.response.lock().await = (
        200,
        json!({"data":[{"id":"chat","capabilities":{"completion_chat":true,"reasoning":true}}]}),
        calls,
    );
    let (a, b) = tokio::join!(
        initialize(&e.pool, &platform, true),
        initialize(&e.pool, &platform, true)
    );
    assert!(a.is_ok() || b.is_ok(), "{a:?} {b:?}");
    initialize(&e.pool, &platform, true).await.unwrap();
    assert!(completion(&e, org.id).await);
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "select revision from organization_model_policy where organization_id=$1"
        )
        .bind(org.id)
        .fetch_one(&e.pool)
        .await
        .unwrap(),
        1
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from organization_model_permission")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        2
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn initialization_preserves_administered_and_deleted_policies() {
    let e = env().await;
    let org = Uuid::new_v4();
    sqlx::query(
        "insert into space (id,kind,name,organization_id) values ($1,'organization','Administered',$1)",
    )
    .bind(org)
    .execute(&e.pool)
    .await
    .unwrap();
    let provider = Provider::start().await;
    let mut platform = PlatformConfig {
        model_sources: vec![provider.source("a")],
        organization_models: vec![declaration("Administered", &["a"])],
        ..Default::default()
    };
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    model_catalog::refresh(&e.pool, &platform.model_sources[0])
        .await
        .unwrap();
    sqlx::query("insert into organization_model_policy (organization_id,revision,created_by,updated_by) values ($1,7,'owner','owner')").bind(org).execute(&e.pool).await.unwrap();
    assert!(sqlx::query("insert into organization_model_permission (organization_id,source_id,upstream_model_id) values ($1,'a','extra')")
        .bind(org).execute(&e.pool).await.is_err());
    sqlx::query(
        "insert into organization_model_source (organization_id,source_id) values ($1,'a')",
    )
    .bind(org)
    .execute(&e.pool)
    .await
    .unwrap();
    sqlx::query("insert into organization_model_permission (organization_id,source_id,upstream_model_id) values ($1,'a','extra')").bind(org).execute(&e.pool).await.unwrap();
    let deleted_policy_org = Uuid::new_v4();
    sqlx::query("insert into space (id,kind,name,organization_id) values ($1,'organization','Deleted policy',$1)")
        .bind(deleted_policy_org).execute(&e.pool).await.unwrap();
    sqlx::query("insert into organization_model_policy (organization_id,revision,created_by,updated_by) values ($1,3,'owner','owner')")
        .bind(deleted_policy_org).execute(&e.pool).await.unwrap();
    sqlx::query("delete from organization_model_policy where organization_id=$1")
        .bind(deleted_policy_org)
        .execute(&e.pool)
        .await
        .unwrap();

    // The seed's chat/default/reasoning choices cannot replace the existing 'extra' decision.
    let calls = provider.response.lock().await.2;
    initialize(&e.pool, &platform, true).await.unwrap();
    assert_eq!(calls, provider.response.lock().await.2);
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "select revision from organization_model_policy where organization_id=$1"
        )
        .bind(org)
        .fetch_one(&e.pool)
        .await
        .unwrap(),
        7
    );
    assert_eq!(
        sqlx::query_scalar::<_, String>(
            "select upstream_model_id from organization_model_permission where organization_id=$1"
        )
        .bind(org)
        .fetch_one(&e.pool)
        .await
        .unwrap(),
        "extra"
    );
    assert!(completion(&e, org).await);
    platform
        .organization_models
        .push(declaration("Deleted policy", &["a"]));
    initialize(&e.pool, &platform, true).await.unwrap();
    assert!(completion(&e, deleted_policy_org).await);
    assert!(
        !sqlx::query_scalar::<_, bool>(
            "select exists(select 1 from organization_model_policy where organization_id=$1)"
        )
        .bind(deleted_policy_org)
        .fetch_one(&e.pool)
        .await
        .unwrap()
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres and FRED_TEST_INFERENCE_CREDENTIAL=synthetic-inference-key"]
async fn common_admission_drives_managed_rig_and_delegated_python_contract() {
    use control_plane::{auth::Authenticator, config::Configuration};
    let e = env().await;
    control_plane::bootstrap::grant_root(&e.pool, "ralph-test-admin")
        .await
        .unwrap();
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let provider = Provider::start().await;
    let catalog = Catalog::start().await;
    let mut platform = catalog.config();
    platform.model_sources = vec![provider.source("a")];
    platform.organization_models = vec![declaration("TSN", &["a"])];
    platform.inference_credentials = vec![fred_rust_sdk::inference::InferenceCredentialBinding {
        source_id: "a".into(),
        source_revision: 1,
        api_root: provider.url.clone(),
        credential_binding: "a".into(),
        api_key_env: "FRED_TEST_INFERENCE_CREDENTIAL".into(),
    }];
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, false).await.unwrap();
    model_catalog::refresh(&e.pool, &platform.model_sources[0])
        .await
        .unwrap();
    let identity = support::IdentityServer::start().await;
    let mut config: Configuration =
        serde_yaml_ng::from_str(include_str!("../../config/configuration.yaml")).unwrap();
    config.security.user.realm_url = identity.realm.clone();
    config.security.delegation.accept_delegated_calls = true;
    config.security.delegation.service_accounts_only = true;
    let state = AppState {
        pool: e.pool.clone(),
        agent_catalog: platform,
        auth: Arc::new(
            Authenticator::start(config.security().unwrap())
                .await
                .unwrap(),
        ),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    };
    let app = routes(state.clone());
    let native = template_id(org.id, "control-plane", fred_rust_agent::AGENT_ID);
    control_plane::authorization::set_agent_default_on(
        &mut e.pool.acquire().await.unwrap(),
        org.id,
        native,
        true,
    )
    .await
    .unwrap();
    // Use the same enrollment, conversation and preparation path as the browser.
    let mut body = creation(native, "Ralph");
    body["recommended_model"] = key("a");
    body["model_options"] = json!({"temperature":0.2,"top_p":0.8,"max_tokens":50});
    let created = create(&app, &identity, team.id, body).await;
    let instance = Uuid::parse_str(created["agent_instance_id"].as_str().unwrap()).unwrap();
    let session = Uuid::new_v4();
    let (status, registered) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!("/spaces/{}/sessions", team.id),
        json!({"session_id":session,"agent_instance_id":instance,"agent_configuration_revision":1}),
    )
    .await;
    assert_eq!(status, 201, "{registered}");
    assert_eq!(
        registered["messages_url"],
        format!("/agents/sessions/{session}/messages")
    );
    let nested = Router::new().nest("/custom/control-plane", app.clone());
    let preparation_path = format!(
        "/custom/control-plane{}/prepare-execution?session_id={session}",
        item(team.id, &created)
    );
    let (status, prepared) = request(
        &nested,
        &identity,
        Some("alice"),
        "POST",
        &preparation_path,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{prepared}");
    assert_eq!(
        prepared["execute_stream_url"],
        "/custom/control-plane/agents/execute/stream"
    );
    assert!(prepared["execute_url"].is_null());
    assert_eq!(
        prepared["messages_url_template"],
        "/custom/control-plane/agents/sessions/{session_id}/messages"
    );
    assert_eq!(prepared["supports_ui_parts"], false);
    assert_eq!(prepared["supports_hitl"], false);
    assert_eq!(
        prepared["chat_controls"],
        json!([{"capability_id":"platform","widget":"reasoning_toggle","params":{"default":false}}])
    );
    assert_ne!(
        request(
            &nested,
            &identity,
            Some("bob"),
            "POST",
            &preparation_path,
            Value::Null
        )
        .await
        .0,
        200
    );
    let runtime_path = format!("/spaces/{}/agent-instances/{instance}/runtime", team.id);
    let (status, public) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &runtime_path,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{public}");
    assert!(public.get("inference").is_none());
    assert!(
        !public.to_string().contains("credential_binding")
            && !public.to_string().contains(&provider.url)
    );
    let now = chrono::Utc::now().timestamp();
    let workload = identity.sign(json!({"sub":"service-account-pod","preferred_username":"service-account-pod",
        "azp":"pod","client_id":"pod","iss":identity.realm,"aud":"fred-delegation","iat":now,"exp":now+300,
        "resource_access":{"fred-delegation":{"roles":["delegation_caller"]}}}));
    let delegated_path = format!(
        "{runtime_path}?person=alice&run=run&agent={instance}&reasoning=true&conversation={session}"
    );
    let resolve = || {
        app.clone().oneshot(
            Request::builder()
                .uri(&delegated_path)
                .header("authorization", format!("Bearer {workload}"))
                .body(Body::empty())
                .unwrap(),
        )
    };
    let response = resolve().await.unwrap();
    assert_eq!(response.status(), 200);
    let delegated: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), 1024 * 1024).await.unwrap())
            .unwrap();
    assert!(delegated.get("title").is_none());
    let decision = &delegated["inference"]["selection"];
    assert_eq!(decision["key"], key("a"));
    assert_eq!(
        decision["options"],
        json!({"temperature":0.2,"max_tokens":50,"top_p":0.8,"reasoning_effort":"high"})
    );
    assert_eq!(
        delegated["inference"]["connection"]["credential_binding"],
        "a"
    );
    // Preparation for the existing Python route projects the same decision, without private data.
    let custom = enable(&e, org.id, "custom", true).await;
    let mut body = creation(custom, "Public preparation");
    body["recommended_model"] = key("a");
    body["model_options"] = json!({"temperature":0.2,"top_p":0.8,"max_tokens":50});
    let public_instance = create(&app, &identity, team.id, body).await;
    let (status, prepared) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!(
            "{}/prepare-execution?reasoning=true",
            item(team.id, &public_instance)
        ),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{prepared}");
    assert_eq!(prepared["inference"], *decision);
    assert!(
        !prepared.to_string().contains("credential_binding")
            && !prepared.to_string().contains(&provider.url)
    );
    // Python's mutating admission, unlike the GET above, consumes one attempt.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &runtime_path,
            Value::Null
        )
        .await
        .0,
        403
    );
    for resume in [false, true] {
        let python_session = Uuid::new_v4();
        assert_eq!(request(&app, &identity, Some("alice"), "POST", &format!("/spaces/{}/sessions", team.id),
            json!({"session_id":python_session,"agent_instance_id":instance,"agent_configuration_revision":1})).await.0, 201);
        for attempt in 0..2 {
            let path = format!(
                "{runtime_path}?person=alice&run=run&agent={instance}&conversation={python_session}&resume={}",
                resume && attempt == 0
            );
            let response = app
                .clone()
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
            assert_eq!(response.status(), 200);
            let admitted: Value =
                serde_json::from_slice(&to_bytes(response.into_body(), 1024 * 1024).await.unwrap())
                    .unwrap();
            assert_eq!(admitted.get("title").is_some(), attempt == 0 && !resume);
            if let Some(title) = admitted.get("title") {
                assert_eq!(
                    title["inference"]["selection"]["options"]["max_tokens"],
                    128
                );
                assert!(title["inference"]["selection"]["options"]["reasoning_effort"].is_null());
            }
        }
    }
    let execute = json!({"agent_instance_id":instance,"input":"fixture question",
        "session_id":session,"steering_turn_id":Uuid::new_v4(),
        "runtime_context":{"space_id":team.id,"reasoning":true,"language":"fr"}});
    let send = |app: Router, body: Value| {
        app.oneshot(
            Request::builder()
                .method("POST")
                .uri("/agents/execute/stream")
                .header(
                    "authorization",
                    format!("Bearer {}", identity.token("alice")),
                )
                .header("content-type", "application/json")
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
    };
    let mut without_session = execute.clone();
    without_session
        .as_object_mut()
        .unwrap()
        .remove("session_id");
    let response = send(app.clone(), without_session).await.unwrap();
    assert_eq!(response.status(), 422);
    let error = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
    assert!(String::from_utf8_lossy(&error).contains("session_id"));
    assert!(provider.inference.lock().await.is_empty());
    let response = send(app.clone(), execute.clone()).await.unwrap();
    assert_eq!(response.status(), 200);
    let stream = String::from_utf8(
        to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap()
            .to_vec(),
    )
    .unwrap();
    assert!(
        stream.contains("managed simulated inference") && stream.contains("\"kind\":\"final\""),
        "{stream}"
    );
    assert!(!stream.contains("synthetic-inference-key"));
    assert!(!stream.contains("tokens") && !stream.contains("usage"));
    let history_path = format!("/agents/sessions/{session}/messages");
    let (status, history) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &history_path,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{history}");
    assert_eq!(history.as_array().unwrap().len(), 2);
    assert_eq!(history[0]["role"], "user");
    assert_eq!(history[0]["parts"][0]["text"], "fixture question");
    assert_eq!(history[1]["role"], "assistant");
    assert_eq!(
        history[1]["parts"][0]["text"],
        "managed simulated inference"
    );
    assert_eq!(history[0]["exchange_id"], history[1]["exchange_id"]);
    let (status, details) = request(
        &nested,
        &identity,
        Some("alice"),
        "GET",
        &format!(
            "/custom/control-plane/spaces/{}/sessions/{session}",
            team.id
        ),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(
        details["messages_url"],
        format!("/custom/control-plane{history_path}")
    );

    // Accounting is asynchronous and bounded; wait for the committed report.
    let reports = |expected| {
        let pool = &e.pool;
        async move {
            tokio::time::timeout(std::time::Duration::from_secs(5), async {
                loop {
                    let rows: Vec<Value> = sqlx::query_scalar(
                        "select to_jsonb(u) from model_usage u where session_id=$1 order by occurred_at",
                    ).bind(session).fetch_all(pool).await.unwrap();
                    assert!(rows.len() <= expected, "duplicate usage reports: {rows:?}");
                    if rows.len() == expected { break rows; }
                    tokio::time::sleep(std::time::Duration::from_millis(10)).await;
                }
            }).await.unwrap()
        }
    };
    let rows = reports(2).await;
    let report = &rows[0];
    assert_eq!(report["session_id"], session.to_string());
    assert_eq!(report["space_id"], team.id.to_string());
    assert_eq!(report["user_id"], "alice");
    assert_eq!(report["agent_instance_id"], instance.to_string());
    assert_eq!(report["model_source_id"], "a");
    assert_eq!(report["upstream_model_id"], "chat");
    assert_eq!(report["input_tokens"], 2);
    assert_eq!(report["output_tokens"], 2);
    assert_eq!(report["cache_read_tokens"], 0);
    assert_eq!(report["cache_creation_tokens"], 0);
    Uuid::parse_str(report["report_id"].as_str().unwrap()).unwrap();
    Uuid::parse_str(report["exchange_id"].as_str().unwrap()).unwrap();
    let captured = provider.inference.lock().await;
    let calls = &captured;
    assert_eq!(calls.len(), 2);
    assert!(stream.contains("session_title"));
    let saved: String =
        sqlx::query_scalar("select title from session_metadata where session_id=$1")
            .bind(session)
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(saved, "managed simulated inference");
    let title_call = calls
        .iter()
        .find(|c| c.1["max_tokens"] == 128 || c.1["max_completion_tokens"] == 128)
        .unwrap();
    assert!(title_call.1.get("reasoning_effort").is_none());
    let calls: Vec<_> = calls.iter().filter(|c| c.1["temperature"] == 0.2).collect();
    assert_eq!(
        calls[0].0["authorization"],
        "Bearer synthetic-inference-key"
    );
    assert_eq!(calls[0].1["model"], "chat");
    for (key, value) in decision["options"].as_object().unwrap() {
        assert_eq!(&calls[0].1[key], value);
    }
    drop(calls);
    drop(captured);

    // A failed provider call does not submit a consumption report.
    *provider.inference_status.lock().await = 500;
    let response = send(app.clone(), execute.clone()).await.unwrap();
    let body = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
    assert!(String::from_utf8_lossy(&body).contains("execution_error"));
    assert_eq!(reports(2).await, rows);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &history_path,
            Value::Null
        )
        .await
        .1,
        history
    );
    *provider.inference_status.lock().await = 200;

    // Hold the journal write until after the browser drops the response body.
    let mut lock = e.pool.begin().await.unwrap();
    sqlx::query("lock table model_usage in access exclusive mode")
        .execute(&mut *lock)
        .await
        .unwrap();
    let response = send(app.clone(), execute.clone()).await.unwrap();
    let mut stream = response.into_body().into_data_stream();
    use futures::StreamExt;
    tokio::time::timeout(std::time::Duration::from_secs(5), async {
        while let Some(frame) = stream.next().await {
            // The provider reports usage when its reply ends, just before this event.
            if String::from_utf8_lossy(&frame.unwrap()).contains("\"kind\":\"final\"") {
                return;
            }
        }
        panic!("missing final event");
    })
    .await
    .unwrap();
    drop(stream);
    lock.commit().await.unwrap();
    let after_drop = reports(3).await;
    assert_ne!(after_drop[0]["report_id"], after_drop[1]["report_id"]);
    assert_ne!(after_drop[0]["exchange_id"], after_drop[1]["exchange_id"]);

    let mut search_state = state.clone();
    search_state.agent_catalog.knowledge_flow_url = Some(provider.url.clone());
    let search_app = routes(search_state);
    let mut hits = vec![
        json!({"uid":"pointer","title":"Dataset","content":"Not evidence","score":0.5,"chunk_kind":"dataset_pointer"}),
    ];
    hits.extend((0..6).map(|i| json!({"uid":format!("doc-{i}"),"title":"é".repeat(260),"content":"界".repeat(4005),"score":0.5,"page":2})));
    for (index, (status, hits)) in [
        (200, json!(hits)),
        (200, json!([])),
        (503, json!({"detail":"private KF failure"})),
    ]
    .into_iter()
    .enumerate()
    {
        *provider.next_message.lock().await = Some(json!({"role":"assistant","content":null,
            "tool_calls":[{"id":format!("search-{}", index + 1),"type":"function","function":{
                "name":"search_documents","arguments":"{\"query\":\"manual question\"}"}}]}));
        *provider.search_response.lock().await = (status, hits);
        let before = provider.inference.lock().await.len();
        let response = send(search_app.clone(), execute.clone()).await.unwrap();
        assert_eq!(response.status(), 200);
        let body = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
        let body = String::from_utf8_lossy(&body);
        // The model answers a failed search, as with a Python agent's failed tool.
        assert!(body.contains("\"kind\":\"final\""));
        assert_eq!(body.contains("\"is_error\":true"), status != 200);
        assert!(!body.contains("private KF failure") && !body.contains("service-token"));
        let rows = reports(4 + index).await;
        let row = rows.last().unwrap();
        assert_eq!(row["input_tokens"], 4);
        assert_eq!(row["output_tokens"], 4);
        assert_eq!(row["agent_instance_id"], instance.to_string());
        assert_eq!(row["model_source_id"], "a");
        let searches = provider.searches.lock().await;
        assert_eq!(searches.len(), index + 1);
        let call = searches.last().unwrap();
        assert_eq!(call["authorization"], "Bearer service-token");
        assert_eq!(call["grant"]["person"], "alice");
        assert_eq!(call["grant"]["agent"], instance.to_string());
        Uuid::parse_str(call["grant"]["run"].as_str().unwrap()).unwrap();
        assert_eq!(
            call["context"],
            json!({"space_id":team.id,"document_scope":{"selections":[]},"attachment_ids":[]})
        );
        assert_eq!(
            call["body"],
            json!({"question":"manual question","top_k":5})
        );
        let calls = provider.inference.lock().await;
        assert_eq!(calls.len() - before, 2);
        if status == 200 {
            let messages = calls.last().unwrap().1["messages"].as_array().unwrap();
            let tool = messages.last().unwrap();
            assert_eq!(tool["role"], "tool");
            assert_eq!(tool["tool_call_id"], format!("search-{}", index + 1));
            let content: Value = serde_json::from_str(tool["content"].as_str().unwrap()).unwrap();
            assert_eq!(content["query"], "manual question");
            let model_hits = content["hits"].as_array().unwrap();
            assert_eq!(model_hits.len(), if index == 0 { 5 } else { 0 });
            for hit in model_hits {
                assert_ne!(hit["uid"], "pointer");
                assert_eq!(hit["content"].as_str().unwrap().chars().count(), 4000);
                assert_eq!(hit["title"].as_str().unwrap().chars().count(), 256);
                assert_eq!(hit["page"], 2);
            }
            let last_event = body
                .lines()
                .filter_map(|line| line.strip_prefix("data: "))
                .next_back()
                .unwrap();
            let last_event: Value = serde_json::from_str(last_event).unwrap();
            assert_eq!(last_event["kind"], "final");
            let cited = last_event["sources"].as_array().unwrap();
            assert_eq!(cited.len(), model_hits.len());
            assert!(cited.iter().all(|source| source["uid"] != "pointer"));
        }
    }
    let after_search = reports(6).await;

    // An admitted answer may finish after its session was physically purged.
    // The FK refuses history resurrection; already consumed model tokens still
    // use the immutable admission provenance, without recreating product metadata.
    let late_session = Uuid::new_v4();
    sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision,title)
        select $1,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision,'Known title'
        from session_metadata where session_id=$2")
        .bind(late_session).bind(session).execute(&e.pool).await.unwrap();
    let mut late_execute = execute.clone();
    late_execute["session_id"] = json!(late_session);
    let response = send(app.clone(), late_execute).await.unwrap();
    assert_eq!(response.status(), 200);
    let mut late_stream = response.into_body().into_data_stream();
    while let Some(frame) = late_stream.next().await {
        if String::from_utf8_lossy(&frame.unwrap()).contains("\"kind\":\"assistant_delta\"") {
            break;
        }
    }
    sqlx::query("delete from session_metadata where session_id=$1")
        .bind(late_session)
        .execute(&e.pool)
        .await
        .unwrap();
    let mut rest = String::new();
    while let Some(frame) = late_stream.next().await {
        rest.push_str(&String::from_utf8_lossy(&frame.unwrap()));
    }
    assert!(rest.contains("execution_error"), "{rest}");
    assert!(!rest.contains("\"kind\":\"final\""));
    tokio::time::timeout(Duration::from_secs(5), async {
        loop {
            let rows: Vec<Value> =
                sqlx::query_scalar("select to_jsonb(u) from model_usage u where session_id=$1")
                    .bind(late_session)
                    .fetch_all(&e.pool)
                    .await
                    .unwrap();
            if let Some(row) = rows.first() {
                assert_eq!(rows.len(), 1);
                assert_eq!(row["user_id"], "alice");
                assert_eq!(row["space_id"], team.id.to_string());
                assert_eq!(row["agent_instance_id"], instance.to_string());
                assert_eq!(row["input_tokens"], 2);
                assert_eq!(row["output_tokens"], 2);
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();
    let recreated: bool = sqlx::query_scalar("select exists(select 1 from session_metadata where session_id=$1) or exists(select 1 from embedded_agent_conversation where session_id=$1)")
        .bind(late_session).fetch_one(&e.pool).await.unwrap();
    assert!(!recreated);
    let calls_after_search = provider.inference.lock().await.len();

    let mut unprovisioned = state;
    unprovisioned.agent_catalog.inference_credentials.clear();
    assert_eq!(
        send(routes(unprovisioned), execute.clone())
            .await
            .unwrap()
            .status(),
        503
    );
    let mut unknown = execute.clone();
    unknown["runtime_context"]["model_choice"] =
        json!({"source_id":"a","upstream_model_id":"unknown"});
    assert_eq!(send(app.clone(), unknown).await.unwrap().status(), 409);
    let mut tx = e.pool.begin().await.unwrap();
    sqlx::query("update organization_model_policy set default_source_id=null, default_upstream_model_id=null, fallback_source_id=null, fallback_upstream_model_id=null, revision=revision+1 where organization_id=$1")
        .bind(org.id).execute(&mut *tx).await.unwrap();
    sqlx::query(
        "delete from organization_model_permission where organization_id=$1 and source_id='a'",
    )
    .bind(org.id)
    .execute(&mut *tx)
    .await
    .unwrap();
    tx.commit().await.unwrap();
    assert_eq!(resolve().await.unwrap().status(), 409);
    sqlx::query("delete from organization_model_source where organization_id=$1 and source_id='a'")
        .bind(org.id)
        .execute(&e.pool)
        .await
        .unwrap();
    assert_eq!(resolve().await.unwrap().status(), 409);
    assert_eq!(send(app.clone(), execute).await.unwrap().status(), 409);
    assert_eq!(provider.inference.lock().await.len(), calls_after_search);
    // Direct demonstration cannot access the provider even though provisioning exists.
    let direct = json!({"agent_id":fred_rust_agent::AGENT_ID,"input":"question"});
    let response = send(app.clone(), direct).await.unwrap();
    assert_eq!(response.status(), 200);
    let _ = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
    assert_eq!(provider.inference.lock().await.len(), calls_after_search);
    assert_eq!(reports(6).await, after_search);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn title_model_policy_uses_organization_offers_and_survives_reload() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let provider = Provider::start().await;
    let catalog = Catalog::start().await;
    let mut platform = catalog.config();
    platform.model_sources = vec![provider.source("a")];
    platform.organization_models = vec![declaration("TSN", &["a"])];
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, platform).await;
    let view = inventory(&app, &identity, org.id).await;
    assert!(view["policy"]["title"].is_null());
    let offer = view["sources"][0]["offers"]
        .as_array()
        .unwrap()
        .iter()
        .find(|o| o["upstream_model_id"] == "chat")
        .unwrap();
    assert_eq!(offer["selectable"], true);
    let path = format!("/organizations/{}/model-policy", org.id);
    let mut body = json!({"expected_revision":1,"permitted":[key("a")],"reasoning_enabled":[],"default":key("a"),"fallback":null,"title":key("a")});
    let (status, saved) = request(&app, &identity, Some("alice"), "PUT", &path, body.clone()).await;
    assert_eq!(status, 200, "{saved}");
    assert_eq!(saved["title"], key("a"));
    assert_eq!(
        inventory(&app, &identity, org.id).await["policy"]["title"],
        key("a")
    );
    let mut missing_title = body.clone();
    missing_title.as_object_mut().unwrap().remove("title");
    assert_eq!(
        request(&app, &identity, Some("alice"), "PUT", &path, missing_title)
            .await
            .0,
        422
    );
    body["expected_revision"] = saved["revision"].clone();
    body["title"] = key("another-organization-source");
    assert_eq!(
        request(&app, &identity, Some("alice"), "PUT", &path, body.clone())
            .await
            .0,
        422
    );
    assert_ne!(
        request(&app, &identity, Some("bob"), "PUT", &path, body.clone())
            .await
            .0,
        200
    );
    body["title"] = Value::Null;
    assert_eq!(
        request(&app, &identity, Some("alice"), "PUT", &path, body.clone())
            .await
            .0,
        200
    );
    sqlx::query(
        "update model_offer set advertised=false, withdrawn_at=now() where source_id='a' and upstream_model_id='chat'",
    )
    .execute(&e.pool)
    .await
    .unwrap();
    body["expected_revision"] = json!(3);
    body["title"] = key("a");
    let view = inventory(&app, &identity, org.id).await;
    let offer = view["sources"][0]["offers"]
        .as_array()
        .unwrap()
        .iter()
        .find(|o| o["upstream_model_id"] == "chat")
        .unwrap();
    assert_eq!(offer["selectable"], false);
    assert_eq!(
        request(&app, &identity, Some("alice"), "PUT", &path, body)
            .await
            .0,
        409
    );
}
