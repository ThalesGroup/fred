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
        authorization: e.authorization.clone(),
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
        json!({"description":"","text":""}),
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
        json!({"logical_name":"a".repeat(64),"display_name":"Empty","text":""}),
    )
    .await;
    assert_eq!(empty["text"], "");
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
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    for actor in ["reader", "platform-editor"] {
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
    let other = support::member_organization(&e.pool, &e.authorization, "Other", "carol")
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
        ("organization placement", Some("alice"), org.id, 400, 400),
        ("project placement", Some("alice"), project.id, 400, 400),
    ] {
        let catalog = collection(space);
        let item = format!("{catalog}/{id}");
        for (method, path, body, expected) in [
            ("GET", &catalog, Value::Null, read),
            ("GET", &item, Value::Null, read),
            ("POST", &catalog, creation("denied"), write),
            ("PATCH", &item, json!({"text":"denied"}), write),
            ("DELETE", &item, Value::Null, write),
        ] {
            let (status, result) = request(&app, &identity, actor, method, path, body).await;
            assert_eq!(status, expected, "{label} {method} {path}: {result}");
            if label == "unadmitted" {
                assert_eq!(result["detail"], "user_not_accept_gcu");
            }
        }
    }
    for (actor, space) in [("alice", personal.id), ("carol", foreign.id)] {
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
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle
        .accept(&e.pool, &e.authorization, "root", team.id)
        .await
        .unwrap();
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
