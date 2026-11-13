// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use axum::{
    Json, Router,
    routing::{get, post},
};
use control_plane::analytics::{
    history::{ReadError, ReadScope},
    opensearch::{Config, OpenSearch},
};
use serde_json::{Value, json};

const ACME: [uuid::Uuid; 1] = [uuid::Uuid::from_u128(1)];
const GLOBEX: [uuid::Uuid; 1] = [uuid::Uuid::from_u128(2)];

fn mapping() -> Value {
    json!({"mappings":{"dynamic":false,"properties":{
        "@timestamp":{"type":"date"},
        "metric":{"properties":{"name":{"type":"keyword"}}},
        "dims":{"properties":{"space_id":{"type":"keyword"},"user_id":{"type":"keyword"},"skill_name":{"type":"keyword"},"skill_origin":{"type":"keyword"}}}
    }}})
}
fn query(subject: &str) -> ReadScope<'_> {
    ReadScope {
        subject,
        spaces: &ACME,
        since: "2026-01-01T00:00:00Z".parse().unwrap(),
        until: "2026-01-03T00:00:00Z".parse().unwrap(),
        limit: 100,
    }
}
fn config(url: String, index: String) -> Config {
    Config {
        url,
        index,
        username: None,
        password_env_var: None,
    }
}
fn response() -> Value {
    json!({"timed_out":false,"_shards":{"total":3,"successful":3,"failed":0},"aggregations":{"skills":{"buckets":[
        {"key":{"skill":"read"},"doc_count":7,"origins":{"buckets":{"user":{"doc_count":5},"agent":{"doc_count":2}}}}
    ]}}})
}

#[tokio::test]
async fn adapter_sends_verified_subject_time_and_origin_and_rejects_partial_responses() {
    let mut broken = Vec::new();
    for (pointer, value) in [
        ("/timed_out", json!(true)),
        ("/_shards/failed", json!(1)),
        ("/_shards/successful", json!(2)),
        ("/aggregations/skills/buckets/0/doc_count", json!(8)),
    ] {
        let mut r = response();
        *r.pointer_mut(pointer).unwrap() = value;
        broken.push(r);
    }
    broken.push(json!({}));
    for reply in std::iter::once(response()).chain(broken) {
        let valid = reply == response();
        let app = Router::new().route("/fixture/_mapping",get(|| async { Json(json!({"fixture":mapping()})) }))
            .route("/fixture/_search",post(move |Json(body): Json<Value>| { let reply=reply.clone(); async move {
                assert_eq!(body["query"]["bool"]["filter"],json!([
                    {"term":{"metric.name":"agent.skill_loaded_total"}}, {"term":{"dims.user_id":"alice"}},
                    {"terms":{"dims.space_id":[ACME[0]]}},
                    {"terms":{"dims.skill_origin":["user","agent"]}},
                    {"range":{"@timestamp":{"gte":"2026-01-01T00:00:00Z","lt":"2026-01-03T00:00:00Z"}}}
                ]));
                assert_eq!(body["aggs"]["skills"]["composite"]["size"],10001);
                Json(reply)
            }}));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let reader = OpenSearch::configured(&config(url, "fixture".into())).unwrap();
        let result = reader.skill_loads(query("alice")).await;
        if valid {
            let result = result.unwrap();
            assert_eq!((result.rows[0].user, result.rows[0].agent), (5, 2));
        } else {
            assert!(matches!(result, Err(ReadError::Unavailable)));
        }
        server.abort();
    }
}

#[tokio::test]
async fn adapter_rejects_absent_or_unindexed_mapping_before_search() {
    let mut old = mapping();
    old["mappings"]["properties"]["dims"]["properties"]
        .as_object_mut()
        .unwrap()
        .remove("skill_origin");
    let mut unscoped = mapping();
    unscoped["mappings"]["properties"]["dims"]["properties"]
        .as_object_mut()
        .unwrap()
        .remove("space_id");
    let mut disabled = mapping();
    disabled["mappings"]["properties"]["dims"]["properties"]["user_id"]["index"] = json!(false);
    for map in [
        json!({}),
        json!({"fixture":old}),
        json!({"fixture":unscoped}),
        json!({"fixture":disabled}),
    ] {
        let app = Router::new().route(
            "/fixture/_mapping",
            get(move || {
                let map = map.clone();
                async move { Json(map) }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let reader = OpenSearch::configured(&config(url, "fixture".into())).unwrap();
        assert!(matches!(
            reader.skill_loads(query("alice")).await,
            Err(ReadError::Unavailable)
        ));
        server.abort();
    }
}

#[tokio::test]
#[ignore = "requires a disposable OpenSearch via CONTROL_PLANE_IT_OPENSEARCH"]
async fn real_multishard_skill_counts_are_exact_self_scoped_and_truncated() {
    let url = std::env::var("CONTROL_PLANE_IT_OPENSEARCH").unwrap();
    let index = format!("analytics-fixture-{}", uuid::Uuid::new_v4());
    let client = reqwest::Client::new();
    let mut map = mapping();
    map["settings"] = json!({"number_of_shards":3,"number_of_replicas":0});
    client
        .put(format!("{url}/{index}"))
        .json(&map)
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap();
    let mut bulk = String::new();
    for (user, skill, origin, at) in [
        ("alice", "shared", "user", "2026-01-01T00:00:00Z"),
        ("alice", "shared", "agent", "2026-01-02T00:00:00Z"),
        ("alice", "shared", "agent", "2026-01-03T00:00:00Z"),
        ("bob", "shared", "user", "2026-01-01T00:00:00Z"),
        ("alice", "shared", "user", "2025-12-31T23:59:59Z"),
    ] {
        bulk.push_str(&format!("{{\"index\":{{}}}}\n{}\n",json!({"@timestamp":at,"metric":{"name":"agent.skill_loaded_total"},"actor":{"type":"system"},"dims":{"user_id":user,"skill_name":skill,"skill_origin":origin,"skill_space_id":"team-owned","space_id":ACME[0]}})));
    }
    for i in 0..105 {
        bulk.push_str(&format!("{{\"index\":{{}}}}\n{}\n",json!({"@timestamp":"2026-01-01T12:00:00Z","metric":{"name":"agent.skill_loaded_total"},"dims":{"user_id":"alice","skill_name":format!("skill-{i:03}"),"skill_origin":"agent","space_id":ACME[0]}})));
    }
    for _ in 0..20 {
        bulk.push_str(&format!("{{\"index\":{{}}}}\n{}\n", json!({"@timestamp":"2026-01-01T12:00:00Z","metric":{"name":"agent.skill_loaded_total"},"dims":{"user_id":"alice","skill_name":"globex-only","skill_origin":"agent","space_id":GLOBEX[0]}})));
    }
    let uploaded: Value = client
        .post(format!("{url}/{index}/_bulk?refresh=true"))
        .header("content-type", "application/x-ndjson")
        .body(bulk)
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap()
        .json()
        .await
        .unwrap();
    assert_eq!(uploaded["errors"], false);
    let reader = OpenSearch::configured(&config(url.clone(), index.clone())).unwrap();
    let alice = reader.skill_loads(query("alice")).await.unwrap();
    assert!(alice.truncated);
    assert_eq!(alice.rows.len(), 100);
    assert_eq!(alice.rows[0].name, "shared");
    assert_eq!((alice.rows[0].user, alice.rows[0].agent), (1, 1));
    let mut globex_query = query("alice");
    globex_query.spaces = &GLOBEX;
    let globex = reader.skill_loads(globex_query).await.unwrap();
    assert_eq!(globex.rows.len(), 1);
    assert_eq!(globex.rows[0].name, "globex-only");
    assert_eq!(globex.rows[0].agent, 20);
    let bob = reader.skill_loads(query("bob")).await.unwrap();
    assert!(!bob.truncated);
    assert_eq!(bob.rows.len(), 1);
    assert_eq!((bob.rows[0].user, bob.rows[0].agent), (1, 0));
    assert!(
        reader
            .skill_loads(query("nobody"))
            .await
            .unwrap()
            .rows
            .is_empty()
    );
    client
        .delete(format!("{url}/{index}"))
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap();
    assert!(matches!(
        reader.skill_loads(query("alice")).await,
        Err(ReadError::Unavailable)
    ));
}

#[tokio::test]
async fn stalled_historical_http_is_unavailable_within_the_deadline() {
    let app = Router::new().route(
        "/fixture/_mapping",
        get(|| async {
            tokio::time::sleep(std::time::Duration::from_secs(30)).await;
            Json(json!({"fixture":mapping()}))
        }),
    );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let reader = OpenSearch::configured(&config(url, "fixture".into())).unwrap();
    let result = tokio::time::timeout(
        std::time::Duration::from_secs(7),
        reader.skill_loads(query("alice")),
    )
    .await
    .unwrap();
    assert!(matches!(result, Err(ReadError::Unavailable)));
    server.abort();
}

fn turn_response() -> Value {
    json!({"timed_out":false,"_shards":{"total":3,"successful":3,"failed":0},
        "hits":{"total":{"value":9007199254740995u64,"relation":"eq"}},
        "aggregations":{"turns":{"buckets":[
            {"key":{"space":ACME[0],"agent":uuid::Uuid::from_u128(10)},"doc_count":9007199254740993u64,
             "latest":{"hits":{"hits":[{"_source":{"@timestamp":"2026-01-02T00:00:00Z","dims":{"agent_instance_name":"Same name"}}}]}}},
            {"key":{"space":ACME[0],"agent":uuid::Uuid::from_u128(11)},"doc_count":2,
             "latest":{"hits":{"hits":[{"_source":{"@timestamp":"2026-01-02T00:00:00Z","dims":{"agent_instance_name":"Same name"}}}]}}}
        ]}}
    })
}

#[tokio::test]
async fn turn_adapter_requires_canonical_scope_complete_counts_and_half_open_windows() {
    let valid = turn_response();
    let mut replies = vec![valid.clone()];
    for (path, value) in [
        ("/timed_out", json!(true)),
        ("/_shards/successful", json!(2)),
        ("/hits/total/relation", json!("gte")),
        ("/hits/total/value", json!(9007199254740996u64)),
        ("/aggregations/turns/buckets/0/key/space", json!(GLOBEX[0])),
        (
            "/aggregations/turns/buckets/0/key/agent",
            json!("missing-uuid"),
        ),
    ] {
        let mut broken = valid.clone();
        *broken.pointer_mut(path).unwrap() = value;
        replies.push(broken);
    }
    for reply in replies {
        let expected = reply == valid;
        let app = Router::new()
            .route("/fixture/_mapping", get(|| async {
                let mut m = mapping();
                m["mappings"]["properties"]["dims"]["properties"]["agent_instance_id"] = json!({"type":"keyword"});
                m["mappings"]["properties"]["dims"]["properties"]["agent_instance_name"] = json!({"type":"keyword"});
                Json(json!({"fixture":m}))
            }))
            .route("/fixture/_search", post(move |Json(body):Json<Value>| {
                let reply = reply.clone();
                async move {
                    assert_eq!(body["query"]["bool"]["filter"], json!([
                        {"term":{"metric.name":"agent.turn_completed"}},
                        {"term":{"dims.user_id":"alice"}},
                        {"terms":{"dims.space_id":[ACME[0]]}},
                        {"range":{"@timestamp":{"gte":"2026-01-01T00:00:00Z","lt":"2026-01-03T00:00:00Z"}}}
                    ]));
                    // No title/token proxy, exchange deduplication, approximate cardinality or top-N shards.
                    assert_eq!(body["aggs"]["turns"]["composite"]["size"], 10001);
                    assert_eq!(body["track_total_hits"], true);
                    Json(reply)
                }
            }));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let reader = OpenSearch::configured(&config(
            format!("http://{}", listener.local_addr().unwrap()),
            "fixture".into(),
        ))
        .unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let result = reader.completed_turns(query("alice")).await;
        if expected {
            let rows = result.unwrap();
            assert_eq!(rows.len(), 2);
            assert_ne!(rows[0].agent_instance_id, rows[1].agent_instance_id);
            assert_eq!(rows[0].count, 9007199254740993);
            // Two observed completions, e.g. HITL pause and resume, remain two.
            assert_eq!(rows[1].count, 2);
        } else {
            assert!(matches!(result, Err(ReadError::Unavailable)));
        }
        server.abort();
    }
}
