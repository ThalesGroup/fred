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
    transcriptions: Arc<Mutex<Vec<Value>>>,
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
        let transcriptions = Arc::new(Mutex::new(Vec::new()));
        let captured_transcriptions = transcriptions.clone();
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
        let app = app.route(
            "/audio/transcriptions",
            post(
                move |headers: HeaderMap, mut form: axum::extract::Multipart| {
                    let captured = captured_transcriptions.clone();
                    async move {
                        let mut call =
                            json!({"authorization": headers["authorization"].to_str().unwrap()});
                        while let Some(field) = form.next_field().await.unwrap() {
                            match field.name() {
                                Some("model") => call["model"] = json!(field.text().await.unwrap()),
                                Some("file") => {
                                    call["filename"] = json!(field.file_name());
                                    call["mime"] = json!(field.content_type());
                                    call["file"] = json!(field.text().await.unwrap());
                                }
                                _ => panic!("unexpected transcription field"),
                            }
                        }
                        captured.lock().await.push(call);
                        Json(json!({"text":"  Un message dicté.  "}))
                    }
                },
            ),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        Self {
            url,
            response,
            inference,
            transcriptions,
            inference_status,
            next_message,
            searches,
            search_response,
            task,
        }
    }
    fn source(&self, id: &str) -> ModelSource {
        serde_json::from_value(json!({"source_id":id,"revision":1,"enabled":true,
            "inventory":{"kind":"discovered","url":format!("{}/models",self.url),
                "authentication":{"mode":"public"},"qualification":"mixed_capabilities_v1",
                "complete_inventory_guaranteed":true},
            "inference":{"credential_binding":id,"api_root":self.url,"wire":"openai_chat",
                "route":"standard","dialect":"openai","auth":{"kind":"api_key"}},
            "visibility_scope":format!("account-{id}"),"allow_insecure_http":true}))
        .unwrap()
    }
    fn declared(&self, id: &str, revision: i64, models: Value) -> ModelSource {
        let mut source = self.source(id);
        source.revision = revision;
        source.inventory =
            serde_json::from_value(json!({"kind":"declared","models":models})).unwrap();
        source
    }
}
fn key(source: &str) -> Value {
    json!({"source_id":source,"upstream_model_id":"chat"})
}
fn declaration(name: &str, sources: &[&str]) -> OrganizationModels {
    serde_json::from_value(json!({"organization":name,"sources":sources,
        "permitted":sources.iter().map(|s| key(s)).collect::<Vec<_>>(),
        "default":sources.first().map(|s| key(s)), "fallback":null}))
    .unwrap()
}
async fn model_app(
    e: &Env,
    identity: &support::IdentityServer,
    platform: PlatformConfig,
) -> Router {
    routes(AppState {
        history: None,
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
async fn a_declared_list_follows_the_published_path_without_discovery_or_permission() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let provider = Provider::start().await;
    let models = json!([
        {"id":"chat","display_name":"Chat","reasoning":true,"max_output_tokens":100},
        {"id":"other"},
    ]);
    let source = provider.declared("d", 1, models.clone());
    let mut platform = PlatformConfig {
        model_sources: vec![source.clone()],
        organization_models: vec![
            serde_json::from_value(json!({"organization":"TSN","sources":["d"],"permitted":[],
                "default":null,"fallback":null}))
            .unwrap(),
        ],
        ..Default::default()
    };
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, platform.clone()).await;
    let refresh = format!("/organizations/{}/model-sources/d/refresh", org.id);
    let policy_path = format!("/organizations/{}/model-policy", org.id);
    let offer = |id: &str| json!({"source_id":"d","upstream_model_id":id});
    let policy = |revision, permitted: Value| {
        json!({"expected_revision":revision,"permitted":permitted,
            "default":null,"fallback":null,"title":null,"creation_assistant":null,"embedding":null,"vision":null,"reranker":null})
    };

    // Declared is not yet observed: nothing is published or selectable before a refresh.
    let view = inventory(&app, &identity, org.id).await;
    assert_eq!(view["sources"][0]["observation"]["state"], "not_observed");
    assert_eq!(view["sources"][0]["offers"], json!([]));
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &policy_path,
        policy(1, json!([offer("chat")])),
    )
    .await;
    assert_eq!(status, 422, "{body}");

    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &refresh,
        Value::Null,
    )
    .await;
    assert_eq!(status, 204, "{body}");
    let view = inventory(&app, &identity, org.id).await;
    assert_eq!(view["sources"][0]["observation"]["state"], "ok");
    assert_eq!(view["sources"][0]["api_root"], provider.url);
    assert!(!view.to_string().contains("credential_binding"));
    let offers = view["sources"][0]["offers"].as_array().unwrap();
    assert_eq!(offers.len(), 2);
    assert_eq!(offers[0]["upstream_model_id"], "chat");
    assert_eq!(offers[0]["selectable"], true);
    assert_eq!(offers[0]["metadata"]["chat"], true);
    assert_eq!(offers[0]["metadata"]["chat_provenance"], "source_guarantee");
    assert_eq!(offers[0]["metadata"]["reasoning"], true);
    assert_eq!(offers[0]["metadata"]["display_name"], "Chat");
    assert_eq!(offers[0]["metadata"]["max_output_tokens"], 100);
    assert_eq!(offers[1]["metadata"]["reasoning"], Value::Null);
    // A declaration grants nothing, and its unknown reasoning stays unknown.
    assert_eq!(view["policy"]["permitted"], json!([]));
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &policy_path,
        policy(1, json!([offer("chat")])),
    )
    .await;
    assert_eq!(status, 200, "{body}");

    // A changed list needs a higher revision, and a changed kind a new source_id.
    let reduced = json!([{"id":"chat","reasoning":true}]);
    assert!(
        model_catalog::configure_sources(&e.pool, &[provider.declared("d", 1, reduced.clone())])
            .await
            .is_err()
    );
    let mut discovered = provider.source("d");
    discovered.revision = 3;
    assert!(
        model_catalog::configure_sources(&e.pool, &[discovered])
            .await
            .is_err()
    );
    platform.model_sources = vec![provider.declared("d", 2, reduced)];
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    let app = model_app(&e, &identity, platform).await;
    let view = inventory(&app, &identity, org.id).await;
    assert_eq!(view["sources"][0]["observation"]["state"], "not_observed");
    assert_eq!(view["sources"][0]["offers"][0]["selectable"], false);
    assert_eq!(view["policy"]["permitted"], json!([offer("chat")]));
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &refresh,
        Value::Null,
    )
    .await;
    assert_eq!(status, 204, "{body}");
    let view = inventory(&app, &identity, org.id).await;
    let offers = view["sources"][0]["offers"].as_array().unwrap();
    assert_eq!(offers[0]["selectable"], true);
    assert_eq!(
        offers.len(),
        1,
        "unreferenced withdrawn offers disappear from the catalogue"
    );
    let (advertised,withdrawn):(bool,bool)=sqlx::query_as("select advertised,withdrawn_at is not null from model_offer where source_id='d' and upstream_model_id='other'").fetch_one(&e.pool).await.unwrap();
    assert!(
        !advertised && withdrawn,
        "withdrawal history remains recorded"
    );
    // The whole journey never reached the provider's list endpoint.
    assert_eq!(provider.response.lock().await.2, 0);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn organization_initialization_publishes_a_declared_list_it_permits() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let provider = Provider::start().await;
    let platform = PlatformConfig {
        model_sources: vec![provider.declared(
            "d",
            1,
            json!([{"id":"chat","reasoning":true},{"id":"extra"}]),
        )],
        organization_models: vec![declaration("TSN", &["d"])],
        ..Default::default()
    };
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    assert!(completion(&e, org.id).await);
    let identity = support::IdentityServer::start().await;
    let view = inventory(&model_app(&e, &identity, platform).await, &identity, org.id).await;
    assert_eq!(view["sources"][0]["observation"]["state"], "ok");
    assert_eq!(view["policy"]["permitted"], json!([key("d")]));
    assert_eq!(view["policy"]["default"], key("d"));
    assert_eq!(provider.response.lock().await.2, 0);
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
    let policy = json!({"expected_revision":1,"permitted":[key("b")],"default":key("b"),"fallback":null,"title":null,"creation_assistant":null,"embedding":null,"vision":null,"reranker":null});
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
    let empty = json!({"expected_revision":1,"permitted":[],"default":null,"fallback":null,"title":null,"creation_assistant":null,"embedding":null,"vision":null,"reranker":null});
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
    assert_eq!(view["sources"].as_array().unwrap().len(), 1);
    assert_eq!(view["policy"]["permitted"], json!([]));
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
async fn configured_sources_are_added_after_initialization_without_reseeding() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let provider = Provider::start().await;
    let mut platform = PlatformConfig {
        model_sources: vec![
            provider.source("a"),
            provider.source("b"),
            provider.source("c"),
        ],
        organization_models: vec![declaration("TSN", &["a"])],
        ..Default::default()
    };
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, platform.clone()).await;
    let before = inventory(&app, &identity, org.id).await;
    let receipt: Value = sqlx::query_scalar(
        "select to_jsonb(r) from organization_model_initialization r where organization_id=$1",
    )
    .bind(org.id)
    .fetch_one(&e.pool)
    .await
    .unwrap();
    let calls = provider.response.lock().await.2;
    // Even changed seed permissions/defaults must not overwrite the Owner's policy.
    platform.organization_models[0] = declaration("TSN", &["b", "a"]);
    let (first, replay) = tokio::join!(
        initialize(&e.pool, &platform, true),
        initialize(&e.pool, &platform, true),
    );
    first.unwrap();
    replay.unwrap();
    let after = inventory(&app, &identity, org.id).await;
    assert_eq!(after["policy"], before["policy"]);
    assert_eq!(after["sources"].as_array().unwrap().len(), 2);
    assert_eq!(calls, provider.response.lock().await.2);
    assert_eq!(
        receipt,
        sqlx::query_scalar::<_, Value>(
            "select to_jsonb(r) from organization_model_initialization r where organization_id=$1",
        )
        .bind(org.id)
        .fetch_one(&e.pool)
        .await
        .unwrap()
    );

    // A missing source rolls back all additions for this organization.
    platform.organization_models[0]
        .sources
        .extend(["c".into(), "unknown".into()]);
    assert!(
        initialize(&e.pool, &platform, true)
            .await
            .unwrap_err()
            .to_string()
            .contains("model_source_unknown")
    );
    assert_eq!(inventory(&app, &identity, org.id).await, after);
    // Removing YAML is not revocation; another organization receives no assignment.
    platform.organization_models[0] = declaration("TSN", &["a"]);
    let other = support::member_organization(&e.pool, "Other", "alice")
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    assert_eq!(inventory(&app, &identity, org.id).await, after);
    assert_eq!(
        inventory(&app, &identity, other.id).await["sources"],
        json!([])
    );
    assert_eq!(calls, provider.response.lock().await.2);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn operator_source_assignment_is_additive_and_preserves_initialization() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let provider = Provider::start().await;
    let mut disabled = provider.source("disabled");
    disabled.enabled = false;
    let platform = PlatformConfig {
        model_sources: vec![provider.source("a"), provider.source("bench"), disabled],
        organization_models: vec![declaration("TSN", &["a"])],
        ..Default::default()
    };
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, platform.clone()).await;
    let before = inventory(&app, &identity, org.id).await;
    let receipt: Value = sqlx::query_scalar(
        "select to_jsonb(r) from organization_model_initialization r where organization_id=$1",
    )
    .bind(org.id)
    .fetch_one(&e.pool)
    .await
    .unwrap();
    let calls = provider.response.lock().await.2;

    let (first, replay) = tokio::join!(
        model_catalog::assign_source(&e.pool, org.id, "bench"),
        model_catalog::assign_source(&e.pool, org.id, "bench"),
    );
    first.unwrap();
    replay.unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let after = inventory(&app, &identity, org.id).await;
    assert_eq!(after["policy"], before["policy"]);
    assert_eq!(after["sources"].as_array().unwrap().len(), 2);
    assert_eq!(calls, provider.response.lock().await.2);
    assert_eq!(
        receipt,
        sqlx::query_scalar::<_, Value>(
            "select to_jsonb(r) from organization_model_initialization r where organization_id=$1",
        )
        .bind(org.id)
        .fetch_one(&e.pool)
        .await
        .unwrap()
    );

    for invalid_org in [team.id, Uuid::new_v4()] {
        assert!(
            model_catalog::assign_source(&e.pool, invalid_org, "bench")
                .await
                .is_err()
        );
    }
    assert!(
        model_catalog::assign_source(&e.pool, org.id, "unknown")
            .await
            .is_err()
    );
    assert_eq!(inventory(&app, &identity, org.id).await, after);

    // Fresh organizations need neither a seed policy nor a receipt to receive a source.
    let fresh = support::member_organization(&e.pool, "Fresh", "alice")
        .await
        .unwrap();
    model_catalog::assign_source(&e.pool, fresh.id, "disabled")
        .await
        .unwrap();
    assert!(!completion(&e, fresh.id).await);
    let fresh_view = inventory(&app, &identity, fresh.id).await;
    assert_eq!(fresh_view["policy"]["revision"], 0);
    assert_eq!(fresh_view["sources"][0]["observation"]["enabled"], false);
    let deletion = Uuid::new_v4();
    sqlx::query("insert into deletion(id,target_id,target_kind,organization_id,actor_subject,requested_at,due_at) values($1,$2,'organization',$2,'alice',now(),now())")
        .bind(deletion).bind(fresh.id).execute(&e.pool).await.unwrap();
    sqlx::query("update space set deletion_id=$1 where id=$2")
        .bind(deletion)
        .bind(fresh.id)
        .execute(&e.pool)
        .await
        .unwrap();
    assert!(
        model_catalog::assign_source(&e.pool, fresh.id, "bench")
            .await
            .is_err()
    );
    assert!(!sqlx::query_scalar::<_, bool>(
        "select exists(select 1 from organization_model_source where organization_id=$1 and source_id='bench')",
    ).bind(fresh.id).fetch_one(&e.pool).await.unwrap());
    assert_eq!(calls, provider.response.lock().await.2);
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
        credential_binding: "a".into(),
        api_root: provider.url.clone(),
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
        history: None,
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
    assert_eq!(prepared["models"]["offers"][0]["reasoning_enabled"], true);
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
    assert!(public["models"]["offers"][0].get("source_name").is_none());
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
        let tool_result = body
            .lines()
            .filter_map(|line| line.strip_prefix("data: "))
            .map(|data| serde_json::from_str::<Value>(data).unwrap())
            .find(|event| event["kind"] == "tool_result")
            .expect("search must emit its tool result");
        assert_eq!(
            tool_result["failure"],
            if status == 200 {
                Value::Null
            } else {
                json!({"code":"unexpected"})
            }
        );
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
            json!({"space_id":team.id,"authorized_space_ids":[org.id,team.id],"document_scope":{"selections":[]},"attachment_ids":[]})
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
async fn dictation_uses_the_authorized_file_model_and_its_bound_credential() {
    use axum::{
        body::{Body, to_bytes},
        http::Request,
    };
    use tower::ServiceExt;

    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    grant(&e, team.id, Role::Owner, "alice").await;
    let local = Provider::start().await;
    let remote = Provider::start().await;
    *remote.response.lock().await = (
        200,
        json!({"data":[
            {"id":"speech"},
            {"id":"live", "capabilities":{"audio_transcription_realtime":true}}
        ]}),
        0,
    );
    let whisper = json!({"source_id":"local", "upstream_model_id":"whisper"});
    let platform = PlatformConfig {
        model_sources: vec![local.declared(
            "local",
            1,
            json!([
            {"id":"chat", "reasoning":true}, {"id":"whisper", "audio_transcription":true}
            ]),
        )],
        organization_models: vec![declaration("TSN", &["local"])],
        inference_credentials: vec![fred_rust_sdk::inference::InferenceCredentialBinding {
            credential_binding: "local".into(),
            api_root: local.url.clone(),
            api_key_env: "FRED_TEST_INFERENCE_CREDENTIAL".into(),
        }],
        ..Default::default()
    };
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let native = template_id(org.id, "control-plane", fred_rust_agent::AGENT_ID);
    control_plane::authorization::set_agent_default_on(
        &mut e.pool.acquire().await.unwrap(),
        org.id,
        native,
        true,
    )
    .await
    .unwrap();
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, platform).await;
    let instance = create(&app, &identity, team.id, creation(native, "Dictation")).await;
    let base = item(team.id, &instance);
    let policy_path = format!("/organizations/{}/model-policy", org.id);
    let sources = format!("/organizations/{}/model-sources", org.id);
    let (status, source) = request(&app, &identity, Some("alice"), "POST", &sources, json!({
        "name":"Speech service", "url":"https://speech.invalid/models", "api_root":"https://speech.invalid",
        "token":"synthetic-original-key", "dialect":"openai_compatible", "wire":"openai_chat"
    })).await;
    assert_eq!(status, 201, "{source}");
    let source = source.as_str().unwrap();
    // Only the isolated fixture permits HTTP. Rotate through the normal API so
    // the encrypted credential is sealed against the fixture's actual destination.
    sqlx::query(
        "update model_source set configuration=configuration || jsonb_build_object(
        'allow_insecure_http', true,
        'inventory', (configuration->'inventory') || jsonb_build_object('url', $2::text),
        'inference', (configuration->'inference') || jsonb_build_object('api_root', $3::text)
    ) where source_id=$1",
    )
    .bind(source)
    .bind(format!("{}/models", remote.url))
    .bind(&remote.url)
    .execute(&e.pool)
    .await
    .unwrap();
    let source_path = format!("{sources}/{source}");
    let result = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &source_path,
        json!({
            "name":"Speech service", "expected_revision":1, "token":"synthetic-speech-key"
        }),
    )
    .await;
    assert_eq!(result.0, 204, "{result:?}");
    let result = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!("{source_path}/refresh"),
        Value::Null,
    )
    .await;
    assert_eq!(result.0, 204, "{result:?}");
    let catalogue = model_catalog::inventory(&e.pool, source)
        .await
        .unwrap()
        .unwrap();
    let offer = catalogue
        .offers
        .iter()
        .find(|offer| offer.upstream_model_id == "speech")
        .unwrap();
    assert!(offer.uses.unverified && offer.uses.transcription);
    assert_eq!(offer.metadata.audio_transcription, None);

    let prepare_path = format!("{base}/prepare-execution");
    let prepare = || {
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &prepare_path,
            Value::Null,
        )
    };
    let transcribe = |user: &'static str| {
        let app = app.clone();
        let uri = format!("{base}/transcriptions");
        let token = identity.token(user);
        async move {
            let request = Request::post(uri)
                .header("authorization", format!("Bearer {token}"))
                .header("content-type", "multipart/form-data; boundary=audio-test")
                .body(Body::from(concat!(
                    "--audio-test\r\nContent-Disposition: form-data; name=\"file\"; filename=\"browser-name.webm\"\r\n",
                    "Content-Type: audio/webm;codecs=opus\r\n\r\nclip-data\r\n--audio-test--\r\n"
                ))).unwrap();
            let result = app.oneshot(request).await.unwrap();
            let status = result.status().as_u16();
            let bytes = to_bytes(result.into_body(), 1 << 20).await.unwrap();
            (status, serde_json::from_slice::<Value>(&bytes).unwrap())
        }
    };
    assert_eq!(prepare().await.1["dictation_available"], false);
    assert_eq!(transcribe("alice").await.0, 409);

    let speech = json!({"source_id":source,"upstream_model_id":"speech"});
    let live = json!({"source_id":source,"upstream_model_id":"live"});
    let replace = |revision: i64, model: Value| {
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &policy_path,
            json!({
                "expected_revision":revision,"permitted":[key("local"),whisper,speech],
                "default":key("local"),"fallback":null,"title":null,"creation_assistant":null,
                "embedding":null,"vision":null,"reranker":null,"transcription":model
            }),
        )
    };
    assert_eq!(replace(1, key("local")).await.0, 422);
    let result = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &policy_path,
        json!({
            "expected_revision":1,"permitted":[key("local"),live],
            "default":key("local"),"fallback":null,"title":null,"creation_assistant":null,
            "embedding":null,"vision":null,"reranker":null,"transcription":live
        }),
    )
    .await;
    assert_eq!(result.0, 422, "{result:?}");
    assert_eq!(result.1["code"], "model_offer_unsuited");
    let saved = replace(1, whisper.clone()).await;
    assert_eq!(saved.0, 200, "{saved:?}");
    assert_eq!(saved.1["transcription"], whisper);
    assert_eq!(prepare().await.1["dictation_available"], true);
    assert!(matches!(transcribe("bob").await.0, 403 | 404));
    assert!(local.transcriptions.lock().await.is_empty());
    assert_eq!(
        transcribe("alice").await,
        (200, json!({"text":"Un message dicté."}))
    );
    assert_eq!(
        *local.transcriptions.lock().await,
        vec![json!({
            "authorization":"Bearer synthetic-inference-key", "model":"whisper",
            "filename":"dictation.webm", "mime":"audio/webm", "file":"clip-data"
        })]
    );

    let revision = saved.1["revision"].as_i64().unwrap();
    let saved = replace(revision, speech.clone()).await;
    assert_eq!(saved.0, 200, "{saved:?}");
    let retained = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &policy_path,
        json!({
            "expected_revision":saved.1["revision"],"permitted":[key("local"),whisper,speech],
            "default":key("local"),"fallback":null,"title":null,
            "creation_assistant":null,"embedding":null,"vision":null,"reranker":null
        }),
    )
    .await;
    assert_eq!(retained.0, 200, "{retained:?}");
    assert_eq!(retained.1["transcription"], speech);
    assert_eq!(transcribe("alice").await.0, 200);
    assert_eq!(
        *remote.transcriptions.lock().await,
        vec![json!({
            "authorization":"Bearer synthetic-speech-key", "model":"speech",
            "filename":"dictation.webm", "mime":"audio/webm", "file":"clip-data"
        })]
    );

    let result = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &format!("/spaces/{}/model-policy", team.id),
        json!({"expected_revision":0,"default":null,"disabled":[speech],"reasoning_default_on":[]}),
    )
    .await;
    assert_eq!(result.0, 204, "{result:?}");
    assert_eq!(prepare().await.1["dictation_available"], false);
    assert_eq!(transcribe("alice").await.0, 409);
    assert_eq!(local.transcriptions.lock().await.len(), 1);
    assert_eq!(remote.transcriptions.lock().await.len(), 1);
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
    let mut body = json!({"expected_revision":1,"permitted":[key("a")],"default":key("a"),"fallback":null,"title":key("a"),"creation_assistant":null,"embedding":null,"vision":null,"reranker":null});
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

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn document_models_need_their_aptitude_and_the_indexed_corpus_keeps_its_embedding() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let provider = Provider::start().await;
    *provider.response.lock().await = (
        200,
        json!({"data": [
            {"id":"chat", "capabilities":{"completion_chat":true,"vision":false,"reasoning":true}},
            {"id":"see", "capabilities":{"completion_chat":true,"vision":true}},
            {"id":"embed", "capabilities":{"completion_chat":false}}
        ]}),
        0,
    );
    let mut source = provider.source("a");
    source.embedding_models = vec!["embed".into()];
    let platform = PlatformConfig {
        model_sources: vec![source],
        organization_models: vec![declaration("TSN", &["a"])],
        ..Default::default()
    };
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, platform).await;
    let offer = |id: &str| json!({"source_id":"a","upstream_model_id":id});
    let offers = inventory(&app, &identity, org.id).await["sources"][0]["offers"].clone();
    let embed = offers
        .as_array()
        .unwrap()
        .iter()
        .find(|o| o["upstream_model_id"] == "embed")
        .unwrap();
    assert_eq!(
        (&embed["metadata"]["chat"], &embed["metadata"]["embedding"]),
        (&json!(false), &json!(true))
    );
    assert_eq!(
        embed["selectable"], true,
        "an attested embedding offer can be permitted"
    );
    let path = format!("/organizations/{}/model-policy", org.id);
    let body = |revision: i64, embedding: Value, vision: Value| {
        json!({"expected_revision":revision,"permitted":[offer("chat"),offer("see"),offer("embed")],
            "default":offer("chat"),"fallback":null,"title":null,"creation_assistant":null,
            "embedding":embedding,"vision":vision,"reranker":null})
    };
    let put = |payload: Value| {
        let (app, identity, path) = (&app, &identity, &path);
        async move { request(app, identity, Some("alice"), "PUT", path, payload).await }
    };
    // Each choice needs its aptitude: no chat model embeds, no embedding model chats or sees.
    for (embedding, vision) in [
        (offer("chat"), Value::Null),
        (offer("embed"), offer("embed")),
        (offer("embed"), offer("chat")),
    ] {
        let (status, error) = put(body(1, embedding, vision)).await;
        assert_eq!(status, 422, "{error}");
    }
    let (status, saved) = put(body(1, offer("embed"), offer("see"))).await;
    assert_eq!(status, 200, "{saved}");
    assert_eq!(
        (
            &saved["embedding"],
            &saved["vision"],
            &saved["embedding_locked"]
        ),
        (&offer("embed"), &offer("see"), &json!(false))
    );
    let projected = |use_: &'static str| {
        let pool = e.pool.clone();
        async move {
            sqlx::query_as::<_, (String, bool)>("select upstream_model_id, available from cp_read.organization_model where space_id=$1 and use=$2")
                .bind(org.id).bind(use_).fetch_optional(&pool).await.unwrap()
        }
    };
    assert_eq!(projected("chat").await, Some(("chat".into(), true)));
    assert_eq!(
        projected("embedding").await,
        None,
        "no corpus is indexed yet"
    );
    // Before any indexing the choice is free; the first indexing claim locks it.
    let (status, saved) = put(body(2, Value::Null, offer("see"))).await;
    assert_eq!(status, 200, "{saved}");
    let (status, saved) = put(body(3, offer("embed"), Value::Null)).await;
    assert_eq!(status, 200, "{saved}");
    sqlx::query(
        "update organization_model_policy set embedding_locked_at=now() where organization_id=$1",
    )
    .bind(org.id)
    .execute(&e.pool)
    .await
    .unwrap();
    assert_eq!(projected("embedding").await, Some(("embed".into(), true)));
    let (status, error) = put(body(4, Value::Null, Value::Null)).await;
    assert_eq!(
        (status, error["code"].as_str()),
        (409, Some("embedding_model_locked")),
        "{error}"
    );
    let (status, saved) = put(body(4, offer("embed"), offer("see"))).await;
    assert_eq!(status, 200, "other choices stay administrable: {saved}");
    assert_eq!(saved["embedding_locked"], true);
    // The database keeps the corpus fact even against a direct write or deletion.
    for statement in [
        "update organization_model_policy set embedding_source_id=null, embedding_upstream_model_id=null where organization_id=$1",
        "update organization_model_policy set embedding_locked_at=null where organization_id=$1",
        "delete from organization_model_policy where organization_id=$1",
    ] {
        let error = sqlx::query(statement)
            .bind(org.id)
            .execute(&e.pool)
            .await
            .unwrap_err();
        assert!(
            error.to_string().contains("keeps its embedding model"),
            "{error}"
        );
    }
    // A withdrawn corpus model is published as unavailable, never replaced.
    sqlx::query("update model_offer set advertised=false, withdrawn_at=now() where upstream_model_id='embed'")
        .execute(&e.pool).await.unwrap();
    assert_eq!(projected("embedding").await, Some(("embed".into(), false)));
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn local_model_policy_preserves_roles_parent_ceiling_and_retained_recommendation() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Owner, "bob").await;
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "Models".into(),
        "alice",
    )
    .await
    .unwrap();
    let provider = Provider::start().await;
    let catalog = Catalog::start().await;
    let mut platform = catalog.config();
    platform.model_sources = vec![provider.source("a"), provider.source("b")];
    platform.organization_models = vec![declaration("TSN", &["a", "b"])];
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, platform).await;
    let policy_path = format!("/spaces/{}/model-policy", team.id);
    let view_path = format!("/spaces/{}/models", team.id);
    let policy = |revision, default: Value, disabled: Value| {
        json!({
            "expected_revision":revision, "default":default, "disabled":disabled,
            "reasoning_default_on":[]
        })
    };
    // Owner-only governance exposes the public model catalogue, without content Read.
    assert!(!reads(&e, "bob", team.id).await);
    assert_eq!(
        request(&app, &identity, Some("bob"), "GET", &view_path, Value::Null)
            .await
            .0,
        200
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("outsider"),
            "GET",
            &view_path,
            Value::Null
        )
        .await
        .0,
        403
    );
    let template = enable(&e, org.id, "custom", true).await;
    let mut body = creation(template, "Retained recommendation");
    body["recommended_model"] = key("a");
    let agent = create(&app, &identity, team.id, body).await;
    let response = request(
        &app,
        &identity,
        Some("bob"),
        "PUT",
        &policy_path,
        policy(0, key("b"), json!([key("a")])),
    )
    .await;
    assert_eq!(response.0, 204, "{response:?}");
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "PUT",
            &policy_path,
            policy(0, key("b"), json!([]))
        )
        .await
        .0,
        409
    );
    // A project owner cannot re-enable a model disabled by its team.
    let response = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &format!("/spaces/{}/model-policy", project.id),
        policy(0, key("a"), json!([])),
    )
    .await;
    assert_eq!(response.0, 422, "{response:?}");
    let response = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("/spaces/{}/models", project.id),
        Value::Null,
    )
    .await;
    assert_eq!(response.0, 200, "{response:?}");
    assert_eq!(response.1["models"]["default"], key("b"));
    assert_eq!(response.1["parent_permitted"], json!([key("b")]));
    // The saved recommendation remains visible and refuses use instead of choosing b.
    let base = item(team.id, &agent);
    let response = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("{base}/runtime"),
        Value::Null,
    )
    .await;
    assert_eq!(response.0, 200, "{response:?}");
    assert_eq!(response.1["models"]["recommendation"], key("a"));
    assert_eq!(response.1["models"]["default"], key("b"));
    let response = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!("{base}/prepare-execution"),
        Value::Null,
    )
    .await;
    assert_eq!(response.0, 200, "{response:?}");
    assert_eq!(response.1["model_error"]["code"], "offer_forbidden");
    // Revocation is observed by a fresh governance request.
    delete_tuple(&e, "bob", "owner", &format!("space:{}", team.id)).await;
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "PUT",
            &policy_path,
            policy(1, key("b"), json!([]))
        )
        .await
        .0,
        403
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn organization_model_scopes_govern_teams_and_personal_spaces_without_granting_parent_rights()
{
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    grant(&e, org.id, Role::Member, "bob").await;
    let second = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Team,
        org.id,
        "Second".into(),
        "bob",
    )
    .await
    .unwrap();
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "Project".into(),
        "alice",
    )
    .await
    .unwrap();
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    let other = support::member_organization(&e.pool, "Other", "bob")
        .await
        .unwrap();
    let foreign = spaces::create_space(
        &e.pool,
        "bob",
        SpaceKind::Team,
        other.id,
        "Foreign".into(),
        "bob",
    )
    .await
    .unwrap();
    let provider = Provider::start().await;
    let catalog = Catalog::start().await;
    let mut platform = catalog.config();
    platform.model_sources = vec![provider.source("a"), provider.source("b")];
    platform.organization_models = vec![declaration("TSN", &["a", "b"])];
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, platform).await;
    let path = format!("/organizations/{}/model-sources/a/access", org.id);
    let view = format!("{path}?upstream_model_id=chat");
    let matrix = request(&app, &identity, Some("alice"), "GET", &view, Value::Null).await;
    assert_eq!(matrix.0, 200, "{matrix:?}");
    let revision = matrix.1["revision"].as_i64().unwrap();
    assert_eq!(matrix.1["teams"].as_array().unwrap().len(), 2);
    assert!(
        matrix.1["teams"]
            .as_array()
            .unwrap()
            .iter()
            .any(|row| row["team_id"] == second.id.to_string())
    );
    assert_eq!(matrix.1["personal"], "default");
    // A team owner or organization member does not gain organization governance.
    assert_eq!(
        request(&app, &identity, Some("bob"), "GET", &view, Value::Null)
            .await
            .0,
        403
    );
    let position = |revision, team: Option<Uuid>, choice: &str, model: &str| json!({"expected_revision":revision,"upstream_model_id":model,"team_id":team,"choice":choice});
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "PUT",
            &path,
            position(revision, Some(second.id), "disabled", "chat")
        )
        .await
        .0,
        403
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &path,
            position(revision, Some(foreign.id), "disabled", "chat")
        )
        .await
        .0,
        404
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &path,
            position(revision, None, "enabled", "extra")
        )
        .await
        .0,
        422
    );
    let template = enable(&e, org.id, "custom", true).await;
    let mut creation = creation(template, "Scoped model");
    creation["recommended_model"] = key("a");
    let agent = create(&app, &identity, team.id, creation).await;
    let response = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &path,
        position(revision, Some(team.id), "disabled", "chat"),
    )
    .await;
    assert_eq!(response.0, 204, "{response:?}");
    // Stale writes cannot overwrite another scope's decision.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &path,
            position(revision, None, "disabled", "chat")
        )
        .await
        .0,
        409
    );
    let model_permitted = |view: &Value| {
        view["models"]["offers"]
            .as_array()
            .unwrap()
            .iter()
            .find(|offer| offer["key"] == key("a"))
            .unwrap()["permitted"]
            .as_bool()
            .unwrap()
    };
    for space in [team.id, project.id] {
        let response = request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("/spaces/{space}/models"),
            Value::Null,
        )
        .await;
        assert_eq!(response.0, 200, "{response:?}");
        assert!(!model_permitted(&response.1));
    }
    let prepared = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!("{}/prepare-execution", item(team.id, &agent)),
        Value::Null,
    )
    .await;
    assert_eq!(prepared.0, 200, "{prepared:?}");
    assert_eq!(prepared.1["model_error"]["code"], "offer_forbidden");
    let response = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &format!("/spaces/{}/model-policy", team.id),
        json!({"expected_revision":0,"default":key("a"),"disabled":[],"reasoning_default_on":[]}),
    )
    .await;
    assert_eq!(response.0, 422, "{response:?}");
    // Personal-class changes cover existing and future personal spaces, independently of teams.
    let response = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &path,
        position(revision + 1, None, "disabled", "chat"),
    )
    .await;
    assert_eq!(response.0, 204, "{response:?}");
    let (future, _) = spaces::create_personal_space(&e.pool, "bob", org.id)
        .await
        .unwrap();
    for (user, space) in [("alice", personal.id), ("bob", future.id)] {
        let response = request(
            &app,
            &identity,
            Some(user),
            "GET",
            &format!("/spaces/{space}/models"),
            Value::Null,
        )
        .await;
        assert_eq!(response.0, 200, "{response:?}");
        assert!(!model_permitted(&response.1));
    }
    let second_models = request(
        &app,
        &identity,
        Some("bob"),
        "GET",
        &format!("/spaces/{}/models", second.id),
        Value::Null,
    )
    .await;
    assert_eq!(second_models.0, 200, "{second_models:?}");
    assert!(model_permitted(&second_models.1));
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &path,
            position(revision + 2, None, "default", "chat")
        )
        .await
        .0,
        204
    );
    let personal_models = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("/spaces/{}/models", personal.id),
        Value::Null,
    )
    .await;
    assert!(model_permitted(&personal_models.1));
    // A central enable does not erase the team's own restrictions or authorize its contents.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &path,
            position(revision + 3, Some(team.id), "enabled", "chat")
        )
        .await
        .0,
        204
    );
    let response = request(&app,&identity,Some("alice"),"PUT",&format!("/spaces/{}/model-policy",team.id),json!({"expected_revision":0,"default":key("b"),"disabled":[key("a")],"reasoning_default_on":[]})).await;
    assert_eq!(response.0, 204, "{response:?}");
    let matrix = request(&app, &identity, Some("alice"), "GET", &view, Value::Null).await;
    let row = matrix.1["teams"]
        .as_array()
        .unwrap()
        .iter()
        .find(|row| row["team_id"] == team.id.to_string())
        .unwrap();
    assert_eq!(row["choice"], "enabled");
    assert_eq!(row["effective"], false);
    assert_eq!(row["locally_disabled"], true);
    assert!(!reads(&e, "alice", second.id).await);
    let filtered = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("{view}&name=Second"),
        Value::Null,
    )
    .await;
    assert_eq!(filtered.1["teams"].as_array().unwrap().len(), 1);
    assert_eq!(filtered.1["teams"][0]["team_id"], second.id.to_string());
    let invalid = sqlx::query("insert into organization_model_scope(organization_id,source_id,upstream_model_id,team_id,enabled,updated_by) values($1,'a','chat',$2,false,'fixture')")
        .bind(org.id).bind(foreign.id).execute(&e.pool).await;
    assert!(invalid.is_err());
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn managed_single_model_registers_and_refreshes_without_catalogue_discovery() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, PlatformConfig::default()).await;
    let path = format!("/organizations/{}/model-sources", org.id);
    let input = json!({
        "name": "Direct embeddings",
        "model": {"id": "direct/embeddings", "usage": "embedding"},
        "api_root": "https://api.openai.com/v1",
        "token": "synthetic-inference-token",
        "dialect": "openai_compatible",
        "wire": "openai_chat",
        "models_dev_enabled": false
    });
    let mut ambiguous = input.clone();
    ambiguous["url"] = json!("https://inference.invalid/v1/models");
    let (status, body) = request(&app, &identity, Some("alice"), "POST", &path, ambiguous).await;
    assert_eq!(status, 422, "{body}");

    let (status, body) = request(&app, &identity, Some("alice"), "POST", &path, input).await;
    assert_eq!(status, 201, "{body}");
    let source_id = body.as_str().unwrap();
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!("{path}/{source_id}/refresh"),
        Value::Null,
    )
    .await;
    assert_eq!(status, 204, "{body}");

    let view = inventory(&app, &identity, org.id).await;
    let sources = view["sources"].as_array().unwrap();
    assert_eq!(sources.len(), 1);
    let source = &sources[0];
    assert_eq!(source["observation"]["source_id"], source_id);
    assert_eq!(source["url"], Value::Null);
    assert_eq!(source["platform_terms_url"], Value::Null);
    let offers = source["offers"].as_array().unwrap();
    assert_eq!(offers.len(), 1);
    assert_eq!(offers[0]["upstream_model_id"], "direct/embeddings");
    assert_eq!(offers[0]["selectable"], true);
    assert_eq!(offers[0]["metadata"]["embedding"], true);
    assert_eq!(offers[0]["metadata"]["chat"], false);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn managed_catalogues_preserve_credentials_ownership_metadata_and_file_sources() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let other = support::member_organization(&e.pool, "Other", "bob")
        .await
        .unwrap();
    let provider = Provider::start().await;
    let catalog = Catalog::start().await;
    let platform = PlatformConfig {
        model_sources: vec![provider.declared("file", 1, json!([{"id":"chat","reasoning":true}]))],
        organization_models: vec![declaration("TSN", &["file"])],
        ..catalog.config()
    };
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    initialize(&e.pool, &platform, true).await.unwrap();
    let identity = support::IdentityServer::start().await;
    let app = model_app(&e, &identity, platform.clone()).await;
    let path = format!("/organizations/{}/model-sources", org.id);
    let platform_terms = "https://inference.invalid/legal#terms";
    let input = json!({"name":"Provider A","url":"https://catalogue.invalid/models","api_root":"https://inference.invalid/v1","token":"synthetic-catalogue-token","dialect":"openai_compatible","wire":"openai_chat","metadata_provider":"example-registry-id","platform_terms_url":platform_terms});
    assert_eq!(
        request(&app, &identity, Some("bob"), "POST", &path, input.clone())
            .await
            .0,
        404
    );
    let (status, body) = request(&app, &identity, Some("alice"), "POST", &path, input).await;
    assert_eq!(status, 201, "{body}");
    let source = body.as_str().unwrap();
    let saved: Vec<u8> = sqlx::query_scalar(
        "select encrypted_token from organization_model_catalog where source_id=$1",
    )
    .bind(source)
    .fetch_one(&e.pool)
    .await
    .unwrap();
    assert!(
        !saved
            .windows(b"synthetic-catalogue-token".len())
            .any(|bytes| bytes == b"synthetic-catalogue-token")
    );
    // Deployment reconfiguration must neither reject nor erase an owned source.
    model_catalog::configure_sources(&e.pool, &platform.model_sources)
        .await
        .unwrap();
    let mut collision = platform.model_sources.clone();
    collision.push(provider.source(source));
    assert!(
        model_catalog::configure_sources(&e.pool, &collision)
            .await
            .is_err(),
        "deployment YAML must not overwrite an organization-owned catalogue"
    );
    let view = inventory(&app, &identity, org.id).await;
    assert_eq!(view["sources"].as_array().unwrap().len(), 2);
    assert!(view["sources"].as_array().unwrap().iter().any(|entry| {
        entry["observation"]["source_id"] == source
            && entry["metadata_provider"] == "example-registry-id"
            && entry["platform_terms_url"] == platform_terms
    }));
    assert!(!view.to_string().contains("synthetic-catalogue-token"));
    assert!(!view.to_string().contains("encrypted_credential"));
    let (status, other_view) = request(
        &app,
        &identity,
        Some("bob"),
        "GET",
        &format!("/organizations/{}/models", other.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{other_view}");
    assert_eq!(other_view["sources"], json!([]));
    assert!(
        sqlx::query(
            "insert into organization_model_source(organization_id,source_id) values($1,$2)"
        )
        .bind(other.id)
        .bind(source)
        .execute(&e.pool)
        .await
        .is_err()
    );
    let source_path = format!("{path}/{source}");
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &source_path,
        json!({"name":"Renamed","expected_revision":1}),
    )
    .await;
    assert_eq!(status, 204, "{body}");
    let renamed = model_catalog::inventory(&e.pool, source)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(
        renamed.metadata_provider.as_deref(),
        Some("example-registry-id")
    );
    assert_eq!(renamed.platform_terms_url.as_deref(), Some(platform_terms));
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &source_path,
            json!({"name":"Stale","expected_revision":1})
        )
        .await
        .0,
        409
    );
    // Only this disposable fixture uses HTTP. The public form still requires HTTPS.
    sqlx::query("update model_source set configuration=jsonb_set(jsonb_set(configuration,'{inventory,url}',to_jsonb($2::text)),'{allow_insecure_http}','true') where source_id=$1")
        .bind(source).bind(format!("{}/models",provider.url)).execute(&e.pool).await.unwrap();
    let refresh = format!("{source_path}/refresh");
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &refresh,
            Value::Null
        )
        .await
        .0,
        204
    );
    if std::env::var_os("CONTROL_PLANE_IT_MODELS_DEV_OFFLINE").is_some() {
        let published = model_catalog::inventory(&e.pool, source)
            .await
            .unwrap()
            .unwrap();
        assert_eq!(published.observation.state, "ok");
        assert_eq!(
            published.observation.error_code.as_deref(),
            Some("models_dev_unavailable")
        );
        assert!(published.offers.iter().all(|offer| offer.selectable));
    }
    let metadata = format!("{source_path}/metadata");
    let license = json!({"name":"MIT","url":"https://example.org/model#license"});
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &metadata,
        json!({"expected_revision":0,"upstream_model_id":"chat","values":{
            "context_window_tokens":4096,"chat":false,"tool_calling":true,
            "license":license,"display_name":"Weaver label"
        }}),
    )
    .await;
    assert_eq!(status, 200, "{body}");
    assert_eq!(body["chat"], true, "provider fact cannot be replaced");
    assert_eq!(body["context_window_tokens"], 4096);
    assert_eq!(body["provenance"]["tool_calling"], "manual");
    assert_eq!(body["license"], license);
    assert_eq!(body["provenance"]["license"], "manual");
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &metadata,
            json!({"expected_revision":0,"upstream_model_id":"chat","values":{}})
        )
        .await
        .0,
        409
    );
    // A successful refresh adds new provider facts without losing manual complements.
    let provider_license =
        json!({"name":"Apache-2.0","url":"https://example.org/provider-license"});
    provider.response.lock().await.1 = json!({"data":[
        {"id":"chat","name":"Provider label","context_length":8192,"max_output_tokens":2048,
         "license":provider_license,"capabilities":{"completion_chat":true}},
        {"id":"embed","capabilities":{"embedding":true,"completion_chat":false}},
        {"id":"unclassified"},
        {"id":"no-chat","capabilities":{"completion_chat":false}}
    ]});
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &refresh,
            Value::Null
        )
        .await
        .0,
        204
    );
    let view = inventory(&app, &identity, org.id).await;
    let offer = &view["sources"]
        .as_array()
        .unwrap()
        .iter()
        .find(|v| v["observation"]["source_id"] == source)
        .unwrap()["offers"][0];
    assert_eq!(offer["metadata"]["context_window_tokens"], 8192);
    assert_eq!(offer["metadata_complements"]["context_window_tokens"], 4096);
    assert_eq!(offer["metadata"]["tool_calling"], true);
    assert_eq!(offer["detected_metadata"]["license"], provider_license);
    assert_eq!(
        offer["detected_metadata"]["provenance"]["license"],
        "provider"
    );
    assert_eq!(offer["upstream_model_id"], "chat");
    assert_eq!(offer["metadata"]["display_name"], "Weaver label");
    assert_eq!(offer["metadata"]["provenance"]["display_name"], "manual");
    assert_eq!(offer["detected_metadata"]["display_name"], "Provider label");
    assert_eq!(
        offer["detected_metadata"]["provenance"]["display_name"],
        "provider"
    );
    // A previous successful registry lookup recorded these limits. Only the
    // missing limit is carried forward once enrichment is disabled.
    sqlx::query("update model_offer set metadata=jsonb_set(
         metadata || '{\"max_input_tokens\":6000,\"max_output_tokens\":1024}'::jsonb,
         '{provenance}', (metadata->'provenance') || '{\"max_input_tokens\":\"models_dev\",\"max_output_tokens\":\"models_dev\"}'::jsonb
       ) where source_id=$1 and upstream_model_id='chat'")
        .bind(source).execute(&e.pool).await.unwrap();
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &source_path,
        json!({"name":"Renamed","expected_revision":2,"metadata_provider":null,"models_dev_enabled":false,"platform_terms_url":null}),
    )
    .await;
    assert_eq!(status, 204, "{body}");
    let pending = model_catalog::inventory(&e.pool, source)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(pending.metadata_provider, None);
    assert_eq!(pending.platform_terms_url, None);
    assert!(!pending.models_dev_enabled);
    assert_eq!(pending.observation.state, "ok");
    assert!(
        pending
            .offers
            .iter()
            .all(|offer| offer.selectable == offer.advertised)
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &refresh,
            Value::Null
        )
        .await
        .0,
        204
    );
    let refreshed = model_catalog::inventory(&e.pool, source)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(refreshed.observation.error_code, None);
    let chat = refreshed
        .offers
        .iter()
        .find(|offer| offer.upstream_model_id == "chat")
        .unwrap();
    assert_eq!(chat.metadata.max_input_tokens, Some(6000));
    assert_eq!(chat.metadata.provenance["max_input_tokens"], "models_dev");
    assert_eq!(chat.metadata.max_output_tokens, Some(2048));
    assert_eq!(chat.metadata.provenance["max_output_tokens"], "provider");
    let unknown = refreshed
        .offers
        .iter()
        .find(|offer| offer.upstream_model_id == "unclassified")
        .unwrap();
    assert_eq!(unknown.metadata.chat, None);
    assert!(unknown.selectable && unknown.uses.unverified && unknown.uses.chat);
    let policy_path = format!("/organizations/{}/model-policy", org.id);
    let managed_key = |id| json!({"source_id":source,"upstream_model_id":id});
    let mut policy = json!({"expected_revision":1,"permitted":[key("file"),managed_key("chat"),managed_key("embed"),managed_key("unclassified"),managed_key("no-chat")],"default":managed_key("chat"),"fallback":null,"title":null,"creation_assistant":null,"embedding":managed_key("embed"),"vision":null,"reranker":null});
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &policy_path,
        policy.clone(),
    )
    .await;
    assert_eq!(status, 200, "{body}");
    policy["expected_revision"] = body["revision"].clone();

    let template = enable(&e, org.id, "custom", true).await;
    let agent = create(
        &app,
        &identity,
        team.id,
        creation(template, "Catalogue labels"),
    )
    .await;
    let (status, prepared) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!("{}/prepare-execution", item(team.id, &agent)),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{prepared}");
    let choice = prepared["models"]["offers"]
        .as_array()
        .unwrap()
        .iter()
        .find(|choice| choice["key"] == managed_key("chat"))
        .unwrap();
    assert_eq!(choice["source_name"], "Renamed");
    assert_eq!(choice["metadata"]["display_name"], "Weaver label");
    assert_eq!(choice["selectable"], true);

    policy["default"] = managed_key("no-chat");
    let refused = request(
        &app,
        &identity,
        Some("alice"),
        "PUT",
        &policy_path,
        policy.clone(),
    )
    .await;
    assert_eq!(refused.1["code"], "model_offer_unsuited");
    policy["default"] = managed_key("unclassified");
    let selected = request(&app, &identity, Some("alice"), "PUT", &policy_path, policy).await;
    assert_eq!(selected.0, 200, "{selected:?}");
    assert_eq!(selected.1["default"], managed_key("unclassified"));
    let (status, space_models) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("/spaces/{}/models", team.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{space_models}");
    let choices = space_models["models"]["offers"].as_array().unwrap();
    assert!(
        choices
            .iter()
            .any(|choice| choice["key"] == managed_key("unclassified")
                && choice["selectable"] == true
                && choice["uses"]["unverified"] == true)
    );
    assert!(
        choices
            .iter()
            .any(|choice| choice["key"] == managed_key("no-chat") && choice["selectable"] == false)
    );
    // The catalogue's usage editor uses the same complements as model admission.
    for (revision, values, unverified) in [
        (0, json!({"chat":true,"max_output_tokens":1024}), false),
        (1, json!({"max_output_tokens":1024}), true),
    ] {
        let (status, edited) = request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &metadata,
            json!({"expected_revision":revision,"upstream_model_id":"unclassified","values":values}),
        )
        .await;
        assert_eq!(status, 200, "{edited}");
        assert_eq!(edited["max_output_tokens"], 1024);
        assert_eq!(
            edited["provenance"]["chat"],
            if unverified {
                Value::Null
            } else {
                json!("manual")
            }
        );
        let (status, space_models) = request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("/spaces/{}/models", team.id),
            Value::Null,
        )
        .await;
        assert_eq!(status, 200, "{space_models}");
        let choice = space_models["models"]["offers"]
            .as_array()
            .unwrap()
            .iter()
            .find(|choice| choice["key"] == managed_key("unclassified"))
            .unwrap();
        assert_eq!(choice["selectable"], true);
        assert_eq!(choice["uses"]["chat"], true);
        assert_eq!(choice["uses"]["unverified"], unverified);
        assert_eq!(choice["uses"]["embedding"], unverified);
    }
    let available: bool = sqlx::query_scalar(
        "select available from cp_read.organization_model where space_id=$1 and use='chat'",
    )
    .bind(team.id)
    .fetch_one(&e.pool)
    .await
    .unwrap();
    assert!(available);
    sqlx::query("update organization_model_policy set embedding_locked_at=clock_timestamp() where organization_id=$1").bind(org.id).execute(&e.pool).await.unwrap();
    // Withdrawal remains withdrawal despite an organization complement.
    provider.response.lock().await.1 = json!({"data":[]});
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &refresh,
            Value::Null
        )
        .await
        .0,
        204
    );
    let advertised: bool = sqlx::query_scalar(
        "select advertised from model_offer where source_id=$1 and upstream_model_id='chat'",
    )
    .bind(source)
    .fetch_one(&e.pool)
    .await
    .unwrap();
    assert!(!advertised);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "DELETE",
            &source_path,
            Value::Null
        )
        .await
        .0,
        204
    );
    let view = inventory(&app, &identity, org.id).await;
    assert_eq!(view["sources"].as_array().unwrap().len(), 1);
    assert_eq!(view["sources"][0]["observation"]["source_id"], "file");
    assert_eq!(view["policy"]["embedding"], managed_key("embed"));
    let available: bool = sqlx::query_scalar(
        "select available from cp_read.organization_model where space_id=$1 and use='embedding'",
    )
    .bind(org.id)
    .fetch_one(&e.pool)
    .await
    .unwrap();
    assert!(!available);
    assert!(
        sqlx::query_scalar::<_, Option<Vec<u8>>>(
            "select encrypted_token from organization_model_catalog where source_id=$1"
        )
        .bind(source)
        .fetch_one(&e.pool)
        .await
        .unwrap()
        .is_none()
    );
}
