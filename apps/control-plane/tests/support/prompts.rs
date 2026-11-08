// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use axum::Router;
use control_plane::api::{AppState, routes};
use serde_json::{Value, json};
use std::sync::Arc;
use support::{IdentityServer, request};

async fn app(e: &Env, identity: &IdentityServer) -> Router {
    routes(AppState {
        pool: e.pool.clone(),
        agent_catalog: Default::default(),
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: control_plane::onboarding::Onboarding {
            gcu_version: Some("prompt-tests".into()),
            ..Default::default()
        },
        lifecycle: Default::default(),
    })
}

async fn admit(e: &Env, actor: &str) {
    control_plane::onboarding::accept(&e.pool, Some("prompt-tests"), actor, "prompt-tests")
        .await
        .unwrap();
}

fn collection(space: Uuid) -> String {
    format!("/spaces/{space}/prompts")
}

fn creation(name: &str) -> Value {
    json!({"logical_name":name,"display_name":"Shared label","text":"Original {{unknown}}"})
}

async fn create(app: &Router, identity: &IdentityServer, space: Uuid, body: Value) -> Value {
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
#[ignore = "needs disposable Postgres: make test-integration"]
async fn prompts_lifecycle_preserves_content_and_server_attribution() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Editor, "bob").await;
    for actor in ["alice", "bob"] {
        admit(&e, actor).await;
    }
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    // Combining accents, multibyte characters, CRLF and template syntax are literal content.
    let text = format!(
        " \t\r\n{{{{unknown}}}} ${{value}} <tag> e\u{301}🙂漢字{}\n ",
        "é🙂".repeat(130)
    );
    let mut body = creation("resume");
    body["text"] = json!(text);
    let mut description = " \r\nDescription {{literal}} e\u{301} ".to_owned();
    description.push_str(&"🙂".repeat(500 - description.chars().count()));
    body["description"] = json!(description);
    body["display_name"] = json!("  Re\u{301}sume\u{301}  ");
    let initial = create(&app, &identity, team.id, body.clone()).await;
    let path = format!(
        "{}/{}",
        collection(team.id),
        initial["prompt_id"].as_str().unwrap()
    );
    assert_eq!(initial["text"], text);
    assert_eq!(initial["description"], body["description"]);
    assert_eq!(initial["display_name"], "Résumé");
    assert_eq!(initial["space_id"], team.id.to_string());
    assert_eq!(initial["created_by"], "alice");
    assert_eq!(initial["updated_by"], "alice");
    assert_eq!(initial["created_at"], initial["updated_at"]);
    assert_eq!(
        request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await,
        (200, initial.clone())
    );
    let (status, page) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &collection(team.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{page}");
    let mut summary = initial.clone();
    summary.as_object_mut().unwrap().remove("text");
    summary["text_preview"] = json!(text.chars().take(240).collect::<String>());
    assert_eq!(page, json!({"items":[summary], "next_cursor":null}));
    body["logical_name"] = json!("other");
    body["description"] = json!("é".repeat(499));
    let other = create(&app, &identity, team.id, body.clone()).await;
    assert_eq!(other["display_name"], initial["display_name"]);
    assert_eq!(other["description"], body["description"]);
    assert_ne!(other["prompt_id"], initial["prompt_id"]);

    for patch in [
        json!({}),
        json!({"display_name":null,"text":null}),
        json!({"text":text}),
    ] {
        assert_eq!(
            request(&app, &identity, Some("bob"), "PATCH", &path, patch.clone()).await,
            (200, initial.clone()),
            "no-op {patch}"
        );
    }
    // Reject immutable/unknown fields even if the supplied value matches the current value.
    for field in [
        "prompt_id",
        "space_id",
        "logical_name",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
        "unknown",
    ] {
        let patch = json!({field: initial.get(field).cloned().unwrap_or(json!("x"))});
        let (status, error) = request(&app, &identity, Some("bob"), "PATCH", &path, patch).await;
        assert_eq!(status, 422, "immutable {field}: {error}");
    }
    for (field, value) in [
        ("text", json!("a\0b")),
        ("description", json!("\0")),
        ("description", json!("🙂".repeat(501))),
        ("display_name", json!("")),
    ] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("bob"),
                "PATCH",
                &path,
                json!({field:value})
            )
            .await
            .0,
            422,
            "invalid {field}"
        );
    }
    for invalid in [
        "",
        "skill",
        "Resume",
        " resume",
        "a b",
        "résumé",
        "/resume",
        &"a".repeat(65),
    ] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "POST",
                &collection(team.id),
                creation(invalid)
            )
            .await
            .0,
            422,
            "name {invalid:?}"
        );
    }
    for field in ["logical_name", "display_name", "text"] {
        let mut invalid = creation("invalid");
        invalid.as_object_mut().unwrap().remove(field);
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
            422,
            "required {field}"
        );
    }
    for (field, value) in [
        ("created_by", json!("forged")),
        ("text", json!("\0")),
        ("text", json!("")),
        ("text", json!(" \r\n\t\u{a0}")),
        ("description", json!("\0")),
        ("description", json!("🙂".repeat(501))),
    ] {
        let mut invalid = creation("invalid");
        invalid[field] = value;
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
            422,
            "create {field}"
        );
    }
    assert_eq!(
        request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await,
        (200, initial.clone())
    );
    let mut expected = initial.clone();
    for patch in [
        json!({"text":" \r\n{{literal}} e\u{301}🙂漢字\t "}),
        json!({"description":"é".repeat(499)}),
        json!({"description":"🙂".repeat(500)}),
        json!({"description":null}),
        json!({"description":"","text":"nonblank"}),
        json!({"display_name":"Renamed"}),
    ] {
        let (status, edited) =
            request(&app, &identity, Some("bob"), "PATCH", &path, patch.clone()).await;
        assert_eq!(status, 200, "{edited}");
        for (key, value) in patch.as_object().unwrap() {
            expected[key] = value.clone();
        }
        assert_eq!(edited["updated_by"], "bob");
        assert!(edited["updated_at"].as_str().unwrap() > initial["updated_at"].as_str().unwrap());
        expected["updated_by"] = edited["updated_by"].clone();
        expected["updated_at"] = edited["updated_at"].clone();
        assert_eq!(edited, expected, "patch {patch}");
        assert_eq!(
            request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await,
            (200, expected.clone())
        );
    }
    let empty = create(
        &app,
        &identity,
        team.id,
        json!({"logical_name":"a".repeat(64),"display_name":"No description","text":"Text"}),
    )
    .await;
    assert_eq!(empty["text"], "Text");
    assert_eq!(empty["description"], Value::Null);
    assert_eq!(
        request(&app, &identity, Some("alice"), "DELETE", &path, Value::Null).await,
        (204, Value::Null)
    );
    for method in ["GET", "PATCH", "DELETE"] {
        assert_eq!(
            request(&app, &identity, Some("alice"), method, &path, json!({}))
                .await
                .0,
            404,
            "deleted {method}"
        );
    }
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from prompt where prompt_id=$1")
            .bind(Uuid::parse_str(initial["prompt_id"].as_str().unwrap()).unwrap())
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn prompts_authorization_admission_and_placement() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    for actor in ["reader", "platform-editor", "unconsented"] {
        grant(&e, org.id, Role::Member, actor).await;
    }
    grant(&e, team.id, Role::Member, "reader").await;
    control_plane::authorization::write_platform(
        &mut e.pool.acquire().await.unwrap(),
        "platform-editor",
        control_plane::roles::PlatformRole::PromptEditor,
        true,
    )
    .await
    .unwrap();
    let other = support::member_organization(&e.pool, "Other", "carol")
        .await
        .unwrap();
    for actor in ["alice", "reader", "platform-editor", "carol"] {
        admit(&e, actor).await;
    }
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    let prompt = create(&app, &identity, team.id, creation("resume")).await;
    let id = prompt["prompt_id"].as_str().unwrap();
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    let personal_prompt = create(&app, &identity, personal.id, creation("resume")).await;
    assert_ne!(personal_prompt["prompt_id"], prompt["prompt_id"]);
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
    grant(&e, org.id, Role::Editor, "alice").await;
    grant(&e, project.id, Role::Editor, "alice").await;
    // The foreign team is writable by Carol, so a 404 there tests the identifier pair.
    let foreign = spaces::create_space(
        &e.pool,
        "carol",
        SpaceKind::Team,
        other.id,
        "Foreign".into(),
        "carol",
    )
    .await
    .unwrap();
    spaces::grant(
        &e.pool,
        &e.subjects(),
        "carol",
        foreign.id,
        Role::Editor,
        "carol",
    )
    .await
    .unwrap();
    for (label, actor, space, read, write) in [
        ("anonymous", None, team.id, 401, 401),
        ("unadmitted", Some("unadmitted"), team.id, 403, 403),
        ("unconsented", Some("unconsented"), team.id, 403, 403),
        ("reader", Some("reader"), team.id, 200, 403),
        (
            "platform role only",
            Some("platform-editor"),
            team.id,
            403,
            403,
        ),
        ("foreign organization", Some("carol"), team.id, 404, 404),
        ("personal isolation", Some("reader"), personal.id, 403, 403),
    ] {
        let catalog = collection(space);
        let item = format!("{catalog}/{id}");
        let categories = format!("/spaces/{space}/prompt-categories");
        let category = format!("{categories}/{id}");
        for (method, path, body, expected) in [
            ("GET", &catalog, Value::Null, read),
            ("GET", &item, Value::Null, read),
            ("POST", &catalog, creation("denied"), write),
            ("PATCH", &item, json!({"text":"denied"}), write),
            ("DELETE", &item, Value::Null, write),
            ("GET", &categories, Value::Null, read),
            ("POST", &categories, json!({"name":"Denied"}), write),
            ("PATCH", &category, json!({"name":"Denied"}), write),
            ("DELETE", &category, Value::Null, write),
        ] {
            let (status, result) = request(&app, &identity, actor, method, path, body).await;
            assert_eq!(status, expected, "{label} {method} {path}: {result}");
            if label == "unadmitted" {
                assert_eq!(result["detail"], "user_not_admitted");
            }
            if label == "unconsented" {
                assert_eq!(result["detail"], "user_not_accept_gcu");
            }
        }
    }
    for (actor, space) in [
        ("alice", personal.id),
        ("alice", org.id),
        ("alice", project.id),
        ("carol", foreign.id),
    ] {
        for method in ["GET", "PATCH", "DELETE"] {
            assert_eq!(
                request(
                    &app,
                    &identity,
                    Some(actor),
                    method,
                    &format!("{}/{id}", collection(space)),
                    json!({})
                )
                .await
                .0,
                404,
                "mismatched pair {actor} {method}"
            );
        }
    }
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("{}/{id}", collection(team.id)),
            Value::Null
        )
        .await,
        (200, prompt.clone())
    );
    let mut personal_summary = personal_prompt.clone();
    let text = personal_summary
        .as_object_mut()
        .unwrap()
        .remove("text")
        .unwrap();
    personal_summary["text_preview"] = text;
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
        (200, json!({"items":[personal_summary], "next_cursor":null}))
    );
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.accept(&e.pool, "root", team.id).await.unwrap();
    for (method, path, body) in [
        ("GET", collection(team.id), Value::Null),
        ("GET", format!("{}/{id}", collection(team.id)), Value::Null),
        ("POST", collection(team.id), creation("retired")),
        (
            "PATCH",
            format!("{}/{id}", collection(team.id)),
            json!({"text":"retired"}),
        ),
        (
            "DELETE",
            format!("{}/{id}", collection(team.id)),
            Value::Null,
        ),
    ] {
        let (status, result) = request(&app, &identity, Some("alice"), method, &path, body).await;
        assert_eq!(status, 409, "retired {method}: {result}");
    }
    assert_eq!(
        sqlx::query_scalar::<_, String>("select text from prompt where prompt_id=$1")
            .bind(Uuid::parse_str(id).unwrap())
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        "Original {{unknown}}"
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn prompts_use_the_same_space_contract_for_all_four_kinds() {
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
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    for space in [&org, &team, &project] {
        grant(&e, space.id, Role::Editor, "alice").await;
        grant(&e, space.id, Role::Member, "reader").await;
    }
    grant(&e, org.id, Role::Member, "team-editor").await;
    grant(&e, team.id, Role::Editor, "team-editor").await;
    sqlx::query("insert into space_role_grant(space_id,subject,role) values($1,'technical-admin','organization_admin')")
        .bind(org.id).execute(&e.pool).await.unwrap();
    for actor in ["alice", "reader", "team-editor", "technical-admin"] {
        admit(&e, actor).await;
    }
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    let (status, sources) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        "/me/prompt-publication-spaces",
        Value::Null,
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(sources["items"].as_array().unwrap().len(), 4);
    for space in [&org, &team, &project, &personal] {
        let source = sources["items"]
            .as_array()
            .unwrap()
            .iter()
            .find(|source| source["id"] == space.id.to_string())
            .unwrap();
        assert_eq!(source["marketplace_space_ids"], json!([org.id]));
    }
    let mut ids = std::collections::HashSet::new();
    for space in [&org, &team, &project, &personal] {
        let catalog = collection(space.id);
        let categories = format!("/spaces/{}/prompt-categories", space.id);
        let (status, category) = request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &categories,
            json!({"name":"Analysis"}),
        )
        .await;
        assert_eq!(status, 201, "{:?}: {category}", space.kind);
        let category_path = format!("{categories}/{}", category["id"].as_str().unwrap());
        let mut body = creation("resume");
        body["category_id"] = category["id"].clone();
        let prompt = create(&app, &identity, space.id, body.clone()).await;
        let id = prompt["prompt_id"].as_str().unwrap();
        assert!(ids.insert(id.to_owned()));
        assert_eq!(prompt["space_id"], space.id.to_string());
        assert_eq!(prompt["published_in"], json!([]));
        let path = format!("{catalog}/{id}");
        let favorite = format!("{path}/favorite");
        for (method, route, body) in [
            ("GET", &catalog, Value::Null),
            ("GET", &path, Value::Null),
            ("GET", &categories, Value::Null),
            ("POST", &catalog, creation("denied")),
            ("PUT", &favorite, Value::Null),
        ] {
            assert_eq!(
                request(
                    &app,
                    &identity,
                    Some("technical-admin"),
                    method,
                    route,
                    body
                )
                .await
                .0,
                403,
                "admin {method} {route}"
            );
        }
        assert_eq!(
            request(&app, &identity, Some("alice"), "POST", &catalog, body)
                .await
                .0,
            409
        );
        let reader = if space.kind == SpaceKind::Personal {
            "alice"
        } else {
            "reader"
        };
        for (method, route, body, expected) in [
            ("GET", &catalog, Value::Null, 200),
            ("GET", &path, Value::Null, 200),
            ("GET", &categories, Value::Null, 200),
            ("PUT", &favorite, Value::Null, 204),
        ] {
            let (status, result) =
                request(&app, &identity, Some(reader), method, route, body).await;
            assert_eq!(
                status, expected,
                "{:?} {method} {route}: {result}",
                space.kind
            );
            if method == "GET" && route == &catalog {
                assert_eq!(result["items"].as_array().unwrap().len(), 1);
                assert_eq!(result["items"][0]["prompt_id"], id);
            }
        }
        let (_, starred) = request(&app, &identity, Some(reader), "GET", &path, Value::Null).await;
        assert_eq!(starred["is_favorite"], true);
        assert_eq!(starred["updated_at"], prompt["updated_at"]);
        assert_eq!(
            request(
                &app,
                &identity,
                Some(reader),
                "DELETE",
                &favorite,
                Value::Null
            )
            .await
            .0,
            204
        );
        if space.kind != SpaceKind::Personal {
            for (method, route, body) in [
                ("POST", &catalog, creation("denied")),
                ("PATCH", &path, json!({"text":"denied"})),
                ("DELETE", &path, Value::Null),
                ("POST", &categories, json!({"name":"Denied"})),
                ("PATCH", &category_path, json!({"name":"Denied"})),
                ("DELETE", &category_path, Value::Null),
            ] {
                assert_eq!(
                    request(&app, &identity, Some(reader), method, route, body)
                        .await
                        .0,
                    403,
                    "{method} {route}"
                );
            }
        }
        let publication = format!("{path}/publications/{}", org.id);
        assert_eq!(
            request(
                &app,
                &identity,
                Some("reader"),
                "PUT",
                &publication,
                json!({"published":true})
            )
            .await
            .0,
            403
        );
        assert_eq!(
            request(
                &app,
                &identity,
                Some("technical-admin"),
                "PUT",
                &publication,
                json!({"published":true})
            )
            .await
            .0,
            403
        );
        let marketplace_detail = format!("/spaces/{}/published-prompts/{id}", org.id);
        for _ in 0..2 {
            assert_eq!(
                request(
                    &app,
                    &identity,
                    Some("alice"),
                    "PUT",
                    &publication,
                    json!({"published":true})
                )
                .await
                .0,
                204
            );
        }
        let (_, public) = request(
            &app,
            &identity,
            Some("reader"),
            "GET",
            &marketplace_detail,
            Value::Null,
        )
        .await;
        assert_eq!(public["text"], prompt["text"]);
        assert_eq!(public["published_in"], json!([org.id]));
        assert_eq!(public["updated_at"], prompt["updated_at"]);
        let (published_by, published_at): (String, chrono::DateTime<chrono::Utc>) = sqlx::query_as(
            "select published_by,published_at from prompt_publication where prompt_id=$1",
        )
        .bind(Uuid::parse_str(id).unwrap())
        .fetch_one(&e.pool)
        .await
        .unwrap();
        assert_eq!(published_by, "alice");
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &publication,
                json!({"published":true})
            )
            .await
            .0,
            204
        );
        assert_eq!(
            sqlx::query_scalar::<_, chrono::DateTime<chrono::Utc>>(
                "select published_at from prompt_publication where prompt_id=$1"
            )
            .bind(Uuid::parse_str(id).unwrap())
            .fetch_one(&e.pool)
            .await
            .unwrap(),
            published_at
        );
        if space.kind == SpaceKind::Personal {
            assert_eq!(
                request(&app, &identity, Some("reader"), "GET", &path, Value::Null)
                    .await
                    .0,
                403
            );
            let secret = create(&app, &identity, space.id, creation("unpublished")).await;
            assert_eq!(
                request(
                    &app,
                    &identity,
                    Some("reader"),
                    "GET",
                    &format!(
                        "/spaces/{}/published-prompts/{}",
                        org.id,
                        secret["prompt_id"].as_str().unwrap()
                    ),
                    Value::Null
                )
                .await
                .0,
                404
            );
        }
        if space.kind != SpaceKind::Team {
            for route in [&catalog, &path, &categories] {
                assert_eq!(
                    request(
                        &app,
                        &identity,
                        Some("team-editor"),
                        "GET",
                        route,
                        Value::Null
                    )
                    .await
                    .0,
                    if space.kind == SpaceKind::Organization {
                        200
                    } else {
                        403
                    }
                );
            }
            assert_eq!(
                request(
                    &app,
                    &identity,
                    Some("team-editor"),
                    "PATCH",
                    &path,
                    json!({"text":"denied"})
                )
                .await
                .0,
                403
            );
        }
        let (status, edited) = request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &path,
            json!({"text":"Revised", "tags":["analysis"]}),
        )
        .await;
        assert_eq!(status, 200);
        assert_eq!(edited["text"], "Revised");
        assert_eq!(edited["tags"], json!(["analysis"]));
        assert_eq!(edited["category_id"], category["id"]);
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PATCH",
                &category_path,
                json!({"name":"Renamed"})
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
                "DELETE",
                &category_path,
                Value::Null
            )
            .await
            .0,
            409
        );
        assert_eq!(
            request(&app, &identity, Some("alice"), "DELETE", &path, Value::Null)
                .await
                .0,
            204
        );
        assert_eq!(
            request(&app, &identity, Some("alice"), "GET", &path, Value::Null)
                .await
                .0,
            404
        );
        assert_eq!(
            request(
                &app,
                &identity,
                Some("reader"),
                "GET",
                &marketplace_detail,
                Value::Null
            )
            .await
            .0,
            404
        );
        assert_eq!(
            sqlx::query_scalar::<_, i64>(
                "select count(*) from prompt_publication where prompt_id=$1"
            )
            .bind(Uuid::parse_str(id).unwrap())
            .fetch_one(&e.pool)
            .await
            .unwrap(),
            0
        );

        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "DELETE",
                &category_path,
                Value::Null
            )
            .await
            .0,
            204
        );
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn prompts_pagination_is_ordered_bounded_and_current() {
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    admit(&e, "alice").await;
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    let path = collection(team.id);
    assert_eq!(
        request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await,
        (200, json!({"items":[],"next_cursor":null}))
    );
    // Bulk fixture insertion keeps this a pagination test; creation is covered above.
    let mut names: Vec<String> = ["-first", "0digit", "_under"]
        .into_iter()
        .map(String::from)
        .chain((0..97).map(|i| format!("p{i:03}")))
        .collect();
    names.sort();
    sqlx::query("insert into prompt(prompt_id,space_id,logical_name,display_name,text,created_by) select gen_random_uuid(),$1,name,'Label','Text','alice' from unnest($2::text[]) as name")
        .bind(team.id).bind(names.iter().rev().cloned().collect::<Vec<_>>()).execute(&e.pool).await.unwrap();
    let (status, boundary) =
        request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await;
    assert_eq!(status, 200, "{boundary}");
    let listed = |page: &Value| -> Vec<String> {
        page["items"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| row["logical_name"].as_str().unwrap().to_owned())
            .collect()
    };
    assert_eq!(listed(&boundary), names);
    assert_eq!(boundary["next_cursor"], Value::Null);
    create(&app, &identity, team.id, creation("z-last")).await;
    let (status, first) = request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await;
    assert_eq!(status, 200, "{first}");
    assert_eq!(listed(&first), names);
    let cursor = first["next_cursor"].as_str().unwrap();
    assert_eq!(cursor, names.last().unwrap());
    let after = format!("{path}?after={cursor}");
    let (status, last) = request(&app, &identity, Some("alice"), "GET", &after, Value::Null).await;
    assert_eq!(status, 200, "{last}");
    let all: Vec<_> = listed(&first).into_iter().chain(listed(&last)).collect();
    names.push("z-last".into());
    assert_eq!(all, names); // Exact traversal: no missing or duplicate entries.
    assert_eq!(last["next_cursor"], Value::Null);
    let row = first["items"].as_array().unwrap().last().unwrap();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "DELETE",
            &format!("{path}/{}", row["prompt_id"].as_str().unwrap()),
            Value::Null
        )
        .await
        .0,
        204
    );
    create(&app, &identity, team.id, creation("a-before")).await;
    create(&app, &identity, team.id, creation("y-after")).await;
    let (status, current) =
        request(&app, &identity, Some("alice"), "GET", &after, Value::Null).await;
    assert_eq!(status, 200, "{current}");
    assert_eq!(listed(&current), ["y-after", "z-last"]);
    assert_eq!(current["next_cursor"], Value::Null);
    let (status, refreshed) =
        request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await;
    assert_eq!(status, 200, "{refreshed}");
    assert!(listed(&refreshed).contains(&"a-before".into()));
    assert!(!listed(&refreshed).contains(&cursor.to_owned()));
    for query in ["?after=skill", "?after=UPPER", "?unexpected=1"] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "GET",
                &format!("{path}{query}"),
                Value::Null
            )
            .await
            .0,
            422,
            "query {query}"
        );
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn prompts_competing_creates_and_independent_patches_persist() {
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    admit(&e, "alice").await;
    let identity = Arc::new(IdentityServer::start().await);
    let app = app(&e, &identity).await;
    let barrier = Arc::new(tokio::sync::Barrier::new(2));
    let launch = |body: Value| {
        let (app, identity, barrier) = (app.clone(), identity.clone(), barrier.clone());
        tokio::spawn(async move {
            barrier.wait().await;
            request(
                &app,
                &identity,
                Some("alice"),
                "POST",
                &collection(team.id),
                body,
            )
            .await
        })
    };
    let a = launch(creation("race"));
    let mut body = creation("race");
    body["text"] = json!("Competitor");
    let b = launch(body);
    let mut results = [a.await.unwrap(), b.await.unwrap()];
    results.sort_by_key(|r| r.0);
    assert_eq!([results[0].0, results[1].0], [201, 409], "{results:?}");
    assert_eq!(results[1].1["code"], "prompt_name_conflict");
    let winner = &results[0].1;
    let id = Uuid::parse_str(winner["prompt_id"].as_str().unwrap()).unwrap();
    let saved: Vec<(Uuid, String)> = sqlx::query_as(
        "select prompt_id,text from prompt where space_id=$1 and logical_name='race'",
    )
    .bind(team.id)
    .fetch_all(&e.pool)
    .await
    .unwrap();
    assert_eq!(saved, [(id, winner["text"].as_str().unwrap().to_owned())]);
    let path = format!("{}/{id}", collection(team.id));
    // Hold the row so the first PATCH retains its organization lock at UPDATE.
    // The second must wait before reading the old fields, otherwise it loses an edit.
    let mut blocker = e.pool.begin().await.unwrap();
    sqlx::query("select prompt_id from prompt where prompt_id=$1 for update")
        .bind(id)
        .fetch_one(&mut *blocker)
        .await
        .unwrap();
    let launch = |patch: Value| {
        let (app, identity, path) = (app.clone(), identity.clone(), path.clone());
        tokio::spawn(
            async move { request(&app, &identity, Some("alice"), "PATCH", &path, patch).await },
        )
    };
    let first = launch(json!({"description":"Concurrent description"}));
    tokio::time::timeout(Duration::from_secs(3), async {
        loop {
            let blocked: bool = sqlx::query_scalar("select exists(select 1 from pg_stat_activity where datname=current_database() and wait_event_type='Lock' and query like 'update prompt%')").fetch_one(&e.pool).await.unwrap();
            if blocked { break; }
            tokio::task::yield_now().await;
        }
    }).await.expect("first PATCH must reach its row update");
    let since: chrono::DateTime<chrono::Utc> = sqlx::query_scalar("select clock_timestamp()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    let second = launch(json!({"text":"Concurrent text"}));
    tokio::time::timeout(Duration::from_secs(3), async {
        loop {
            let retried: bool = sqlx::query_scalar("select exists(select 1 from pg_stat_activity where datname=current_database() and state='idle' and query ilike 'rollback%' and state_change >= $1)").bind(since).fetch_one(&e.pool).await.unwrap();
            if retried { break; }
            tokio::task::yield_now().await;
        }
    }).await.expect("second PATCH must contend on the organization lock");
    blocker.commit().await.unwrap();
    for result in [first.await.unwrap(), second.await.unwrap()] {
        assert_eq!(result.0, 200, "{result:?}");
    }
    let persisted: (String, String) =
        sqlx::query_as("select description,text from prompt where prompt_id=$1")
            .bind(id)
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(
        persisted,
        ("Concurrent description".into(), "Concurrent text".into())
    );
    let (status, read) = request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await;
    assert_eq!(status, 200, "{read}");
    assert_eq!(read["description"], persisted.0);
    assert_eq!(read["text"], persisted.1);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn prompt_categories_are_space_owned_and_protect_used_categories() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    grant(&e, org.id, Role::Member, "reader").await;
    grant(&e, team.id, Role::Member, "reader").await;
    for actor in ["alice", "reader"] {
        admit(&e, actor).await;
    }
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    let categories = format!("/spaces/{}/prompt-categories", team.id);
    let (status, category) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &categories,
        json!({"name":"  Analyse  "}),
    )
    .await;
    assert_eq!(status, 201, "{category}");
    assert_eq!(category["name"], "Analyse");
    let category_path = format!("{categories}/{}", category["id"].as_str().unwrap());
    let (status, duplicate) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &categories,
        json!({"name":"Analyse"}),
    )
    .await;
    assert_eq!(status, 409);
    assert_eq!(duplicate["code"], "prompt_category_name_conflict");
    for invalid in ["".to_owned(), " ".into(), "x".repeat(121), "a\nb".into()] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "POST",
                &categories,
                json!({"name":invalid})
            )
            .await
            .0,
            422
        );
    }
    let (status, listed) = request(
        &app,
        &identity,
        Some("reader"),
        "GET",
        &categories,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(listed["items"], json!([category.clone()]));
    for (method, path, body) in [
        ("POST", &categories, json!({"name":"Denied"})),
        ("PATCH", &category_path, json!({"name":"Denied"})),
        ("DELETE", &category_path, Value::Null),
    ] {
        assert_eq!(
            request(&app, &identity, Some("reader"), method, path, body)
                .await
                .0,
            403
        );
    }
    let personal_categories = format!("/spaces/{}/prompt-categories", personal.id);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("reader"),
            "GET",
            &personal_categories,
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
            "POST",
            &personal_categories,
            json!({"name":"Analyse"})
        )
        .await
        .0,
        201
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &format!("{personal_categories}/{}", category["id"].as_str().unwrap()),
            json!({"name":"Foreign"})
        )
        .await
        .0,
        404
    );

    let mut body = creation("classified");
    body["category_id"] = category["id"].clone();
    let prompt = create(&app, &identity, team.id, body.clone()).await;
    assert_eq!(prompt["category_id"], category["id"]);
    // Even a writer of both spaces cannot assign another space's category.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &collection(personal.id),
            body
        )
        .await
        .0,
        409
    );
    let item = format!(
        "{}/{}",
        collection(team.id),
        prompt["prompt_id"].as_str().unwrap()
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "DELETE",
            &category_path,
            Value::Null
        )
        .await
        .0,
        409
    );
    let (status, kept) = request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &item,
        json!({"description":"Changed"}),
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(kept["category_id"], category["id"]);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &category_path,
            json!({"name":"Research"})
        )
        .await
        .0,
        200
    );
    let (status, cleared) = request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &item,
        json!({"category_id":null}),
    )
    .await;
    assert_eq!(status, 200);
    assert!(cleared["category_id"].is_null());
    assert_ne!(cleared["updated_at"], kept["updated_at"]);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &item,
            json!({"category_id":null})
        )
        .await,
        (200, cleared)
    );

    // Assignment and deletion serialize; either assignment wins and deletion is
    // refused, or deletion wins and assignment is refused. Never a dangling id.
    let (assignment, deletion) = tokio::join!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &item,
            json!({"category_id":category["id"]})
        ),
        request(
            &app,
            &identity,
            Some("alice"),
            "DELETE",
            &category_path,
            Value::Null
        ),
    );
    assert!(matches!(
        (assignment.0, deletion.0),
        (200, 409) | (409, 204)
    ));
    // Restore a used category to exercise both cascades on enclosing-space purge.
    let (status, purge_category) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &categories,
        json!({"name":"Purge"}),
    )
    .await;
    assert_eq!(status, 201);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &item,
            json!({"category_id":purge_category["id"]})
        )
        .await
        .0,
        200
    );
    sqlx::query("delete from space where id=$1")
        .bind(team.id)
        .execute(&e.pool)
        .await
        .unwrap();
    for query in [
        "select count(*) from prompt where space_id=$1",
        "select count(*) from prompt_category where space_id=$1",
    ] {
        let count: i64 = sqlx::query_scalar(query)
            .bind(team.id)
            .fetch_one(&e.pool)
            .await
            .unwrap();
        assert_eq!(count, 0);
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn prompt_category_pagination_survives_renaming() {
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    admit(&e, "alice").await;
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    let ids: Vec<Uuid> = (1..=101).map(Uuid::from_u128).collect();
    sqlx::query("insert into prompt_category(id,space_id,name) select id,$1,id::text from unnest($2::uuid[]) id")
        .bind(team.id).bind(&ids).execute(&e.pool).await.unwrap();
    let path = format!("/spaces/{}/prompt-categories", team.id);
    let (status, first) = request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await;
    assert_eq!(status, 200);
    assert_eq!(first["items"].as_array().unwrap().len(), 100);
    assert_eq!(first["next_cursor"], ids[99].to_string());
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PATCH",
            &format!("{path}/{}", ids[99]),
            json!({"name":"Renamed"})
        )
        .await
        .0,
        200
    );
    let (status, last) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("{path}?after={}", ids[99]),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(last["items"].as_array().unwrap().len(), 1);
    assert_eq!(last["items"][0]["id"], ids[100].to_string());
    assert!(last["next_cursor"].is_null());
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn prompt_tags_and_caller_favorites_preserve_access_and_attribution() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    support::member_organization(&e.pool, "Outside", "outsider")
        .await
        .unwrap();
    grant(&e, team.id, Role::Editor, "alice").await;
    grant(&e, org.id, Role::Member, "reader").await;
    grant(&e, team.id, Role::Member, "reader").await;
    for actor in ["alice", "reader", "outsider"] {
        admit(&e, actor).await;
    }
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    let mut body = creation("tagged");
    body["tags"] = json!(["  Re\u{301}sume\u{301} ", "Résumé", "work"]);
    let initial = create(&app, &identity, team.id, body).await;
    assert_eq!(initial["tags"], json!(["Résumé", "work"]));
    assert_eq!(initial["is_favorite"], false);
    let id = initial["prompt_id"].as_str().unwrap();
    let path = format!("{}/{id}", collection(team.id));
    let favorite = format!("{path}/favorite");
    for method in ["PUT", "PUT"] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("reader"),
                method,
                &favorite,
                Value::Null
            )
            .await
            .0,
            204
        );
    }
    // A reader can change their preference, never the authored content.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("reader"),
            "PATCH",
            &path,
            json!({"tags":[]})
        )
        .await
        .0,
        403
    );
    let (_, mut read) = request(&app, &identity, Some("reader"), "GET", &path, Value::Null).await;
    assert_eq!(read["is_favorite"], true);
    read["is_favorite"] = json!(false);
    assert_eq!(read, initial);
    assert_eq!(
        request(&app, &identity, Some("alice"), "GET", &path, Value::Null)
            .await
            .1,
        initial
    );
    let (_, listed) = request(
        &app,
        &identity,
        Some("reader"),
        "GET",
        &collection(team.id),
        Value::Null,
    )
    .await;
    assert_eq!(listed["items"][0]["is_favorite"], true);
    assert_eq!(listed["items"][0]["tags"], initial["tags"]);
    for method in ["PUT", "DELETE"] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("outsider"),
                method,
                &favorite,
                Value::Null
            )
            .await
            .0,
            404
        );
        let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
            .await
            .unwrap();
        let wrong_space = format!("{}/{id}/favorite", collection(personal.id));
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                method,
                &wrong_space,
                Value::Null
            )
            .await
            .0,
            404
        );
    }
    spaces::revoke(&e.pool, "alice", team.id, Role::Member, "reader")
        .await
        .unwrap();
    assert_eq!(
        request(&app, &identity, Some("reader"), "GET", &path, Value::Null)
            .await
            .0,
        403
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("reader"),
            "PUT",
            &favorite,
            Value::Null
        )
        .await
        .0,
        403
    );
    grant(&e, team.id, Role::Member, "reader").await;
    assert_eq!(
        request(&app, &identity, Some("reader"), "GET", &path, Value::Null)
            .await
            .1["is_favorite"],
        true
    );
    for tags in [
        json!([""]),
        json!(["\n"]),
        json!(["x\0"]),
        json!(["a".repeat(65)]),
        json!(vec!["a"; 21]),
    ] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PATCH",
                &path,
                json!({"tags":tags})
            )
            .await
            .0,
            422
        );
    }
    let (status, cleared) = request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &path,
        json!({"tags":[]}),
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(cleared["tags"], json!([]));
    assert!(cleared["updated_at"].as_str().unwrap() > initial["updated_at"].as_str().unwrap());
    for patch in [json!({}), json!({"tags":null}), json!({"tags":[]})] {
        assert_eq!(
            request(&app, &identity, Some("alice"), "PATCH", &path, patch)
                .await
                .1,
            cleared
        );
    }
    for method in ["DELETE", "DELETE", "PUT"] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("reader"),
                method,
                &favorite,
                Value::Null
            )
            .await
            .0,
            204
        );
    }
    assert_eq!(
        request(&app, &identity, Some("alice"), "DELETE", &path, Value::Null)
            .await
            .0,
        204
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from prompt_favorite where prompt_id=$1")
            .bind(Uuid::parse_str(id).unwrap())
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("reader"),
            "PUT",
            &favorite,
            Value::Null
        )
        .await
        .0,
        404
    );
}

// Proves: I8, I20, I23
#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn publication_uses_current_definition_and_organization_participation() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let other = support::member_organization(&e.pool, "Other", "carol")
        .await
        .unwrap();
    for (actor, role) in [
        ("owner-only", "owner"),
        ("technical-only", "organization_admin"),
    ] {
        sqlx::query("insert into space_role_grant(space_id,subject,role) values($1,$2,$3)")
            .bind(org.id)
            .bind(actor)
            .bind(role)
            .execute(&e.pool)
            .await
            .unwrap();
    }
    for actor in ["alice", "owner-only", "technical-only", "carol"] {
        admit(&e, actor).await;
    }
    grant(&e, org.id, Role::Member, "team-owner").await;
    grant(&e, team.id, Role::Owner, "team-owner").await;
    admit(&e, "team-owner").await;
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    let prompt = create(&app, &identity, team.id, creation("publication")).await;
    assert_eq!(prompt["published_in"], json!([]));
    let id = prompt["prompt_id"].as_str().unwrap();
    let private = format!("{}/{id}", collection(team.id));
    let publication = format!("{private}/publications/{}", org.id);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &format!("{private}/publications/{}", other.id),
            json!({"published":true})
        )
        .await
        .0,
        400
    );
    let catalog = format!("/spaces/{}/published-prompts", org.id);
    let detail = format!("{catalog}/{id}");

    let (status, page) = request(
        &app,
        &identity,
        Some("owner-only"),
        "GET",
        &catalog,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(page["items"], json!([]));
    for (actor, expected_marketplace, expected_team) in [
        ("alice", true, true),
        ("owner-only", true, false),
        ("technical-only", false, false),
    ] {
        let (status, marketplaces) = request(
            &app,
            &identity,
            Some(actor),
            "GET",
            "/me/marketplaces",
            Value::Null,
        )
        .await;
        assert_eq!(status, 200);
        assert_eq!(
            marketplaces["items"]
                .as_array()
                .unwrap()
                .iter()
                .any(|item| item["space_id"] == org.id.to_string()),
            expected_marketplace
        );
        let (status, teams) = request(
            &app,
            &identity,
            Some(actor),
            "GET",
            "/me/prompt-publication-spaces",
            Value::Null,
        )
        .await;
        assert_eq!(status, 200);
        assert_eq!(
            teams["items"]
                .as_array()
                .unwrap()
                .iter()
                .any(|item| item["id"] == team.id.to_string()),
            expected_team
        );
    }
    assert_eq!(
        request(
            &app,
            &identity,
            Some("team-owner"),
            "GET",
            &private,
            Value::Null
        )
        .await
        .0,
        403
    );
    // Organization participation opens the marketplace, never private team content.
    assert_eq!(
        request(
            &app,
            &identity,
            Some("owner-only"),
            "GET",
            &private,
            Value::Null
        )
        .await
        .0,
        403
    );
    for (actor, expected) in [
        ("owner-only", 403),
        ("team-owner", 403),
        ("technical-only", 403),
        ("carol", 404),
    ] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some(actor),
                "PUT",
                &publication,
                json!({"published":true})
            )
            .await
            .0,
            expected
        );
    }
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &publication,
            json!({"published":true})
        )
        .await
        .0,
        204
    );
    for actor in ["owner-only", "team-owner", "alice"] {
        assert_eq!(
            request(&app, &identity, Some(actor), "GET", &detail, Value::Null)
                .await
                .0,
            200
        );
    }
    for actor in ["technical-only", "carol"] {
        for path in [&catalog, &detail] {
            assert_eq!(
                request(&app, &identity, Some(actor), "GET", path, Value::Null)
                    .await
                    .0,
                404
            );
        }
    }
    assert_eq!(
        request(
            &app,
            &identity,
            Some("carol"),
            "GET",
            &format!("/spaces/{}/published-prompts/{id}", other.id),
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
            "PATCH",
            &private,
            json!({"text":"Current text"})
        )
        .await
        .0,
        200
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("owner-only"),
            "GET",
            &detail,
            Value::Null
        )
        .await
        .1["text"],
        "Current text"
    );

    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &publication,
            json!({"published":false})
        )
        .await
        .0,
        204
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("owner-only"),
            "GET",
            &detail,
            Value::Null
        )
        .await
        .0,
        404
    );
    assert_eq!(
        request(&app, &identity, Some("alice"), "GET", &private, Value::Null)
            .await
            .0,
        200
    );

    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    let personal_prompt = create(&app, &identity, personal.id, creation("private")).await;
    let personal_id = personal_prompt["prompt_id"].as_str().unwrap();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &format!(
                "/spaces/{}/prompts/{personal_id}/publications/{}",
                personal.id, org.id
            ),
            json!({"published":true})
        )
        .await
        .0,
        204
    );
    // Removing the last collective role removes admission, even with old consent.
    sqlx::query("delete from space_role_grant where subject='owner-only'")
        .execute(&e.pool)
        .await
        .unwrap();
    let (status, body) = request(
        &app,
        &identity,
        Some("owner-only"),
        "GET",
        &catalog,
        Value::Null,
    )
    .await;
    assert_eq!(status, 403);
    assert_eq!(body["detail"], "user_not_admitted");
    // Admission through another organization still grants no marketplace visibility here.
    spaces::grant(
        &e.pool,
        &e.subjects(),
        "carol",
        other.id,
        Role::Member,
        "owner-only",
    )
    .await
    .unwrap();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("owner-only"),
            "GET",
            &catalog,
            Value::Null
        )
        .await
        .0,
        404
    );
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "Published project".into(),
        "alice",
    )
    .await
    .unwrap();
    grant(&e, project.id, Role::Editor, "alice").await;
    let project_prompt = create(&app, &identity, project.id, creation("published-project")).await;
    let project_id = project_prompt["prompt_id"].as_str().unwrap();
    for route in [
        &publication,
        &format!(
            "/spaces/{}/prompts/{project_id}/publications/{}",
            project.id, org.id
        ),
    ] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                route,
                json!({"published":true})
            )
            .await
            .0,
            204
        );
    }
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.accept(&e.pool, "root", team.id).await.unwrap();
    for hidden in [id, project_id] {
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "GET",
                &format!("{catalog}/{hidden}"),
                Value::Null
            )
            .await
            .0,
            404
        );
    }
    let (_, remaining) =
        request(&app, &identity, Some("alice"), "GET", &catalog, Value::Null).await;
    assert!(
        remaining["items"]
            .as_array()
            .unwrap()
            .iter()
            .all(|row| row["prompt_id"] != id && row["prompt_id"] != project_id)
    );
    for actor in ["alice", "technical-only"] {
        let (status, body) = request(
            &app,
            &identity,
            Some(actor),
            "PUT",
            &publication,
            json!({"published": true}),
        )
        .await;
        assert_eq!(status, 409);
        assert_eq!(body["code"], "space_pending_deletion");
    }
    assert_eq!(
        request(
            &app,
            &identity,
            Some("carol"),
            "PUT",
            &publication,
            json!({"published": true})
        )
        .await
        .0,
        404
    );
    e.pool.close().await;
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn prompts_and_publications_survive_the_authors_departure() {
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
    for space in [&org, &team, &project] {
        grant(&e, space.id, Role::Editor, "bob").await;
        grant(&e, space.id, Role::Editor, "alice").await;
    }
    let (personal, _) = spaces::create_personal_space(&e.pool, "bob", org.id)
        .await
        .unwrap();
    for actor in ["alice", "bob"] {
        admit(&e, actor).await;
    }
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    let mut definitions = Vec::new();
    for space in [&org, &team, &project, &personal] {
        let (status, prompt) = request(
            &app,
            &identity,
            Some("bob"),
            "POST",
            &collection(space.id),
            creation("retained"),
        )
        .await;
        assert_eq!(status, 201, "{prompt}");
        let id = prompt["prompt_id"].as_str().unwrap();
        assert_eq!(
            request(
                &app,
                &identity,
                Some("bob"),
                "PUT",
                &format!("{}/{id}/publications/{}", collection(space.id), org.id),
                json!({"published":true})
            )
            .await
            .0,
            204
        );
        definitions.push((space, prompt));
    }
    let (status, private) = request(
        &app,
        &identity,
        Some("bob"),
        "POST",
        &collection(personal.id),
        creation("still-private"),
    )
    .await;
    assert_eq!(status, 201);

    // Use the common revocation path, children first. Departure is not space deletion.
    for space in [&project, &team, &personal, &org] {
        spaces::revoke(&e.pool, "alice", space.id, Role::Editor, "bob")
            .await
            .unwrap();
        if space.kind == SpaceKind::Personal {
            spaces::revoke(&e.pool, "alice", space.id, Role::Member, "bob")
                .await
                .unwrap();
        }
    }
    assert!(
        control_plane::authorization::roles_of(&e.pool, "bob")
            .await
            .unwrap()
            .is_empty()
    );
    for (space, prompt) in definitions {
        let id = prompt["prompt_id"].as_str().unwrap();
        let source = format!("{}/{id}", collection(space.id));
        let public = format!("/spaces/{}/published-prompts/{id}", org.id);
        for (method, route, body) in [
            ("GET", source.as_str(), Value::Null),
            ("GET", public.as_str(), Value::Null),
            ("PATCH", source.as_str(), json!({"text":"denied"})),
            ("DELETE", source.as_str(), Value::Null),
        ] {
            let (status, error) = request(&app, &identity, Some("bob"), method, route, body).await;
            assert!(
                matches!(status, 403 | 404),
                "{method} {route}: {status} {error}"
            );
        }
        let (status, published) =
            request(&app, &identity, Some("alice"), "GET", &public, Value::Null).await;
        assert_eq!(status, 200, "{published}");
        assert_eq!(published["text"], prompt["text"]);
        assert_eq!(published["created_by"], "bob");
        assert_eq!(published["updated_at"], prompt["updated_at"]);
        let publisher: String =
            sqlx::query_scalar("select published_by from prompt_publication where prompt_id=$1")
                .bind(Uuid::parse_str(id).unwrap())
                .fetch_one(&e.pool)
                .await
                .unwrap();
        assert_eq!(publisher, "bob");
        // Existing editors continue managing collective definitions; no personal access is added.
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PATCH",
                &source,
                json!({"description":"Maintained"})
            )
            .await
            .0,
            if space.kind == SpaceKind::Personal {
                403
            } else {
                200
            }
        );
    }
    let id = private["prompt_id"].as_str().unwrap();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("{}/{id}", collection(personal.id)),
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
            &format!("/spaces/{}/published-prompts/{id}", org.id),
            Value::Null
        )
        .await
        .0,
        404
    );
    assert_eq!(
        sqlx::query_scalar::<_, String>("select text from prompt where prompt_id=$1")
            .bind(Uuid::parse_str(id).unwrap())
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        private["text"].as_str().unwrap()
    );
}
