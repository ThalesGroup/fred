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
    session: Uuid,
    agent: Uuid,
    report: Uuid,
}
impl Fixture {
    async fn new() -> Self {
        let e = env().await;
        bootstrap::grant_root(&e.pool, "usage-fixture-root")
            .await
            .unwrap();
        let (_, team) = org_and_team(&e).await;
        let agent = Uuid::new_v4();
        let session = Uuid::new_v4();
        sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values($1,$2,$1,'native','assistant','Usage','{}','alice','usage')")
            .bind(agent).bind(team.id).execute(&e.pool).await.unwrap();
        sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision) values($1,'alice',$2,$3,$3,'native','Usage',1)")
            .bind(session).bind(team.id).bind(agent).execute(&e.pool).await.unwrap();
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
    async fn get(&self, user: Option<&str>, path: &str) -> (u16, Value) {
        support::request(&self.app, &self.identity, user, "GET", path, Value::Null).await
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

const READ_RANGE: &str = "since=2026-01-01T00:00:00Z&until=2026-01-03T00:00:00Z";

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
        let (status, response) = f
            .get(
                Some(user),
                &format!("/spaces/{}/usage?{READ_RANGE}", f.space),
            )
            .await;
        assert_eq!(status, expected, "{user}: {response}");
        // A team role does not authorize the project's own endpoint.
        assert_eq!(
            f.get(
                Some(user),
                &format!("/spaces/{}/usage?{READ_RANGE}", project.id)
            )
            .await
            .0,
            403
        );
    }
    f.admit("alice").await;
    let personal = spaces::create_personal_space(&f.pool, "alice", org)
        .await
        .unwrap()
        .0;
    for unsupported in [org, personal.id] {
        let (status, error) = f
            .get(
                Some("alice"),
                &format!("/spaces/{unsupported}/usage?{READ_RANGE}"),
            )
            .await;
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
        f.get(Some("parent-owner"), &format!("/spaces/{}/usage", f.space))
            .await
            .0,
        403
    );
    assert_eq!(f.get(None, "/me/usage").await.0, 401);
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
    let (status, team) = f
        .get(
            Some("analyst"),
            &format!("/spaces/{}/usage?{READ_RANGE}", f.space),
        )
        .await;
    assert_eq!(status, 200, "{team}");
    assert_eq!(
        team["totals"],
        json!({"turns":4,"input_tokens":1000,"output_tokens":120,"cache_read_tokens":80,"cache_creation_tokens":40})
    );
    assert_eq!(
        team["by_agent"]
            .as_array()
            .unwrap()
            .iter()
            .map(|a| a["display_name"].as_str().unwrap())
            .collect::<Vec<_>>(),
        vec!["Purged", "Retired", "Active", "Usage"]
    );
    assert_eq!(
        team["by_agent"][0]["agent_instance_id"],
        agents[2].to_string()
    );
    assert_eq!(team["by_agent"][0]["space_id"], purged.id.to_string());
    assert!(!team.to_string().contains("user_id"));
    let (status, project) = f
        .get(
            Some("alice"),
            &format!("/spaces/{}/usage?{READ_RANGE}", active.id),
        )
        .await;
    assert_eq!(status, 200, "{project}");
    assert_eq!(project["totals"]["input_tokens"], 200);
    assert_eq!(project["by_agent"].as_array().unwrap().len(), 1);
    assert_eq!(
        f.get(Some("alice"), &format!("/spaces/{}/usage", retired.id))
            .await
            .0,
        409
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn personal_usage_keeps_only_the_persons_facts_after_all_roles_are_removed() {
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
    sqlx::query("delete from space_role_grant where subject='alice'")
        .execute(&f.pool)
        .await
        .unwrap();
    // No bootstrap or current consent either: authentication alone suffices.
    sqlx::query("delete from platform_bootstrap")
        .execute(&f.pool)
        .await
        .unwrap();
    sqlx::query("delete from platform_role_grant where subject='alice'")
        .execute(&f.pool)
        .await
        .unwrap();
    let (status, own) = f
        .get(Some("alice"), &format!("/me/usage?{READ_RANGE}"))
        .await;
    assert_eq!(status, 200, "{own}");
    assert_eq!(own["totals"]["turns"], 3);
    assert_eq!(own["totals"]["input_tokens"], 500);
    let (status, bob) = f.get(Some("bob"), &format!("/me/usage?{READ_RANGE}")).await;
    assert_eq!(status, 200, "{bob}");
    assert_eq!(bob["totals"]["input_tokens"], 900);
    assert_eq!(
        f.get(
            Some("alice"),
            &format!("/me/usage?{READ_RANGE}&user_id=bob")
        )
        .await
        .0,
        422
    );
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
    for path in ["/me/usage".to_owned(), format!("/spaces/{}/usage", f.space)] {
        let (status, all) = f.get(Some("alice"), &format!("{path}?{READ_RANGE}")).await;
        assert_eq!(status, 200, "{all}");
        assert_eq!(
            all["totals"],
            json!({"turns":2,"input_tokens":350,"output_tokens":90,"cache_read_tokens":60,"cache_creation_tokens":30})
        );
        assert_eq!(all["interval"], "hour");
        assert_eq!(all["series"].as_array().unwrap().len(), 48);
        assert_eq!(
            all["series"][0],
            json!({"start":"2026-01-01T00:00:00Z","turns":0,"input_tokens":0,"output_tokens":0,"cache_read_tokens":0,"cache_creation_tokens":0})
        );
        assert_eq!(all["series"][23]["turns"], 1);
        assert_eq!(all["series"][25]["turns"], 0);
        assert_eq!(all["series"][25]["input_tokens"], 200);
        assert_eq!(all["series"][26]["turns"], 1);
        assert_eq!(all["by_agent"][0]["turns"], 1);
        assert_eq!(all["by_model"][0]["turns"], 2);
        let (status, resumed) = f
            .get(
                Some("alice"),
                &format!("{path}?since=2026-01-02T01:00:00Z&until=2026-01-02T02:00:00Z"),
            )
            .await;
        assert_eq!(status, 200, "{resumed}");
        assert_eq!(resumed["totals"]["turns"], 0);
        assert_eq!(resumed["totals"]["input_tokens"], 200);
        assert_eq!(resumed["by_agent"][0]["turns"], 0);
        assert_eq!(resumed["by_model"][0]["turns"], 0);
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
    let (_, current) = f
        .get(Some("alice"), &format!("/me/usage?{READ_RANGE}"))
        .await;
    assert_eq!(current["by_agent"][0]["display_name"], "Usage");
    assert_eq!(current["totals"]["turns"], 1);
    assert_eq!(current["by_model"][0]["model_source_id"], "test-source");
    assert_eq!(current["by_model"][1]["model_source_id"], "other-source");
    assert_eq!(current["by_model"][0]["turns"], 1);
    assert_eq!(current["by_model"][1]["turns"], 1);
    sqlx::query("delete from agent_instance where agent_instance_id=$1")
        .bind(f.agent)
        .execute(&f.pool)
        .await
        .unwrap();
    let (_, deleted) = f
        .get(Some("alice"), &format!("/me/usage?{READ_RANGE}"))
        .await;
    assert_eq!(deleted["by_agent"][0]["display_name"], "Latest snapshot");
    sqlx::query("delete from session_metadata where agent_instance_id=$1")
        .bind(f.agent)
        .execute(&f.pool)
        .await
        .unwrap();
    let (_, purged) = f
        .get(Some("alice"), &format!("/me/usage?{READ_RANGE}"))
        .await;
    assert_eq!(purged["by_agent"][0]["display_name"], Value::Null);
    assert_eq!(purged["totals"], deleted["totals"]);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn usage_ranges_validate_dates_and_generate_continuous_utc_buckets() {
    let f = Fixture::new().await;
    f.admit("alice").await;
    for path in ["/me/usage".to_owned(), format!("/spaces/{}/usage", f.space)] {
        for invalid in [
            "since=no-date",
            "until=2026-01-01",
            "since=2026-01-01T00:00:00",
            "since=2026-01-01T00:00:00Z&until=2026-01-01T00:00:00Z",
            "since=2026-01-02T00:00:00Z&until=2026-01-01T00:00:00Z",
            "since=2024-01-01T00:00:00Z&until=2025-01-01T00:00:01Z",
        ] {
            let (status, error) = f.get(Some("alice"), &format!("{path}?{invalid}")).await;
            assert_eq!(status, 422, "{invalid}: {error}");
            assert_eq!(error["code"], "invalid_fields");
        }
        for (since, until, interval, count, first) in [
            (
                "2026-01-01T01:15:00%2B02:00",
                "2026-01-01T03:00:00%2B02:00",
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
                .get(
                    Some("alice"),
                    &format!("{path}?since={since}&until={until}"),
                )
                .await;
            assert_eq!(status, 200, "{response}");
            assert_eq!(response["interval"], interval);
            let series = response["series"].as_array().unwrap();
            assert_eq!(series.len(), count);
            assert_eq!(series[0]["start"], first);
            for point in series {
                for field in [
                    "turns",
                    "input_tokens",
                    "output_tokens",
                    "cache_read_tokens",
                    "cache_creation_tokens",
                ] {
                    assert_eq!(point[field], 0);
                }
            }
            assert_eq!(response["by_agent"], json!([]));
            assert_eq!(response["by_model"], json!([]));
        }
        let before = chrono::Utc::now();
        let (status, defaults) = f.get(Some("alice"), &path).await;
        assert_eq!(status, 200, "{defaults}");
        let since: chrono::DateTime<chrono::Utc> =
            defaults["since"].as_str().unwrap().parse().unwrap();
        let until: chrono::DateTime<chrono::Utc> =
            defaults["until"].as_str().unwrap().parse().unwrap();
        assert_eq!(until - since, chrono::Duration::days(30));
        assert!(until >= before && until <= chrono::Utc::now());
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
