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
