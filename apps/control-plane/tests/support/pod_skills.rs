// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use control_plane::agents::{catalog as store, enablement, skills};

fn inventory() -> Value {
    json!({"complete":true,"capabilities":[{"id":"tool","name":"Tool","description":"A tool","icon":"tune","version":"1","kind":"tool"}], "template_capabilities":[],
    "skills":{"availability":"available","supported":true,"policy_supported":true,"revision":"a".repeat(64),"skills":[
        {"name":"graph","description":"Draw","argument_hint":null,"builtin":true,"user_invocable":true,"disable_model_invocation":false},
        {"name":"private-procedure","description":"Custom source","argument_hint":null,"builtin":false,"user_invocable":false,"disable_model_invocation":false}
    ]}})
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
async fn local(
    app: &Router,
    identity: &support::IdentityServer,
    actor: &str,
    space: Uuid,
    revision: i64,
    restricted: bool,
    ids: &[&str],
) -> u16 {
    request(
        app,
        identity,
        Some(actor),
        "PUT",
        &format!("/spaces/{space}/capability-policies/fixture"),
        json!({"expected_revision":revision,"restricted":restricted,"permitted_ids":ids}),
    )
    .await
    .0
}
async fn allowed(e: &Env, space: &Space) -> Vec<String> {
    let mut tx = e.pool.begin().await.unwrap();
    let policy = enablement::Policy::load(&mut *tx, space.organization)
        .await
        .unwrap();
    skills::resolve(&mut tx, space, "fixture", &policy)
        .await
        .unwrap()
        .unwrap()
        .skills
        .into_iter()
        .map(|s| s.name)
        .collect()
}
async fn permit(app: &Router, identity: &support::IdentityServer, org: Uuid, id: &str, on: bool) {
    let result = request(
        app,
        identity,
        Some("alice"),
        "PUT",
        &format!("/organizations/{org}/capabilities/fixture/{id}/default-on"),
        json!({"default_on":on}),
    )
    .await;
    assert_eq!(result.0, 204, "{result:?}");
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn pod_skills_ceilings_roles_concurrency_and_project_resolution() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    catalog.state.lock().await.inventory = inventory();
    let app = app(&e, &identity, &catalog).await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Member, "bob").await;
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "Atlas".into(),
        "bob",
    )
    .await
    .unwrap();
    assert_eq!(observe(&app, &identity, org.id).await, 204);
    assert!(allowed(&e, &project).await.is_empty()); // exact capability default
    permit(&app, &identity, org.id, "skill:graph", true).await;
    permit(&app, &identity, org.id, "skill:private-procedure", true).await;
    permit(&app, &identity, org.id, "tool", true).await;
    assert_eq!(allowed(&e, &project).await, ["graph", "private-procedure"]);
    // Parent authority never becomes a child role; Owner does not grant Read.
    assert_eq!(
        local(&app, &identity, "alice", project.id, 0, true, &[]).await,
        403
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "GET",
            &format!("/spaces/{}/capability-policies", team.id),
            Value::Null
        )
        .await
        .0,
        403
    );
    assert_eq!(
        local(
            &app,
            &identity,
            "bob",
            project.id,
            0,
            true,
            &["skill:graph", "tool"]
        )
        .await,
        204
    );
    assert_eq!(
        local(&app, &identity, "alice", team.id, 0, true, &[]).await,
        204
    );
    assert!(allowed(&e, &project).await.is_empty());
    let policy = enablement::Policy::load(&e.pool, org.id).await.unwrap();
    assert!(!enablement::usable(&policy, &project, "fixture", "tool"));
    // Reset retains its revision: old editors cannot bypass a later reset.
    assert_eq!(
        local(&app, &identity, "alice", team.id, 1, false, &[]).await,
        204
    );
    assert_eq!(allowed(&e, &project).await, ["graph"]);
    assert_eq!(
        local(&app, &identity, "alice", team.id, 0, true, &[]).await,
        409
    );
    let (a, b) = tokio::join!(
        local(&app, &identity, "bob", project.id, 1, true, &[]),
        local(&app, &identity, "bob", project.id, 1, false, &[])
    );
    assert!((a == 204 && b == 409) || (a == 409 && b == 204));
    assert_eq!(
        local(&app, &identity, "bob", project.id, 2, false, &[]).await,
        204
    );
    permit(&app, &identity, org.id, "skill:graph", false).await;
    assert_eq!(allowed(&e, &project).await, ["private-procedure"]);
    let other = support::member_organization(&e.pool, "Other", "alice")
        .await
        .unwrap();
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", other.id)
        .await
        .unwrap();
    assert!(allowed(&e, &personal).await.is_empty());
    assert_eq!(
        local(&app, &identity, "alice", personal.id, 0, true, &[]).await,
        403
    );

    let template = enable(&e, org.id, "custom", true).await;
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "POST",
            &collection(project.id),
            creation(template, "Project agent")
        )
        .await
        .0,
        403
    );
    spaces::grant(
        &e.pool,
        &e.subjects(),
        "bob",
        project.id,
        Role::Editor,
        "bob",
    )
    .await
    .unwrap();
    let (status, instance) = request(
        &app,
        &identity,
        Some("bob"),
        "POST",
        &collection(project.id),
        creation(template, "Project agent"),
    )
    .await;
    assert_eq!(status, 201, "{instance}");
    let runtime = format!("{}/runtime", item(project.id, &instance));
    let (status, resolved) =
        request(&app, &identity, Some("bob"), "GET", &runtime, Value::Null).await;
    assert_eq!(status, 200, "{resolved}");
    assert_eq!(resolved["space"]["team_id"], json!(team.id));
    assert_eq!(resolved["space"]["project_id"], json!(project.id));
    assert_eq!(resolved["skills"]["skills"][0]["name"], "private-procedure");
    assert!(resolved.get("inference").is_none());
    assert!(resolved.get("title_job").is_none_or(Value::is_null));
    assert_eq!(
        request(&app, &identity, Some("alice"), "GET", &runtime, Value::Null)
            .await
            .0,
        403
    );
    let (status, prepared) = request(
        &app,
        &identity,
        Some("bob"),
        "POST",
        &format!("{}/prepare-execution", item(project.id, &instance)),
        Value::Null,
    )
    .await;
    assert_eq!(status, 200, "{prepared}");
    assert_eq!(prepared["skills"], resolved["skills"]);
    assert_eq!(
        prepared["skill_detail_url_template"],
        "/fixture-pod/agents/skills/{skill_name}"
    );
    assert_eq!(
        local(&app, &identity, "bob", project.id, 3, true, &[]).await,
        204
    );
    let (_, next) = request(&app, &identity, Some("bob"), "GET", &runtime, Value::Null).await;
    assert_eq!(next["skills"]["skills"], json!([]));
    assert_eq!(resolved["skills"]["skills"].as_array().unwrap().len(), 1); // old immutable facts

    // Retirement fences reads immediately; physical cleanup removes both local
    // tables while preserving the parent policy and pod inventory.
    use control_plane::lifecycle::{Lifecycle, Status, cleanup, store as deletions};
    assert_eq!(
        local(
            &app,
            &identity,
            "bob",
            project.id,
            4,
            true,
            &["skill:graph"]
        )
        .await,
        204
    );
    let mut lifecycle = Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.catalog.space_policies.purge.default.retention =
        serde_yaml_ng::from_str("P7D").unwrap();
    let receipt = lifecycle.accept(&e.pool, "root", project.id).await.unwrap();
    assert_eq!(
        local(&app, &identity, "bob", project.id, 5, false, &[]).await,
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
        if deletions::status(&e.pool, "root", receipt.id)
            .await
            .unwrap()
            .status
            == Status::Completed
        {
            break;
        }
    }
    assert_eq!(
        deletions::status(&e.pool, "root", receipt.id)
            .await
            .unwrap()
            .status,
        Status::Completed
    );
    let remaining: i64 = sqlx::query_scalar("select (select count(*) from space_capability_policy where space_id=$1) + (select count(*) from space_capability_permission where space_id=$1)")
        .bind(project.id).fetch_one(&e.pool).await.unwrap();
    assert_eq!(remaining, 0);
    assert_eq!(sqlx::query_scalar::<_,i64>("select revision from space_capability_policy where space_id=$1 and runtime_id='fixture'").bind(team.id).fetch_one(&e.pool).await.unwrap(),2);
    assert!(
        !store::capabilities(&e.pool, "fixture")
            .await
            .unwrap()
            .is_empty()
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn pod_skills_discovery_preserves_decisions_and_rejects_bad_snapshots() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    let app = app(&e, &identity, &catalog).await;
    catalog.state.lock().await.inventory = inventory();
    assert_eq!(observe(&app, &identity, org.id).await, 204);
    permit(&app, &identity, org.id, "skill:graph", true).await;
    assert_eq!(
        local(&app, &identity, "alice", team.id, 0, true, &["skill:graph"]).await,
        204
    );
    // A replica with invalid or unsupported claims never replaces the last good snapshot.
    catalog.state.lock().await.inventory["skills"]["policy_supported"] = json!(false);
    assert!(observe(&app, &identity, org.id).await >= 500);
    assert_eq!(allowed(&e, &team).await, ["graph"]);
    catalog.state.lock().await.inventory = inventory();
    catalog.state.lock().await.inventory["skills"]["availability"] = json!("unavailable");
    catalog.state.lock().await.inventory["skills"]["skills"] = json!([]);
    assert_eq!(observe(&app, &identity, org.id).await, 204);
    assert!(allowed(&e, &team).await.is_empty());
    assert!(
        store::capabilities(&e.pool, "fixture")
            .await
            .unwrap()
            .iter()
            .any(|v| v.capability_id == "skill:graph" && v.advertised)
    );
    // A successful withdrawal preserves saved choices but prevents new grants.
    catalog.state.lock().await.inventory = inventory();
    catalog.state.lock().await.inventory["skills"]["skills"] = json!([]);
    assert_eq!(observe(&app, &identity, org.id).await, 204);
    assert!(allowed(&e, &team).await.is_empty());
    assert_eq!(
        local(&app, &identity, "alice", team.id, 1, true, &["skill:graph"]).await,
        204
    );
    assert_eq!(
        local(
            &app,
            &identity,
            "alice",
            team.id,
            2,
            true,
            &["skill:private-procedure"]
        )
        .await,
        409
    );
    let (_, policies) = request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("/spaces/{}/capability-policies", team.id),
        Value::Null,
    )
    .await;
    assert_eq!(policies[0]["permitted_ids"], json!(["skill:graph"]));
    catalog.state.lock().await.inventory = inventory();
    assert_eq!(observe(&app, &identity, org.id).await, 204);
    assert_eq!(allowed(&e, &team).await, ["graph"]);
}

use crate::environment::database;

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn pod_skills_upgrade_preserves_existing_offers_and_has_no_implicit_local_grant() {
    let mut previous = sqlx::migrate!();
    previous.migrations =
        std::borrow::Cow::Owned(previous.iter().filter(|m| m.version < 5).cloned().collect());
    let pool = database::database_with_migrator(previous).await;
    let org = support::member_organization(&pool, "Before upgrade", "alice")
        .await
        .unwrap();
    sqlx::query("insert into runtime_catalog(runtime_id,reachable) values('fixture',true)")
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("insert into runtime_capability(runtime_id,capability_id,version,descriptor,advertised) values('fixture','tool','1','{}',true)").execute(&pool).await.unwrap();
    sqlx::query("insert into organization_capability(organization_id,runtime_id,capability_id,enabled_by) values($1,'fixture','tool','alice')").bind(org.id).execute(&pool).await.unwrap();
    sqlx::migrate!().run(&pool).await.unwrap();
    let policy = enablement::Policy::load(&pool, org.id).await.unwrap();
    assert!(policy.default_on("fixture", "tool"));
    assert!(!policy.default_on("fixture", "skill:graph"));
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space_capability_policy")
            .fetch_one(&pool)
            .await
            .unwrap(),
        0
    );
    assert!(
        store::observation(&pool, "fixture")
            .await
            .unwrap()
            .unwrap()
            .skills_availability
            .is_none()
    );
    sqlx::migrate!().run(&pool).await.unwrap(); // replay is inert
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn pod_skills_preparation_preserves_deep_family_and_space_ceilings() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "Deep project".into(),
        "alice",
    )
    .await
    .unwrap();
    grant(&e, project.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let catalog = Catalog::start().await;
    catalog.state.lock().await.inventory = inventory();
    let app = app(&e, &identity, &catalog).await;
    assert_eq!(observe(&app, &identity, org.id).await, 204);
    permit(&app, &identity, org.id, "skill:graph", true).await;
    permit(&app, &identity, org.id, "skill:private-procedure", true).await;
    assert_eq!(
        local(&app, &identity, "alice", team.id, 0, true, &["skill:graph"]).await,
        204
    );
    let template = enable(&e, org.id, "custom", true).await;

    for family in ["deep", "graph", "proxy"] {
        catalog.state.lock().await.templates[0]["kind"] = json!(family);
        for space in [&team, &project] {
            let instance = create(&app, &identity, space.id, creation(template, family)).await;
            let path = format!("{}/prepare-execution", item(space.id, &instance));
            let (status, prepared) =
                request(&app, &identity, Some("alice"), "POST", &path, Value::Null).await;
            if family == "proxy" {
                assert_eq!(status, 409, "{prepared}");
                assert_eq!(prepared["code"], "agent_execution_not_connected");
                continue;
            }
            assert_eq!(status, 200, "{family}: {prepared}");
            if family == "deep" {
                assert_eq!(prepared["skills"]["skills"].as_array().unwrap().len(), 1);
                assert_eq!(prepared["skills"]["skills"][0]["name"], "graph");
                assert_eq!(
                    prepared["skill_detail_url_template"],
                    "/fixture-pod/agents/skills/{skill_name}"
                );
                // The real template stays Deep; it is not relabelled as ReAct.
                let (status, templates) = request(
                    &app,
                    &identity,
                    Some("alice"),
                    "GET",
                    &format!("/spaces/{}/agent-templates", space.id),
                    Value::Null,
                )
                .await;
                assert_eq!(status, 200, "{templates}");
                let advertised = templates
                    .as_array()
                    .unwrap()
                    .iter()
                    .find(|entry| entry["source_agent_id"] == "custom")
                    .unwrap();
                assert_eq!(advertised["category"], "deep");
            } else {
                assert!(prepared["skills"].is_null());
                assert!(prepared["skill_detail_url_template"].is_null());
            }
        }
    }
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
