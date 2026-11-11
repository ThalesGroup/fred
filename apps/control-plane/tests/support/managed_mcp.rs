// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

async fn publish_fixture(
    e: &Env,
    app: &Router,
    identity: &support::IdentityServer,
    space_id: Uuid,
) -> Value {
    publish_configured_fixture(
        e,
        app,
        identity,
        space_id,
        json!({"url":"https://tools.invalid/mcp","authentication":{"kind":"none"}}),
    )
    .await
}

async fn publish_configured_fixture(
    e: &Env,
    app: &Router,
    identity: &support::IdentityServer,
    space_id: Uuid,
    configuration: Value,
) -> Value {
    let body = json!({"logical_name":"tool","display_name":"Central tools","description":"Shared endpoint",
        "configuration": configuration});
    let (status, denied) = request(
        app,
        identity,
        Some("fixture-root"),
        "POST",
        &format!("/spaces/{space_id}/mcp-connections"),
        body.clone(),
    )
    .await;
    assert_eq!(status, 404, "{denied}"); // Platform administration confers no space management.
    let (status, created) = request(
        app,
        identity,
        Some("alice"),
        "POST",
        &format!("/spaces/{space_id}/mcp-connections"),
        body,
    )
    .await;
    assert_eq!(status, 201, "{created}");
    assert_eq!(created["available"], false);
    assert_eq!(created["enabled"], false);
    assert_eq!(created["tool_changes"], Value::Null);
    let id = created["id"].as_str().unwrap();
    let tools = json!([{"name":"search","description":"Find","input_schema":{"type":"object"},"output_schema":null,"annotations":null}]);
    // Discovery has its own local HTTP test. This fixture establishes its successful observation.
    sqlx::query("update mcp_connection set observed_tools=$2,observation_state='available',observation_revision=revision,checked_at=clock_timestamp() where id=$1")
        .bind(Uuid::parse_str(id).unwrap()).bind(tools).execute(&e.pool).await.unwrap();
    let (_, list) = request(
        app,
        identity,
        Some("alice"),
        "GET",
        &format!("/spaces/{space_id}/mcp-connections"),
        Value::Null,
    )
    .await;
    assert_eq!(
        list[0]["tool_changes"],
        json!({"added":["search"],"modified":[],"removed":[]})
    );
    let (status, published) = request(
        app,
        identity,
        Some("alice"),
        "POST",
        &format!("/spaces/{space_id}/mcp-connections/{id}/publish"),
        json!({"expected_revision":1,"expected_checked_at":list[0]["checked_at"]}),
    )
    .await;
    assert_eq!(status, 200, "{published}");
    assert_eq!(
        published["tool_changes"],
        json!({"added":[],"modified":[],"removed":[]})
    );
    let (status,enabled)=request(app,identity,Some("alice"),"PUT",&format!("/spaces/{space_id}/mcp-connections/{id}"),
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
    let space_id = org.id;
    grant(&e, team.id, Role::Editor, "alice").await;
    let other = support::member_organization(&e.pool, "Other MCP organization", "alice")
        .await
        .unwrap();
    let identity = support::IdentityServer::start().await;
    identity
        .users
        .lock()
        .await
        .insert("alice".into(), "Alice Martin".into());
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
            space_id,
            json!({"url":"", "authentication":{"kind":"knowledge_flow_tabular"}}),
        )
        .await
    } else {
        publish_fixture(&e, &app, &identity, space_id).await
    };
    let foreign = publish_configured_fixture(
        &e,
        &app,
        &identity,
        other.id,
        connection["configuration"].clone(),
    )
    .await;
    assert_ne!(connection["id"], foreign["id"]);
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
            let (status, _) = request(&app, &identity, Some("alice"), "POST", &format!("/spaces/{space_id}/mcp-connections"), json!({
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
        404
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
        assert_eq!(
            instance["selected_capability_names"],
            json!({capability.clone(): "Central tools"})
        );
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
    // A team role is sufficient for use; no direct organization role is required.
    sqlx::query("insert into space_role_grant(space_id,subject,role) values($1,'bob','editor')")
        .bind(team.id)
        .execute(&e.pool)
        .await
        .unwrap();
    assert!(!reads(&e, "bob", org.id).await);
    for (runtime, _) in &instances {
        assert_eq!(
            request(&app, &identity, Some("bob"), "GET", runtime, Value::Null)
                .await
                .0,
            200
        );
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
            request(&app, &identity, Some("bob"), "GET", runtime, Value::Null)
                .await
                .0,
            422
        );
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
    let (status, next_connection) = request(&app, &identity, Some("alice"), "PUT", &format!("/spaces/{space_id}/mcp-connections/{id}"),
        json!({"expected_revision":connection["revision"],"display_name":"Renamed centrally","description":"Shared endpoint","configuration":connection["configuration"],"enabled":true})).await;
    assert_eq!(status, 200, "{next_connection}");
    assert_eq!(next_connection["capability_id"], capability);
    identity.control.lock().await.subject_lookups.clear();
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
    assert_eq!(identity.control.lock().await.subject_lookups, vec!["alice"]);
    for item in list["items"].as_array().unwrap() {
        assert_eq!(item["created_by_name"], "Alice Martin");
        assert_eq!(item["updated_by_name"], "Alice Martin");
    }

    assert_eq!(
        list["items"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|item| item["selected_capability_names"][&capability] == "Renamed centrally")
            .count(),
        2
    );
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
    identity.users.lock().await.remove("alice");
    let (status, missing_author) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        instances[0].0.strip_suffix("/runtime").unwrap(),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{missing_author}");
    assert_eq!(missing_author["created_by_name"], Value::Null);
    assert_eq!(missing_author["created_by"], "alice");
    identity
        .users
        .lock()
        .await
        .insert("alice".into(), "Alice Martin".into());
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
            Some("alice"),
            "PUT",
            &format!("/spaces/{space_id}/mcp-connections/{id}"),
            edit.clone()
        )
        .await
        .0,
        200
    );
    // A withdrawn connection is still named from its canonical offer, without enabling it.
    let (status, detail) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        instances[1].0.strip_suffix("/runtime").unwrap(),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{detail}");
    assert_eq!(
        detail["selected_capability_names"],
        json!({capability.clone(): "Central tools"})
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
            Some("alice"),
            "PUT",
            &format!("/spaces/{space_id}/mcp-connections/{id}"),
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
    sqlx::query("delete from mcp_connection where id=$1")
        .bind(Uuid::parse_str(id).unwrap())
        .execute(&e.pool)
        .await
        .unwrap();
    let remaining: i64 =
        sqlx::query_scalar("select count(*) from capability_offer where connection_id=$1")
            .bind(Uuid::parse_str(id).unwrap())
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(remaining, 0);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn slow_discovery_cannot_overwrite_a_new_destination() {
    use axum::{http::StatusCode, response::IntoResponse};
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let space_id = org.id;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let application = app(&e, &identity, &catalog).await;
    let connection = publish_fixture(&e, &application, &identity, space_id).await;
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
        "/spaces/{space_id}/mcp-connections/{}",
        connection["id"].as_str().unwrap()
    );
    let mut edit = json!({"expected_revision":connection["revision"],"display_name":"Central tools","description":"Shared endpoint","enabled":true,
        "configuration":{"url":endpoint,"allow_insecure_http":true,"authentication":{"kind":"none"}}});
    let (status, current) = request(
        &application,
        &identity,
        Some("alice"),
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
        Some("alice"),
        "POST",
        &test_path,
        json!({"expected_revision":current["revision"]}),
    );
    let replace = async {
        gate.entered.notified().await;
        edit["expected_revision"] = current["revision"].clone();
        edit["configuration"] = connection["configuration"].clone();
        let result = request(&application, &identity, Some("alice"), "PUT", &path, edit).await;
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
        Some("alice"),
        "POST",
        &format!("{path}/publish"),
        json!({"expected_revision":new["revision"],"expected_checked_at":connection["checked_at"]}),
    )
    .await;
    assert_eq!(status, 409);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn impact_counts_only_the_owning_organization() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let space_id = org.id;
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
    let connection = publish_fixture(&e, &app, &identity, space_id).await;
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
        Some("alice"),
        "GET",
        &format!("/spaces/{space_id}/mcp-connections"),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{inventory}");
    assert_eq!(inventory[0]["affected_instance_count"], 2);
    assert!(inventory[0].get("affected_instances").is_none());
    let response = inventory.to_string();
    for private in private_values {
        assert!(!response.contains(&private), "business information leaked");
    }
    for field in [
        "agent_instance_id",
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
    let (org, _) = org_and_team(&e).await;
    let space_id = org.id;
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
        space_id,
        credential_binding: "withdrawn".into(),
        url: "https://tools.invalid/mcp".into(),
        secret_env: "UNUSED_FIXTURE_MCP_SECRET".into(),
    }]);
    let (status, created) = request(&provisioned, &identity, Some("alice"), "POST", &format!("/spaces/{space_id}/mcp-connections"),
        json!({"logical_name":"withdrawal", "display_name":"Tools", "description":"", "configuration":{
            "url":"https://tools.invalid/mcp", "authentication":{"kind":"bearer", "credential_binding":"withdrawn"}}})).await;
    assert_eq!(status, 201, "{created}");
    let path = format!(
        "/spaces/{space_id}/mcp-connections/{}",
        created["id"].as_str().unwrap()
    );
    let mut edit = json!({"expected_revision":created["revision"], "display_name":"Tools", "description":"",
        "configuration":created["configuration"], "enabled":true});
    let (status, enabled) = request(
        &provisioned,
        &identity,
        Some("alice"),
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
            Some("alice"),
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
            Some("fixture-root"),
            "PUT",
            &path,
            edit.clone()
        )
        .await
        .0,
        404
    );
    let mut invalid = edit.clone();
    invalid["configuration"]["url"] = json!("https://different.invalid/mcp");
    assert_eq!(
        request(&withdrawn, &identity, Some("alice"), "PUT", &path, invalid)
            .await
            .0,
        422
    );
    let mut invalid = edit.clone();
    invalid["display_name"] = json!("");
    assert_eq!(
        request(&withdrawn, &identity, Some("alice"), "PUT", &path, invalid)
            .await
            .0,
        422
    );
    let (status, disabled) = request(
        &withdrawn,
        &identity,
        Some("alice"),
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
        request(&withdrawn, &identity, Some("alice"), "PUT", &path, edit)
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
    let space_id = org.id;
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
        space_id,
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
    assert_eq!(request(&app,&identity,Some("alice"),"PUT",&format!("/spaces/{space_id}/mcp-connections/{id}"),json!({"expected_revision":connection["revision"],"display_name":"Tabular","description":"Included","configuration":connection["configuration"],"enabled":false})).await.0,200);
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

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn space_ownership_isolates_management_credentials_catalogs_and_purge() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    grant(&e, org.id, Role::Editor, "alice").await;
    let other = support::member_organization(&e.pool, "Other owner", "alice")
        .await
        .unwrap();
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    catalog.state.lock().await.templates[0]["supports_managed_mcp"] = json!(true);
    let mut config = catalog.config();
    config.knowledge_flow_url = Some("https://kf.invalid/api".into());
    config.mcp_credentials = vec![control_plane::mcp_connections::McpCredentialBinding {
        space_id: other.id,
        credential_binding: "other-secret".into(),
        url: "https://tools.invalid/mcp".into(),
        secret_env: "UNUSED_FIXTURE_MCP_SECRET".into(),
    }];
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
    let a = publish_fixture(&e, &app, &identity, org.id).await;
    let b = publish_fixture(&e, &app, &identity, other.id).await;
    assert_eq!(a["logical_name"], b["logical_name"]);
    assert_ne!(a["id"], b["id"]);
    let foreign = b["id"].as_str().unwrap();
    let capability = format!("managed-mcp:{foreign}");
    let collection_path = format!("/spaces/{}/mcp-connections", org.id);
    let edit = json!({"expected_revision":b["revision"],"display_name":"Foreign","description":"", "configuration":b["configuration"],"enabled":false});
    for (method, path, body) in [
        ("PUT", format!("{collection_path}/{foreign}"), edit),
        (
            "POST",
            format!("{collection_path}/{foreign}/test"),
            json!({"expected_revision":b["revision"]}),
        ),
        (
            "POST",
            format!("{collection_path}/{foreign}/publish"),
            json!({"expected_revision":b["revision"],"expected_checked_at":b["checked_at"]}),
        ),
    ] {
        let (status, response) = request(&app, &identity, Some("alice"), method, &path, body).await;
        assert_eq!(status, 404, "{response}");
    }
    let (_, listed) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &collection_path,
        Value::Null,
    )
    .await;
    assert_eq!(listed.as_array().unwrap().len(), 1);
    assert_eq!(listed[0]["id"], a["id"]);
    let (_, credentials) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("/spaces/{}/mcp-credentials", org.id),
        Value::Null,
    )
    .await;
    assert_eq!(credentials, json!([]));
    let (status, _) = request(&app, &identity, Some("alice"), "POST", &collection_path,
        json!({"logical_name":"foreign-secret","display_name":"Foreign","description":"", "configuration":{"url":"https://tools.invalid/mcp","authentication":{"kind":"bearer","credential_binding":"other-secret"}}})).await;
    assert_eq!(status, 422);
    // The public journey rejects team management, even for a direct team Owner.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("/spaces/{}/mcp-connections", team.id),
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
            Some("fixture-root"),
            "GET",
            "/platform/mcp-connections",
            Value::Null
        )
        .await
        .0,
        404
    );
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
        404
    );
    assert!(sqlx::query("insert into organization_capability(organization_id,source_id,capability_id,enabled_by) values($1,'$mcp',$2,'alice')")
        .bind(org.id).bind(&capability).execute(&e.pool).await.is_err());
    sqlx::query(
        "insert into space_role_grant(space_id,subject,role) values($1,'bob','organization_admin')",
    )
    .bind(org.id)
    .execute(&e.pool)
    .await
    .unwrap();
    for (method, path, body) in [
        ("GET", collection_path.clone(), Value::Null),
        (
            "GET",
            format!("/spaces/{}/mcp-credentials", org.id),
            Value::Null,
        ),
        (
            "POST",
            format!("{collection_path}/{}/test", a["id"].as_str().unwrap()),
            json!({"expected_revision":a["revision"]}),
        ),
        (
            "POST",
            format!("{collection_path}/{}/publish", a["id"].as_str().unwrap()),
            json!({"expected_revision":a["revision"],"expected_checked_at":a["checked_at"]}),
        ),
    ] {
        assert_eq!(
            request(&app, &identity, Some("bob"), method, &path, body)
                .await
                .0,
            403
        );
    }
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!(
                "/organizations/{}/capabilities/$mcp/{capability}/revoke-impact",
                org.id
            ),
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
            "PUT",
            &format!("/spaces/{}/capability-policies/$mcp", team.id),
            json!({"expected_revision":0,"restricted":true,"permitted_ids":[capability]})
        )
        .await
        .0,
        422
    );
    let template = enable(&e, org.id, "custom", true).await;
    for path in [
        format!("/organizations/{}/capabilities", org.id),
        format!("/spaces/{}/agent-templates", team.id),
        format!("/spaces/{}/capability-policies", team.id),
    ] {
        let (status, inventory) =
            request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await;
        assert_eq!(status, 200, "{inventory}");
        assert!(!inventory.to_string().contains(foreign));
    }
    let mut body = creation(template, "Foreign selection");
    body["capability_ids"] = json!([capability]);
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
    let instance = create(&app, &identity, team.id, creation(template, "Local agent")).await;
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &item(team.id, &instance),
            json!({"capability_ids":[capability]})
        )
        .await
        .0,
        422
    );
    // Marketplace import keeps the same organization boundary and current policy.
    let own_capability = format!("managed-mcp:{}", a["id"].as_str().unwrap());
    let own_policy = format!(
        "/organizations/{}/capabilities/$mcp/{own_capability}/default-on",
        org.id
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &own_policy,
            json!({"default_on":true})
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
            "PATCH",
            &item(team.id, &instance),
            json!({"capability_ids":[own_capability]})
        )
        .await
        .0,
        200
    );
    let revision = saved(&e, team.id, &instance).await.configuration_revision;
    let proposals = format!("/spaces/{}/marketplace/proposals", org.id);
    let (status, proposal) = support::request_with_headers(&app,&identity,Some("alice"),"POST",&proposals,
        json!({"source_space_id":team.id,"source_resource_id":instance["agent_instance_id"],"kind":"agent","expected_revision":revision.to_string()}),
        &[("Idempotency-Key",Uuid::new_v4().to_string())]).await;
    assert_eq!(status, 200, "{proposal}");
    let decision = format!(
        "{proposals}/{}/decision",
        proposal["proposal_id"].as_str().unwrap()
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &decision,
            json!({"approve":true,"expected_publication_version":0})
        )
        .await
        .0,
        200
    );
    let installation = format!(
        "/spaces/{}/marketplace/entries/{}/installations",
        org.id,
        proposal["entry_id"].as_str().unwrap()
    );
    let install = json!({"proposal_id":proposal["proposal_id"],"destination_space_id":team.id,"options":{"kind":"agent","display_name":"Imported","logical_name":"imported"}});
    let (status, imported) = support::request_with_headers(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &installation,
        install.clone(),
        &[("Idempotency-Key", Uuid::new_v4().to_string())],
    )
    .await;
    assert_eq!(status, 200, "{imported}");
    let (other_personal, _) = spaces::create_personal_space(&e.pool, "alice", other.id)
        .await
        .unwrap();
    let mut foreign_install = install.clone();
    foreign_install["destination_space_id"] = json!(other_personal.id);
    assert_eq!(
        support::request_with_headers(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &installation,
            foreign_install,
            &[("Idempotency-Key", Uuid::new_v4().to_string())]
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
            &own_policy,
            json!({"default_on":false})
        )
        .await
        .0,
        204
    );
    let (status, rejected) = support::request_with_headers(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &installation,
        install,
        &[("Idempotency-Key", Uuid::new_v4().to_string())],
    )
    .await;
    assert_eq!(status, 422, "{rejected}");
    // A corrupted saved selection must still fail at admission.
    sqlx::query("update agent_instance set tuning=jsonb_set(tuning,'{selected_capability_ids}',$2) where agent_instance_id=$1")
        .bind(Uuid::parse_str(instance["agent_instance_id"].as_str().unwrap()).unwrap())
        .bind(json!([capability])).execute(&e.pool).await.unwrap();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("{}/runtime", item(team.id, &instance)),
            Value::Null
        )
        .await
        .0,
        422
    );
    // Each organization can own Tabular without colliding with the other.
    for space in [org.id, other.id] {
        let body = json!({"logical_name":"tabular","display_name":"Tabular","description":"", "configuration":{"url":"","authentication":{"kind":"knowledge_flow_tabular"}}});
        let path = format!("/spaces/{space}/mcp-connections");
        assert_eq!(
            request(&app, &identity, Some("alice"), "POST", &path, body.clone())
                .await
                .0,
            201
        );
        assert_eq!(
            request(&app, &identity, Some("alice"), "POST", &path, body)
                .await
                .0,
            409
        );
    }
    assert!(
        sqlx::query("update mcp_connection set space_id=$2 where id=$1")
            .bind(Uuid::parse_str(foreign).unwrap())
            .bind(org.id)
            .execute(&e.pool)
            .await
            .is_err()
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &format!(
                "/organizations/{}/capabilities/$mcp/{capability}/default-on",
                other.id
            ),
            json!({"default_on":true})
        )
        .await
        .0,
        204
    );
    // Exercise the existing retirement and bounded purge, without external storage.
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    let receipt = lifecycle
        .accept(&e.pool, "fixture-root", other.id, false)
        .await
        .unwrap();
    sqlx::query("update deletion set due_at=clock_timestamp() where id=$1")
        .bind(receipt.id)
        .execute(&e.pool)
        .await
        .unwrap();
    for _ in 0..8 {
        control_plane::lifecycle::cleanup::batch(&e.pool, receipt.id, &Default::default(), None)
            .await
            .unwrap();
    }
    let remaining: (i64, i64, i64) = sqlx::query_as("select (select count(*) from mcp_connection where space_id=$1), (select count(*) from capability_offer where capability_id=$2), (select count(*) from organization_capability where capability_id=$2)")
        .bind(other.id).bind(&capability).fetch_one(&e.pool).await.unwrap();
    assert_eq!(remaining, (0, 0, 0));
    assert_eq!(
        control_plane::lifecycle::store::status(&e.pool, "fixture-root", receipt.id)
            .await
            .unwrap()
            .status,
        control_plane::lifecycle::Status::Completed
    );
}
