// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use axum::{
    Json, Router,
    body::{Body, to_bytes},
    http::Request,
    routing::get,
};
use control_plane::{
    agent_instances as storage,
    agents::{PlatformConfig, RuntimeCatalogSource, template_id},
    api::{AppState, routes},
};
use serde_json::{Value, json};
use std::sync::Arc;
use tokio::sync::Mutex;
use tower::ServiceExt;

struct CatalogState {
    templates: Value,
    status: u16,
    calls: usize,
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
            status: 200,
            calls: 0,
            gate: None,
        }));
        let shared = state.clone();
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
                public_base_url: None,
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
async fn request(
    app: &Router,
    identity: &support::IdentityServer,
    actor: Option<&str>,
    method: &str,
    path: &str,
    body: Value,
) -> (u16, Value) {
    let mut req = Request::builder()
        .method(method)
        .uri(path)
        .header("content-type", "application/json");
    if let Some(actor) = actor {
        req = req.header("authorization", format!("Bearer {}", identity.token(actor)));
    }
    let response = app
        .clone()
        .oneshot(req.body(Body::from(body.to_string())).unwrap())
        .await
        .unwrap();
    let status = response.status().as_u16();
    let bytes = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
    (
        status,
        serde_json::from_slice(&bytes).unwrap_or(Value::Null),
    )
}
async fn app(e: &Env, identity: &support::IdentityServer, catalog: &Catalog, fga: Fga) -> Router {
    routes(AppState {
        pool: e.pool.clone(),
        fga,
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
    let mut guard = e.fga.guard(&[Scope::Organization(org)]).await.unwrap();
    e.fga
        .set_agent_default_on(&mut guard, org, id, on)
        .await
        .unwrap();
    id
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
    json!({"template_id":template,"display_name":name,"usage_statement":"Use me"})
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
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn instances_round_trip_validation_and_saved_snapshot() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog, e.fga.clone()).await;
    let template = enable(&e, org.id, "custom", true).await;
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
        (200, json!([first]))
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
    for patch in [
        json!({"display_name":"Second"}),
        json!({"display_name":" second "}),
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
            .await
            .0,
            409
        );
    }
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
    assert_eq!(listed.1[0], renamed.1);
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
        .1
        .as_array()
        .unwrap()
        .iter()
        .all(|v| v["agent_instance_id"] != first["agent_instance_id"])
    );
    create(&app, &identity, team.id, creation(template, "Renamed")).await;
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn instances_capabilities_and_profiles_fail_explicitly() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog, e.fga.clone()).await;
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
            "agent_chat_profile_not_connected"
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
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn instances_discovery_concurrency_rechecks_and_isolation() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = Arc::new(support::IdentityServer::start().await);
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog, e.fga.clone()).await;
    let template = enable(&e, org.id, "custom", true).await;
    let instance = create(&app, &identity, team.id, creation(template, "Existing")).await;
    for actor in [None, Some("stranger")] {
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
            assert_eq!(
                request(&app, &identity, actor, method, &path, body).await.0,
                if actor.is_none() { 401 } else { 404 }
            );
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
    grant(&e, org.id, Role::PersonalSpaceCreator, "alice").await;
    let (personal, _) = spaces::create_personal_space(&e.pool, &e.fga, "alice", org.id)
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
        (200, json!([personal_instance]))
    );
    let other = support::member_organization(&e.pool, &e.fga, "Other", "bob")
        .await
        .unwrap();
    let other_team = spaces::create_space(
        &e.pool,
        &e.fga,
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
        &e.fga,
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
        storage::list_by_space(&e.pool, team.id)
            .await
            .unwrap()
            .len(),
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
        (200, json!([]))
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
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn instances_retention_and_exact_space_purge() {
    use control_plane::lifecycle::{Lifecycle, Status, cleanup, store};
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let identity = Arc::new(support::IdentityServer::start().await);
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog, e.fga.clone()).await;
    let template = enable(&e, org.id, "custom", true).await;
    let instance = create(&app, &identity, team.id, creation(template, "Retained")).await;
    grant(&e, org.id, Role::PersonalSpaceCreator, "alice").await;
    let (personal, _) = spaces::create_personal_space(&e.pool, &e.fga, "alice", org.id)
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
        .accept(&e.pool, &e.fga, "root", team.id)
        .await
        .unwrap();
    gate.release.notify_one();
    assert_eq!(pending.await.unwrap().0, 409);
    cleanup::batch(&e.pool, &e.fga, receipt.id).await.unwrap();
    assert_eq!(
        storage::list_by_space(&e.pool, team.id)
            .await
            .unwrap()
            .len(),
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
        cleanup::batch(&e.pool, &e.fga, receipt.id).await.unwrap();
        if store::status(&e.pool, &e.fga, "root", receipt.id)
            .await
            .unwrap()
            .status
            == Status::Completed
        {
            break;
        }
    }
    assert_eq!(
        store::status(&e.pool, &e.fga, "root", receipt.id)
            .await
            .unwrap()
            .status,
        Status::Completed
    );
    assert!(
        storage::list_by_space(&e.pool, team.id)
            .await
            .unwrap()
            .is_empty()
    );
    assert_eq!(
        saved(&e, personal.id, &other).await.display_name,
        "Unaffected"
    );
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn instances_list_deduplicates_bounded_checks_and_propagates_failures() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let observed = Fga::connect(
        &proxy.base,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap()
    .load(&e.pool)
    .await
    .unwrap();
    let app = app(&e, &identity, &catalog, observed).await;
    let mut ids = Vec::new();
    for n in 0..12 {
        let template = enable(&e, org.id, &format!("template-{n}"), true).await;
        for copy in 0..2 {
            let id = Uuid::new_v4();
            ids.push(id);
            storage::create(
                &e.pool,
                &storage::NewAgentInstance {
                    agent_instance_id: id,
                    space_id: team.id,
                    template_id: template,
                    source_runtime_id: "fixture".into(),
                    source_agent_id: format!("template-{n}"),
                    display_name: format!("Instance-{n}-{copy}"),
                    description: None,
                    enabled: copy == 0,
                    created_by: Some("alice".into()),
                    updated_by: None,
                    tuning: json!({"role":"Saved", "values":{}, "capability_config":{}}),
                },
            )
            .await
            .unwrap();
        }
    }
    // Equal timestamps force the UUID tie-breaker, independent of insertion order.
    sqlx::query("update agent_instance set created_at='2026-01-01T00:00:00Z' where space_id=$1")
        .bind(team.id)
        .execute(&e.pool)
        .await
        .unwrap();
    ids.sort();
    *proxy.fault.lock().await = support::fga_proxy::Fault {
        template_check_delay: Some(Duration::from_millis(40)),
        ..Default::default()
    };
    let (status, list) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &collection(team.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{list}");
    assert_eq!(
        list.as_array()
            .unwrap()
            .iter()
            .map(|v| Uuid::parse_str(v["agent_instance_id"].as_str().unwrap()).unwrap())
            .collect::<Vec<_>>(),
        ids
    );
    {
        let fault = proxy.fault.lock().await;
        assert_eq!(fault.template_checks.len(), 12);
        assert!(fault.peak_template_checks > 1);
        assert!(fault.peak_template_checks <= control_plane::fga::READ_CONCURRENCY);
        for check in &fault.template_checks {
            assert_eq!(check["consistency"], "HIGHER_CONSISTENCY");
            assert!(check["authorization_model_id"].is_string());
        }
    }
    assert_eq!(catalog.state.lock().await.calls, 0);
    for instance in list.as_array().unwrap() {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "GET",
                &item(team.id, instance),
                Value::Null
            )
            .await,
            (200, instance.clone())
        );
    }
    *proxy.fault.lock().await = support::fga_proxy::Fault {
        fail_template_check_at: 2,
        ..Default::default()
    };
    let failure = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &collection(team.id),
        Value::Null,
    )
    .await;
    assert!(failure.0 >= 500, "{failure:?}");
    assert!(!failure.1.is_array());
    assert!(!failure.1.to_string().contains("private-template-error"));
    // Already dispatched calls may still complete after try_collect returns an error.
    proxy.fault.lock().await.fail_template_check_at = 0;
    enable(&e, org.id, "template-0", false).await;
    let filtered = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &collection(team.id),
        Value::Null,
    )
    .await;
    assert_eq!(filtered.0, 200);
    assert_eq!(filtered.1.as_array().unwrap().len(), 22);
    // Authorized corrupt snapshots and SQL failures cannot produce partial success.
    sqlx::query("update agent_instance set tuning='{}'::jsonb where source_agent_id='template-1'")
        .execute(&e.pool)
        .await
        .unwrap();
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
        500
    );
    sqlx::query("alter table agent_instance rename to unavailable_instances")
        .execute(&e.pool)
        .await
        .unwrap();
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
        500
    );
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn instances_store_tuning_opaquely() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let org = org.id;
    let mut conn = e.pool.acquire().await.unwrap();
    for (n,tuning) in [Value::Null,json!({"unknown":{"nested":[null,{},[]]},"selected_capability_ids":null,"capability_config":{"tool":{"schema_version":2,"config":{"nested":{"list":[1,false]}}}}}),json!({"selected_capability_ids":[]})].into_iter().enumerate() {
        let record=storage::create(&mut *conn,&storage::NewAgentInstance{agent_instance_id:Uuid::new_v4(),space_id:org,template_id:Uuid::new_v4(),source_runtime_id:"fixture".into(),source_agent_id:"opaque".into(),display_name:format!("  Opaque {n}  "),description:None,enabled:false,created_by:None,updated_by:None,tuning:tuning.clone()}).await.unwrap();
        assert_eq!(record.tuning.0,tuning);assert_eq!(record.display_name,format!("Opaque {n}"));
        assert_eq!(storage::get_for_space(&mut *conn,org,record.agent_instance_id).await.unwrap().unwrap().tuning.0,tuning);
    }
    assert_eq!(
        storage::list_by_space(&mut *conn, org).await.unwrap().len(),
        3
    );
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn instances_space_revocation_during_discovery_preserves_configuration() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = Arc::new(support::IdentityServer::start().await);
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog, e.fga.clone()).await;
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
        spaces::revoke(&e.pool, &e.fga, "alice", team.id, Role::Editor, "alice")
            .await
            .unwrap();
        gate.release.notify_one();
        assert_eq!(pending.await.unwrap().0, 403);
    }
    assert_eq!(
        storage::list_by_space(&e.pool, team.id)
            .await
            .unwrap()
            .len(),
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
