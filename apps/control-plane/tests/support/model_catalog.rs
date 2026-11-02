// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use control_plane::model_catalog::{
    self,
    config::ModelSource,
    initialization::{OrganizationModels, initialize},
};

struct Provider {
    url: String,
    response: Arc<Mutex<(u16, Value, usize)>>,
    inference: Arc<Mutex<Vec<(HeaderMap, Value)>>>,
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
            async move {
                completions.lock().await.push((headers, body));
                Json(json!({"id":"fixture", "object":"chat.completion", "created":0, "model":"chat",
                    "choices":[{"index":0,"message":{"role":"assistant","content":"managed simulated inference"},"finish_reason":"stop"}],
                    "usage":{"prompt_tokens":2,"completion_tokens":2,"total_tokens":4}}))
            }
        }));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        Self {
            url,
            response,
            inference,
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
    control_plane::authorization::write_platform(
        &mut e.pool.acquire().await.unwrap(),
        "operator",
        control_plane::roles::PlatformRole::PlatformAdmin,
        true,
    )
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
    let policy = json!({"expected_revision":1,"permitted":[key("b")],"reasoning_enabled":[],"default":key("b"),"fallback":null});
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
    let empty = json!({"expected_revision":1,"permitted":[],"reasoning_enabled":[],"default":null,"fallback":null});
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
    platform.organization_models[0] = declaration("Administered", &["a"]);
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
    let instance = Uuid::new_v4();
    let native = template_id(org.id, "control-plane", fred_rust_agent::AGENT_ID);
    control_plane::authorization::set_agent_default_on(
        &mut e.pool.acquire().await.unwrap(),
        org.id,
        native,
        true,
    )
    .await
    .unwrap();
    storage::create(
        &e.pool,
        &storage::NewAgentInstance {
            agent_instance_id: instance,
            space_id: team.id,
            template_id: native,
            source_runtime_id: "control-plane".into(),
            source_agent_id: fred_rust_agent::AGENT_ID.into(),
            logical_name: Some("managed-inference".into()),
            display_name: "Managed inference fixture".into(),
            description: None,
            enabled: true,
            created_by: "alice".into(),
            tuning: json!({"selected_capability_ids":[],"recommended_model":key("a"),
            "model_options":{"temperature":0.2,"top_p":0.8,"max_tokens":50}}),
        },
    )
    .await
    .unwrap();
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
    let delegated_path =
        format!("{runtime_path}?person=alice&run=run&agent={instance}&reasoning=true");
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
    let execute = json!({"agent_instance_id":instance,"input":"fixture question",
        "runtime_context":{"space_id":team.id,"reasoning":true}});
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
    let calls = provider.inference.lock().await;
    assert_eq!(calls.len(), 1);
    assert_eq!(
        calls[0].0["authorization"],
        "Bearer synthetic-inference-key"
    );
    assert_eq!(calls[0].1["model"], "chat");
    for (key, value) in decision["options"].as_object().unwrap() {
        assert_eq!(&calls[0].1[key], value);
    }
    drop(calls);
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
    assert_eq!(provider.inference.lock().await.len(), 1);
    // Direct demonstration cannot access the provider even though provisioning exists.
    let direct = json!({"agent_id":fred_rust_agent::AGENT_ID,"input":"question"});
    let response = send(app.clone(), direct).await.unwrap();
    assert_eq!(response.status(), 200);
    let _ = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
    assert_eq!(provider.inference.lock().await.len(), 1);
}
