// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use axum::{
    Router,
    body::{Body, to_bytes},
    http::Request,
};
use control_plane::{
    api::{AppState, routes},
    auth::Authenticator,
    config::Configuration,
};
use serde_json::{Value, json};
use tower::ServiceExt;

struct Fixture {
    pool: PgPool,
    app: Router,
    identity: support::IdentityServer,
    workload: String,
    space: Uuid,
    organization: Uuid,
    session: Uuid,
    agent: Uuid,
    report: Uuid,
}
impl Fixture {
    async fn new() -> Self {
        Self::with_runtime(false).await
    }

    async fn with_runtime(embedded: bool) -> Self {
        Self::with_history(embedded, None).await
    }

    async fn with_history(
        embedded: bool,
        history: Option<std::sync::Arc<dyn control_plane::analytics::history::Reader>>,
    ) -> Self {
        let e = env().await;
        bootstrap::grant_root(&e.pool, "usage-fixture-root")
            .await
            .unwrap();
        let (_, team) = org_and_team(&e).await;
        sqlx::query(
            "insert into space_role_grant(space_id,subject,role) values($1,'bob','member')",
        )
        .bind(team.id)
        .execute(&e.pool)
        .await
        .unwrap();
        let agent = Uuid::new_v4();
        let session = Uuid::new_v4();
        let (runtime, source_agent) = if embedded {
            ("control-plane", fred_rust_agent::AGENT_ID)
        } else {
            ("native", "assistant")
        };
        let template = if embedded {
            control_plane::agents::template_id(team.organization, runtime, source_agent)
        } else {
            agent
        };
        sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values($1,$2,$3,$4,$5,'Usage','{}','alice','usage')")
            .bind(agent).bind(team.id).bind(template).bind(runtime).bind(source_agent).execute(&e.pool).await.unwrap();
        sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,'alice',$2,$3,$4,$5,'Usage',1)")
            .bind(session).bind(team.id).bind(agent).bind(template).bind(runtime).execute(&e.pool).await.unwrap();
        let identity = support::IdentityServer::start().await;
        let mut config: Configuration =
            serde_yaml_ng::from_str(include_str!("../../config/configuration.yaml")).unwrap();
        config.security.user.realm_url = identity.realm.clone();
        config.security.m2m = None;
        config.security.delegation.accept_delegated_calls = true;
        config.security.delegation.service_accounts_only = true;
        let auth = Authenticator::start(config.security().unwrap())
            .await
            .unwrap();
        let app = routes(AppState {
            history,
            pool: e.pool.clone(),
            auth: std::sync::Arc::new(auth),
            // Recording consumption must not refresh the admitted person's consent.
            onboarding: control_plane::onboarding::Onboarding {
                gcu_version: Some("new-version".into()),
                ..Default::default()
            },
            agent_catalog: Default::default(),
            lifecycle: Default::default(),
            directory: None,
            content: None,
            processing: None,
        });
        let now = chrono::Utc::now().timestamp();
        let workload = identity.sign(json!({
            "sub":"service-account-runtime", "preferred_username":"service-account-runtime",
            "azp":"runtime", "client_id":"runtime", "iss":identity.realm,
            "aud":"fred-delegation", "iat":now, "exp":now+300,
            "resource_access":{"fred-delegation":{"roles":["delegation_caller"]}}
        }));
        Self {
            pool: e.pool,
            app,
            identity,
            workload,
            space: team.id,
            organization: team.organization,
            session,
            agent,
            report: Uuid::new_v4(),
        }
    }

    fn path(&self, exchange: &str) -> String {
        format!(
            "/spaces/{}/sessions/{}/exchanges/{exchange}/usage",
            self.space, self.session
        )
    }

    async fn retire(&self) -> Uuid {
        let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
        lifecycle.config.enabled = true;
        let receipt = lifecycle
            .accept_session(&self.pool, "alice", self.space, self.session, false)
            .await
            .unwrap();
        // Simulate the retention deadline, keeping acceptance and cleanup real.
        sqlx::query("update deletion set due_at=requested_at where id=$1")
            .bind(receipt.id)
            .execute(&self.pool)
            .await
            .unwrap();
        receipt.id
    }

    async fn post(&self, token: &str, path: &str, body: &Value) -> (u16, Value) {
        self.post_report(token, path, body, self.report).await
    }

    async fn post_report(
        &self,
        token: &str,
        path: &str,
        body: &Value,
        report: Uuid,
    ) -> (u16, Value) {
        self.post_headers(token, path, body, &[report.to_string()])
            .await
    }

    async fn post_headers(
        &self,
        token: &str,
        path: &str,
        body: &Value,
        keys: &[String],
    ) -> (u16, Value) {
        let mut request = Request::builder()
            .method("POST")
            .uri(path)
            .header("authorization", format!("Bearer {token}"))
            .header("content-type", "application/json");
        for key in keys {
            request = request.header("Idempotency-Key", key.as_str());
        }
        let response = self
            .app
            .clone()
            .oneshot(request.body(Body::from(body.to_string())).unwrap())
            .await
            .unwrap();
        let status = response.status().as_u16();
        let bytes = to_bytes(response.into_body(), 65536).await.unwrap();
        assert!(status != 204 || bytes.is_empty());
        (
            status,
            if bytes.is_empty() {
                Value::Null
            } else {
                serde_json::from_slice(&bytes).unwrap()
            },
        )
    }
}

fn model(source: &str, upstream: &str) -> Value {
    json!({"model_source_id":source, "upstream_model_id":upstream,
        "input_tokens":100, "output_tokens":30, "cache_read_tokens":20,
        "cache_creation_tokens":10})
}

fn usage() -> Value {
    json!({"occurred_at":"2026-01-01T12:00:00.123456789Z", "models":[
        model("test-source", "test-model"), model("other-source", "test-model")
    ]})
}

impl Fixture {
    async fn analytics(&self, user: Option<&str>, mut body: Value) -> (u16, Value) {
        // Existing fixtures default to their own organization; explicit invalid scopes stay intact.
        if let Some(queries) = body["queries"].as_array_mut() {
            for q in queries {
                if q["scope"]["kind"] == "self" && q["scope"].get("organization_id").is_none() {
                    q["scope"]["organization_id"] = json!(self.organization);
                }
            }
        }
        support::request(
            &self.app,
            &self.identity,
            user,
            "POST",
            "/analytics/query",
            body,
        )
        .await
    }

    async fn read_usage(&self, user: Option<&str>, space: Option<Uuid>) -> (u16, Value) {
        self.analytics(
            user,
            analytics_request(space, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z"),
        )
        .await
    }

    async fn admit(&self, user: &str) {
        control_plane::onboarding::accept(&self.pool, Some("new-version"), user, "new-version")
            .await
            .unwrap();
    }

    async fn organization(&self) -> Uuid {
        sqlx::query_scalar("select organization_id from space where id=$1")
            .bind(self.space)
            .fetch_one(&self.pool)
            .await
            .unwrap()
    }

    async fn project(&self, name: &str) -> Space {
        spaces::create_space(
            &self.pool,
            "alice",
            SpaceKind::Project,
            self.space,
            name.into(),
            "alice",
        )
        .await
        .unwrap()
    }

    async fn agent_session(&self, space: Uuid, user: &str, name: &str) -> (Uuid, Uuid) {
        let agent = Uuid::new_v4();
        let session = Uuid::new_v4();
        sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values($1,$2,$1,'native','assistant',$3,'{}','alice',$4)")
            .bind(agent).bind(space).bind(name).bind(agent.to_string()).execute(&self.pool).await.unwrap();
        sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,$2,$3,$4,$4,'native',$5,1)")
            .bind(session).bind(user).bind(space).bind(agent).bind(name).execute(&self.pool).await.unwrap();
        (agent, session)
    }

    async fn record_at(&self, space: Uuid, session: Uuid, exchange: &str, at: &str, input: i64) {
        let mut offer = model("source", "model");
        offer["input_tokens"] = json!(input);
        let body = json!({"occurred_at":at,"models":[offer]});
        let path = format!("/spaces/{space}/sessions/{session}/exchanges/{exchange}/usage");
        let (status, problem) = self
            .post_report(&self.workload, &path, &body, Uuid::new_v4())
            .await;
        assert_eq!(status, 204, "{problem}");
    }
}

fn analytics_request(space: Option<Uuid>, since: &str, until: &str) -> Value {
    let scope = space.map_or(json!({"kind":"self"}), |id| json!({"kind":"space","id":id}));
    let queries: Vec<_> = [("total",vec![]),("series",vec!["time"]),("agents",vec!["agent"]),("models",vec!["model"])]
        .into_iter().map(|(name,group)| json!({"name":name,"scope":scope,"time":{"since":since,"until":until,"timezone":"UTC"},
            "measures":["usage.recorded_exchanges","usage.input_tokens","usage.output_tokens","usage.cache_read_tokens","usage.cache_creation_tokens"],"group_by":group})).collect();
    json!({"queries":queries})
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn usage_read_requires_direct_owner_or_analyst_and_supported_space_kind() {
    let f = Fixture::new().await;
    let org = f.organization().await;
    let project = f.project("Child").await;
    for (user, role, expected) in [
        ("owner", Role::Owner, 200),
        ("analyst", Role::Analyst, 200),
        ("member", Role::Member, 403),
        ("editor", Role::Editor, 403),
    ] {
        let mut conn = f.pool.acquire().await.unwrap();
        for (space, grant) in [(org, Role::Member), (f.space, role)] {
            control_plane::authorization::write_role(&mut conn, user, grant, space, true)
                .await
                .unwrap();
        }
        drop(conn);
        f.admit(user).await;
        let (status, response) = f.read_usage(Some(user), Some(f.space)).await;
        assert_eq!(status, expected, "{user}: {response}");
        // A team role does not authorize the project's own endpoint.
        assert_eq!(f.read_usage(Some(user), Some(project.id)).await.0, 403);
    }
    f.admit("alice").await;
    let personal = spaces::create_personal_space(&f.pool, "alice", org)
        .await
        .unwrap()
        .0;
    for unsupported in [org, personal.id] {
        let (status, error) = f.read_usage(Some("alice"), Some(unsupported)).await;
        assert_eq!(status, 422, "{error}");
        assert_eq!(error["code"], "invalid_fields");
    }
    // An organization owner alone cannot read team usage either.
    control_plane::authorization::write_role(
        &mut f.pool.acquire().await.unwrap(),
        "parent-owner",
        Role::Owner,
        org,
        true,
    )
    .await
    .unwrap();
    f.admit("parent-owner").await;
    assert_eq!(
        f.read_usage(Some("parent-owner"), Some(f.space)).await.0,
        403
    );
    assert_eq!(f.read_usage(None, None).await.0, 401);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn team_usage_includes_retired_and_purged_projects_and_their_agent_names() {
    let f = Fixture::new().await;
    let org = f.organization().await;
    f.admit("alice").await;
    let active = f.project("Active").await;
    let retired = f.project("Retired").await;
    let purged = f.project("Purged").await;
    let other_team = spaces::create_space(
        &f.pool,
        "alice",
        SpaceKind::Team,
        org,
        "Other team".into(),
        "alice",
    )
    .await
    .unwrap();
    let (_, other_session) = f.agent_session(other_team.id, "alice", "Outside").await;
    f.record_at(
        other_team.id,
        other_session,
        "outside",
        "2026-01-01T10:00:00Z",
        10000,
    )
    .await;
    f.record_at(f.space, f.session, "team", "2026-01-01T10:00:00Z", 100)
        .await;
    let mut agents = Vec::new();
    for (project, input) in [(&active, 200), (&retired, 300), (&purged, 400)] {
        let (agent, session) = f.agent_session(project.id, "alice", &project.name).await;
        f.record_at(
            project.id,
            session,
            "project",
            "2026-01-01T11:00:00Z",
            input,
        )
        .await;
        agents.push(agent);
    }
    for project in [&retired, &purged] {
        let deletion = Uuid::new_v4();
        sqlx::query("insert into deletion(id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at) values($1,$2,'project',$3,$4,'alice',now(),now())")
            .bind(deletion).bind(project.id).bind(f.space).bind(org).execute(&f.pool).await.unwrap();
        sqlx::query("update space set deletion_id=$1 where id=$2")
            .bind(deletion)
            .bind(project.id)
            .execute(&f.pool)
            .await
            .unwrap();
    }
    // The receipt and journal outlive physical space/instance removal.
    sqlx::query("delete from agent_instance where space_id=$1")
        .bind(purged.id)
        .execute(&f.pool)
        .await
        .unwrap();
    sqlx::query("delete from space_role_grant where space_id=$1")
        .bind(purged.id)
        .execute(&f.pool)
        .await
        .unwrap();
    sqlx::query("delete from space where id=$1")
        .bind(purged.id)
        .execute(&f.pool)
        .await
        .unwrap();
    sqlx::query("update deletion set status='completed',completed_at=now() where target_id=$1 and target_kind='project'")
        .bind(purged.id).execute(&f.pool).await.unwrap();

    // The analyst has no project role, yet sees aggregate names from those projects.
    for (space, role) in [(org, Role::Member), (f.space, Role::Analyst)] {
        control_plane::authorization::write_role(
            &mut f.pool.acquire().await.unwrap(),
            "analyst",
            role,
            space,
            true,
        )
        .await
        .unwrap();
    }
    f.admit("analyst").await;
    let (status, team) = f.read_usage(Some("analyst"), Some(f.space)).await;
    assert_eq!(status, 200, "{team}");
    assert_eq!(
        team["results"]["total"]["rows"][0]["values"],
        json!({"usage.recorded_exchanges":"4","usage.input_tokens":"1000","usage.output_tokens":"120","usage.cache_read_tokens":"80","usage.cache_creation_tokens":"40"})
    );
    assert_eq!(
        team["results"]["agents"]["rows"]
            .as_array()
            .unwrap()
            .iter()
            .map(|a| a["dimensions"]["display_name"].as_str().unwrap())
            .collect::<Vec<_>>(),
        vec!["Purged", "Retired", "Active", "Usage"]
    );
    assert_eq!(
        team["results"]["agents"]["rows"][0]["dimensions"]["agent_instance_id"],
        agents[2].to_string()
    );
    assert_eq!(
        team["results"]["agents"]["rows"][0]["dimensions"]["space_id"],
        purged.id.to_string()
    );
    assert!(!team.to_string().contains("user_id"));
    let (status, project) = f.read_usage(Some("alice"), Some(active.id)).await;
    assert_eq!(status, 200, "{project}");
    assert_eq!(
        project["results"]["total"]["rows"][0]["values"]["usage.input_tokens"],
        "200"
    );
    assert_eq!(
        project["results"]["agents"]["rows"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(f.read_usage(Some("alice"), Some(retired.id)).await.0, 409);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn personal_usage_retains_old_space_facts_only_while_the_organization_is_authorized() {
    let f = Fixture::new().await;
    let org = f.organization().await;
    let project = f.project("Project").await;
    let personal = spaces::create_personal_space(&f.pool, "alice", org)
        .await
        .unwrap()
        .0;
    f.record_at(f.space, f.session, "team", "2026-01-01T10:00:00Z", 100)
        .await;
    for space in [project.id, personal.id] {
        let (_, session) = f.agent_session(space, "alice", "Own").await;
        f.record_at(space, session, "own", "2026-01-01T11:00:00Z", 200)
            .await;
    }
    let (_, bob_session) = f.agent_session(f.space, "bob", "Bob").await;
    f.record_at(f.space, bob_session, "other", "2026-01-01T12:00:00Z", 900)
        .await;
    sqlx::query("delete from space_role_grant where subject='alice' and space_id<>$1")
        .bind(org)
        .execute(&f.pool)
        .await
        .unwrap();
    // Old space memberships are unnecessary; a current organization grant remains required.
    sqlx::query("delete from platform_bootstrap")
        .execute(&f.pool)
        .await
        .unwrap();
    sqlx::query("delete from platform_role_grant where subject='alice'")
        .execute(&f.pool)
        .await
        .unwrap();
    let (status, own) = f.read_usage(Some("alice"), None).await;
    assert_eq!(status, 200, "{own}");
    assert_eq!(
        own["results"]["total"]["rows"][0]["values"]["usage.recorded_exchanges"],
        "3"
    );
    assert_eq!(
        own["results"]["total"]["rows"][0]["values"]["usage.input_tokens"],
        "500"
    );
    let (status, bob) = f.read_usage(Some("bob"), None).await;
    assert_eq!(status, 200, "{bob}");
    assert_eq!(
        bob["results"]["total"]["rows"][0]["values"]["usage.input_tokens"],
        "900"
    );
    let mut spoof = analytics_request(None, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z");
    spoof["queries"][0]["scope"]["user_id"] = json!("bob");
    assert_eq!(f.analytics(Some("alice"), spoof).await.0, 422);
    sqlx::query("delete from space_role_grant where subject='alice'")
        .execute(&f.pool)
        .await
        .unwrap();
    assert_ne!(f.read_usage(Some("alice"), None).await.0, 200);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn hitl_turns_stay_at_first_consumption_while_tokens_follow_each_report() {
    let f = Fixture::new().await;
    f.admit("alice").await;
    f.record_at(f.space, f.session, "hitl", "2026-01-01T23:30:00Z", 100)
        .await;
    f.record_at(f.space, f.session, "hitl", "2026-01-02T01:30:00Z", 200)
        .await;
    // Same exchange spelling in another session is a different turn.
    let (_, other_session) = f.agent_session(f.space, "alice", "Other").await;
    f.record_at(f.space, other_session, "hitl", "2026-01-02T02:30:00Z", 50)
        .await;
    for space in [None, Some(f.space)] {
        let (status, all) = f.read_usage(Some("alice"), space).await;
        assert_eq!(status, 200, "{all}");
        assert_eq!(
            all["results"]["total"]["rows"][0]["values"],
            json!({"usage.recorded_exchanges":"2","usage.input_tokens":"350","usage.output_tokens":"90","usage.cache_read_tokens":"60","usage.cache_creation_tokens":"30"})
        );
        assert_eq!(all["results"]["series"]["bucket"], "hour");
        assert_eq!(
            all["results"]["series"]["rows"].as_array().unwrap().len(),
            48
        );
        assert_eq!(
            all["results"]["series"]["rows"][0],
            json!({"dimensions":{"kind":"time","start":"2026-01-01T00:00:00Z"},"values":{"usage.recorded_exchanges":"0","usage.input_tokens":"0","usage.output_tokens":"0","usage.cache_read_tokens":"0","usage.cache_creation_tokens":"0"}})
        );
        assert_eq!(
            all["results"]["series"]["rows"][23]["values"]["usage.recorded_exchanges"],
            "1"
        );
        assert_eq!(
            all["results"]["series"]["rows"][25]["values"]["usage.recorded_exchanges"],
            "0"
        );
        assert_eq!(
            all["results"]["series"]["rows"][25]["values"]["usage.input_tokens"],
            "200"
        );
        assert_eq!(
            all["results"]["series"]["rows"][26]["values"]["usage.recorded_exchanges"],
            "1"
        );
        assert_eq!(
            all["results"]["agents"]["rows"][0]["values"]["usage.recorded_exchanges"],
            "1"
        );
        assert_eq!(
            all["results"]["models"]["rows"][0]["values"]["usage.recorded_exchanges"],
            "2"
        );
        let (status, resumed) = f
            .analytics(
                Some("alice"),
                analytics_request(space, "2026-01-02T01:00:00Z", "2026-01-02T02:00:00Z"),
            )
            .await;
        assert_eq!(status, 200, "{resumed}");
        assert_eq!(
            resumed["results"]["total"]["rows"][0]["values"]["usage.recorded_exchanges"],
            "0"
        );
        assert_eq!(
            resumed["results"]["total"]["rows"][0]["values"]["usage.input_tokens"],
            "200"
        );
        assert_eq!(
            resumed["results"]["agents"]["rows"][0]["values"]["usage.recorded_exchanges"],
            "0"
        );
        assert_eq!(
            resumed["results"]["models"]["rows"][0]["values"]["usage.recorded_exchanges"],
            "0"
        );
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn usage_names_fall_back_to_latest_session_and_models_sort_by_total_tokens() {
    let f = Fixture::new().await;
    let mut body = usage();
    body["models"][0]["input_tokens"] = json!(200);
    assert_eq!(f.post(&f.workload, &f.path("models"), &body).await.0, 204);
    let newer_session = Uuid::new_v4();
    sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision,updated_at) values($1,'alice',$2,$3,$3,'native','Latest snapshot',1,now()+interval '1 second')")
        .bind(newer_session).bind(f.space).bind(f.agent).execute(&f.pool).await.unwrap();
    let (_, current) = f.read_usage(Some("alice"), None).await;
    assert_eq!(
        current["results"]["agents"]["rows"][0]["dimensions"]["display_name"],
        "Usage"
    );
    assert_eq!(
        current["results"]["total"]["rows"][0]["values"]["usage.recorded_exchanges"],
        "1"
    );
    assert_eq!(
        current["results"]["models"]["rows"][0]["dimensions"]["model_source_id"],
        "test-source"
    );
    assert_eq!(
        current["results"]["models"]["rows"][1]["dimensions"]["model_source_id"],
        "other-source"
    );
    assert_eq!(
        current["results"]["models"]["rows"][0]["values"]["usage.recorded_exchanges"],
        "1"
    );
    assert_eq!(
        current["results"]["models"]["rows"][1]["values"]["usage.recorded_exchanges"],
        "1"
    );
    sqlx::query("delete from agent_instance where agent_instance_id=$1")
        .bind(f.agent)
        .execute(&f.pool)
        .await
        .unwrap();
    let (_, deleted) = f.read_usage(Some("alice"), None).await;
    assert_eq!(
        deleted["results"]["agents"]["rows"][0]["dimensions"]["display_name"],
        "Latest snapshot"
    );
    sqlx::query("delete from session_metadata where agent_instance_id=$1")
        .bind(f.agent)
        .execute(&f.pool)
        .await
        .unwrap();
    let (_, purged) = f.read_usage(Some("alice"), None).await;
    assert_eq!(
        purged["results"]["agents"]["rows"][0]["dimensions"]["display_name"],
        Value::Null
    );
    assert_eq!(
        purged["results"]["total"]["rows"][0]["values"],
        deleted["results"]["total"]["rows"][0]["values"]
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn usage_ranges_validate_dates_and_generate_continuous_utc_buckets() {
    let f = Fixture::new().await;
    f.admit("alice").await;
    for space in [None, Some(f.space)] {
        for (since, until) in [
            ("no-date", "2026-01-02T00:00:00Z"),
            ("2026-01-01T00:00:00Z", "2026-01-01"),
            ("2026-01-01T00:00:00", "2026-01-02T00:00:00Z"),
            ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            ("2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"),
            ("2024-01-01T00:00:00Z", "2025-01-01T00:00:01Z"),
        ] {
            let (status, error) = f
                .analytics(Some("alice"), analytics_request(space, since, until))
                .await;
            assert_eq!(status, 422, "{error}");
            assert_eq!(error["code"], "invalid_fields");
        }
        for (since, until, bucket, count, first) in [
            (
                "2026-01-01T01:15:00+02:00",
                "2026-01-01T03:00:00+02:00",
                "hour",
                2,
                "2025-12-31T23:00:00Z",
            ),
            (
                "2026-01-01T00:00:00Z",
                "2026-04-03T00:00:00Z",
                "day",
                92,
                "2026-01-01T00:00:00Z",
            ),
            (
                "2026-01-01T00:00:00Z",
                "2026-04-03T00:00:01Z",
                "week",
                14,
                "2025-12-29T00:00:00Z",
            ),
        ] {
            let (status, response) = f
                .analytics(Some("alice"), analytics_request(space, since, until))
                .await;
            assert_eq!(status, 200, "{response}");
            assert_eq!(response["results"]["series"]["bucket"], bucket);
            let series = response["results"]["series"]["rows"].as_array().unwrap();
            assert_eq!(series.len(), count);
            assert_eq!(series[0]["dimensions"]["start"], first);
            for point in series {
                assert!(
                    point["values"]
                        .as_object()
                        .unwrap()
                        .values()
                        .all(|v| v == "0")
                );
            }
            assert_eq!(response["results"]["agents"]["rows"], json!([]));
            assert_eq!(response["results"]["models"]["rows"], json!([]));
        }
        let mut missing = analytics_request(space, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z");
        missing["queries"][0]["time"]
            .as_object_mut()
            .unwrap()
            .remove("until");
        assert_eq!(f.analytics(Some("alice"), missing).await.0, 422);
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn usage_replays_the_whole_report_and_never_changes_its_offer_set() {
    let f = Fixture::new().await;
    let body = usage();
    let path = f.path("turn-1");
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
    let mut reordered = body.clone();
    reordered["models"].as_array_mut().unwrap().reverse();
    assert_eq!(f.post(&f.workload, &path, &reordered).await.0, 204);
    let (count, space, user, agent): (i64, Uuid, String, Uuid) = sqlx::query_as(
        "select count(*) over (), space_id, user_id, agent_instance_id from model_usage",
    )
    .fetch_one(&f.pool)
    .await
    .unwrap();
    assert_eq!(
        (count, space, user.as_str(), agent),
        (2, f.space, "alice", f.agent)
    );
    let offers: Vec<(String, String, i64)> = sqlx::query_as(
        "select model_source_id, upstream_model_id, cache_creation_tokens
         from model_usage where session_id=$1 order by model_source_id",
    )
    .bind(f.session)
    .fetch_all(&f.pool)
    .await
    .unwrap();
    assert_eq!(
        offers,
        vec![
            ("other-source".into(), "test-model".into(), 10),
            ("test-source".into(), "test-model".into(), 10),
        ]
    );
    let mut differences = Vec::new();
    for (field, value) in [
        ("model_source_id", json!("changed-source")),
        ("upstream_model_id", json!("other")),
        ("input_tokens", json!(101)),
        ("output_tokens", json!(31)),
        ("cache_read_tokens", json!(21)),
        ("cache_creation_tokens", json!(11)),
    ] {
        let mut changed = body.clone();
        changed["models"][0][field] = value;
        differences.push(changed);
    }
    let mut changed = body.clone();
    changed["occurred_at"] = json!("2026-01-01T12:00:01Z");
    differences.push(changed);
    let mut added = body.clone();
    added["models"]
        .as_array_mut()
        .unwrap()
        .push(model("test-source", "extra-model"));
    differences.push(added);
    let mut removed = body.clone();
    removed["models"].as_array_mut().unwrap().pop();
    differences.push(removed);
    for changed in differences {
        let (status, problem) = f.post(&f.workload, &path, &changed).await;
        assert_eq!(status, 409, "{problem}");
        assert_eq!(problem["code"], "idempotency_conflict");
        assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn concurrent_usage_reports_agree_or_keep_exactly_one_complete_set() {
    let f = Fixture::new().await;
    let body = usage();
    let path = f.path("identical");
    let (left, right) = tokio::join!(
        f.post(&f.workload, &path, &body),
        f.post(&f.workload, &path, &body),
    );
    assert_eq!((left.0, right.0), (204, 204));
    let count: i64 = sqlx::query_scalar("select count(*) from model_usage")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(count, 2);

    let mut changed_counter = body.clone();
    changed_counter["models"][0]["cache_creation_tokens"] = json!(11);
    let mut added = body.clone();
    added["models"]
        .as_array_mut()
        .unwrap()
        .push(model("test-source", "extra-model"));
    let mut removed = body.clone();
    removed["models"].as_array_mut().unwrap().pop();
    for (i, different) in [changed_counter, added, removed].iter().enumerate() {
        let exchange = format!("different-{i}");
        let path = f.path(&exchange);
        let report = Uuid::new_v4();
        let (left, right) = tokio::join!(
            f.post_report(&f.workload, &path, &body, report),
            f.post_report(&f.workload, &path, different, report),
        );
        let (winner, loser, problem) = match (left.0, right.0) {
            (204, 409) => (&body, different, right.1),
            (409, 204) => (different, &body, left.1),
            statuses => panic!("expected one complete winner: {statuses:?}"),
        };
        assert_eq!(problem["code"], "idempotency_conflict");
        assert_eq!(
            f.post_report(&f.workload, &path, winner, report).await.0,
            204
        );
        assert_eq!(
            f.post_report(&f.workload, &path, loser, report).await.0,
            409
        );
        let count: i64 = sqlx::query_scalar(
            "select count(*) from model_usage where session_id=$1 and exchange_id=$2",
        )
        .bind(f.session)
        .bind(exchange)
        .fetch_one(&f.pool)
        .await
        .unwrap();
        assert_eq!(count as usize, winner["models"].as_array().unwrap().len());
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn usage_rolls_back_the_entire_report_if_a_later_insert_fails() {
    let f = Fixture::new().await;
    // Inject a database failure on the second offer, after the first insert succeeded.
    sqlx::raw_sql(
        "create function reject_usage_offer() returns trigger language plpgsql as $$
        begin
            if new.model_source_id = 'other-source' then
                raise exception 'injected usage write failure';
            end if;
            return new;
        end $$;
        create trigger reject_usage_offer before insert on model_usage
        for each row execute function reject_usage_offer();",
    )
    .execute(&f.pool)
    .await
    .unwrap();
    let body = usage();
    let path = f.path("atomic");
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 500);
    let count: i64 = sqlx::query_scalar("select count(*) from model_usage")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(count, 0);
    sqlx::query("drop trigger reject_usage_offer on model_usage")
        .execute(&f.pool)
        .await
        .unwrap();
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn usage_requires_a_trusted_workload_and_uses_session_provenance_after_retirement() {
    let f = Fixture::new().await;
    let body = usage();
    let path = f.path("turn-1");
    let person = f.identity.token("alice");
    let now = chrono::Utc::now().timestamp();
    let untrusted = f.identity.sign(json!({
        "sub":"service-account-other", "preferred_username":"service-account-other",
        "azp":"other", "client_id":"other", "iss":f.identity.realm,
        "aud":"app", "iat":now, "exp":now+300
    }));
    for token in [&person, &untrusted] {
        let (status, problem) = f.post(token, &path, &body).await;
        assert_eq!(status, 403, "{problem}");
        assert_eq!(problem["code"], "forbidden");
    }
    for query in [
        "person=alice",
        "run=run-1",
        "agent=agent-1",
        "unknown=value",
        "person=alice&run=run-1&agent=agent-1",
    ] {
        let (status, problem) = f.post(&f.workload, &format!("{path}?{query}"), &body).await;
        assert_eq!(status, 422, "{problem}");
        assert_eq!(problem["code"], "invalid_fields");
    }
    let other_space: Uuid = sqlx::query_scalar("select organization_id from space where id=$1")
        .bind(f.space)
        .fetch_one(&f.pool)
        .await
        .unwrap();
    for other in [
        path.replace(&f.space.to_string(), &other_space.to_string()),
        path.replace(&f.session.to_string(), &Uuid::new_v4().to_string()),
    ] {
        let (status, problem) = f.post(&f.workload, &other, &body).await;
        assert_eq!(status, 404, "{problem}");
        assert_eq!(problem["code"], "not_found");
    }
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
    let provenance: Vec<(String, Uuid, Uuid)> = sqlx::query_as(
        "select user_id, space_id, agent_instance_id from model_usage where report_id=$1",
    )
    .bind(f.report)
    .fetch_all(&f.pool)
    .await
    .unwrap();
    assert_eq!(provenance, vec![("alice".into(), f.space, f.agent); 2]);
    let deletion = Uuid::new_v4();
    sqlx::query("insert into deletion(id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at) select $1,$2,'session',id,organization_id,'alice',now(),now() from space where id=$3")
        .bind(deletion).bind(f.session).bind(f.space).execute(&f.pool).await.unwrap();
    sqlx::query("update session_metadata set deletion_id=$2 where session_id=$1")
        .bind(f.session)
        .bind(deletion)
        .execute(&f.pool)
        .await
        .unwrap();
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
    assert_eq!(
        f.post_report(&f.workload, &path, &body, Uuid::new_v4())
            .await
            .0,
        204
    );
    sqlx::query("delete from session_metadata where session_id=$1")
        .bind(f.session)
        .execute(&f.pool)
        .await
        .unwrap();
    let retained: i64 = sqlx::query_scalar("select count(*) from model_usage where session_id=$1")
        .bind(f.session)
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(retained, 4);
    f.admit("alice").await;
    let (status, retained_usage) = f.read_usage(Some("alice"), None).await;
    assert_eq!(status, 200, "{retained_usage}");
    assert_eq!(
        retained_usage["results"]["total"]["rows"][0]["values"]["usage.input_tokens"],
        "400"
    );
    assert_eq!(
        retained_usage["results"]["total"]["rows"][0]["values"]["usage.recorded_exchanges"],
        "1"
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn usage_after_effective_purge_keeps_server_provenance_and_idempotency() {
    let f = Fixture::with_runtime(true).await;
    let operation = f.retire().await;
    // A parent-space purge may be requested by somebody other than the owner.
    sqlx::query("update deletion set actor_subject='platform-owner' where id=$1")
        .bind(operation)
        .execute(&f.pool)
        .await
        .unwrap();
    control_plane::lifecycle::cleanup::batch(&f.pool, operation, &Default::default(), None)
        .await
        .unwrap();
    control_plane::lifecycle::cleanup::batch(&f.pool, operation, &Default::default(), None)
        .await
        .unwrap();
    let state: (String, String, Uuid, bool) = sqlx::query_as(
        "select status,session_user_id,session_agent_instance_id,
            exists(select 1 from session_metadata where session_id=$2)
         from deletion where id=$1",
    )
    .bind(operation)
    .bind(f.session)
    .fetch_one(&f.pool)
    .await
    .unwrap();
    assert_eq!(state, ("completed".into(), "alice".into(), f.agent, false));
    // No earlier report is available to reconstruct the late run's attribution.
    let body = usage();
    let path = f.path("late-turn");
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
    let mut conflicting = body.clone();
    conflicting["models"][0]["input_tokens"] = json!(1);
    assert_eq!(f.post(&f.workload, &path, &conflicting).await.0, 409);
    for foreign in [
        path.replace(&f.space.to_string(), &Uuid::new_v4().to_string()),
        path.replace(&f.session.to_string(), &Uuid::new_v4().to_string()),
    ] {
        assert_eq!(f.post(&f.workload, &foreign, &body).await.0, 404);
    }
    assert_eq!(
        f.post(&f.identity.token("alice"), &path, &body).await.0,
        403
    );

    // Removing the agent and placement does not remove facts or require a live
    // association when a later HITL report arrives for the same exchange.
    sqlx::query("delete from agent_instance where agent_instance_id=$1")
        .bind(f.agent)
        .execute(&f.pool)
        .await
        .unwrap();
    sqlx::query("delete from space where id=$1")
        .bind(f.space)
        .execute(&f.pool)
        .await
        .unwrap();
    assert_eq!(
        f.post_report(&f.workload, &path, &body, Uuid::new_v4())
            .await
            .0,
        204
    );
    let provenance: Vec<(String, Uuid, Uuid)> = sqlx::query_as(
        "select user_id,space_id,agent_instance_id from model_usage where session_id=$1",
    )
    .bind(f.session)
    .fetch_all(&f.pool)
    .await
    .unwrap();
    assert_eq!(provenance, vec![("alice".into(), f.space, f.agent); 4]);
    let (status, retained) = f.read_usage(Some("alice"), None).await;
    assert_eq!(status, 200, "{retained}");
    assert_eq!(
        retained["results"]["total"]["rows"][0]["values"]["usage.input_tokens"],
        "400"
    );
    assert_eq!(
        retained["results"]["total"]["rows"][0]["values"]["usage.recorded_exchanges"],
        "1"
    );
    assert_eq!(
        retained["results"]["agents"]["rows"][0]["dimensions"]["display_name"],
        Value::Null
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn usage_racing_purge_keeps_every_complete_report() {
    let f = Fixture::with_runtime(true).await;
    let operation = f.retire().await;
    let body = usage();
    let path = f.path("racing-turn");
    let reports = futures::future::join_all(
        (0..16).map(|_| f.post_report(&f.workload, &path, &body, Uuid::new_v4())),
    );
    let runtime = Default::default();
    let (purge, results) = tokio::join!(
        control_plane::lifecycle::cleanup::batch(&f.pool, operation, &runtime, None),
        reports
    );
    purge.unwrap();
    for (status, problem) in results {
        assert_eq!(status, 204, "{problem}");
    }
    let count: i64 = sqlx::query_scalar("select count(*) from model_usage where session_id=$1")
        .bind(f.session)
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(count, 32);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn usage_rejects_invalid_fields_without_writing() {
    let f = Fixture::new().await;
    let body = usage();
    let path = f.path("turn-1");
    for (field, value) in [
        ("input_tokens", json!(-1)),
        ("output_tokens", json!(-1)),
        ("cache_read_tokens", json!(-1)),
        ("cache_creation_tokens", json!(-1)),
        ("model_source_id", Value::Null),
        ("model_source_id", json!("")),
        ("model_source_id", json!("-source")),
        ("model_source_id", json!("source/name")),
        ("model_source_id", json!("é")),
        ("model_source_id", json!("s".repeat(65))),
        ("upstream_model_id", Value::Null),
        ("model", json!("legacy-model")),
        ("upstream_model_id", json!("")),
        ("upstream_model_id", json!(" leading")),
        ("upstream_model_id", json!("trailing ")),
        ("upstream_model_id", json!("\tleading")),
        ("upstream_model_id", json!("trailing\u{a0}")),
        ("upstream_model_id", json!("invalid\u{0}model")),
        ("upstream_model_id", json!("x".repeat(257))),
        ("upstream_model_id", json!("é".repeat(129))),
    ] {
        let mut invalid = body.clone();
        invalid["models"][1][field] = value;
        let result = f.post(&f.workload, &path, &invalid).await;
        assert_eq!(result.0, 422, "{field}: {result:?}");
    }
    for field in [
        "model_source_id",
        "upstream_model_id",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
    ] {
        let mut missing = body.clone();
        missing["models"][1].as_object_mut().unwrap().remove(field);
        assert_eq!(f.post(&f.workload, &path, &missing).await.0, 422);
    }
    for (field, value) in [
        (
            "occurred_at",
            json!(chrono::Utc::now() + chrono::Duration::minutes(6)),
        ),
        ("models", json!([])),
        (
            "models",
            json!([model("source", "model"), model("source", "model")]),
        ),
        ("models", Value::Null),
        (
            "models",
            json!(
                (0..9)
                    .map(|i| model("source", &format!("model-{i}")))
                    .collect::<Vec<_>>()
            ),
        ),
        ("space_id", json!(Uuid::new_v4())),
        ("user_id", json!("bob")),
        ("agent_instance_id", json!(Uuid::new_v4())),
    ] {
        let mut invalid = body.clone();
        invalid[field] = value;
        assert_eq!(f.post(&f.workload, &path, &invalid).await.0, 422);
    }
    for field in ["models", "occurred_at"] {
        let mut missing = body.clone();
        missing.as_object_mut().unwrap().remove(field);
        assert_eq!(f.post(&f.workload, &path, &missing).await.0, 422);
    }
    for exchange in [
        "%20leading".into(),
        "trailing%20".into(),
        "control%0A".into(),
        "%C2%A0leading".into(),
        "x".repeat(257),
    ] {
        assert_eq!(f.post(&f.workload, &f.path(&exchange), &body).await.0, 422);
    }
    let count: i64 = sqlx::query_scalar("select count(*) from model_usage")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(count, 0);
    let mut boundary = body;
    boundary["models"] = json!([{
        "model_source_id":"s".repeat(64), "upstream_model_id":"é".repeat(128),
        "input_tokens":0, "output_tokens":0, "cache_read_tokens":0, "cache_creation_tokens":0
    }]);
    boundary["occurred_at"] = json!(chrono::Utc::now() + chrono::Duration::minutes(4));
    let exchange =
        percent_encoding::utf8_percent_encode(&"é".repeat(256), percent_encoding::NON_ALPHANUMERIC)
            .to_string();
    assert_eq!(
        f.post(&f.workload, &f.path(&exchange), &boundary).await.0,
        204
    );
    boundary["models"] = json!(
        (0..8)
            .map(|i| model("source", &format!("model-{i}")))
            .collect::<Vec<_>>()
    );
    assert_eq!(
        f.post_report(
            &f.workload,
            &f.path("eight-offers"),
            &boundary,
            Uuid::new_v4()
        )
        .await
        .0,
        204
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn multiple_reports_for_one_exchange_are_distinct_and_keys_cannot_move() {
    let f = Fixture::new().await;
    let body = usage();
    let path = f.path("hitl-exchange");
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
    let mut resumed = body.clone();
    resumed["models"][0]["input_tokens"] = json!(200);
    let resume_report = Uuid::new_v4();
    assert_eq!(
        f.post_report(&f.workload, &path, &resumed, resume_report)
            .await
            .0,
        204
    );
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
    assert_eq!(
        f.post_report(&f.workload, &path, &resumed, resume_report)
            .await
            .0,
        204
    );
    let totals: (i64, i64, i64) = sqlx::query_as(
        "select count(*), count(distinct report_id), sum(input_tokens)::bigint
         from model_usage where session_id=$1 and exchange_id='hitl-exchange'",
    )
    .bind(f.session)
    .fetch_one(&f.pool)
    .await
    .unwrap();
    assert_eq!(totals, (4, 2, 500));

    let other_session = Uuid::new_v4();
    sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,'alice',$2,$3,$3,'native','Usage',1)")
        .bind(other_session).bind(f.space).bind(f.agent).execute(&f.pool).await.unwrap();
    for moved in [
        f.path("other-exchange"),
        path.replace(&f.session.to_string(), &other_session.to_string()),
    ] {
        let (status, problem) = f.post(&f.workload, &moved, &body).await;
        assert_eq!(status, 409, "{problem}");
        assert_eq!(problem["code"], "idempotency_conflict");
    }
    let count: i64 = sqlx::query_scalar("select count(*) from model_usage")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(count, 4);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn usage_requires_exactly_one_uuid_idempotency_key() {
    let f = Fixture::new().await;
    let body = usage();
    let path = f.path("headers");
    let key = f.report.to_string();
    for keys in [
        vec![],
        vec!["".into()],
        vec!["not-a-uuid".into()],
        vec![key.clone(), key.clone()],
        vec![key.clone(), Uuid::new_v4().to_string()],
        vec![format!("{key}, {key}")],
    ] {
        let (status, problem) = f.post_headers(&f.workload, &path, &body, &keys).await;
        assert_eq!(status, 422, "{problem}");
        assert_eq!(
            problem,
            json!({"code":"invalid_fields", "detail":"Idempotency-Key must be one UUID"})
        );
    }
    let count: i64 = sqlx::query_scalar("select count(*) from model_usage")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(count, 0);
    assert_eq!(f.post(&f.workload, &path, &body).await.0, 204);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn analytics_rejects_unsupported_requests_and_keeps_batches_atomic() {
    let f = Fixture::new().await;
    let mut base = analytics_request(None, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z");
    for q in base["queries"].as_array_mut().unwrap() {
        q["scope"]["organization_id"] = json!(f.organization);
    }
    for (pointer, invalid) in [
        ("/queries/0/scope", json!({})),
        ("/queries/0/scope", Value::Null),
        ("/queries/0/scope", json!({"kind":"spaces","ids":[]})),
        ("/queries/0/scope", json!({"kind":"platform"})),
        (
            "/queries/0/scope",
            json!({"kind":"organization","id":f.space}),
        ),
        ("/queries/0/time/timezone", json!("Europe/Paris")),
        ("/queries/0/measures", json!(["usage.unknown"])),
        ("/queries/0/measures", json!([])),
        (
            "/queries/0/measures",
            json!(["usage.input_tokens", "usage.input_tokens"]),
        ),
        ("/queries/0/group_by", json!(["user"])),
        ("/queries/0/group_by", json!(["agent", "model"])),
        ("/queries/1/name", json!("total")),
        ("/queries/0/name", json!("")),
        ("/queries", json!([])),
    ] {
        let mut body = base.clone();
        *body.pointer_mut(pointer).unwrap() = invalid;
        let (status, error) = f.analytics(Some("alice"), body).await;
        assert_eq!(status, 422, "{pointer}: {error}");
        assert!(error.get("results").is_none());
    }
    for field in ["filters", "comparison", "calendar", "engine"] {
        let mut body = base.clone();
        body["queries"][0][field] = json!({});
        assert_eq!(f.analytics(Some("alice"), body).await.0, 422, "{field}");
    }
    let mut body = base.clone();
    body["queries"][0].as_object_mut().unwrap().remove("scope");
    assert_eq!(f.analytics(Some("alice"), body).await.0, 422);
    for (index, limit) in [(0, 1), (1, 1), (2, 0), (3, 101)] {
        let mut body = base.clone();
        body["queries"][index]["limit"] = json!(limit);
        assert_eq!(f.analytics(Some("alice"), body).await.0, 422);
    }
    let mut body = base.clone();
    body["queries"] = json!(vec![body["queries"][0].clone(); 9]);
    assert_eq!(f.analytics(Some("alice"), body).await.0, 422);
    let mut body = base.clone();
    body["queries"][1]["time"]["bucket"] = json!("hour");
    body["queries"][1]["time"]["until"] = json!("2026-12-31T00:00:00Z");
    let (status, error) = f.analytics(Some("alice"), body).await;
    assert_eq!(status, 422);
    assert_eq!(error["code"], "query_too_large");
    // An authorized personal query cannot hide a forbidden collective query.
    f.admit("alice").await;
    let mut body = base.clone();
    body["queries"][3]["scope"] = json!({"kind":"space","id":Uuid::new_v4()});
    let (status, error) = f.analytics(Some("alice"), body).await;
    assert_eq!(status, 404);
    assert!(error.get("results").is_none());
    let now = chrono::Utc::now().timestamp();
    for claims in [
        json!({"sub":"service-account-runtime", "preferred_username":"service-account-runtime","client_id":"runtime"}),
        json!({"sub":"role-only", "preferred_username":"role-only","resource_access":{"app":{"roles":["service_agent"]}}}),
    ] {
        let mut claims = claims;
        for (key, value) in json!({"iss":f.identity.realm,"aud":"app","iat":now,"exp":now+300})
            .as_object()
            .unwrap()
        {
            claims[key] = value.clone();
        }
        let token = f.identity.sign(claims);
        assert_eq!(f.post(&token, "/analytics/query", &base).await.0, 403);
    }
    for path in ["/me/usage".to_owned(), format!("/spaces/{}/usage", f.space)] {
        assert_eq!(
            support::request(
                &f.app,
                &f.identity,
                Some("alice"),
                "GET",
                &path,
                Value::Null
            )
            .await
            .0,
            404
        );
    }
    let mut too_big = base.clone();
    too_big["queries"][0]["name"] = json!("x".repeat(70_000));
    assert_eq!(f.analytics(Some("alice"), too_big).await.0, 413);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn analytics_preserves_big_integers_and_marks_truncated_rankings() {
    let f = Fixture::new().await;
    let max = i64::MAX;
    for n in 0..3 {
        let mut offer = model("source", &format!("model-{n}"));
        offer["input_tokens"] = json!(max);
        let report = json!({"occurred_at":"2026-01-01T12:00:00Z", "models":[offer]});
        assert_eq!(
            f.post_report(
                &f.workload,
                &f.path(&format!("exchange-{n}")),
                &report,
                Uuid::new_v4()
            )
            .await
            .0,
            204
        );
    }
    let mut request = analytics_request(None, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z");
    request["queries"][3]["limit"] = json!(2);
    request["queries"][0]["measures"]
        .as_array_mut()
        .unwrap()
        .push(json!("usage.total_tokens"));
    let (status, body) = f.analytics(Some("alice"), request).await;
    assert_eq!(status, 200, "{body}");
    assert_eq!(body["calculation"], "exact");
    assert_eq!(body["collection_completeness"], "unknown");
    let total = &body["results"]["total"]["rows"][0]["values"];
    assert_eq!(
        total["usage.input_tokens"],
        (i128::from(max) * 3).to_string()
    );
    assert_eq!(
        total["usage.total_tokens"],
        (i128::from(max) * 3 + 90).to_string()
    );
    assert_eq!(body["results"]["models"]["truncated"], true);
    assert_eq!(
        body["results"]["models"]["rows"].as_array().unwrap().len(),
        2
    );
    assert_eq!(
        body["results"]["models"]["rows"][0]["dimensions"]["upstream_model_id"],
        "model-0"
    );
    for name in ["total", "series", "agents"] {
        assert_eq!(body["results"][name]["truncated"], false);
    }
    for measure in [
        "usage.input_tokens",
        "usage.output_tokens",
        "usage.recorded_exchanges",
    ] {
        let sum: i128 = body["results"]["series"]["rows"]
            .as_array()
            .unwrap()
            .iter()
            .map(|r| {
                r["values"][measure]
                    .as_str()
                    .unwrap()
                    .parse::<i128>()
                    .unwrap()
            })
            .sum();
        assert_eq!(total[measure], sum.to_string());
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn analytics_source_lock_failure_never_returns_zero_or_partial_results() {
    let f = Fixture::new().await;
    let mut held = f.pool.begin().await.unwrap();
    sqlx::query("lock table model_usage in access exclusive mode")
        .execute(&mut *held)
        .await
        .unwrap();
    let (status, body) = f.read_usage(Some("alice"), None).await;
    assert_eq!(status, 503, "{body}");
    assert_eq!(body["code"], "dependency_unavailable");
    assert!(body.get("results").is_none());
    held.rollback().await.unwrap();
    assert_eq!(f.read_usage(Some("alice"), None).await.0, 200);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn analytics_distinct_reads_share_a_snapshot_during_concurrent_reporting() {
    let f = Fixture::new().await;
    f.record_at(f.space, f.session, "before", "2026-01-01T12:00:00Z", 100)
        .await;
    // Only this disposable database: gate the journal scan after its snapshot is
    // acquired, without adding any test hook to production code.
    sqlx::raw_sql(
        "alter table model_usage rename to fixture_usage;
        create function fixture_usage_gate() returns boolean language plpgsql volatile as $$
        begin perform pg_advisory_xact_lock(897126); return true; end $$;
        create view model_usage as select * from fixture_usage where fixture_usage_gate();",
    )
    .execute(&f.pool)
    .await
    .unwrap();
    let mut gate = f.pool.begin().await.unwrap();
    sqlx::query("select pg_advisory_xact_lock(897126)")
        .execute(&mut *gate)
        .await
        .unwrap();
    let mut body = analytics_request(None, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z");
    // Two genuinely distinct SQL reads; compatible total/series/rankings are
    // separately covered by the planner test and existing equivalence tests.
    let mut second = body["queries"][0].clone();
    second["name"] = json!("later_end");
    second["time"]["until"] = json!("2026-01-04T00:00:00Z");
    body["queries"].as_array_mut().unwrap().push(second);
    let request = f.analytics(Some("alice"), body);
    let writer = async {
        tokio::time::timeout(Duration::from_secs(3), async {
            loop {
                let waiting: bool = sqlx::query_scalar("select exists(select 1 from pg_stat_activity where datname=current_database() and wait_event='advisory' and query like 'with scoped%')")
                    .fetch_one(&f.pool).await.unwrap();
                if waiting { break; }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        }).await.unwrap();
        sqlx::query("insert into fixture_usage select $1,session_id,'after',occurred_at,space_id,user_id,agent_instance_id,model_source_id,upstream_model_id,200,output_tokens,cache_read_tokens,cache_creation_tokens from fixture_usage limit 1")
            .bind(Uuid::new_v4()).execute(&f.pool).await.unwrap();
        gate.commit().await.unwrap();
    };
    let ((status, response), ()) = tokio::join!(request, writer);
    assert_eq!(status, 200, "{response}");
    for name in ["total", "later_end"] {
        assert_eq!(
            response["results"][name]["rows"][0]["values"]["usage.input_tokens"],
            "100"
        );
    }
    let (status, after) = f.read_usage(Some("alice"), None).await;
    assert_eq!(status, 200, "{after}");
    assert_eq!(
        after["results"]["total"]["rows"][0]["values"]["usage.input_tokens"],
        "300"
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn analytics_documented_request_and_response() {
    let f = Fixture::new().await;
    f.record_at(f.space, f.session, "one", "2026-01-01T12:00:00Z", 100)
        .await;
    let (status, response) = f.analytics(Some("alice"), json!({"queries":[{"name":"input","scope":{"kind":"self"},"time":{"since":"2026-01-01T00:00:00Z","until":"2026-01-03T00:00:00Z","timezone":"UTC"},"measures":["usage.input_tokens"],"group_by":[]}]})).await;
    assert_eq!(status, 200, "{response}");
    assert_eq!(
        response,
        json!({"calculation":"exact","collection_completeness":"unknown","results":{"input":{"since":"2026-01-01T00:00:00Z","until":"2026-01-03T00:00:00Z","timezone":"UTC","measures":[{"id":"usage.input_tokens","unit":"token","value_type":"integer","calculation":"exact"}],"rows":[{"dimensions":{"kind":"total"},"values":{"usage.input_tokens":"100"}}],"truncated":false}}})
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn analytics_estimates_cover_all_models_and_keep_zero_distinct_from_missing() {
    let f = Fixture::new().await;
    let mut request = analytics_request(None, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z");
    request["queries"][0]["measures"] = json!([
        "usage.total_tokens",
        "usage.cost_eur",
        "usage.co2e_grams",
        "usage.energy_kwh"
    ]);
    let (status, empty) = f.analytics(Some("alice"), request.clone()).await;
    assert_eq!(status, 200, "{empty}");
    assert_eq!(
        empty["results"]["total"]["rows"][0]["estimates"]["usage.cost_eur"]["value"],
        "0"
    );
    for n in 0..101 {
        let body = json!({"occurred_at":"2026-01-01T12:00:00Z", "models":[model("source", &format!("unknown-{n}"))]});
        assert_eq!(
            f.post_report(
                &f.workload,
                &f.path(&format!("turn-{n}")),
                &body,
                Uuid::new_v4()
            )
            .await
            .0,
            204
        );
    }
    let (status, body) = f.analytics(Some("alice"), request.clone()).await;
    assert_eq!(status, 200, "{body}");
    assert_eq!(body["calculation"], "mixed");
    assert_eq!(body["results"]["models"]["truncated"], true);
    let row = &body["results"]["total"]["rows"][0];
    assert_eq!(row["values"]["usage.total_tokens"], "13130");
    assert_eq!(row["estimates"]["usage.cost_eur"]["value"], Value::Null);
    assert_eq!(
        row["estimates"]["usage.cost_eur"]["coverage"],
        "unavailable"
    );
    let co2e = &row["estimates"]["usage.co2e_grams"];
    assert_eq!(co2e["fallback"], true);
    assert_eq!(co2e["coverage"], "complete");
    assert!((co2e["value"].as_str().unwrap().parse::<f64>().unwrap() - 7.878).abs() < 1e-10);
    let (_, bob) = f.analytics(Some("bob"), request).await;
    assert_eq!(
        bob["results"]["total"]["rows"][0]["estimates"]["usage.cost_eur"]["value"],
        "0"
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn analytics_estimation_sql_exercises_cache_currency_and_partial_factors() {
    let f = Fixture::new().await;
    assert_eq!(f.post(&f.workload, &f.path("one"), &usage()).await.0, 204);
    // Synthetic coefficients are test inputs only; production embeds the sole maintained YAML.
    let base = json!({"usd_per_eur":2,"models":{"default":{
        "cost_per_1k_input_tokens":1,"cost_per_1k_output_tokens":2,"cost_per_1k_cached_input_tokens":0.1,
        "co2e_grams_per_1k_tokens":3,"kwh_per_1k_tokens":0.001
    }}});
    let sql = concat!(
        "select estimates from (with scoped as not materialized (select * from model_usage where user_id=$1) ",
        include_str!("../../src/sessions/usage/read.sql"),
        ") result where start is null and agent_instance_id is null and model_source_id is null"
    );
    let since: chrono::DateTime<chrono::Utc> = "2026-01-01T00:00:00Z".parse().unwrap();
    let until: chrono::DateTime<chrono::Utc> = "2026-01-03T00:00:00Z".parse().unwrap();
    for (catalog, expected_value, coverage) in [
        (base.clone(), Some(0.142), "complete"),
        (
            {
                let mut c = base.clone();
                c["models"]["default"]["cost_per_1k_cached_input_tokens"] = json!(0);
                c
            },
            None,
            "unavailable",
        ),
    ] {
        let estimates: Value = sqlx::query_scalar(sql)
            .bind("alice")
            .bind(since)
            .bind(until)
            .bind("day")
            .bind(101_i64)
            .bind(catalog)
            .fetch_one(&f.pool)
            .await
            .unwrap();
        assert_eq!(estimates["usage.cost_eur"]["coverage"], coverage);
        let value = estimates["usage.cost_eur"]["value"]
            .as_str()
            .map(|v| v.parse::<f64>().unwrap());
        assert_eq!(value, expected_value);
        assert_eq!(estimates["usage.energy_kwh"]["coverage"], "complete");
    }
    sqlx::query(
        "update model_usage set upstream_model_id='missing' where model_source_id='other-source'",
    )
    .execute(&f.pool)
    .await
    .unwrap();
    let mut partial = base;
    partial["models"]["missing"] = json!({});
    let estimates: Value = sqlx::query_scalar(sql)
        .bind("alice")
        .bind(since)
        .bind(until)
        .bind("day")
        .bind(101_i64)
        .bind(partial)
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(estimates["usage.cost_eur"]["coverage"], "partial");
    assert_eq!(
        estimates["usage.cost_eur"]["value"]
            .as_str()
            .unwrap()
            .parse::<f64>()
            .unwrap(),
        0.071
    );
    assert_eq!(estimates["usage.co2e_grams"]["coverage"], "partial");
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn analytics_historical_is_self_only_and_unavailable_is_not_empty() {
    let f = Fixture::new().await;
    let mut request = analytics_request(None, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z");
    let q = json!({"name":"skills","scope":{"kind":"self"},"time":request["queries"][0]["time"],"measures":["skills.user_loads","skills.agent_loads","skills.total_loads"],"group_by":["skill"]});
    request["queries"] = json!([q]);
    assert_eq!(f.analytics(Some("alice"), request.clone()).await.0, 503);
    assert_eq!(f.analytics(None, request.clone()).await.0, 401);
    let mut collective = request.clone();
    collective["queries"][0]["scope"] = json!({"kind":"space","id":f.space});
    assert_eq!(f.analytics(Some("alice"), collective).await.0, 403);
    let mut forged = request.clone();
    forged["queries"][0]["scope"]["user_id"] = json!("bob");
    assert_eq!(f.analytics(Some("alice"), forged).await.0, 422);
    request["queries"].as_array_mut().unwrap().push(
        analytics_request(None, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z")["queries"][0]
            .clone(),
    );
    assert_eq!(f.analytics(Some("alice"), request).await.0, 422);
    assert_eq!(f.read_usage(Some("alice"), None).await.0, 200);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn analytics_historical_route_injects_identity_and_never_needs_a_sql_transaction() {
    use axum::{
        Json,
        routing::{get, post},
    };
    use control_plane::analytics::opensearch::{Config, OpenSearch};
    let observed = std::sync::Arc::new(std::sync::Mutex::new(Vec::<Value>::new()));
    let capture = observed.clone();
    let upstream = Router::new()
        .route("/fixture/_mapping", get(|| async { Json(json!({"fixture":{"mappings":{"properties":{
            "@timestamp":{"type":"date"},"metric":{"properties":{"name":{"type":"keyword"}}},
            "dims":{"properties":{"space_id":{"type":"keyword"},"user_id":{"type":"keyword"},"skill_name":{"type":"keyword"},"skill_origin":{"type":"keyword"}}}
        }}}})) }))
        .route("/fixture/_search", post(move |Json(body): Json<Value>| { let capture = capture.clone(); async move {
            capture.lock().unwrap().push(body["query"]["bool"]["filter"][2]["terms"]["dims.space_id"].clone());
            let subject=&body["query"]["bool"]["filter"][1]["term"]["dims.user_id"];
            let count=if subject == "alice" { 3 } else if subject == "bob" { 7 } else { panic!("unexpected subject") };
            Json(json!({"timed_out":false,"_shards":{"total":1,"successful":1,"failed":0},"aggregations":{"skills":{"buckets":[{
                "key":{"skill":"read"},"doc_count":count,"origins":{"buckets":{"user":{"doc_count":count},"agent":{"doc_count":0}}}
            }]}}}))
        }}));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let config = Config {
        url: format!("http://{}", listener.local_addr().unwrap()),
        index: "fixture".into(),
        username: None,
        password_env_var: None,
    };
    let server = tokio::spawn(async move { axum::serve(listener, upstream).await.unwrap() });
    let f = Fixture::with_history(false, Some(OpenSearch::configured(&config).unwrap())).await;
    let globex = support::member_organization(&f.pool, "Globex", "alice")
        .await
        .unwrap();
    // Journal reads fail while organization authority remains available.
    let mut locked = f.pool.begin().await.unwrap();
    sqlx::query("lock table model_usage in access exclusive mode")
        .execute(&mut *locked)
        .await
        .unwrap();
    let request = json!({"queries":[{"name":"skills","scope":{"kind":"self"},"time":{"since":"2026-01-01T00:00:00Z","until":"2026-01-03T00:00:00Z","timezone":"UTC"},"measures":["skills.user_loads","skills.agent_loads","skills.total_loads"],"group_by":["skill"],"limit":100}]});
    for (subject, count) in [("alice", "3"), ("bob", "7")] {
        let (status, response) = f.analytics(Some(subject), request.clone()).await;
        assert_eq!(status, 200, "{response}");
        assert_eq!(
            response["results"]["skills"]["rows"][0]["values"]["skills.total_loads"],
            count
        );
        assert_eq!(response["calculation"], "exact");
        assert_eq!(response["collection_completeness"], "unknown");
    }
    let mut globex_request = request.clone();
    globex_request["queries"][0]["scope"]["organization_id"] = json!(globex.id);
    assert_eq!(
        f.analytics(Some("alice"), globex_request.clone()).await.0,
        200
    );
    assert_eq!(f.analytics(Some("bob"), globex_request).await.0, 404);
    {
        let calls = observed.lock().unwrap();
        assert_eq!(calls.len(), 3); // Bob's forbidden organization never reaches the source.
        for scope in &calls[..2] {
            let ids = scope.as_array().unwrap();
            assert!(ids.contains(&json!(f.space)));
            assert!(!ids.contains(&json!(globex.id)));
        }
        assert_eq!(calls[2], json!([globex.id]));
    }
    assert_ne!(f.read_usage(Some("alice"), None).await.0, 200);
    server.abort();
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn personal_analytics_never_combines_acme_and_globex_and_requires_current_organization_access()
 {
    let f = Fixture::new().await;
    sqlx::query("update space set name='Acme' where id=$1")
        .bind(f.organization)
        .execute(&f.pool)
        .await
        .unwrap();
    let globex = support::member_organization(&f.pool, "Globex", "alice")
        .await
        .unwrap();
    let team = spaces::create_space(
        &f.pool,
        "alice",
        SpaceKind::Team,
        globex.id,
        "Globex team".into(),
        "alice",
    )
    .await
    .unwrap();
    let (_, session) = f.agent_session(team.id, "alice", "Globex agent").await;
    f.record_at(f.space, f.session, "acme", "2026-01-01T12:00:00Z", 100)
        .await;
    f.record_at(team.id, session, "globex", "2026-01-01T12:00:00Z", 300)
        .await;
    for (org, tokens, co2e) in [(f.organization, "130", 0.078), (globex.id, "330", 0.198)] {
        let mut request = analytics_request(None, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z");
        for q in request["queries"].as_array_mut().unwrap() {
            q["scope"]["organization_id"] = json!(org);
            q["measures"] = json!([
                "usage.total_tokens",
                "usage.cost_eur",
                "usage.co2e_grams",
                "usage.energy_kwh"
            ]);
        }
        let (status, response) = f.analytics(Some("alice"), request).await;
        assert_eq!(status, 200, "{response}");
        for name in ["total", "agents", "models"] {
            let rows = response["results"][name]["rows"].as_array().unwrap();
            assert_eq!(rows.len(), 1);
            assert_eq!(rows[0]["values"]["usage.total_tokens"], tokens);
            assert!(
                (rows[0]["estimates"]["usage.co2e_grams"]["value"]
                    .as_str()
                    .unwrap()
                    .parse::<f64>()
                    .unwrap()
                    - co2e)
                    .abs()
                    < 1e-10
            );
            assert_eq!(
                rows[0]["estimates"]["usage.cost_eur"]["coverage"],
                "unavailable"
            );
            assert!(
                (rows[0]["estimates"]["usage.energy_kwh"]["value"]
                    .as_str()
                    .unwrap()
                    .parse::<f64>()
                    .unwrap()
                    - co2e / 200.0)
                    .abs()
                    < 1e-10
            );
        }
        let sum: u64 = response["results"]["series"]["rows"]
            .as_array()
            .unwrap()
            .iter()
            .map(|r| {
                r["values"]["usage.total_tokens"]
                    .as_str()
                    .unwrap()
                    .parse::<u64>()
                    .unwrap()
            })
            .sum();
        assert_eq!(sum.to_string(), tokens);
    }
    let mut request = analytics_request(None, "2026-01-01T00:00:00Z", "2026-01-03T00:00:00Z");
    let token = f.identity.token("alice");
    // Deliberately bypass the test fixture's default organization: the public contract requires it.
    assert_eq!(f.post(&token, "/analytics/query", &request).await.0, 422);
    for q in request["queries"].as_array_mut().unwrap() {
        q["scope"]["organization_id"] = json!(globex.id);
    }
    assert_eq!(f.analytics(Some("bob"), request.clone()).await.0, 404);
    sqlx::query("delete from space_role_grant where subject='alice' and space_id in (select id from space where organization_id=$1)").bind(globex.id).execute(&f.pool).await.unwrap();
    assert_eq!(f.analytics(Some("alice"), request).await.0, 404);
    assert_eq!(f.read_usage(Some("alice"), None).await.0, 200);
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn boss_platform_admin_observes_only_self_in_one_authorized_organization() {
    let f = Fixture::new().await;
    let globex = support::member_organization(&f.pool, "Globex", "alice")
        .await
        .unwrap();
    control_plane::authorization::write_platform(
        &mut f.pool.acquire().await.unwrap(),
        "boss",
        control_plane::roles::PlatformRole::PlatformAdmin,
        true,
    )
    .await
    .unwrap();
    for org in [f.organization, globex.id] {
        sqlx::query(
            "insert into space_role_grant(space_id,subject,role) values($1,'boss','member')",
        )
        .bind(org)
        .execute(&f.pool)
        .await
        .unwrap();
    }
    let (_, acme_session) = f.agent_session(f.space, "boss", "Boss Acme").await;
    let (_, globex_session) = f.agent_session(globex.id, "boss", "Boss Globex").await;
    f.record_at(f.space, acme_session, "acme", "2026-01-01T12:00:00Z", 100)
        .await;
    f.record_at(
        globex.id,
        globex_session,
        "globex",
        "2026-01-01T12:00:00Z",
        300,
    )
    .await;
    // Platform administration must not add Alice's consumption to Boss's self view.
    f.record_at(f.space, f.session, "alice", "2026-01-01T12:00:00Z", 900)
        .await;
    let request = |org| {
        json!({"queries":[{"name":"total","scope":{"kind":"self","organization_id":org},
        "time":{"since":"2026-01-01T00:00:00Z","until":"2026-01-03T00:00:00Z","timezone":"UTC"},
        "measures":["usage.input_tokens"]}]})
    };
    for (org, expected) in [
        (f.organization, "100"),
        (globex.id, "300"),
        (f.organization, "100"),
    ] {
        let (status, response) = f.analytics(Some("boss"), request(org)).await;
        assert_eq!(status, 200, "{response}");
        assert_eq!(
            response["results"]["total"]["rows"][0]["values"]["usage.input_tokens"],
            expected
        );
    }
    sqlx::query("delete from space_role_grant where subject='boss' and space_id=$1")
        .bind(globex.id)
        .execute(&f.pool)
        .await
        .unwrap();
    assert_eq!(f.analytics(Some("boss"), request(globex.id)).await.0, 404);
    assert_eq!(
        f.analytics(Some("boss"), request(f.organization)).await.0,
        200
    );
    // His platform role also grants no implicit collective analytics permission.
    f.admit("boss").await;
    assert_eq!(f.read_usage(Some("boss"), Some(f.space)).await.0, 403);
}
