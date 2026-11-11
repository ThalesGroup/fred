// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

async fn publish_fixture(e: &Env, app: &Router, identity: &support::IdentityServer) -> Value {
    publish_configured_fixture(
        e,
        app,
        identity,
        json!({"url":"https://tools.invalid/mcp","authentication":{"kind":"none"}}),
    )
    .await
}

async fn publish_configured_fixture(
    e: &Env,
    app: &Router,
    identity: &support::IdentityServer,
    configuration: Value,
) -> Value {
    let body = json!({"logical_name":"tool","display_name":"Central tools","description":"Shared endpoint",
        "configuration": configuration});
    let (status, denied) = request(
        app,
        identity,
        Some("alice"),
        "POST",
        "/platform/mcp-connections",
        body.clone(),
    )
    .await;
    assert_eq!(status, 403, "{denied}"); // Business Owner cannot create technical connections.
    let (status, created) = request(
        app,
        identity,
        Some("fixture-root"),
        "POST",
        "/platform/mcp-connections",
        body,
    )
    .await;
    assert_eq!(status, 201, "{created}");
    assert_eq!(created["available"], false);
    assert_eq!(created["enabled"], false);
    let id = created["id"].as_str().unwrap();
    let tools = json!([{"name":"search","description":"Find","input_schema":{"type":"object"},"output_schema":null,"annotations":null}]);
    // Discovery has its own local HTTP test. This fixture establishes its successful observation.
    sqlx::query("update mcp_connection set observed_tools=$2,observation_state='available',observation_revision=revision,checked_at=clock_timestamp() where id=$1")
        .bind(Uuid::parse_str(id).unwrap()).bind(tools).execute(&e.pool).await.unwrap();
    let (_, list) = request(
        app,
        identity,
        Some("fixture-root"),
        "GET",
        "/platform/mcp-connections",
        Value::Null,
    )
    .await;
    let (status, published) = request(
        app,
        identity,
        Some("fixture-root"),
        "POST",
        &format!("/platform/mcp-connections/{id}/publish"),
        json!({"expected_revision":1,"expected_checked_at":list[0]["checked_at"]}),
    )
    .await;
    assert_eq!(status, 200, "{published}");
    let (status,enabled)=request(app,identity,Some("fixture-root"),"PUT",&format!("/platform/mcp-connections/{id}"),
        json!({"expected_revision":published["revision"],"display_name":"Central tools","description":"Shared endpoint","configuration":published["configuration"],"enabled":true})).await;
    assert_eq!(status, 200, "{enabled}");
    assert_eq!(enabled["available"], true);
    enabled
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn one_central_offer_two_pods_native_collision_and_local_ceiling() {
    central_offer_two_pods(false).await;
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn knowledge_flow_one_offer_two_pods_and_local_ceiling() {
    central_offer_two_pods(true).await;
}

async fn central_offer_two_pods(trusted: bool) {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let other = support::member_organization(&e.pool, "Other MCP organization", "bob")
        .await
        .unwrap();
    let identity = support::IdentityServer::start().await;
    let first = Catalog::start().await;
    let second = Catalog::start().await;
    for catalog in [&first, &second] {
        let mut state = catalog.state.lock().await;
        state.templates[0]["supports_managed_mcp"] = json!(true);
        if trusted {
            state.templates[0]["available_capabilities"].as_array_mut().unwrap().push(json!({
                "id":"mcp-knowledge-flow-mcp-tabular", "mcp_service":"knowledge_flow_tabular", "version":"1", "config_fields":[]
            }));
        }
    }
    let mut config = first.config();
    if trusted {
        config.knowledge_flow_url = Some("https://kf.invalid/api".into());
    }
    config.runtime_catalog_sources.push(RuntimeCatalogSource {
        runtime_id: "second".into(),
        base_url: second.base.clone(),
        public_base_url: Some("/second".into()),
        enabled: true,
    });
    let app = routes(AppState {
        pool: e.pool.clone(),
        agent_catalog: config,
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    });
    let connection = if trusted {
        publish_configured_fixture(
            &e,
            &app,
            &identity,
            json!({"url":"", "authentication":{"kind":"knowledge_flow_tabular"}}),
        )
        .await
    } else {
        publish_fixture(&e, &app, &identity).await
    };
    if trusted {
        assert_eq!(
            connection["configuration"]["url"],
            "https://kf.invalid/api/mcp/tabular"
        );
        for (configuration, expected) in [
            (
                json!({"url":"", "authentication":{"kind":"knowledge_flow_tabular"}}),
                409,
            ),
            (
                json!({"url":"https://attacker.invalid/mcp", "authentication":{"kind":"knowledge_flow_tabular"}}),
                422,
            ),
        ] {
            let (status, _) = request(&app, &identity, Some("fixture-root"), "POST", "/platform/mcp-connections", json!({
                "logical_name":"another", "display_name":"Another", "description":"Test", "configuration":configuration
            })).await;
            assert_eq!(status, expected);
        }
    }
    let id = connection["id"].as_str().unwrap();
    let capability = format!("managed-mcp:{id}");
    let policy_path = format!(
        "/organizations/{}/capabilities/$mcp/{capability}/default-on",
        org.id
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("fixture-root"),
            "PUT",
            &policy_path,
            json!({"default_on":true})
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
            &policy_path,
            json!({"default_on":true})
        )
        .await
        .0,
        204
    );
    enable_capability(&e, org.id, "tool").await; // Same logical name, independent native provenance.
    let first_id = enable(&e, org.id, "custom", true).await;
    let second_id = template_id(org.id, "second", "custom");
    control_plane::authorization::set_agent_default_on(
        &mut e.pool.acquire().await.unwrap(),
        org.id,
        second_id,
        true,
    )
    .await
    .unwrap();
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
    for template in [first_id, second_id] {
        let summary = templates
            .as_array()
            .unwrap()
            .iter()
            .find(|row| row["template_id"] == template.to_string())
            .unwrap();
        assert_eq!(
            summary["available_capabilities"]
                .as_array()
                .unwrap()
                .iter()
                .filter(|offer| offer["id"] == capability)
                .count(),
            1
        );
    }
    let mut native_body = creation(first_id, "Native tools");
    native_body["capability_ids"] = json!(["tool"]);
    native_body["capability_config_values"] = json!({"tool":{"endpoint":"https://native.invalid"}});
    let native_instance = create(&app, &identity, team.id, native_body).await;
    let native_runtime = format!("{}/runtime", item(team.id, &native_instance));
    let mut instances = Vec::new();
    for template in [first_id, second_id] {
        let mut body = creation(template, &template.to_string());
        body["capability_ids"] = json!([capability]);
        if trusted {
            body["capability_config_values"] =
                json!({capability.clone(): {"chat_options.documents_selection":true}});
        }
        let instance = create(&app, &identity, team.id, body).await;
        let runtime = format!("{}/runtime", item(team.id, &instance));
        let (status, admitted) =
            request(&app, &identity, Some("alice"), "GET", &runtime, Value::Null).await;
        assert_eq!(status, 200, "{admitted}");
        assert_eq!(admitted["mcp_bindings"][0]["connection_id"], id);
        if trusted {
            assert_eq!(
                admitted["agent"]["configuration"]["capability_config"][&capability]["config"]["chat_options.documents_selection"],
                true
            );
        }
        instances.push((runtime, admitted));
    }
    let count: i64 =
        sqlx::query_scalar("select count(*) from capability_offer where connection_id=$1")
            .bind(Uuid::parse_str(id).unwrap())
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(count, 1);
    let native = control_plane::agents::enablement::Policy::load(&e.pool, org.id)
        .await
        .unwrap();
    assert!(native.default_on("fixture", "tool"));
    assert!(!native.default_on("second", "tool"));
    let other_policy = control_plane::agents::enablement::Policy::load(&e.pool, other.id)
        .await
        .unwrap();
    assert!(!other_policy.default_on("$mcp", &capability));
    let local = format!("/spaces/{}/capability-policies/$mcp", team.id);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &local,
            json!({"expected_revision":0,"restricted":true,"permitted_ids":[]})
        )
        .await
        .0,
        204
    );
    for (runtime, admitted) in &instances {
        assert_eq!(
            request(&app, &identity, Some("alice"), "GET", runtime, Value::Null)
                .await
                .0,
            422
        );
        assert_eq!(
            admitted["mcp_bindings"][0]["revision"],
            connection["revision"]
        );
    }
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &local,
            json!({"expected_revision":0,"restricted":false,"permitted_ids":[]})
        )
        .await
        .0,
        409
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &local,
            json!({"expected_revision":1,"restricted":false,"permitted_ids":[]})
        )
        .await
        .0,
        204
    );
    let (status, native_admission) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &native_runtime,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{native_admission}");
    assert_eq!(native_admission["mcp_bindings"], json!([]));
    let (status, next_connection) = request(&app, &identity, Some("fixture-root"), "PUT", &format!("/platform/mcp-connections/{id}"),
        json!({"expected_revision":connection["revision"],"display_name":"Renamed centrally","description":"Shared endpoint","configuration":connection["configuration"],"enabled":true})).await;
    assert_eq!(status, 200, "{next_connection}");
    for (runtime, old_admission) in &instances {
        let (status, next) =
            request(&app, &identity, Some("alice"), "GET", runtime, Value::Null).await;
        assert_eq!(status, 200, "{next}");
        assert_eq!(
            next["mcp_bindings"][0]["revision"],
            next_connection["revision"]
        );
        assert_eq!(
            old_admission["mcp_bindings"][0]["revision"],
            connection["revision"]
        );
    }
    // Template support is checked again for a new admission, including fixed templates.
    first.state.lock().await.templates[0]["supports_capabilities"] = json!(false);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &instances[0].0,
            Value::Null
        )
        .await
        .0,
        422
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &instances[1].0,
            Value::Null
        )
        .await
        .0,
        200
    );
    let edit = json!({"expected_revision":next_connection["revision"],"display_name":"Central tools","description":"Shared endpoint","configuration":connection["configuration"],"enabled":false});
    assert_eq!(
        request(
            &app,
            &identity,
            Some("fixture-root"),
            "PUT",
            &format!("/platform/mcp-connections/{id}"),
            edit.clone()
        )
        .await
        .0,
        200
    );
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
    assert!(!templates.as_array().unwrap().is_empty());
    assert!(templates.as_array().unwrap().iter().all(|row| {
        row["available_capabilities"]
            .as_array()
            .unwrap()
            .iter()
            .all(|offer| offer["id"] != capability)
    }));
    assert_eq!(
        request(
            &app,
            &identity,
            Some("fixture-root"),
            "PUT",
            &format!("/platform/mcp-connections/{id}"),
            edit
        )
        .await
        .0,
        409
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &instances[1].0,
            Value::Null
        )
        .await
        .0,
        422
    );
    assert_eq!(
        instances[1].1["mcp_bindings"][0]["revision"],
        connection["revision"]
    );
    assert!(
        sqlx::query("delete from mcp_connection where id=$1")
            .bind(Uuid::parse_str(id).unwrap())
            .execute(&e.pool)
            .await
            .is_err()
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn slow_discovery_cannot_overwrite_a_new_destination() {
    use axum::{http::StatusCode, response::IntoResponse};
    let e = env().await;
    org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let application = app(&e, &identity, &catalog).await;
    let connection = publish_fixture(&e, &application, &identity).await;
    let gate = Arc::new(support::Gate::default());
    let server_gate = gate.clone();
    let server=Router::new().route("/mcp",post(move |Json(body):Json<Value>| {
        let gate=server_gate.clone();
        async move {
            let id=body["id"].clone();
            match body["method"].as_str().unwrap_or_default() {
                "server/discover" => Json(json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"legacy"}})).into_response(),
                "initialize" => Json(json!({"jsonrpc":"2.0","id":id,"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"fixture","version":"1"}}})).into_response(),
                "notifications/initialized" => StatusCode::ACCEPTED.into_response(),
                "tools/list" => {
                    gate.entered.notify_one();
                    gate.release.notified().await;
                    Json(json!({"jsonrpc":"2.0","id":id,"result":{"tools":[{"name":"stale","inputSchema":{"type":"object"}}]}})).into_response()
                },
                _ => StatusCode::BAD_REQUEST.into_response(),
            }
        }
    }));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let endpoint = format!("http://{}/mcp", listener.local_addr().unwrap());
    let server = tokio::spawn(async move { axum::serve(listener, server).await.unwrap() });
    let path = format!(
        "/platform/mcp-connections/{}",
        connection["id"].as_str().unwrap()
    );
    let mut edit = json!({"expected_revision":connection["revision"],"display_name":"Central tools","description":"Shared endpoint","enabled":true,
        "configuration":{"url":endpoint,"allow_insecure_http":true,"authentication":{"kind":"none"}}});
    let (status, current) = request(
        &application,
        &identity,
        Some("fixture-root"),
        "PUT",
        &path,
        edit.clone(),
    )
    .await;
    assert_eq!(status, 200, "{current}");
    let test_path = format!("{path}/test");
    let discover = request(
        &application,
        &identity,
        Some("fixture-root"),
        "POST",
        &test_path,
        json!({"expected_revision":current["revision"]}),
    );
    let replace = async {
        gate.entered.notified().await;
        edit["expected_revision"] = current["revision"].clone();
        edit["configuration"] = connection["configuration"].clone();
        let result = request(
            &application,
            &identity,
            Some("fixture-root"),
            "PUT",
            &path,
            edit,
        )
        .await;
        gate.release.notify_one();
        result
    };
    let outcome = tokio::time::timeout(std::time::Duration::from_secs(30), async {
        tokio::join!(discover, replace)
    })
    .await;
    server.abort();
    let ((status, _), (edited, new)) = outcome.unwrap();
    assert_eq!(status, 409);
    assert_eq!(edited, 200);
    assert_eq!(new["observed_tools"], connection["observed_tools"]);
    assert_eq!(new["available"], false);
    let (status, _) = request(
        &application,
        &identity,
        Some("fixture-root"),
        "POST",
        &format!("{path}/publish"),
        json!({"expected_revision":new["revision"],"expected_checked_at":connection["checked_at"]}),
    )
    .await;
    assert_eq!(status, 409);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn platform_impact_is_aggregate_without_business_visibility() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    let other = support::member_organization(&e.pool, "Private other organization", "bob")
        .await
        .unwrap();
    let (other_personal, _) = spaces::create_personal_space(&e.pool, "bob", other.id)
        .await
        .unwrap();
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let connection = publish_fixture(&e, &app, &identity).await;
    let capability = format!("managed-mcp:{}", connection["id"].as_str().unwrap());
    let mut private_values = Vec::new();
    for (space, owner) in [
        (team.id, "alice"),
        (personal.id, "alice"),
        (other_personal.id, "bob"),
    ] {
        // Saved selections can outlive authorization/availability; technical impact
        // counts them without turning the platform role into a business reader.
        let record = storage::create(
            &mut *e.pool.acquire().await.unwrap(),
            &storage::NewAgentInstance {
                agent_instance_id: Uuid::new_v4(),
                space_id: space,
                template_id: Uuid::new_v4(),
                source_runtime_id: "fixture".into(),
                source_agent_id: "custom".into(),
                logical_name: None,
                display_name: format!("Private agent {space}"),
                description: None,
                enabled: true,
                created_by: owner.into(),
                tuning: json!({"selected_capability_ids":[capability]}),
            },
        )
        .await
        .unwrap();
        private_values.extend([
            record.agent_instance_id.to_string(),
            record.display_name,
            space.to_string(),
        ]);
        let (status, _) = request(
            &app,
            &identity,
            Some("fixture-root"),
            "GET",
            &collection(space),
            Value::Null,
        )
        .await;
        assert!(
            matches!(status, 403 | 404),
            "platform admin gained business visibility: {status}"
        );
    }
    let (status, inventory) = request(
        &app,
        &identity,
        Some("fixture-root"),
        "GET",
        "/platform/mcp-connections",
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{inventory}");
    assert_eq!(inventory[0]["affected_instance_count"], 3);
    assert!(inventory[0].get("affected_instances").is_none());
    let response = inventory.to_string();
    for private in private_values {
        assert!(!response.contains(&private), "business information leaked");
    }
    for field in [
        "agent_instance_id",
        "space_id",
        "space_name",
        "space_kind",
        "owner_name",
    ] {
        assert!(!response.contains(field));
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn withdrawal_after_provisioning_removal_preserves_role_revision_and_validation() {
    let e = env().await;
    org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let auth = Arc::new(identity.auth().await);
    let configured_app = |credentials| {
        let mut config = catalog.config();
        config.mcp_credentials = credentials;
        routes(AppState {
            pool: e.pool.clone(),
            agent_catalog: config,
            auth: auth.clone(),
            directory: Some(identity.directory()),
            content: None,
            processing: None,
            onboarding: Default::default(),
            lifecycle: Default::default(),
        })
    };
    let provisioned = configured_app(vec![control_plane::mcp_connections::McpCredentialBinding {
        credential_binding: "withdrawn".into(),
        url: "https://tools.invalid/mcp".into(),
        secret_env: "UNUSED_FIXTURE_MCP_SECRET".into(),
    }]);
    let (status, created) = request(&provisioned, &identity, Some("fixture-root"), "POST", "/platform/mcp-connections",
        json!({"logical_name":"withdrawal", "display_name":"Tools", "description":"", "configuration":{
            "url":"https://tools.invalid/mcp", "authentication":{"kind":"bearer", "credential_binding":"withdrawn"}}})).await;
    assert_eq!(status, 201, "{created}");
    let path = format!(
        "/platform/mcp-connections/{}",
        created["id"].as_str().unwrap()
    );
    let mut edit = json!({"expected_revision":created["revision"], "display_name":"Tools", "description":"",
        "configuration":created["configuration"], "enabled":true});
    let (status, enabled) = request(
        &provisioned,
        &identity,
        Some("fixture-root"),
        "PUT",
        &path,
        edit.clone(),
    )
    .await;
    assert_eq!(status, 200, "{enabled}");
    assert_eq!(enabled["enabled"], true);
    let withdrawn = configured_app(vec![]);
    edit["enabled"] = json!(false);
    assert_eq!(
        request(
            &withdrawn,
            &identity,
            Some("fixture-root"),
            "PUT",
            &path,
            edit.clone()
        )
        .await
        .0,
        409
    );
    edit["expected_revision"] = enabled["revision"].clone();
    assert_eq!(
        request(
            &withdrawn,
            &identity,
            Some("alice"),
            "PUT",
            &path,
            edit.clone()
        )
        .await
        .0,
        403
    );
    let mut invalid = edit.clone();
    invalid["configuration"]["url"] = json!("https://different.invalid/mcp");
    assert_eq!(
        request(
            &withdrawn,
            &identity,
            Some("fixture-root"),
            "PUT",
            &path,
            invalid
        )
        .await
        .0,
        422
    );
    let mut invalid = edit.clone();
    invalid["display_name"] = json!("");
    assert_eq!(
        request(
            &withdrawn,
            &identity,
            Some("fixture-root"),
            "PUT",
            &path,
            invalid
        )
        .await
        .0,
        422
    );
    let (status, disabled) = request(
        &withdrawn,
        &identity,
        Some("fixture-root"),
        "PUT",
        &path,
        edit.clone(),
    )
    .await;
    assert_eq!(status, 200, "{disabled}");
    assert_eq!(disabled["enabled"], false);
    assert_eq!(disabled["available"], false);
    assert_eq!(disabled["configuration"], enabled["configuration"]);
    assert_eq!(
        disabled["revision"].as_i64().unwrap(),
        enabled["revision"].as_i64().unwrap() + 1
    );
    edit["expected_revision"] = disabled["revision"].clone();
    edit["enabled"] = json!(true);
    assert_eq!(
        request(
            &withdrawn,
            &identity,
            Some("fixture-root"),
            "PUT",
            &path,
            edit
        )
        .await
        .0,
        422
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn fixed_graph_tabular_requires_its_central_offer_and_preserves_configuration() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let owner = "mcp-knowledge-flow-mcp-tabular";
    {
        let mut state = catalog.state.lock().await;
        state.templates[0]["kind"] = json!("graph");
        state.templates[0]["supports_capabilities"] = json!(false);
        state.templates[0]["supports_managed_mcp"] = json!(true);
        state.templates[0]["default_capability_ids"] = json!([owner]);
        state.templates[0]["available_capabilities"] = json!([{"id":owner,"mcp_service":"knowledge_flow_tabular","version":"1","config_fields":[]}]);
    }
    let mut config = catalog.config();
    config.knowledge_flow_url = Some("https://kf.invalid/api".into());
    let app = routes(AppState {
        pool: e.pool.clone(),
        agent_catalog: config,
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    });
    let template = enable(&e, org.id, "custom", true).await;
    let body = creation(template, "Included Tabular");
    let templates_path = format!("/spaces/{}/agent-templates", team.id);
    // No connection: declaration alone neither enrolls nor grants access.
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
    let (_, templates) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &templates_path,
        Value::Null,
    )
    .await;
    let summary = templates
        .as_array()
        .unwrap()
        .iter()
        .find(|row| row["template_id"] == template.to_string())
        .unwrap();
    assert_eq!(summary["status"], "dependency_unavailable");
    let connection = publish_configured_fixture(
        &e,
        &app,
        &identity,
        json!({"url":"","authentication":{"kind":"knowledge_flow_tabular"}}),
    )
    .await;
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
    let id = connection["id"].as_str().unwrap();
    let capability = format!("managed-mcp:{id}");
    let policy = format!(
        "/organizations/{}/capabilities/$mcp/{capability}/default-on",
        org.id
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &policy,
            json!({"default_on":true})
        )
        .await
        .0,
        204
    );
    let (_, templates) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &templates_path,
        Value::Null,
    )
    .await;
    let summary = templates
        .as_array()
        .unwrap()
        .iter()
        .find(|row| row["template_id"] == template.to_string())
        .unwrap();
    assert_eq!(summary["status"], "available");
    assert_eq!(summary["supports_capabilities"], false);
    assert_eq!(summary["supports_managed_mcp"], true);
    assert_eq!(summary["default_capability_ids"], json!([capability]));
    assert_eq!(
        summary["available_capabilities"].as_array().unwrap().len(),
        1
    );
    let instance = create(&app, &identity, team.id, body.clone()).await;
    let path = item(team.id, &instance);
    // Configuration-only edits and an empty submitted selection cannot remove the default.
    for patch in [
        json!({"capability_config_values":{capability.clone():{"chat_options.attach_files":true}}}),
        json!({"capability_ids":[]}),
    ] {
        let (status, edited) = request(&app, &identity, Some("alice"), "PATCH", &path, patch).await;
        assert_eq!(status, 200, "{edited}");
        assert_eq!(edited["selected_capability_ids"], json!([capability]));
    }
    let runtime_path = format!("{path}/runtime");
    let (status, admitted) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &runtime_path,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{admitted}");
    assert_eq!(admitted["mcp_bindings"][0]["connection_id"], id);
    assert_eq!(
        admitted["agent"]["configuration"]["capability_config"][&capability]["config"]["chat_options.attach_files"],
        true
    );
    let arbitrary = format!("managed-mcp:{}", Uuid::new_v4());
    let mut invalid = body.clone();
    invalid["capability_ids"] = json!([capability, arbitrary]);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &collection(team.id),
            invalid
        )
        .await
        .0,
        422
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &path,
            json!({"capability_ids":[capability,arbitrary]})
        )
        .await
        .0,
        422
    );
    // Even the authorized connection is arbitrary on a fixed template that no longer declares it.
    catalog.state.lock().await.templates[0]["default_capability_ids"] = json!([]);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &runtime_path,
            Value::Null
        )
        .await
        .0,
        422
    );
    catalog.state.lock().await.templates[0]["default_capability_ids"] = json!([owner]);
    for allowed in [false, true] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &policy,
                json!({"default_on":allowed})
            )
            .await
            .0,
            204
        );
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "GET",
                &runtime_path,
                Value::Null
            )
            .await
            .0,
            if allowed { 200 } else { 422 }
        );
    }
    let local = format!("/spaces/{}/capability-policies/$mcp", team.id);
    for (revision, restricted) in [(0, true), (1, false)] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &local,
                json!({"expected_revision":revision,"restricted":restricted,"permitted_ids":[]})
            )
            .await
            .0,
            204
        );
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "GET",
                &runtime_path,
                Value::Null
            )
            .await
            .0,
            if restricted { 422 } else { 200 }
        );
    }
    assert_eq!(request(&app,&identity,Some("fixture-root"),"PUT",&format!("/platform/mcp-connections/{id}"),json!({"expected_revision":connection["revision"],"display_name":"Tabular","description":"Included","configuration":connection["configuration"],"enabled":false})).await.0,200);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &runtime_path,
            Value::Null
        )
        .await
        .0,
        422
    );
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
    let (_, templates) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &templates_path,
        Value::Null,
    )
    .await;
    let summary = templates
        .as_array()
        .unwrap()
        .iter()
        .find(|row| row["template_id"] == template.to_string())
        .unwrap();
    assert_eq!(summary["status"], "dependency_unavailable");
}
