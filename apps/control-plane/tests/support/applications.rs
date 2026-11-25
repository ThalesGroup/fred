// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use axum::{
    Router,
    body::{Body, to_bytes},
    extract::Request,
    http::header,
    response::IntoResponse,
    routing::any,
};
use control_plane::api::{self, AppState};
use serde_json::{Value, json};
use std::sync::Arc;
use support::request;
use tower::ServiceExt;

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn hosted_applications_registration_governance_and_proxy() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
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
    let other = support::member_organization(&e.pool, "Other applications", "bob")
        .await
        .unwrap();
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    for (user, role) in [
        ("analyst", Role::Analyst),
        ("editor", Role::Editor),
        ("member", Role::Member),
    ] {
        spaces::grant(&e.pool, &e.subjects(), "alice", org.id, Role::Member, user)
            .await
            .unwrap();
        spaces::grant(&e.pool, &e.subjects(), "alice", team.id, role, user)
            .await
            .unwrap();
    }
    authorization::write_platform(
        &mut e.pool.acquire().await.unwrap(),
        "feature-manager",
        control_plane::roles::PlatformRole::FeatureManager,
        true,
    )
    .await
    .unwrap();
    authorization::write_role(
        &mut e.pool.acquire().await.unwrap(),
        "admin",
        Role::OrganizationAdmin,
        org.id,
        true,
    )
    .await
    .unwrap();
    let identity = support::IdentityServer::start().await;
    let state = AppState {
        history: None,
        pool: e.pool.clone(),
        agent_catalog: Default::default(),
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    };
    let app = api::routes(state.clone());
    let public = api::router(state, "/control-plane/v1", &[]);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base = format!("http://{}/", listener.local_addr().unwrap());
    let upstream = tokio::spawn(async move {
        axum::serve(listener,Router::new().fallback(any(|req: Request| async move {
            if req.uri().path().ends_with("redirect") {
                return (axum::http::StatusCode::FOUND,[(header::LOCATION,"https://unapproved.invalid/")],"redirect").into_response();
            }
            if req.uri().path().ends_with("binary") {
                return ([(header::CONTENT_TYPE,"application/octet-stream"),(header::SET_COOKIE,"forbidden=1")],vec![0u8,255,1,128]).into_response();
            }
            let uri=req.uri().to_string();
            let headers=req.headers().clone();
            let bytes=to_bytes(req.into_body(),1024*1024).await.unwrap();
            axum::Json(json!({"uri":uri,"authorization":headers.get("authorization").and_then(|v|v.to_str().ok()),"cookie":headers.get("cookie").and_then(|v|v.to_str().ok()),"forwarded":headers.get("x-forwarded-host").and_then(|v|v.to_str().ok()),"bytes":bytes.len()})).into_response()
        }))).await.unwrap();
    });
    let create = json!({"logical_name":"evaluation","display_name":"Evaluation","display_name_by_lang":{"fr":"Évaluation"},"description":"Evaluation service","icon":"science","ui_base_url":format!("{base}apps/evaluation/"),"api_base_url":format!("{base}api/"),"entry_permission":"run_evaluations"});
    for (actor, expected) in [
        ("fixture-root", 404),
        ("feature-manager", 404),
        ("bob", 404),
        ("member", 403),
        ("admin", 403),
    ] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some(actor),
                "POST",
                &format!("/organizations/{}/applications", org.id),
                create.clone()
            )
            .await
            .0,
            expected,
            "{actor}"
        );
        assert_eq!(
            request(
                &app,
                &identity,
                Some(actor),
                "GET",
                &format!("/organizations/{}/applications", org.id),
                Value::Null
            )
            .await
            .0,
            expected,
            "{actor}"
        );
    }
    let (status, created) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!("/organizations/{}/applications", org.id),
        create.clone(),
    )
    .await;
    assert_eq!(status, 201, "{created}");
    assert_eq!(created["enabled"], false);
    assert_eq!(created["version"], "1.0.0");
    assert_eq!(created["organization_id"], org.id.to_string());
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &format!("/organizations/{}/applications", org.id),
            create.clone()
        )
        .await
        .0,
        409
    );
    let id = created["id"].as_str().unwrap();
    let capability = created["capability_id"].as_str().unwrap();
    let registry = format!("/organizations/{}/applications/{id}", org.id);
    let team_policy = format!("/spaces/{}/capability-policies/$applications", team.id);
    let project_policy = format!("/spaces/{}/capability-policies/$applications", project.id);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("/spaces/{}/applications", team.id),
            Value::Null
        )
        .await
        .1,
        json!([])
    );
    let mut update = create.clone();
    update.as_object_mut().unwrap().remove("logical_name");
    update["expected_revision"] = json!(1);
    update["enabled"] = json!(true);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("feature-manager"),
            "PUT",
            &registry,
            update.clone()
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
            &registry,
            update.clone()
        )
        .await
        .0,
        200
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &registry,
            update.clone()
        )
        .await
        .0,
        409
    );
    for space in [org.id, team.id, project.id] {
        let (status, list) = request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("/spaces/{space}/applications"),
            Value::Null,
        )
        .await;
        assert_eq!(status, 200, "{list}");
        assert_eq!(list[0]["logical_name"], "evaluation");
        assert_eq!(list[0]["ui_path"], format!("/apps/{id}/"));
        assert!(list[0].get("ui_base_url").is_none());
    }
    for actor in ["member", "editor"] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some(actor),
                "GET",
                &format!("/spaces/{}/applications", team.id),
                Value::Null
            )
            .await
            .1,
            json!([])
        );
    }
    assert_eq!(
        request(
            &app,
            &identity,
            Some("analyst"),
            "GET",
            &format!("/spaces/{}/applications", team.id),
            Value::Null
        )
        .await
        .1[0]["logical_name"],
        "evaluation"
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("/spaces/{}/applications", personal.id),
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
            Some("bob"),
            "GET",
            &format!("/spaces/{}/applications", other.id),
            Value::Null
        )
        .await
        .1,
        json!([])
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "GET",
            &format!("/spaces/{}/applications", team.id),
            Value::Null
        )
        .await
        .0,
        404
    );
    let (_, inventory) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("/organizations/{}/capabilities", org.id),
        Value::Null,
    )
    .await;
    let source = inventory
        .as_array()
        .unwrap()
        .iter()
        .find(|v| v["source_id"] == "$applications")
        .unwrap();
    assert_eq!(source["origin"], "application");
    assert_eq!(source["runtime_id"], Value::Null);
    assert_eq!(
        source["capabilities"][0]["application_logical_name"],
        "evaluation"
    );
    assert_eq!(source["capabilities"][0]["version"], "1.0.0");
    assert!(
        source["capabilities"][0]["descriptor"]
            .get("application_logical_name")
            .is_none()
    );
    assert_eq!(
        source["capabilities"][0]["descriptor"]["kind"],
        "application"
    );
    assert_eq!(source["template_capabilities"], json!([]));
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "select count(*) from runtime_catalog where runtime_id='$applications'"
        )
        .fetch_one(&e.pool)
        .await
        .unwrap(),
        0
    );
    // An inheriting project cannot reopen a denied parent ceiling.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &team_policy,
            json!({"expected_revision":0,"restricted":true,"permitted_ids":[]})
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
            "PUT",
            &project_policy,
            json!({"expected_revision":0,"restricted":true,"permitted_ids":[capability]})
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
            &format!("/spaces/{}/applications", project.id),
            Value::Null
        )
        .await
        .1,
        json!([])
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &team_policy,
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
            &team_policy,
            json!({"expected_revision":1,"restricted":false,"permitted_ids":[]})
        )
        .await
        .0,
        204
    );
    // Each organization has a dedicated deployment, even for the same SDK key.
    let other_registry = format!("/organizations/{}/applications", other.id);
    let mut other_create = create.clone();
    other_create["ui_base_url"] = json!(format!("{base}other-ui/"));
    other_create["api_base_url"] = Value::Null;
    let (status, denied) = request(
        &app,
        &identity,
        Some("bob"),
        "POST",
        &other_registry,
        other_create.clone(),
    )
    .await;
    assert_eq!(status, 409, "{denied}");
    assert_eq!(denied["code"], "application_service_owned");
    let other_listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let other_base = format!("http://{}/", other_listener.local_addr().unwrap());
    let other_upstream = tokio::spawn(async move {
        axum::serve(
            other_listener,
            Router::new().fallback(any(|req: Request| async move {
                axum::Json(json!({"uri":req.uri().to_string()}))
            })),
        )
        .await
        .unwrap();
    });
    other_create["ui_base_url"] = json!(format!("{other_base}other-ui/"));
    // Switching a UI origin into the API field must not bypass ownership.
    other_create["api_base_url"] = create["ui_base_url"].clone();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "POST",
            &other_registry,
            other_create.clone()
        )
        .await
        .0,
        409
    );
    other_create["api_base_url"] = json!(format!("{other_base}other-api/"));
    let (status, other_app) = request(
        &app,
        &identity,
        Some("bob"),
        "POST",
        &other_registry,
        other_create.clone(),
    )
    .await;
    assert_eq!(status, 201, "{other_app}");
    assert_ne!(other_app["id"], created["id"]);
    let other_id = other_app["id"].as_str().unwrap();
    let other_capability = other_app["capability_id"].as_str().unwrap();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "GET",
            &other_registry,
            Value::Null
        )
        .await
        .1,
        json!([other_app])
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "PUT",
            &format!("{other_registry}/{id}"),
            update.clone()
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
            &other_registry,
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
            "PUT",
            &format!(
                "/organizations/{}/capabilities/$applications/{capability}/default-on",
                other.id
            ),
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
            &team_policy,
            json!({"expected_revision":2,"restricted":true,"permitted_ids":[other_capability]})
        )
        .await
        .0,
        422
    );
    let (_, other_inventory) = request(
        &app,
        &identity,
        Some("bob"),
        "GET",
        &format!("/organizations/{}/capabilities", other.id),
        Value::Null,
    )
    .await;
    let other_offers = other_inventory
        .as_array()
        .unwrap()
        .iter()
        .find(|source| source["source_id"] == "$applications")
        .unwrap();
    assert_eq!(other_offers["capabilities"].as_array().unwrap().len(), 1);
    assert_eq!(
        other_offers["capabilities"][0]["capability_id"],
        other_capability
    );
    let error = sqlx::query("insert into organization_capability(organization_id,source_id,capability_id,enabled_by) values($1,'$applications',$2,'bob')").bind(other.id).bind(capability).execute(&e.pool).await.unwrap_err();
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some("23514")
    );
    let mut other_update = other_create;
    other_update.as_object_mut().unwrap().remove("logical_name");
    other_update["expected_revision"] = json!(1);
    other_update["enabled"] = json!(true);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "PUT",
            &format!("{other_registry}/{other_id}"),
            other_update
        )
        .await
        .0,
        200
    );
    let (status, echo) = request(
        &public,
        &identity,
        Some("bob"),
        "GET",
        &format!("/app-services/evaluation/teams/{}/runs", other.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{echo}");
    assert_eq!(echo["uri"], format!("/other-api/teams/{}/runs", other.id));
    assert_eq!(
        request(
            &public,
            &identity,
            None,
            "GET",
            &format!("/apps/{other_id}/asset.js"),
            Value::Null
        )
        .await
        .1["uri"],
        "/other-ui/asset.js"
    );
    let error = sqlx::query("update application set organization_id=$2 where id=$1")
        .bind(Uuid::parse_str(id).unwrap())
        .bind(other.id)
        .execute(&e.pool)
        .await
        .unwrap_err();
    assert_eq!(
        error.as_database_error().unwrap().code().as_deref(),
        Some("23514")
    );
    let api_path = format!("/app-services/evaluation/teams/{}/runs?q=1", team.id);
    let (status, echo) = request(
        &public,
        &identity,
        Some("analyst"),
        "POST",
        &api_path,
        json!({"test":true}),
    )
    .await;
    assert_eq!(status, 200, "{echo}");
    assert_eq!(echo["uri"], format!("/api/teams/{}/runs?q=1", team.id));
    assert!(
        echo["authorization"]
            .as_str()
            .unwrap()
            .starts_with("Bearer ")
    );
    assert_eq!(
        request(
            &public,
            &identity,
            Some("member"),
            "GET",
            &api_path,
            Value::Null
        )
        .await
        .0,
        403
    );
    assert_eq!(
        request(&public, &identity, None, "GET", &api_path, Value::Null)
            .await
            .0,
        401
    );
    let (status, echo) = support::request_with_headers(
        &public,
        &identity,
        Some("analyst"),
        "GET",
        &format!("/apps/{id}/assets/app.js"),
        Value::Null,
        &[
            ("cookie", "secret=1".into()),
            ("x-forwarded-host", "evil".into()),
        ],
    )
    .await;
    assert_eq!(status, 200, "{echo}");
    assert_eq!(echo["uri"], "/apps/evaluation/assets/app.js");
    assert_eq!(echo["authorization"], Value::Null);
    assert_eq!(echo["cookie"], Value::Null);
    assert_eq!(echo["forwarded"], Value::Null);
    assert_eq!(
        request(
            &public,
            &identity,
            None,
            "GET",
            &format!("/apps/{id}/redirect"),
            Value::Null
        )
        .await
        .0,
        503
    );
    for path in [
        format!("/apps/{id}/%2e%2e/private"),
        format!("/apps/{id}/x%2fy"),
        format!("/apps/{id}/%252e%252e/private"),
    ] {
        assert_eq!(
            request(&public, &identity, None, "GET", &path, Value::Null)
                .await
                .0,
            400,
            "{path}"
        );
    }
    let response = public
        .clone()
        .oneshot(
            axum::http::Request::builder()
                .uri(format!("/apps/{id}/binary"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), 200);
    assert!(response.headers().get(header::SET_COOKIE).is_none());
    assert_eq!(
        to_bytes(response.into_body(), 1024).await.unwrap().as_ref(),
        &[0, 255, 1, 128]
    );
    // Static-only applications remain usable without manufacturing an API target.
    update["expected_revision"] = json!(2);
    update["api_base_url"] = Value::Null;
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &registry,
            update.clone()
        )
        .await
        .0,
        200
    );
    assert_eq!(
        request(
            &public,
            &identity,
            Some("analyst"),
            "GET",
            &api_path,
            Value::Null
        )
        .await
        .0,
        404
    );
    update["expected_revision"] = json!(3);
    update["enabled"] = json!(false);
    assert_eq!(
        request(&app, &identity, Some("alice"), "PUT", &registry, update)
            .await
            .0,
        200
    );
    assert_eq!(
        request(
            &public,
            &identity,
            None,
            "GET",
            &format!("/apps/{id}/"),
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
            &format!("/spaces/{}/applications", team.id),
            Value::Null
        )
        .await
        .1,
        json!([])
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "select count(*) from organization_capability where source_id='$applications' and organization_id=$1"
        )
        .bind(org.id)
        .fetch_one(&e.pool)
        .await
        .unwrap(),
        0
    );
    // SQL protects identity and typed provenance independently of the HTTP writer.
    for statement in [
        "update application set logical_name='changed' where id=$1",
        "update capability_offer set descriptor='{}' where application_id=$1",
        "update capability_offer set application_id=null where application_id=$1",
    ] {
        let error = sqlx::query(sqlx::AssertSqlSafe(statement))
            .bind(Uuid::parse_str(id).unwrap())
            .execute(&e.pool)
            .await
            .unwrap_err();
        assert_eq!(
            error.as_database_error().unwrap().code().as_deref(),
            Some("23514")
        );
    }
    // Organization purge owns the registry and its offer/permission projections.
    sqlx::query("delete from space where id=$1")
        .bind(other.id)
        .execute(&e.pool)
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, i64>(
            "select count(*) from capability_offer where application_id=$1"
        )
        .bind(Uuid::parse_str(other_id).unwrap())
        .fetch_one(&e.pool)
        .await
        .unwrap(),
        0
    );
    assert_eq!(
        request(
            &public,
            &identity,
            None,
            "GET",
            &format!("/apps/{other_id}/"),
            Value::Null
        )
        .await
        .0,
        404
    );
    other_upstream.abort();
    upstream.abort();
}
