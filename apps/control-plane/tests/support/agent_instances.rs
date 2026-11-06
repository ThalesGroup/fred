// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use axum::{
    Json, Router,
    body::{Body, to_bytes},
    http::{HeaderMap, Request},
    routing::{get, post},
};
use control_plane::{
    agent_instances as storage,
    agents::{PlatformConfig, RuntimeCatalogSource, template_id},
    api::{AppState, routes},
};
use serde_json::{Value, json};
use std::sync::Arc;
use support::request;
use tokio::sync::Mutex;
use tower::ServiceExt;

struct CatalogState {
    templates: Value,
    inventory: Value,
    status: u16,
    calls: usize,
    control_requests: Vec<(Option<String>, Value)>,
    gate: Option<Arc<support::Gate>>,
}
struct Catalog {
    base: String,
    state: Arc<Mutex<CatalogState>>,
    task: tokio::task::JoinHandle<()>,
}
impl Drop for Catalog {
    fn drop(&mut self) {
        self.task.abort();
    }
}
impl Catalog {
    async fn start() -> Self {
        let state = Arc::new(Mutex::new(CatalogState {
            templates: json!([definition()]),
            inventory: json!({"complete": true, "capabilities": [], "template_capabilities": []}),
            status: 200,
            calls: 0,
            control_requests: Vec::new(),
            gate: None,
        }));
        let shared = state.clone();
        let controls = state.clone();
        let inventory = state.clone();
        let app = Router::new().route(
            "/agents/templates",
            get(move || {
                let shared = shared.clone();
                async move {
                    let (status, templates, gate) = {
                        let mut s = shared.lock().await;
                        s.calls += 1;
                        (s.status, s.templates.clone(), s.gate.take())
                    };
                    if let Some(gate) = gate {
                        gate.entered.notify_one();
                        gate.release.notified().await;
                    }
                    (
                        axum::http::StatusCode::from_u16(status).unwrap(),
                        Json(templates),
                    )
                }
            }),
        );
        let app = app.route(
            "/agents/capabilities",
            get(move || {
                let inventory = inventory.clone();
                async move {
                    let state = inventory.lock().await;
                    (
                        axum::http::StatusCode::from_u16(state.status).unwrap(),
                        Json(state.inventory.clone()),
                    )
                }
            }),
        );
        let app = app.route(
            "/agents/capabilities/chat-controls",
            post(move |headers: HeaderMap, Json(body): Json<Value>| {
                let controls = controls.clone();
                async move {
                    controls.lock().await.control_requests.push((
                        headers
                            .get("authorization")
                            .map(|v| v.to_str().unwrap().to_owned()),
                        body,
                    ));
                    Json(json!({"results": [{"capability_id": "tool", "controls": [
                        {"widget": "custom_picker", "params": {"opaque": [42]}}
                    ]}]}))
                }
            }),
        );
        let export_state = state.clone();
        let app=app.route("/agents/templates/custom/export-tuning", post(move |Json(body): Json<Value>| {
            let shared=export_state.clone();
            async move {
                let gate=shared.lock().await.gate.take();
                if let Some(gate)=gate {gate.entered.notify_one(); gate.release.notified().await;}
                Json(json!({"values":body["values"]}))
            }
        })).route("/agents/capabilities/tool/export-config", post(|Json(body): Json<Value>| async move {
            Json(json!({"schema_version":"1", "config":{"endpoint":body["config"]["config"]["endpoint"]}, "files":{}}))
        })).route("/agents/capabilities/tool/copy-config", post(|Json(body): Json<Value>| async move {
            assert!(body.get("source_space_id").is_none());
            assert_eq!(body["asset_files"],json!({}));
            Json(json!({"schema_version":"1","config":body["config"]["config"],"notices":[]}))
        })).route("/agents/capabilities/tool/validate-config", post(|axum::Form(form): axum::Form<std::collections::BTreeMap<String,String>>| async move {
            let config:Value=serde_json::from_str(&form["config"]).unwrap();
            Json(json!({"schema_version":"1","config":config}))
        }));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        Self { base, state, task }
    }
    fn config(&self) -> PlatformConfig {
        PlatformConfig {
            runtime_catalog_sources: vec![RuntimeCatalogSource {
                runtime_id: "fixture".into(),
                base_url: self.base.clone(),
                public_base_url: Some("/fixture-pod".into()),
                enabled: true,
            }],
            ..Default::default()
        }
    }
}
fn definition() -> Value {
    json!({"template_agent_id":"custom", "title":"Custom", "description":"Assistant", "kind":"react",
        "description_by_lang":{"fr":"Assistant français"}, "supports_capabilities":true, "default_capability_ids":[],
        "available_capabilities":[{"id":"tool", "kind":"tool", "config_fields":[{"key":"endpoint","type":"url"}]}],
        "default_tuning":{"role":"Original", "description":"Original description", "usage_statement":"Original usage",
            "tags":["custom"], "unknown":{"nested":[null,{},[]]}, "values":{"prompts.system":"Default prompt"},
            "fields":[{"key":"prompts.system","type":"prompt","required":true,"default_by_lang":{"fr":"Défaut"}},
                {"key":"count","type":"integer","min":1,"max":4}, {"key":"ratio","type":"number","min":0,"max":1},
                {"key":"flag","type":"boolean"}, {"key":"choice","type":"select","enum":["a","b"]},
                {"key":"code","type":"string","pattern":"[A-Z]+"}, {"key":"items","type":"array","item_type":"integer"},
                {"key":"object","type":"object"}]}})
}
async fn app(e: &Env, identity: &support::IdentityServer, catalog: &Catalog) -> Router {
    routes(AppState {
        pool: e.pool.clone(),
        agent_catalog: catalog.config(),
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    })
}
async fn enable(e: &Env, org: Uuid, key: &str, on: bool) -> Uuid {
    let id = template_id(org, "fixture", key);
    control_plane::authorization::set_agent_default_on(
        &mut e.pool.acquire().await.unwrap(),
        org,
        id,
        on,
    )
    .await
    .unwrap();
    id
}
/// Offers are denied by default; seed one observed offer enabled for `org`.
async fn enable_capability(e: &Env, org: Uuid, capability_id: &str) {
    for statement in [
        "insert into runtime_catalog (runtime_id, reachable) values ('fixture', true) on conflict do nothing",
        "insert into runtime_capability (runtime_id, capability_id, version, descriptor, advertised)
         values ('fixture', $2, '1', '{}', true)",
        "insert into organization_capability (organization_id, runtime_id, capability_id, enabled_by)
         values ($1, 'fixture', $2, 'fixture')",
    ] {
        sqlx::query(statement)
            .bind(org)
            .bind(capability_id)
            .execute(&e.pool)
            .await
            .unwrap();
    }
}
fn collection(space: Uuid) -> String {
    format!("/spaces/{space}/agent-instances")
}
fn item(space: Uuid, instance: &Value) -> String {
    format!(
        "{}/{}",
        collection(space),
        instance["agent_instance_id"].as_str().unwrap()
    )
}
fn creation(template: Uuid, name: &str) -> Value {
    json!({"template_id":template,"logical_name":Uuid::new_v4().to_string(),"display_name":name,"usage_statement":"Use me"})
}
async fn saved(e: &Env, space: Uuid, instance: &Value) -> storage::AgentInstance {
    storage::get_for_space(
        &e.pool,
        space,
        Uuid::parse_str(instance["agent_instance_id"].as_str().unwrap()).unwrap(),
    )
    .await
    .unwrap()
    .unwrap()
}
async fn create(
    app: &Router,
    identity: &support::IdentityServer,
    space: Uuid,
    body: Value,
) -> Value {
    let (status, result) = request(
        app,
        identity,
        Some("alice"),
        "POST",
        &collection(space),
        body,
    )
    .await;
    assert_eq!(status, 201, "{result}");
    result
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn instances_round_trip_validation_and_saved_snapshot() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    enable_capability(&e, org.id, "tool").await;
    let (status, templates) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("/spaces/{}/agent-templates", team.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{templates}");
    assert_eq!(templates.as_array().unwrap().len(), 1);
    assert_eq!(
        templates[0]["default_tuning_fields"],
        definition()["default_tuning"]["fields"]
    );
    assert_eq!(
        templates[0]["description_by_lang"]["fr"],
        "Assistant français"
    );
    assert_eq!(
        templates[0]["available_capabilities"],
        definition()["available_capabilities"]
    );
    let mut body = creation(template, "  My Agent  ");
    body["tuning_field_values"] = json!({"prompts.system":"Saved prompt", "count":2,"ratio":0.5,"flag":true,"choice":"a","code":"ABC","items":[1,2],"object":{"a":1,"b":false},"unknown":"ignored"});
    let first = create(&app, &identity, team.id, body.clone()).await;
    assert_eq!(first["display_name"], "My Agent");
    assert_eq!(first["role"], "My Agent");
    assert!(first["tuning_field_values"].get("unknown").is_none());
    assert_eq!(
        saved(&e, team.id, &first).await.tuning.0["unknown"],
        definition()["default_tuning"]["unknown"]
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &item(team.id, &first),
            Value::Null
        )
        .await,
        (200, first.clone())
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &collection(team.id),
            Value::Null
        )
        .await,
        (200, json!({"items":[first],"next_cursor":null}))
    );
    body["display_name"] = json!("my AGENT");
    let conflict = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &collection(team.id),
        body,
    )
    .await;
    assert_eq!(conflict.0, 409);
    assert_eq!(conflict.1["code"], "agent_name_conflict");
    let second = create(&app, &identity, team.id, creation(template, "Second")).await;
    assert_eq!(
        second["tuning_field_values"]["prompts.system"],
        "Default prompt"
    );
    for value in [Value::Null, json!({})] {
        let mut body = creation(template, &format!("default-{value}"));
        body["tuning_field_values"] = value;
        let instance = create(&app, &identity, team.id, body).await;
        assert_eq!(
            instance["tuning_field_values"],
            second["tuning_field_values"]
        );
    }
    for values in [
        json!({"count":0}),
        json!({"count":5}),
        json!({"count":1.5}),
        json!({"ratio":2}),
        json!({"flag":1}),
        json!({"choice":"c"}),
        json!({"code":"abc"}),
        json!({"items":["1"]}),
        json!({"object":{"x":[]}}),
        json!({"unknown":null}),
        json!({"unknown":[null]}),
        json!({"unknown":{"x":{}}}),
        json!({"prompts.system":"<tools>bad</tools>"}),
    ] {
        let response = request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &item(team.id, &first),
            json!({"tuning_field_values":values}),
        )
        .await;
        assert_eq!(response.0, 422, "{values}: {response:?}");
    }
    // Display names are unique even when the caller supplies a different logical reference.
    let conflict = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &collection(team.id),
        creation(template, "My Agent"),
    )
    .await;
    assert_eq!(conflict.0, 409);
    assert_eq!(conflict.1["code"], "agent_name_conflict");
    let before = saved(&e, team.id, &first).await;
    for patch in [
        json!({}),
        json!({"display_name":null,"description":null,"status":null}),
        json!({"display_name":" My Agent "}),
    ] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PATCH",
                &item(team.id, &first),
                patch
            )
            .await,
            (200, first.clone())
        );
    }
    let after = saved(&e, team.id, &first).await;
    assert_eq!(after.updated_at, before.updated_at);
    assert_eq!(after.configuration_revision, before.configuration_revision);
    assert_eq!(after.updated_by, before.updated_by);
    catalog.state.lock().await.status = 503;
    let calls = catalog.state.lock().await.calls;
    let renamed = request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &item(team.id, &first),
        json!({"display_name":"Renamed","status":"disabled"}),
    )
    .await;
    assert_eq!(renamed.0, 200);
    assert_eq!(renamed.1["role"], first["role"]);
    assert_eq!(
        renamed.1["tuning_field_values"],
        first["tuning_field_values"]
    );
    assert_eq!(renamed.1["status"], "disabled");
    assert_eq!(renamed.1["updated_by"], "alice");
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &item(team.id, &first),
            Value::Null
        )
        .await,
        renamed
    );
    let listed = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &collection(team.id),
        Value::Null,
    )
    .await;
    assert_eq!(listed.0, 200);
    assert!(listed.1["items"].as_array().unwrap().contains(&renamed.1));
    assert_eq!(catalog.state.lock().await.calls, calls);
    // Tuning alone falls back; capabilities always require the current catalog.
    let replaced = request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &item(team.id, &first),
        json!({"tuning_field_values":{"prompts.system":"Replacement"}}),
    )
    .await;
    assert_eq!(replaced.0, 200);
    assert_eq!(
        replaced.1["tuning_field_values"],
        json!({"prompts.system":"Replacement"})
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &item(team.id, &first),
            json!({"capability_ids":[]})
        )
        .await
        .0,
        503
    );
    for status in [401, 403] {
        catalog.state.lock().await.status = status;
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PATCH",
                &item(team.id, &first),
                json!({"tuning_field_values":null})
            )
            .await
            .0,
            403
        );
        assert_eq!(
            saved(&e, team.id, &first).await.tuning.0["values"],
            replaced.1["tuning_field_values"]
        );
    }
    catalog.state.lock().await.status = 200;
    catalog.state.lock().await.templates[0]["default_tuning"]["fields"][0]["default_by_lang"]["fr"] =
        json!("Nouveau");
    catalog.state.lock().await.templates[0]["default_tuning"]["unknown"] =
        json!("must not replace saved snapshot");
    for values in [Value::Null, json!({})] {
        let edited = request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &item(team.id, &first),
            json!({"tuning_field_values":values,"status":"enabled"}),
        )
        .await;
        assert_eq!(edited.0, 200);
        assert_eq!(edited.1["tuning_field_values"], json!({}));
        assert_eq!(edited.1["status"], "enabled");
    }
    let stored = saved(&e, team.id, &first).await;
    assert_eq!(
        stored.tuning.0["fields"][0]["default_by_lang"]["fr"],
        "Nouveau"
    );
    assert_eq!(
        stored.tuning.0["unknown"],
        definition()["default_tuning"]["unknown"]
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "DELETE",
            &item(team.id, &first),
            Value::Null
        )
        .await,
        (204, Value::Null)
    );
    for method in ["GET", "DELETE"] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                method,
                &item(team.id, &first),
                Value::Null
            )
            .await
            .0,
            404
        );
    }
    assert!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &collection(team.id),
            Value::Null
        )
        .await
        .1["items"]
            .as_array()
            .unwrap()
            .iter()
            .all(|v| v["agent_instance_id"] != first["agent_instance_id"])
    );
    create(&app, &identity, team.id, creation(template, "Renamed")).await;
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn instances_capabilities_and_profiles_fail_explicitly() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    let instance = create(&app, &identity, team.id, creation(template, "Existing")).await;
    // Metadata edits preserve opaque, not-yet-connected saved settings.
    sqlx::query("update agent_instance set tuning = tuning || $1 where space_id=$2")
        .bind(sqlx::types::Json(json!({"recommended_chat_profile_id":"saved-profile","capability_config":{"tool":{"version":2,"config":{"nested":[1,null]}}}})))
        .bind(team.id).execute(&e.pool).await.unwrap();
    let before = saved(&e, team.id, &instance).await.tuning.0;
    catalog.state.lock().await.status = 503;
    let metadata = request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &item(team.id, &instance),
        json!({"description":"Metadata only"}),
    )
    .await;
    assert_eq!(metadata.0, 200);
    assert_eq!(metadata.1["recommended_chat_profile_id"], "saved-profile");
    assert_eq!(
        saved(&e, team.id, &instance).await.tuning.0["capability_config"],
        before["capability_config"]
    );
    let cleared = request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &item(team.id, &instance),
        json!({"recommended_chat_profile_id":null}),
    )
    .await;
    assert_eq!(cleared.0, 200);
    assert!(cleared.1["recommended_chat_profile_id"].is_null());
    for value in [Value::Null, json!({})] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PATCH",
                &item(team.id, &instance),
                json!({"capability_config_values":value})
            )
            .await
            .0,
            503
        );
    }
    catalog.state.lock().await.status = 200;
    for value in [Value::Null, json!({})] {
        let cleared = request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &item(team.id, &instance),
            json!({"capability_config_values":value}),
        )
        .await;
        assert_eq!(cleared.0, 200);
        assert_eq!(cleared.1["capability_config"], json!({}));
    }
    for visibility in ["public", "team_instantiable"] {
        catalog.state.lock().await.templates[0][visibility] = json!(false);
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PATCH",
                &item(team.id, &instance),
                json!({"tuning_field_values":{}})
            )
            .await
            .0,
            404
        );
        catalog.state.lock().await.templates[0][visibility] = json!(true);
    }
    for patch in [
        json!({"capability_ids":["tool"]}),
        json!({"recommended_chat_profile_id":"profile"}),
    ] {
        let code = if patch.get("capability_ids").is_some() {
            "agent_capability_unavailable"
        } else {
            "legacy_model_reselection_required"
        };
        let mut body = creation(template, "Rejected");
        body.as_object_mut()
            .unwrap()
            .extend(patch.as_object().unwrap().clone());
        for (method, path, body) in [
            ("POST", collection(team.id), body),
            ("PATCH", item(team.id, &instance), patch),
        ] {
            let result = request(&app, &identity, Some("alice"), method, &path, body).await;
            assert_eq!(result.0, 422, "{result:?}");
            assert_eq!(result.1["code"], code);
        }
    }
    for (selectable, defaults) in [
        (true, json!(["tool"])),
        (false, json!(["tool"])),
        (false, json!(["app__hidden"])),
    ] {
        catalog.state.lock().await.templates[0]["supports_capabilities"] = json!(selectable);
        catalog.state.lock().await.templates[0]["default_capability_ids"] = defaults;
        for selection in [Value::Null, json!([])] {
            let expected = if selectable && selection == json!([]) {
                200
            } else {
                422
            };
            let result = request(
                &app,
                &identity,
                Some("alice"),
                "PATCH",
                &item(team.id, &instance),
                json!({"capability_ids":selection}),
            )
            .await;
            assert_eq!(result.0, expected, "{selectable} {selection}: {result:?}");
            let mut body = creation(template, &format!("Selection-{selectable}-{selection}"));
            body["capability_ids"] = selection;
            let result = request(
                &app,
                &identity,
                Some("alice"),
                "POST",
                &collection(team.id),
                body,
            )
            .await;
            assert_eq!(
                result.0,
                if expected == 200 { 201 } else { 422 },
                "{result:?}"
            );
        }
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn instances_discovery_concurrency_rechecks_and_isolation() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    support::member_organization(&e.pool, "Outside", "outsider")
        .await
        .unwrap();
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = Arc::new(support::IdentityServer::start().await);
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    let instance = create(&app, &identity, team.id, creation(template, "Existing")).await;
    for (actor, expected) in [
        (None, 401),
        (Some("stranger"), 403),
        (Some("outsider"), 404),
    ] {
        for (method, path, body) in [
            ("GET", collection(team.id), Value::Null),
            ("GET", item(team.id, &instance), Value::Null),
            (
                "POST",
                collection(team.id),
                creation(template, "Unauthorized"),
            ),
            ("PATCH", item(team.id, &instance), json!({})),
            ("DELETE", item(team.id, &instance), Value::Null),
        ] {
            let (status, body) = request(&app, &identity, actor, method, &path, body).await;
            assert_eq!(status, expected, "{actor:?} {method}: {body}");
            if actor == Some("stranger") {
                assert_eq!(body["detail"], "user_not_admitted");
            }
        }
    }
    grant(&e, org.id, Role::Member, "viewer").await;
    grant(&e, team.id, Role::Member, "viewer").await;
    assert_eq!(
        request(
            &app,
            &identity,
            Some("viewer"),
            "GET",
            &item(team.id, &instance),
            Value::Null
        )
        .await
        .0,
        200
    );
    for method in ["PATCH", "DELETE"] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("viewer"),
                method,
                &item(team.id, &instance),
                json!({})
            )
            .await
            .0,
            403
        );
    }
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    let personal_instance =
        create(&app, &identity, personal.id, creation(template, "Existing")).await;
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &item(personal.id, &instance),
            Value::Null
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
            "GET",
            &collection(personal.id),
            Value::Null
        )
        .await,
        (200, json!({"items":[personal_instance],"next_cursor":null}))
    );
    let other = support::member_organization(&e.pool, "Other", "bob")
        .await
        .unwrap();
    let other_team = spaces::create_space(
        &e.pool,
        "bob",
        SpaceKind::Team,
        other.id,
        "Other team".into(),
        "bob",
    )
    .await
    .unwrap();
    spaces::grant(
        &e.pool,
        &e.subjects(),
        "bob",
        other_team.id,
        Role::Editor,
        "bob",
    )
    .await
    .unwrap();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "GET",
            &item(other_team.id, &instance),
            Value::Null
        )
        .await
        .0,
        404
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "POST",
            &collection(other_team.id),
            creation(template, "Foreign template")
        )
        .await
        .0,
        404
    );
    // A delayed discovery must apply omissions to the current, locked row.
    let gate = Arc::new(support::Gate::default());
    catalog.state.lock().await.gate = Some(gate.clone());
    let pending = {
        let app = app.clone();
        let identity = identity.clone();
        let path = item(team.id, &instance);
        tokio::spawn(async move {
            request(
                &app,
                &identity,
                Some("alice"),
                "PATCH",
                &path,
                json!({"tuning_field_values":{"count":3}}),
            )
            .await
        })
    };
    tokio::time::timeout(Duration::from_secs(5), gate.entered.notified())
        .await
        .unwrap();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &item(team.id, &instance),
            json!({"display_name":"Concurrent","role":"Concurrent role"})
        )
        .await
        .0,
        200
    );
    gate.release.notify_one();
    let result = pending.await.unwrap();
    assert_eq!(result.0, 200);
    assert_eq!(result.1["display_name"], "Concurrent");
    assert_eq!(result.1["role"], "Concurrent role");
    // Revoke template use while POST and PATCH are discovering, never commit either.
    for method in ["POST", "PATCH"] {
        enable(&e, org.id, "custom", true).await;
        let gate = Arc::new(support::Gate::default());
        catalog.state.lock().await.gate = Some(gate.clone());
        let pending = {
            let app = app.clone();
            let identity = identity.clone();
            let path = if method == "POST" {
                collection(team.id)
            } else {
                item(team.id, &instance)
            };
            let body = if method == "POST" {
                creation(template, "Race")
            } else {
                json!({"tuning_field_values":{"count":4}})
            };
            tokio::spawn(async move {
                request(&app, &identity, Some("alice"), method, &path, body).await
            })
        };
        tokio::time::timeout(Duration::from_secs(5), gate.entered.notified())
            .await
            .unwrap();
        enable(&e, org.id, "custom", false).await;
        gate.release.notify_one();
        assert_eq!(pending.await.unwrap().0, 404);
    }
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from agent_instance where space_id=$1")
            .bind(team.id)
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        1
    );
    assert_eq!(
        saved(&e, team.id, &instance).await.tuning.0["values"],
        json!({"count":3})
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &collection(team.id),
            Value::Null
        )
        .await,
        (200, json!({"items":[],"next_cursor":null}))
    );
    for method in ["GET", "PATCH"] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                method,
                &item(team.id, &instance),
                json!({})
            )
            .await
            .0,
            404
        );
    }
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "DELETE",
            &item(team.id, &instance),
            Value::Null
        )
        .await
        .0,
        204
    );
}

// Proves: I24
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn instances_retention_and_exact_space_purge() {
    use control_plane::lifecycle::{Lifecycle, Status, cleanup, store};
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = Arc::new(support::IdentityServer::start().await);
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    let instance = create(&app, &identity, team.id, creation(template, "Retained")).await;
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    let other = create(
        &app,
        &identity,
        personal.id,
        creation(template, "Unaffected"),
    )
    .await;
    let mut lifecycle = Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.catalog.space_policies.purge.default.retention =
        serde_yaml_ng::from_str("P7D").unwrap();
    let gate = Arc::new(support::Gate::default());
    catalog.state.lock().await.gate = Some(gate.clone());
    let pending = {
        let app = app.clone();
        let identity = identity.clone();
        tokio::spawn(async move {
            request(
                &app,
                &identity,
                Some("alice"),
                "POST",
                &collection(team.id),
                creation(template, "During retirement"),
            )
            .await
        })
    };
    tokio::time::timeout(Duration::from_secs(5), gate.entered.notified())
        .await
        .unwrap();
    let receipt = lifecycle
        .accept(&e.pool, "root", team.id, false)
        .await
        .unwrap();
    gate.release.notify_one();
    assert_eq!(pending.await.unwrap().0, 409);
    cleanup::batch(&e.pool, receipt.id, &Default::default(), None)
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from agent_instance where space_id=$1")
            .bind(team.id)
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        1
    );
    for method in ["GET", "PATCH", "DELETE"] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                method,
                &item(team.id, &instance),
                json!({})
            )
            .await
            .0,
            409
        );
    }
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &collection(team.id),
            Value::Null
        )
        .await
        .0,
        409
    );
    sqlx::query("update deletion set requested_at=now(),due_at=now() where id=$1")
        .bind(receipt.id)
        .execute(&e.pool)
        .await
        .unwrap();
    for _ in 0..100 {
        cleanup::batch(&e.pool, receipt.id, &Default::default(), None)
            .await
            .unwrap();
        if store::status(&e.pool, "root", receipt.id)
            .await
            .unwrap()
            .status
            == Status::Completed
        {
            break;
        }
    }
    assert_eq!(
        store::status(&e.pool, "root", receipt.id)
            .await
            .unwrap()
            .status,
        Status::Completed
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from agent_instance where space_id=$1")
            .bind(team.id)
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );
    assert_eq!(
        saved(&e, personal.id, &other).await.display_name,
        "Unaffected"
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn instances_store_tuning_opaquely() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let org = org.id;
    let mut conn = e.pool.acquire().await.unwrap();
    for (n,tuning) in [Value::Null,json!({"unknown":{"nested":[null,{},[]]},"selected_capability_ids":null,"capability_config":{"tool":{"schema_version":2,"config":{"nested":{"list":[1,false]}}}}}),json!({"selected_capability_ids":[]})].into_iter().enumerate() {
        let record=storage::create(&mut *conn,&storage::NewAgentInstance{agent_instance_id:Uuid::new_v4(),space_id:org,template_id:Uuid::new_v4(),source_runtime_id:"fixture".into(),source_agent_id:"opaque".into(),logical_name:Some(format!("opaque-{n}")),display_name:format!("  Opaque {n}  "),description:None,enabled:false,created_by:"fixture-author".into(),tuning:tuning.clone()}).await.unwrap();
        assert_eq!(record.tuning.0,tuning);assert_eq!(record.display_name,format!("Opaque {n}"));
        assert_eq!(storage::get_for_space(&mut *conn,org,record.agent_instance_id).await.unwrap().unwrap().tuning.0,tuning);
    }
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from agent_instance where space_id=$1")
            .bind(org)
            .fetch_one(&mut *conn)
            .await
            .unwrap(),
        3
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn instances_space_revocation_during_discovery_preserves_configuration() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = Arc::new(support::IdentityServer::start().await);
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    let instance = create(&app, &identity, team.id, creation(template, "Existing")).await;
    for method in ["POST", "PATCH"] {
        grant(&e, team.id, Role::Editor, "alice").await;
        let gate = Arc::new(support::Gate::default());
        catalog.state.lock().await.gate = Some(gate.clone());
        let pending = {
            let app = app.clone();
            let identity = identity.clone();
            let path = if method == "POST" {
                collection(team.id)
            } else {
                item(team.id, &instance)
            };
            let body = if method == "POST" {
                creation(template, "Must not exist")
            } else {
                json!({"tuning_field_values":{"count":4}})
            };
            tokio::spawn(async move {
                request(&app, &identity, Some("alice"), method, &path, body).await
            })
        };
        tokio::time::timeout(Duration::from_secs(5), gate.entered.notified())
            .await
            .unwrap();
        spaces::revoke(&e.pool, "alice", team.id, Role::Editor, "alice")
            .await
            .unwrap();
        gate.release.notify_one();
        assert_eq!(pending.await.unwrap().0, 403);
    }
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from agent_instance where space_id=$1")
            .bind(team.id)
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        1
    );
    assert_eq!(
        saved(&e, team.id, &instance).await.tuning.0["values"],
        json!({"prompts.system":"Default prompt"})
    );
    // Same-organization admission does not confer Read on a team.
    grant(&e, org.id, Role::Member, "no-team").await;
    assert_eq!(
        request(
            &app,
            &identity,
            Some("no-team"),
            "GET",
            &collection(team.id),
            Value::Null
        )
        .await
        .0,
        403
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("no-team"),
            "GET",
            &item(team.id, &instance),
            Value::Null
        )
        .await
        .0,
        403
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn preparation_uses_live_runtime_hitl_support_and_defaults_to_false() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    let instance = create(&app, &identity, team.id, creation(template, "HITL")).await;
    let path = format!("{}/prepare-execution", item(team.id, &instance));
    for advertised in [None, Some(true), Some(false)] {
        let mut template = definition();
        if let Some(value) = advertised {
            template["supports_hitl"] = json!(value);
        }
        catalog.state.lock().await.templates = json!([template]);
        let (status, prepared) =
            request(&app, &identity, Some("alice"), "POST", &path, Value::Null).await;
        assert_eq!(status, 200, "{prepared}");
        assert_eq!(prepared["supports_hitl"], advertised.unwrap_or(false));
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn wiki_publication_checks_owner_session_and_publishes_once() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    enable_capability(&e, org.id, "team_wiki").await;
    let instance = create(&app, &identity, team.id, creation(template, "Wiki")).await;
    let agent = Uuid::parse_str(instance["agent_instance_id"].as_str().unwrap()).unwrap();
    let session = Uuid::new_v4();
    let proposal = Uuid::new_v4();
    sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,'alice',$2,$3,$4,'fixture','Wiki',1)")
        .bind(session).bind(team.id).bind(agent).bind(template).execute(&e.pool).await.unwrap();
    sqlx::query("insert into wiki_revision(revision_id,space_id,content_md,status,author_user_id,author_kind,agent_instance_id,session_id,proposed_title,expires_at) values($1,$2,'Approved text','proposed','alice','agent',$3,$4,'Isolated approval',clock_timestamp()+interval '1 day')")
        .bind(proposal).bind(team.id).bind(agent).bind(session).execute(&e.pool).await.unwrap();
    let path = format!(
        "/spaces/{}/wiki/proposals/{proposal}/publish?session_id={session}",
        team.id
    );
    for actor in [None, Some("bob")] {
        let (status, _) = request(&app, &identity, actor, "POST", &path, Value::Null).await;
        assert!(matches!(status, 401 | 403 | 404));
    }
    let wrong_session = path.replace(&session.to_string(), &Uuid::new_v4().to_string());
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &wrong_session,
            Value::Null
        )
        .await
        .0,
        404
    );
    let count: i64 = sqlx::query_scalar("select count(*) from wiki_page where space_id=$1")
        .bind(team.id)
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(count, 0);
    let (a, b) = tokio::join!(
        request(&app, &identity, Some("alice"), "POST", &path, Value::Null),
        request(&app, &identity, Some("alice"), "POST", &path, Value::Null),
    );
    let mut statuses = [a.0, b.0];
    statuses.sort();
    assert_eq!(statuses, [200, 404], "{a:?} {b:?}");
    assert_eq!(
        request(&app, &identity, Some("alice"), "POST", &path, Value::Null)
            .await
            .0,
        404
    );
    let count: i64 = sqlx::query_scalar(
        "select count(*) from wiki_page where space_id=$1 and current_revision_id=$2",
    )
    .bind(team.id)
    .bind(proposal)
    .fetch_one(&e.pool)
    .await
    .unwrap();
    assert_eq!(count, 1);
    let status: String =
        sqlx::query_scalar("select status from wiki_revision where revision_id=$1")
            .bind(proposal)
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(status, "published");
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn preparation_combines_pod_controls_and_reasoning_after_capability_governance() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    sqlx::query("insert into runtime_catalog (runtime_id, reachable) values ('fixture', true)")
        .execute(&e.pool)
        .await
        .unwrap();
    sqlx::query("insert into runtime_capability (runtime_id, capability_id, version, descriptor, advertised)
        values ('fixture', 'tool', '1', '{}', true)")
        .execute(&e.pool).await.unwrap();
    sqlx::query("insert into organization_capability (organization_id, runtime_id, capability_id, enabled_by)
        values ($1, 'fixture', 'tool', 'alice')")
        .bind(org.id).execute(&e.pool).await.unwrap();
    let instance = create(&app, &identity, team.id, creation(template, "Controls")).await;
    let envelope = json!({"schema_version": "old-version", "config": {"opaque": [42]}});
    sqlx::query("update agent_instance set tuning = tuning || $1 where agent_instance_id = $2")
        .bind(sqlx::types::Json(
            json!({"selected_capability_ids": ["tool"], "capability_config": {"tool": envelope}}),
        ))
        .bind(Uuid::parse_str(instance["agent_instance_id"].as_str().unwrap()).unwrap())
        .execute(&e.pool)
        .await
        .unwrap();
    sqlx::query(
        r#"insert into model_source (source_id, configuration, state, snapshot_source_revision)
        values ('models', '{"source_id":"models","revision":1,"enabled":true}', 'ok', 1)"#,
    )
    .execute(&e.pool)
    .await
    .unwrap();
    sqlx::query(r#"insert into model_offer (source_id, upstream_model_id, metadata, first_seen_at, last_seen_at, advertised)
        values ('models', 'reasoner', '{"chat":true,"reasoning":true}', now(), now(), true)"#)
        .execute(&e.pool).await.unwrap();
    sqlx::query(
        "insert into organization_model_policy (organization_id, revision, created_by, updated_by)
        values ($1, 1, 'alice', 'alice')",
    )
    .bind(org.id)
    .execute(&e.pool)
    .await
    .unwrap();
    sqlx::query(
        "insert into organization_model_source (organization_id, source_id) values ($1, 'models')",
    )
    .bind(org.id)
    .execute(&e.pool)
    .await
    .unwrap();
    sqlx::query("insert into organization_model_permission (organization_id, source_id, upstream_model_id, reasoning_enabled)
        values ($1, 'models', 'reasoner', true)")
        .bind(org.id).execute(&e.pool).await.unwrap();
    let path = format!("{}/prepare-execution", item(team.id, &instance));
    let authorization = format!("Bearer {}", identity.token("alice"));
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(&path)
                .header("authorization", &authorization)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status().as_u16();
    let prep: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), 1024 * 1024).await.unwrap())
            .unwrap();
    assert_eq!(status, 200, "{prep}");
    assert_eq!(
        prep["chat_controls"],
        json!([
            {"capability_id": "tool", "widget": "custom_picker", "params": {"opaque": [42]}},
            {"capability_id": "platform", "widget": "reasoning_toggle", "params": {"default": false}}
        ])
    );
    assert_eq!(prep["execute_url"], "/fixture-pod/agents/execute");
    {
        let state = catalog.state.lock().await;
        assert_eq!(state.control_requests.len(), 1);
        assert_eq!(state.control_requests[0].0, Some(authorization));
        assert_eq!(
            state.control_requests[0].1,
            json!({"items": [
                {"capability_id": "tool", "config_envelope": envelope}
            ]})
        );
    }
    sqlx::query("delete from organization_capability where organization_id = $1")
        .bind(org.id)
        .execute(&e.pool)
        .await
        .unwrap();
    let (status, _) = request(&app, &identity, Some("alice"), "POST", &path, Value::Null).await;
    assert_eq!(status, 422);
    assert_eq!(catalog.state.lock().await.control_requests.len(), 1);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn session_creation_rechecks_agent_after_concurrent_deletion() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    let instance = create(&app, &identity, team.id, creation(template, "Concurrent")).await;
    let agent: Uuid = serde_json::from_value(instance["agent_instance_id"].clone()).unwrap();
    let mut deleting = e.pool.begin().await.unwrap();
    let pid: i32 = sqlx::query_scalar("select pg_backend_pid()")
        .fetch_one(&mut *deleting)
        .await
        .unwrap();
    sqlx::query("delete from agent_instance where agent_instance_id=$1")
        .bind(agent)
        .execute(&mut *deleting)
        .await
        .unwrap();
    let sid = Uuid::new_v4();
    let path = format!("/spaces/{}/sessions", team.id);
    let creation = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &path,
        json!({"session_id":sid,"agent_instance_id":agent,"agent_configuration_revision":1}),
    );
    let release = async {
        // Wait for the application's explicit source lock, not the trigger's late lock.
        tokio::time::timeout(std::time::Duration::from_secs(3), async {
            loop {
                let waiting: bool = sqlx::query_scalar(
                    "select exists(select 1 from pg_stat_activity where datname=current_database()
                     and $1=any(pg_blocking_pids(pid)) and query like 'select agent_instance_id%for share')")
                    .bind(pid).fetch_one(&e.pool).await.unwrap();
                if waiting { break; }
                tokio::time::sleep(std::time::Duration::from_millis(10)).await;
            }
        }).await.unwrap();
        deleting.commit().await.unwrap();
    };
    let ((status, body), ()) = tokio::join!(creation, release);
    assert_eq!(status, 404, "{body}");
    assert_eq!(body["code"], "not_found");
    assert!(
        !sqlx::query_scalar::<_, bool>(
            "select exists(select 1 from session_metadata where session_id=$1)"
        )
        .bind(sid)
        .fetch_one(&e.pool)
        .await
        .unwrap()
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn conversations_pin_configuration_and_keep_history_after_agent_edits() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    let instance = create(&app, &identity, team.id, creation(template, "Revision")).await;
    let base = item(team.id, &instance);
    let sessions = format!("/spaces/{}/sessions", team.id);
    let sid = Uuid::new_v4();
    let session = format!("{sessions}/{sid}");
    let creation = |id, revision| {
        json!({
            "session_id": id, "agent_instance_id": instance["agent_instance_id"],
            "agent_configuration_revision": revision
        })
    };
    let prepared = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!("{base}/prepare-execution"),
        Value::Null,
    )
    .await;
    assert_eq!(prepared.0, 200, "{prepared:?}");
    assert_eq!(prepared.1["agent_configuration_revision"], 1);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &sessions,
            creation(sid, 1)
        )
        .await
        .0,
        201
    );
    let resolve = format!("{base}/runtime?conversation={sid}");
    let admitted = request(&app, &identity, Some("alice"), "GET", &resolve, Value::Null).await;
    assert_eq!(admitted.0, 200, "{admitted:?}");
    assert_eq!(admitted.1["agent"]["configuration_revision"], 1);

    // A no-op keeps the association valid, including normalized metadata.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &base,
            json!({"display_name":" Revision "})
        )
        .await
        .0,
        200
    );
    assert_eq!(
        saved(&e, team.id, &instance).await.configuration_revision,
        1
    );
    assert_eq!(
        request(&app, &identity, Some("alice"), "GET", &resolve, Value::Null)
            .await
            .0,
        200
    );

    // The preparation predates the persisted edit; admission must reread both rows.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &base,
            json!({"display_name":"Renamed"})
        )
        .await
        .0,
        200
    );
    assert_eq!(
        saved(&e, team.id, &instance).await.configuration_revision,
        2
    );
    for (method, path, body) in [
        ("GET", resolve, Value::Null),
        (
            "POST",
            format!("{base}/prepare-execution?session_id={sid}"),
            Value::Null,
        ),
        ("POST", sessions.clone(), creation(Uuid::new_v4(), 1)),
        ("POST", sessions.clone(), creation(sid, 1)),
        ("POST", sessions.clone(), creation(sid, 2)),
    ] {
        let refused = request(&app, &identity, Some("alice"), method, &path, body).await;
        assert_eq!(refused.0, 409, "{refused:?}");
        assert_eq!(refused.1["code"], "agent_configuration_changed");
    }
    // Reading and renaming history do not perform execution admission.
    let history = request(&app, &identity, Some("alice"), "GET", &session, Value::Null).await;
    assert_eq!(history.0, 200);
    assert_eq!(history.1["agent_configuration_revision"], 1);
    assert_eq!(history.1["agent_configuration_changed"], true);
    assert!(history.1["messages_url"].is_string());
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &session,
            json!({"title":"Kept history"})
        )
        .await
        .0,
        200
    );
    assert_ne!(
        request(
            &app,
            &identity,
            Some("stranger"),
            "GET",
            &session,
            Value::Null
        )
        .await
        .0,
        200
    );
    let fresh = Uuid::new_v4();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &sessions,
            creation(fresh, 2)
        )
        .await
        .0,
        201
    );
    let accepted = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("{base}/runtime?conversation={fresh}"),
        Value::Null,
    )
    .await;
    assert_eq!(accepted.0, 200, "{accepted:?}");
    assert_eq!(accepted.1["agent"]["configuration_revision"], 2);

    // Every editable persisted field uses the same monotone revision, even a revert.
    for (index, patch) in [
        json!({"description":"Changed"}),
        json!({"role":"Another role"}),
        json!({"usage_statement":"Another use"}),
        json!({"tuning_field_values":{"count":2}}),
        json!({"status":"disabled"}),
        json!({"status":"enabled"}),
        json!({"display_name":"Revision"}),
    ]
    .into_iter()
    .enumerate()
    {
        let changed = request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &base,
            patch.clone(),
        )
        .await;
        assert_eq!(changed.0, 200, "{changed:?}");
        let revision = 3 + index as i64;
        assert_eq!(
            saved(&e, team.id, &instance).await.configuration_revision,
            revision
        );
        assert_eq!(
            request(&app, &identity, Some("alice"), "PATCH", &base, patch)
                .await
                .0,
            200
        );
        assert_eq!(
            saved(&e, team.id, &instance).await.configuration_revision,
            revision
        );
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn runtime_binding_lists_all_eligible_conversation_attachments() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Member, "bob").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    let instance = create(&app, &identity, team.id, creation(template, "Files")).await;
    let base = item(team.id, &instance);
    let session = Uuid::new_v4();
    let other = Uuid::new_v4();
    for id in [session, other] {
        let response = request(&app, &identity, Some("alice"), "POST",
            &format!("/spaces/{}/sessions", team.id),
            json!({"session_id":id,"agent_instance_id":instance["agent_instance_id"],"agent_configuration_revision":1})).await;
        assert_eq!(response.0, 201, "{response:?}");
    }
    let ids: Vec<Uuid> = sqlx::query_scalar(
        "select fixture_document(p_id=>gen_random_uuid(),p_space_id=>$1,p_session_id=>case n when 5 then null::uuid when 6 then $3 else $2 end,p_name=>'file-' || n || case n % 3 when 0 then '.csv' when 1 then '.xlsx' else '.txt' end,p_mime=>case n % 3 when 0 then 'text/csv' when 1 then 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' else 'text/plain' end,p_size=>1,p_sha256=>repeat('a',64),p_created_by=>'alice',p_object_key=>gen_random_uuid()::text,p_quota_owner=>$1,p_retrievable=>true) from generate_series(1,110) n",
    ).bind(team.id).bind(session).bind(other).fetch_all(&e.pool).await.unwrap();
    sqlx::query(
        "insert into document_processing(id,request_key,actor,document_id,profile,workflow_id,submission,deadline_at,profile_settings,preparation_seconds,extraction_seconds,indexing_seconds)
         select id,id,'alice',id,'fast',id::text,'{}',now()+interval '1 hour','{}',60,60,60 from document where id=any($1)",
    ).bind(&ids).execute(&e.pool).await.unwrap();
    // Published CSV/Excel need no vectors, just like text documents in this fixture.
    sqlx::query(
        "insert into generation(id,processing_id,stage,execution_id,activity_id,attempt,expires_at,prefix,committed_at,vector_ordinals,cleanup_after,document_id)
         select id,id,'indexing',id,id,1,now()+interval '1 hour',id::text,now(),'{}',now()+interval '2 hours',id from document where id=any($1)",
    ).bind(&ids).execute(&e.pool).await.unwrap();
    sqlx::query("update document set published_generation=id where id=any($1)")
        .bind(&ids)
        .execute(&e.pool)
        .await
        .unwrap();
    sqlx::query("update document set published_generation=null where id=$1")
        .bind(ids[0])
        .execute(&e.pool)
        .await
        .unwrap();
    sqlx::query("update document set retrievable=false where id=$1")
        .bind(ids[1])
        .execute(&e.pool)
        .await
        .unwrap();
    sqlx::query("update document set retrieval_id=id,retrieval_actor='alice',retrieval_target=true,retrieval_phase='ready',retrieval_confirmed=false where id=$1")
        .bind(ids[2]).execute(&e.pool).await.unwrap();
    let deletion = Uuid::new_v4();
    sqlx::query("insert into deletion(id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at) values ($1,$2,'document',$3,$4,'alice',now(),now())")
        .bind(deletion).bind(ids[3]).bind(team.id).bind(org.id).execute(&e.pool).await.unwrap();
    sqlx::query("update document set deletion_id=$2,purge_after=now() where id=$1")
        .bind(ids[3])
        .bind(deletion)
        .execute(&e.pool)
        .await
        .unwrap();
    let resolve = format!("{base}/runtime?conversation={session}");
    let first = request(&app, &identity, Some("alice"), "GET", &resolve, Value::Null).await;
    assert_eq!(first.0, 200, "{first:?}");
    let files = first.1["attachments"].as_array().unwrap();
    assert_eq!(files.len(), 104);
    let mut expected = ids[6..].to_vec();
    expected.sort();
    assert_eq!(
        files
            .iter()
            .map(|f| Uuid::parse_str(f["document_id"].as_str().unwrap()).unwrap())
            .collect::<Vec<_>>(),
        expected
    );
    assert!(
        files
            .iter()
            .all(|f| f["name"].is_string() && f["mime"].is_string())
    );
    let repeated = request(&app, &identity, Some("alice"), "GET", &resolve, Value::Null).await;
    assert_eq!(first.1["attachments"], repeated.1["attachments"]);
    let no_conversation = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("{base}/runtime"),
        Value::Null,
    )
    .await;
    assert_eq!(no_conversation.0, 200, "{no_conversation:?}");
    assert_eq!(no_conversation.1["attachments"], json!([]));
    assert_eq!(
        request(&app, &identity, Some("bob"), "GET", &resolve, Value::Null)
            .await
            .0,
        404
    );
    sqlx::query("update document set published_generation=id where id=$1")
        .bind(ids[0])
        .execute(&e.pool)
        .await
        .unwrap();
    let next = request(&app, &identity, Some("alice"), "GET", &resolve, Value::Null).await;
    assert_eq!(next.1["attachments"].as_array().unwrap().len(), 105);
    let error =
        sqlx::query("update session_metadata set runtime_id='wrong-runtime' where session_id=$1")
            .bind(session)
            .execute(&e.pool)
            .await
            .unwrap_err();
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some("23514")
    );
    assert_eq!(
        request(&app, &identity, Some("alice"), "GET", &resolve, Value::Null)
            .await
            .0,
        200
    );
}

#[path = "model_catalog.rs"]
mod model_catalog;

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn instances_generate_references_for_creation_and_copies_but_keep_them_on_rename() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let template = enable(&e, org.id, "custom", true).await;
    let catalog = Catalog::start().await;
    let identity = support::IdentityServer::start().await;
    let app = app(&e, &identity, &catalog).await;
    enable_capability(&e, org.id, "tool").await;

    for label in [
        "Assistant commercial",
        "Équipe de rédaction",
        "東京 助手",
        "مساعد",
    ] {
        let mut body = creation(template, label);
        body.as_object_mut().unwrap().remove("logical_name");
        let source = create(&app, &identity, team.id, body.clone()).await;
        assert_eq!(source["display_name"], label);
        let source_id = Uuid::parse_str(source["agent_instance_id"].as_str().unwrap()).unwrap();
        assert_eq!(
            source["logical_name"],
            format!("agent-{}", source_id.simple())
        );
        assert_eq!(
            saved(&e, team.id, &source).await.logical_name,
            source["logical_name"]
        );

        // Duplication uses creation with copied editable fields, without the source identity.
        // Null has the same generation contract as omission; a copy needs its own display name.
        body["logical_name"] = Value::Null;
        body["display_name"] = json!(format!("{label} (copie)"));
        let copy = create(&app, &identity, team.id, body).await;
        assert_eq!(copy["display_name"], format!("{label} (copie)"));
        assert_ne!(copy["agent_instance_id"], source["agent_instance_id"]);
        assert_ne!(copy["logical_name"], source["logical_name"]);
        let (status, renamed) = request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &item(team.id, &source),
            json!({"display_name":format!("Nouveau nom {label}")}),
        )
        .await;
        assert_eq!(status, 200);
        assert_eq!(renamed["logical_name"], source["logical_name"]);
        assert_eq!(renamed["agent_instance_id"], source["agent_instance_id"]);
        assert_eq!(
            saved(&e, team.id, &source).await.logical_name,
            source["logical_name"]
        );
    }
    let body = json!({"template_id":template,"display_name":"Concurrent label","usage_statement":"Use me"});
    let mut other = body.clone();
    other["display_name"] = json!("Another concurrent label");
    let path = collection(team.id);
    let (left, right) = tokio::join!(
        request(&app, &identity, Some("alice"), "POST", &path, body.clone()),
        request(&app, &identity, Some("alice"), "POST", &path, other),
    );
    assert_eq!((left.0, right.0), (201, 201));
    assert_ne!(left.1["logical_name"], right.1["logical_name"]);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn instances_display_names_are_unique_per_space_on_create_and_rename() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let template = enable(&e, org.id, "custom", true).await;
    let catalog = Catalog::start().await;
    let identity = support::IdentityServer::start().await;
    let app = app(&e, &identity, &catalog).await;
    enable_capability(&e, org.id, "tool").await;
    let body =
        |name: &str| json!({"template_id":template,"display_name":name,"usage_statement":"Use me"});
    let simon = create(&app, &identity, team.id, body(" Simon ")).await;
    assert_eq!(simon["display_name"], "Simon");
    for name in ["Simon", "sIMON", " Simon "] {
        let conflict = request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &collection(team.id),
            body(name),
        )
        .await;
        assert_eq!(conflict.0, 409);
        assert_eq!(conflict.1["code"], "agent_name_conflict");
        assert_eq!(
            conflict.1["detail"],
            "An agent with this display name already exists in this space."
        );
    }
    let eva = create(&app, &identity, team.id, body("Eva")).await;
    let before = saved(&e, team.id, &eva).await;
    let conflict = request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &item(team.id, &eva),
        json!({"display_name":" simon "}),
    )
    .await;
    assert_eq!(conflict.0, 409);
    assert_eq!(conflict.1["code"], "agent_name_conflict");
    let after = saved(&e, team.id, &eva).await;
    assert_eq!(after.display_name, "Eva");
    assert_eq!(after.logical_name, before.logical_name);
    assert_eq!(after.configuration_revision, before.configuration_revision);
    assert_eq!(after.updated_at, before.updated_at);
    let (status, renamed) = request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &item(team.id, &simon),
        json!({"display_name":"SIMON"}),
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(renamed["logical_name"], simon["logical_name"]);
    assert_eq!(renamed["agent_instance_id"], simon["agent_instance_id"]);

    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    let other = create(&app, &identity, personal.id, body("Simon")).await;
    assert_ne!(other["agent_instance_id"], simon["agent_instance_id"]);
    let path = collection(team.id);
    let (left, right) = tokio::join!(
        request(&app, &identity, Some("alice"), "POST", &path, body("Nora")),
        request(&app, &identity, Some("alice"), "POST", &path, body("nora")),
    );
    let conflict = match (left, right) {
        ((201, _), (409, conflict)) | ((409, conflict), (201, _)) => conflict,
        results => panic!("expected one creation and one conflict: {results:?}"),
    };
    assert_eq!(conflict["code"], "agent_name_conflict");
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn instances_logical_identity_and_authorized_catalog_pagination() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let template = enable(&e, org.id, "custom", true).await;
    let catalog = Catalog::start().await;
    let identity = support::IdentityServer::start().await;
    let app = app(&e, &identity, &catalog).await;
    enable_capability(&e, org.id, "tool").await;
    let mut body = creation(template, "Shared label");
    body["logical_name"] = json!("b-reference");
    let source = create(&app, &identity, team.id, body.clone()).await;
    assert_eq!(source["logical_name"], "b-reference");
    // Isolate the logical-reference conflict from the display-name constraint.
    body["display_name"] = json!("Another label");
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &collection(team.id),
            body.clone()
        )
        .await
        .0,
        409
    );
    for name in [
        "",
        "Upper",
        "white space",
        "/agent",
        "référence",
        &"a".repeat(65),
    ] {
        body["logical_name"] = json!(name);
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "POST",
                &collection(team.id),
                body.clone()
            )
            .await
            .0,
            422
        );
    }
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &item(team.id, &source),
            json!({"logical_name":"changed"})
        )
        .await
        .0,
        422
    );
    // Copy the validated saved tuning with independent identities and display names
    // to exercise a complete page plus continuation.
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,logical_name,display_name,tuning,created_by)
        select gen_random_uuid(),space_id,template_id,source_runtime_id,source_agent_id,'a-'||lpad(n::text,3,'0'),display_name||' '||n,tuning,'alice'
        from agent_instance cross join generate_series(1,101) n where agent_instance_id=$1")
        .bind(Uuid::parse_str(source["agent_instance_id"].as_str().unwrap()).unwrap()).execute(&e.pool).await.unwrap();
    // A disabled template must not leak its rows or its names into page cursors.
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,logical_name,display_name,tuning,created_by)
        select gen_random_uuid(),space_id,$2,source_runtime_id,source_agent_id,'a-hidden','Hidden label',tuning,'alice'
        from agent_instance where agent_instance_id=$1")
        .bind(Uuid::parse_str(source["agent_instance_id"].as_str().unwrap()).unwrap()).bind(Uuid::new_v4()).execute(&e.pool).await.unwrap();
    let (status, first) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &collection(team.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(first["items"].as_array().unwrap().len(), 100);
    assert_eq!(first["next_cursor"], "a-100");
    let first_id = first["items"][0]["agent_instance_id"].as_str().unwrap();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &format!("{}/{first_id}", collection(team.id)),
            json!({"display_name":"New label"})
        )
        .await
        .0,
        200
    );
    let (_, last) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("{}?after=a-100", collection(team.id)),
        Value::Null,
    )
    .await;
    assert_eq!(
        last["items"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| row["logical_name"].as_str().unwrap())
            .collect::<Vec<_>>(),
        ["a-101", "b-reference"]
    );
    assert_eq!(last["next_cursor"], Value::Null);
    for (query, expected) in [("?after=Upper", 400), ("?unexpected=1", 422)] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "GET",
                &format!("{}{query}", collection(team.id)),
                Value::Null
            )
            .await
            .0,
            expected
        );
    }
    enable(&e, org.id, "custom", false).await;
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &collection(team.id),
            Value::Null
        )
        .await
        .1,
        json!({"items":[],"next_cursor":null})
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn manual_session_title_write_cancels_attempt_even_when_text_is_identical() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    let instance = create(&app, &identity, team.id, creation(template, "Title")).await;
    let sid = Uuid::new_v4();
    let path = format!("/spaces/{}/sessions", team.id);
    let (status, _) = request(&app, &identity, Some("alice"), "POST", &path,
        json!({"session_id":sid,"agent_instance_id":instance["agent_instance_id"],"agent_configuration_revision":1,"title":"Initial"})).await;
    assert_eq!(status, 201);
    sqlx::query(
        "update session_metadata set title_pending=false,title_attempt=$2 where session_id=$1",
    )
    .bind(sid)
    .bind(Uuid::new_v4())
    .execute(&e.pool)
    .await
    .unwrap();
    let path = format!("{path}/{sid}");
    let (status, _) = request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &path,
        json!({"updated_at":chrono::Utc::now()}),
    )
    .await;
    assert_eq!(status, 200);
    assert!(
        sqlx::query_scalar::<_, bool>(
            "select title_attempt is not null from session_metadata where session_id=$1"
        )
        .bind(sid)
        .fetch_one(&e.pool)
        .await
        .unwrap()
    );
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &path,
        json!({"title":"Initial"}),
    )
    .await;
    assert_eq!(status, 200, "{body}");
    let row: (String, bool, Option<Uuid>) = sqlx::query_as(
        "select title,title_pending,title_attempt from session_metadata where session_id=$1",
    )
    .bind(sid)
    .fetch_one(&e.pool)
    .await
    .unwrap();
    assert_eq!(row, ("Initial".into(), false, None));
}

#[path = "pod_skills.rs"]
mod pod_skills;

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn marketplace_agents_install_frozen_configuration_with_current_offers() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "alice").await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Editor, "bob").await;
    let (personal, _) = spaces::create_personal_space(&e.pool, "bob", org.id)
        .await
        .unwrap();
    let identity = Arc::new(support::IdentityServer::start().await);
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let template = enable(&e, org.id, "custom", true).await;
    enable_capability(&e, org.id, "tool").await;
    let mut body = creation(template, "Agent snapshot");
    body["capability_ids"] = json!(["tool"]);
    body["capability_config_values"] =
        json!({"tool":{"endpoint":"https://example.test/initial","library_id":"private"}});
    body["tuning_field_values"] = json!({"prompts.system":"Original instruction"});
    let (status, source) = request(
        &app,
        &identity,
        Some("bob"),
        "POST",
        &collection(personal.id),
        body,
    )
    .await;
    assert_eq!(status, 201, "{source}");
    let source_path = item(personal.id, &source);
    let revision = saved(&e, personal.id, &source).await.configuration_revision;
    let proposals = format!("/spaces/{}/marketplace/proposals", org.id);
    let submission = json!({"source_space_id":personal.id,"source_resource_id":source["agent_instance_id"],"kind":"agent","expected_revision":revision.to_string()});
    let key = Uuid::new_v4().to_string();
    let (status, proposal) = support::request_with_headers(
        &app,
        &identity,
        Some("bob"),
        "POST",
        &proposals,
        submission.clone(),
        &[("Idempotency-Key", key.clone())],
    )
    .await;
    assert_eq!(status, 200, "{proposal}");
    assert_eq!(
        proposal["package"]["content"]["capabilities"]["tool"]["config"],
        json!({"endpoint":"https://example.test/initial"})
    );
    // A changed source during pod export is never committed under a stale revision.
    let gate = Arc::new(support::Gate::default());
    catalog.state.lock().await.gate = Some(gate.clone());
    let pending = {
        let app = app.clone();
        let identity = identity.clone();
        let proposals = proposals.clone();
        let submission = submission.clone();
        tokio::spawn(async move {
            support::request_with_headers(
                &app,
                &identity,
                Some("bob"),
                "POST",
                &proposals,
                submission,
                &[("Idempotency-Key", Uuid::new_v4().to_string())],
            )
            .await
        })
    };
    tokio::time::timeout(std::time::Duration::from_secs(5), gate.entered.notified())
        .await
        .unwrap();
    let changed = tokio::time::timeout(
        std::time::Duration::from_secs(5),
        request(
            &app,
            &identity,
            Some("bob"),
            "PATCH",
            &source_path,
            json!({"description":"Changed during export"}),
        ),
    )
    .await
    .unwrap();
    assert_eq!(changed.0, 200, "{}", changed.1);
    gate.release.notify_one();
    let rejected = pending.await.unwrap();
    assert_eq!(rejected.0, 409, "{}", rejected.1);
    assert_eq!(rejected.1["code"], "source_changed");
    let proposal_path = format!("{proposals}/{}", proposal["proposal_id"].as_str().unwrap());
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &source_path,
            Value::Null
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
            "GET",
            &proposal_path,
            Value::Null
        )
        .await
        .0,
        200
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "PUT",
            &format!("{proposal_path}/decision"),
            json!({"approve":true,"expected_publication_version":0})
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
            &format!("{proposal_path}/decision"),
            json!({"approve":true,"expected_publication_version":0})
        )
        .await
        .0,
        200
    );
    let entry = format!(
        "/spaces/{}/marketplace/entries/{}",
        org.id,
        proposal["entry_id"].as_str().unwrap()
    );
    let installation = format!("{entry}/installations");
    let install = json!({"proposal_id":proposal["proposal_id"],"destination_space_id":team.id,"options":{"kind":"agent","display_name":"Installed","logical_name":"installed"}});
    let install_key = Uuid::new_v4().to_string();
    let headers = [("Idempotency-Key", install_key.clone())];
    // An enabled publication grants neither its template nor its capabilities.
    enable(&e, org.id, "custom", false).await;
    assert_eq!(
        support::request_with_headers(
            &app,
            &identity,
            Some("bob"),
            "POST",
            &installation,
            install.clone(),
            &headers
        )
        .await
        .0,
        404
    );
    enable(&e, org.id, "custom", true).await;
    sqlx::query("delete from organization_capability where organization_id=$1 and runtime_id='fixture' and capability_id='tool'").bind(org.id).execute(&e.pool).await.unwrap();
    assert_eq!(
        support::request_with_headers(
            &app,
            &identity,
            Some("bob"),
            "POST",
            &installation,
            install.clone(),
            &headers
        )
        .await
        .0,
        422
    );
    sqlx::query("insert into organization_capability (organization_id,runtime_id,capability_id,enabled_by) values ($1,'fixture','tool','fixture')").bind(org.id).execute(&e.pool).await.unwrap();
    // Policy revocation during external preflight is rechecked in the final transaction.
    let gate = Arc::new(support::Gate::default());
    catalog.state.lock().await.gate = Some(gate.clone());
    let pending = {
        let app = app.clone();
        let identity = identity.clone();
        let installation = installation.clone();
        let install = install.clone();
        let key = install_key.clone();
        tokio::spawn(async move {
            support::request_with_headers(
                &app,
                &identity,
                Some("bob"),
                "POST",
                &installation,
                install,
                &[("Idempotency-Key", key)],
            )
            .await
        })
    };
    tokio::time::timeout(std::time::Duration::from_secs(5), gate.entered.notified())
        .await
        .unwrap();
    enable(&e, org.id, "custom", false).await;
    gate.release.notify_one();
    assert_eq!(pending.await.unwrap().0, 404);
    enable(&e, org.id, "custom", true).await;
    // Source edits and deletion are irrelevant to the published package and import.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "PATCH",
            &source_path,
            json!({"tuning_field_values":{"prompts.system":"Changed"}})
        )
        .await
        .0,
        200
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "DELETE",
            &source_path,
            Value::Null
        )
        .await
        .0,
        204
    );
    assert_eq!(
        support::request_with_headers(
            &app,
            &identity,
            Some("bob"),
            "POST",
            &proposals,
            submission,
            &[("Idempotency-Key", key)]
        )
        .await
        .1["package"],
        proposal["package"]
    );
    let (a, b) = tokio::join!(
        support::request_with_headers(
            &app,
            &identity,
            Some("bob"),
            "POST",
            &installation,
            install.clone(),
            &headers
        ),
        support::request_with_headers(
            &app,
            &identity,
            Some("bob"),
            "POST",
            &installation,
            install.clone(),
            &headers
        )
    );
    assert_eq!(a.0, 200, "{}", a.1);
    assert_eq!(a, b);
    let installed = format!(
        "{}/{}",
        collection(team.id),
        a.1["resource_id"].as_str().unwrap()
    );
    let (status, local) =
        request(&app, &identity, Some("bob"), "GET", &installed, Value::Null).await;
    assert_eq!(status, 200, "{local}");
    assert_eq!(
        local["tuning_field_values"]["prompts.system"],
        "Original instruction"
    );
    assert_eq!(local["selected_capability_ids"], json!(["tool"]));
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &format!("{entry}/withdrawal"),
            json!({"expected_publication_version":1})
        )
        .await
        .0,
        204
    );
    assert_eq!(
        support::request_with_headers(
            &app,
            &identity,
            Some("bob"),
            "POST",
            &installation,
            install,
            &headers
        )
        .await,
        a
    );
    assert_eq!(
        request(&app, &identity, Some("bob"), "GET", &installed, Value::Null)
            .await
            .0,
        200
    );
    e.pool.close().await;
}
