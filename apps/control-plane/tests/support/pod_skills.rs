// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

fn inventory() -> Value {
    json!({"complete":true,"capabilities":[{"id":"tool","name":"Tool","description":"A tool","icon":"tune","version":"1","kind":"tool"}], "template_capabilities":[]})
}
async fn observe(app: &Router, identity: &support::IdentityServer, org: Uuid) -> u16 {
    request(
        app,
        identity,
        Some("alice"),
        "POST",
        &format!("/organizations/{org}/capabilities/fixture/refresh"),
        Value::Null,
    )
    .await
    .0
}
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn pod_skills_ralph_preparation_and_selection_remain_unsupported() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let native = template_id(org.id, "control-plane", fred_rust_agent::AGENT_ID);
    control_plane::authorization::set_agent_default_on(
        &mut e.pool.acquire().await.unwrap(),
        org.id,
        native,
        true,
    )
    .await
    .unwrap();
    let instance = create(&app, &identity, team.id, creation(native, "Ralph")).await;
    let (status, prepared) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        &format!("{}/prepare-execution", item(team.id, &instance)),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{prepared}");
    assert!(prepared["skills"].is_null());
    assert!(prepared["skill_detail_url_template"].is_null());
    let (status, refused) = request(
        &app,
        &identity,
        Some("alice"),
        "POST",
        "/agents/execute/stream",
        json!({"agent_instance_id":instance["agent_instance_id"],"input":"hello",
            "session_id":Uuid::new_v4(),
            "runtime_context":{"space_id":team.id,"skills":[{"name":"graph"}]}}),
    )
    .await;
    assert_eq!(status, 422, "{refused}");
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn capability_browser_route_uses_approved_ingress() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let mut advertised = inventory();
    advertised["capabilities"][0]["route_base_url"] =
        json!("https://untrusted.invalid/capabilities/tool");
    catalog.state.lock().await.inventory = advertised;
    let app = app(&e, &identity, &catalog).await;
    assert_eq!(observe(&app, &identity, org.id).await, 204);
    let (status, body) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("/organizations/{}/capabilities", org.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{body}");
    let offers = body[0]["capabilities"].as_array().unwrap();
    let tool = offers
        .iter()
        .find(|offer| offer["capability_id"] == "tool")
        .unwrap();
    assert_eq!(tool["route_base_url"], "/fixture-pod/capabilities/tool");
    assert!(tool["descriptor"].get("route_base_url").is_none());
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn space_skills_use_shared_scope_atomic_packages_and_direct_rights() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "alice").await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let org_path = format!("/spaces/{}/skills", org.id);
    let team_path = format!("/spaces/{}/skills", team.id);
    let call = |actor, method, path: String, body| {
        let app = &app;
        let identity = &identity;
        async move { request(app, identity, Some(actor), method, &path, body).await }
    };
    let (status, defaults) = call("alice", "GET", "/skills/defaults".into(), Value::Null).await;
    assert_eq!(status, 200, "{defaults}");
    assert_eq!(defaults.as_array().unwrap().len(), 7);
    assert_eq!(
        call("alice", "GET", org_path.clone(), Value::Null).await.1,
        json!([])
    );
    assert_eq!(
        call(
            "alice",
            "POST",
            format!("{org_path}/packages/graph/install"),
            Value::Null
        )
        .await
        .0,
        204
    );
    assert_eq!(
        call(
            "alice",
            "POST",
            format!("{team_path}/packages/meeting-minutes/install"),
            Value::Null
        )
        .await
        .0,
        204
    );
    let (status, scope) = call("alice", "GET", format!("{team_path}/scope"), Value::Null).await;
    assert_eq!(status, 200, "{scope}");
    assert_eq!(scope["skills"].as_array().unwrap().len(), 2);
    let graph_id = scope["skills"]
        .as_array()
        .unwrap()
        .iter()
        .find(|s| s["name"] == "graph")
        .unwrap()["skill_id"]
        .as_str()
        .unwrap();
    assert_eq!(
        call("alice", "GET", team_path.clone(), Value::Null)
            .await
            .1
            .as_array()
            .unwrap()
            .len(),
        1
    );
    sqlx::query(
        "delete from space_role_grant where subject='alice' and space_id=$1 and role in ('editor', 'member')",
    )
    .bind(org.id)
    .execute(&e.pool)
    .await
    .unwrap();
    let (_, local_only) = call("alice", "GET", format!("{team_path}/scope"), Value::Null).await;
    assert_eq!(local_only["skills"].as_array().unwrap().len(), 1);
    grant(&e, org.id, Role::Editor, "alice").await;
    let (status, preview) = call(
        "alice",
        "GET",
        format!("{team_path}/scope/{graph_id}"),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{preview}");
    assert!(
        preview["content"]
            .as_str()
            .unwrap()
            .contains("references/mermaid.md")
    );
    assert_eq!(
        call(
            "bob",
            "GET",
            format!("{team_path}/scope/{graph_id}"),
            Value::Null
        )
        .await
        .0,
        403
    );
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Analyst, "bob").await;
    assert_eq!(
        call(
            "bob",
            "POST",
            format!("{team_path}/packages/graph/install"),
            Value::Null
        )
        .await
        .0,
        403
    );
    // Owner is governance, not an override for reading/editing content.
    assert_eq!(
        call("root", "GET", org_path.clone(), Value::Null).await.0,
        403
    );
    let mut tx = e.pool.begin().await.unwrap();
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await
        .unwrap();
    let admitted = control_plane::skills::resolve(&mut tx, "alice", &team, true)
        .await
        .unwrap();
    tx.commit().await.unwrap();
    let path = format!("{org_path}/{graph_id}");
    let (status, mut package) = call("alice", "GET", path.clone(), Value::Null).await;
    assert_eq!(status, 200);
    let stale = package.clone();
    package["files"]["references/mermaid.md"] = json!("New reference");
    assert_eq!(call("alice", "PUT", path.clone(), package).await.0, 204);
    assert_eq!(call("alice", "PUT", path.clone(), stale).await.0, 409);
    assert_ne!(
        admitted.files[&format!("/skills/{graph_id}/references/mermaid.md")],
        "New reference"
    );
    assert_eq!(call("alice", "DELETE", path, Value::Null).await.0, 204);
    assert_eq!(
        call(
            "alice",
            "GET",
            format!("{team_path}/scope/{graph_id}"),
            Value::Null
        )
        .await
        .0,
        404
    );
    assert_eq!(
        call("alice", "GET", format!("{team_path}/scope"), Value::Null)
            .await
            .1["skills"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn space_skills_accept_standard_packages_and_refuse_unsafe_paths() {
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let collection = format!("/spaces/{}/skills", team.id);
    let mut body = json!({"name":"scope", "files":{"SKILL.md":"---\nname: scope\ndescription: A standard skill\n---\nRead [reference](references/guide.md).", "references/guide.md":"Evidence"}});
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &collection,
            body.clone()
        )
        .await
        .0,
        204
    );
    let (_, owned) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &collection,
        Value::Null,
    )
    .await;
    let skill_id = owned[0]["skill_id"].as_str().unwrap();
    let path = format!("{collection}/{skill_id}");
    body.as_object_mut().unwrap().remove("name");
    let (status, preview) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("/spaces/{}/skills/scope/{skill_id}", team.id),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{preview}");
    assert!(
        preview["content"]
            .as_str()
            .unwrap()
            .contains("references/guide.md")
    );
    let current = request(&app, &identity, Some("alice"), "GET", &path, Value::Null)
        .await
        .1;
    body["expected_revision"] = current["expected_revision"].clone();
    body["files"]["../escape.md"] = json!("forbidden");
    assert_eq!(
        request(&app, &identity, Some("alice"), "PUT", &path, body)
            .await
            .0,
        422
    );
    assert_eq!(
        request(&app, &identity, Some("alice"), "GET", &path, Value::Null)
            .await
            .1,
        current
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn space_skills_share_the_four_space_kinds_contract() {
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
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    for (space, name, count) in [
        (&org, "compare-options", 1),
        (&team, "graph", 2),
        (&project, "meeting-minutes", 3),
        (&personal, "grill-me", 1),
    ] {
        let path = format!("/spaces/{}/skills", space.id);
        let (status, body) = request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &format!("{path}/packages/{name}/install"),
            Value::Null,
        )
        .await;
        assert_eq!(status, 204, "{body}");
        let (status, owned) =
            request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await;
        assert_eq!(status, 200, "{owned}");
        assert_eq!(owned.as_array().unwrap().len(), 1);
        let (status, scope) = request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("{path}/scope"),
            Value::Null,
        )
        .await;
        assert_eq!(status, 200, "{scope}");
        assert_eq!(scope["skills"].as_array().unwrap().len(), count);
        assert_eq!(
            request(&app, &identity, Some("reader"), "GET", &path, Value::Null)
                .await
                .0,
            if space.kind == SpaceKind::Personal {
                403
            } else {
                200
            }
        );
        assert_eq!(
            request(
                &app,
                &identity,
                Some("reader"),
                "DELETE",
                &format!("{path}/{}", owned[0]["skill_id"].as_str().unwrap()),
                Value::Null
            )
            .await
            .0,
            403
        );
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn space_skills_homonyms_keep_distinct_identity_content_and_owner() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    for space in [&org, &team] {
        grant(&e, space.id, Role::Editor, "alice").await;
    }
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    let mut ids = Vec::new();
    for space in [&org, &team] {
        let root = format!("/spaces/{}/skills", space.id);
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "POST",
                &format!("{root}/packages/graph/install"),
                Value::Null
            )
            .await
            .0,
            204
        );
        let (_, owned) = request(&app, &identity, Some("alice"), "GET", &root, Value::Null).await;
        ids.push(owned[0]["skill_id"].as_str().unwrap().to_owned());
    }
    assert_ne!(ids[0], ids[1]);
    let scope_path = format!("/spaces/{}/skills/scope", team.id);
    let (status, scope) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &scope_path,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{scope}");
    assert_eq!(scope["skills"].as_array().unwrap().len(), 2);
    let team_package = format!("/spaces/{}/skills/{}", team.id, ids[1]);
    let (_, mut package) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &team_package,
        Value::Null,
    )
    .await;
    package["files"]["references/mermaid.md"] = json!("Team reference");
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &team_package,
            package
        )
        .await
        .0,
        204
    );
    for (id, owner) in ids.iter().zip([org.id, team.id]) {
        let (status, preview) = request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &format!("{scope_path}/{id}"),
            Value::Null,
        )
        .await;
        assert_eq!(status, 200, "{preview}");
        assert_eq!(preview["skill"]["name"], "graph");
        assert_eq!(preview["skill"]["space_id"], owner.to_string());
        assert_eq!(preview["skill"]["skill_id"], *id);
    }
    let wrong_owner = format!("/spaces/{}/skills/{}", org.id, ids[1]);
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &wrong_owner,
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
            "DELETE",
            &wrong_owner,
            Value::Null
        )
        .await
        .0,
        404
    );
    let mut tx = e.pool.begin().await.unwrap();
    let admitted = control_plane::skills::resolve(&mut tx, "alice", &team, true)
        .await
        .unwrap();
    tx.commit().await.unwrap();
    assert_eq!(admitted.catalog.skills.len(), 2);
    assert_eq!(
        admitted.files[&format!("/skills/{}/references/mermaid.md", ids[1])],
        "Team reference"
    );
    assert_ne!(
        admitted.files[&format!("/skills/{}/references/mermaid.md", ids[0])],
        "Team reference"
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "DELETE",
            &team_package,
            Value::Null
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
            &format!("{scope_path}/{}", ids[1]),
            Value::Null
        )
        .await
        .0,
        404
    );
    let (status, surviving) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &scope_path,
        Value::Null,
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(surviving["skills"].as_array().unwrap().len(), 1);
    assert_eq!(surviving["skills"][0]["skill_id"], ids[0]);
    // An already admitted turn still owns both immutable versions.
    assert_eq!(
        admitted.files[&format!("/skills/{}/references/mermaid.md", ids[1])],
        "Team reference"
    );
}
