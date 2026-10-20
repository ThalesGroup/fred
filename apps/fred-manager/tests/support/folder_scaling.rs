// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use axum::{
    body::{Body, to_bytes},
    http::Request,
};
use serde_json::{Value, json};
use sqlx::Connection;
use std::{
    collections::BTreeMap,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::Instant,
};
use tower::ServiceExt;

async fn request(app: axum::Router, token: &str, method: &str, path: &str, body: Value) -> Value {
    let response = app
        .oneshot(
            Request::builder()
                .method(method)
                .uri(format!("/api{path}"))
                .header("authorization", format!("Bearer {token}"))
                .header("content-type", "application/json")
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let bytes = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
    assert!(
        status.is_success(),
        "{status}: {}",
        String::from_utf8_lossy(&bytes)
    );
    if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap()
    }
}

async fn tuples(e: &Env) -> usize {
    let client = reqwest::Client::new();
    let mut token = String::new();
    let mut total = 0;
    loop {
        let page: Value = client
            .post(format!("{}/stores/{}/read", e.openfga, e.fga.store_id()))
            .json(&json!({"page_size":100,"continuation_token":token}))
            .send()
            .await
            .unwrap()
            .error_for_status()
            .unwrap()
            .json()
            .await
            .unwrap();
        total += page["tuples"].as_array().unwrap().len();
        token = page["continuation_token"].as_str().unwrap_or("").into();
        if token.is_empty() {
            return total;
        }
    }
}

fn stats(mut samples: Vec<f64>) -> Value {
    samples.sort_by(f64::total_cmp);
    if samples.is_empty() {
        return json!({"observations":0});
    }
    json!({"observations":samples.len(), "p50_ms":samples[(samples.len()-1)/2],
        "p95_ms":samples[((samples.len()*95).div_ceil(100)-1).min(samples.len()-1)], "max_ms":samples.last()})
}

// Client-timed pg_locks samples approximate residency; they are not exact lock timings.
pub(super) async fn sample_locks(
    pool: PgPool,
    stop: Arc<AtomicBool>,
    ready: tokio::sync::oneshot::Sender<()>,
) -> Value {
    let mut connection = sqlx::PgConnection::connect_with(&pool.connect_options())
        .await
        .unwrap();
    let mut seen: BTreeMap<(i32, String, bool), (Instant, Instant)> = BTreeMap::new();
    let mut max_interval: f64 = 0.0;
    let mut previous = Instant::now();
    ready.send(()).unwrap();
    while !stop.load(Ordering::Relaxed) {
        let rows: Vec<(i32, String, bool)> = sqlx::query_as("select pid, virtualtransaction, granted from pg_locks where locktype='advisory' and database=(select oid from pg_database where datname=current_database())")
            .fetch_all(&mut connection).await.unwrap();
        let now = Instant::now();
        max_interval = max_interval.max(now.duration_since(previous).as_secs_f64() * 1000.0);
        previous = now;
        for key in rows {
            seen.entry(key)
                .and_modify(|range| range.1 = now)
                .or_insert((now, now));
        }
        tokio::time::sleep(Duration::from_millis(1)).await;
    }
    let samples = |granted| {
        seen.iter()
            .filter(|(key, _)| key.2 == granted)
            .map(|(_, (first, last))| last.duration_since(*first).as_secs_f64() * 1000.0)
            .collect()
    };
    json!({"wait_sampled_span":stats(samples(false)),"hold_sampled_span":stats(samples(true)),"max_poll_interval_ms":max_interval})
}

struct Campaign<'a> {
    app: &'a axum::Router,
    proxy: &'a support::fga_proxy::Proxy,
    pool: &'a PgPool,
}
impl Campaign<'_> {
    async fn run(
        &self,
        label: &str,
        concurrency: usize,
        targets: &[(Uuid, String)],
        reads: usize,
        write: bool,
        parent: Option<Uuid>,
    ) {
        *self.proxy.fault.lock().await = support::fga_proxy::Fault {
            read_page_size: Some(10),
            ..Default::default()
        };
        let stop = Arc::new(AtomicBool::new(false));
        let (ready, started) = tokio::sync::oneshot::channel();
        let sampling = tokio::spawn(sample_locks(self.pool.clone(), stop.clone(), ready));
        started.await.unwrap();
        let begin = Instant::now();
        let mut jobs = tokio::task::JoinSet::new();
        for i in 0..concurrency {
            let (space, token) = targets[i % targets.len()].clone();
            let app = self.app.clone();
            let name = format!("{label}-{concurrency}-{i}");
            jobs.spawn(async move {
                let start = Instant::now();
                let page = if write {
                    request(
                        app,
                        &token,
                        "POST",
                        "/folders",
                        json!({"space_id":space,"name":name,"parent_id":parent}),
                    )
                    .await
                } else {
                    request(
                        app,
                        &token,
                        "GET",
                        &format!(
                            "/spaces/{space}/folders?limit=50&parent_id={}",
                            parent.unwrap()
                        ),
                        Value::Null,
                    )
                    .await
                };
                if !write {
                    assert_eq!(page["items"].as_array().unwrap().len(), 50);
                    assert!(page["total"].as_i64().unwrap() >= 9985);
                }
                start.elapsed().as_secs_f64() * 1000.0
            });
        }
        let mut latencies = Vec::new();
        while let Some(result) = jobs.join_next().await {
            latencies.push(result.unwrap());
        }
        let elapsed = begin.elapsed().as_secs_f64();
        stop.store(true, Ordering::Relaxed);
        let locks = sampling.await.unwrap();
        let fault = self.proxy.fault.lock().await;
        assert_eq!(
            fault.calls.get("read"),
            Some(&(reads * concurrency)),
            "{label}"
        );
        assert_eq!(
            fault.calls.get("check"),
            Some(&((if write { 1 } else { 2 }) * concurrency)),
            "{label}"
        );
        assert_eq!(fault.writes, if write { concurrency } else { 0 });
        assert_eq!(fault.calls.len(), if write { 3 } else { 2 });
        for operation in &fault.written {
            for action in ["writes", "deletes"] {
                let keys = operation[action]["tuple_keys"].as_array().unwrap();
                assert_eq!(keys.len(), 1);
                assert!(keys[0]["object"].as_str().unwrap().starts_with("guard:"));
            }
        }
        assert!(fault.reads.iter().all(|r| {
            r["tuple_key"]["object"]
                .as_str()
                .is_some_and(|o| o.starts_with("space:") || o.starts_with("guard:"))
        }));
        println!(
            "FOLDER_MEASURE {}",
            json!({"case":label,"concurrency":concurrency,"latency":stats(latencies),"requests_per_second":concurrency as f64/elapsed,"fga_rpc":fault.calls,"locks":locks})
        );
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
#[ignore = "needs disposable Postgres and OpenFGA: make test-integration CARGO_TEST_OPTS=folder_scaling"]
async fn folder_scaling() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "writer").await;
    let identity = support::IdentityServer::start().await;
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let observed = Fga::connect(
        &proxy.base,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap()
    .load(&e.pool)
    .await
    .unwrap();
    let app = fred_manager::api::router(
        fred_manager::api::AppState {
            auth: Arc::new(identity.auth().await),
            pool: e.pool.clone(),
            fga: observed,
            onboarding: Default::default(),
            lifecycle: Default::default(),
            directory: None,
            content: None,
            processing: None,
        },
        "/api",
        &[],
    );
    let token = identity.token("writer");
    let root = spaces::create_folder(&e.pool, &e.fga, "writer", org.id, None, "Library".into())
        .await
        .unwrap();
    let baseline_tuples = tuples(&e).await;
    let list = format!("/spaces/{}/folders?parent_id={}", org.id, root.id);
    // Folder count changes neither authorization RPCs nor persisted tuples.
    for count in [0, 9985] {
        if count > 0 {
            sqlx::query("insert into folder(id,space_id,parent_id,name,path) select id,$1,$2,'child-'||lpad(n::text,5,'0'),$3||id::text||'/' from (select gen_random_uuid() as id,n from generate_series(1,9985) n) s")
                .bind(org.id).bind(root.id).bind(&root.path).execute(&e.pool).await.unwrap();
        }
        *proxy.fault.lock().await = Default::default();
        let page = request(app.clone(), &token, "GET", &list, Value::Null).await;
        assert_eq!(page["total"], count);
        assert_eq!(
            page["items"].as_array().unwrap().len(),
            count.min(50) as usize
        );
        let fault = proxy.fault.lock().await;
        assert_eq!(fault.calls.get("read"), Some(&1));
        assert_eq!(fault.calls.get("check"), Some(&2));
        assert_eq!(fault.writes, 0);
        assert_eq!(tuples(&e).await, baseline_tuples);
    }
    let mut parent = root.clone();
    for depth in 2..=15 {
        parent = spaces::create_folder(
            &e.pool,
            &e.fga,
            "writer",
            org.id,
            Some(parent.id),
            format!("depth-{depth}"),
        )
        .await
        .unwrap();
    }
    let folder_count: i64 = sqlx::query_scalar("select count(*) from folder")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(folder_count, 10000);
    let deep = request(
        app.clone(),
        &token,
        "GET",
        &format!("/spaces/{}/folders?parent_id={}", org.id, parent.id),
        Value::Null,
    )
    .await;
    assert_eq!(deep["ancestors"].as_array().unwrap().len(), 15);
    assert_eq!(deep["items"].as_array().unwrap().len(), 0);
    sqlx::query("analyze folder")
        .execute(&e.pool)
        .await
        .unwrap();
    for (label, parent) in [("wide", root.id), ("deep", parent.parent_id.unwrap())] {
        let plan:Value=sqlx::query_scalar("explain(analyze,buffers,format json) select id,space_id,parent_id,name,path,created_at from folder where space_id=$1 and parent_id=$2 order by name,id limit 50")
            .bind(org.id).bind(parent).fetch_one(&e.pool).await.unwrap();
        println!("FOLDER_PLAN {label} {plan}");
    }
    for (label, sql) in [
        (
            "wide-count",
            "explain(analyze,buffers,format json) select count(*) from folder where space_id=$1 and parent_id=$2",
        ),
        (
            "wide-last-page",
            "explain(analyze,buffers,format json) select id,space_id,parent_id,name,path,created_at from folder where space_id=$1 and parent_id=$2 order by name,id limit 50 offset 9900",
        ),
        (
            "wide-search",
            "explain(analyze,buffers,format json) select id,space_id,parent_id,name,path,created_at from folder where space_id=$1 and parent_id=$2 and strpos(lower(name),lower('child-09'))>0 order by name,id limit 50",
        ),
        (
            "wide-date",
            "explain(analyze,buffers,format json) select id,space_id,parent_id,name,path,created_at from folder where space_id=$1 and parent_id=$2 order by created_at,id limit 50",
        ),
    ] {
        let plan: Value = sqlx::query_scalar(sql)
            .bind(org.id)
            .bind(root.id)
            .fetch_one(&e.pool)
            .await
            .unwrap();
        println!("FOLDER_PLAN {label} {plan}");
    }
    println!(
        "FOLDER_FIXTURE {}",
        json!({"folders":folder_count,"max_depth":15,"initial_tuples":baseline_tuples,"pool_max_connections":e.pool.options().get_max_connections()})
    );
    let targets = vec![(org.id, token.clone())];
    let campaign = Campaign {
        app: &app,
        proxy: &proxy,
        pool: &e.pool,
    };
    for c in [1, 10, 50] {
        campaign
            .run("few-read", c, &targets, 1, false, Some(root.id))
            .await;
        campaign
            .run("same-org-few-write", c, &targets, 2, true, Some(root.id))
            .await;
    }
    // 41 direct roles, forced pages of 10, and 40 team placements: Q=5+40.
    for i in 0..40 {
        let space = if i == 0 {
            team.clone()
        } else {
            spaces::create_space(
                &e.pool,
                &e.fga,
                "alice",
                SpaceKind::Team,
                org.id,
                format!("membership-{i}"),
                "alice",
            )
            .await
            .unwrap()
        };
        grant(&e, space.id, Role::Member, "writer").await;
    }
    let before = tuples(&e).await;
    for c in [1, 10, 50] {
        campaign
            .run("many-read", c, &targets, 45, false, Some(root.id))
            .await;
        campaign
            .run("same-org-many-write", c, &targets, 46, true, Some(root.id))
            .await;
    }
    assert_eq!(tuples(&e).await, before);
    let mut separate = Vec::new();
    for i in 0..50 {
        let owner = format!("owner-{i}");
        let writer = format!("writer-{i}");
        let space = spaces::create_organization(&e.pool, &e.fga, &format!("separate-{i}"), &owner)
            .await
            .unwrap();
        spaces::grant(
            &e.pool,
            &e.fga,
            None,
            &owner,
            space.id,
            Role::Editor,
            &writer,
        )
        .await
        .unwrap();
        separate.push((space.id, identity.token(&writer)));
    }
    for c in [1, 10, 50] {
        campaign
            .run("separate-org-few-write", c, &separate, 2, true, None)
            .await;
    }
    let before = tuples(&e).await;
    *proxy.fault.lock().await = support::fga_proxy::Fault {
        read_page_size: Some(10),
        ..Default::default()
    };
    let stop = Arc::new(AtomicBool::new(false));
    let (ready, started) = tokio::sync::oneshot::channel();
    let sample = tokio::spawn(sample_locks(e.pool.clone(), stop.clone(), ready));
    started.await.unwrap();
    let start = Instant::now();
    request(
        app.clone(),
        &token,
        "DELETE",
        &format!("/folders/{}", root.id),
        Value::Null,
    )
    .await;
    stop.store(true, Ordering::Relaxed);
    println!(
        "FOLDER_DELETE {}",
        json!({"rows":10122,"elapsed_ms":start.elapsed().as_secs_f64()*1000.0,"locks":sample.await.unwrap()})
    );
    assert_eq!(tuples(&e).await, before);
    let fault = proxy.fault.lock().await;
    assert_eq!(fault.calls.get("read"), Some(&46));
    assert_eq!(fault.calls.get("check"), Some(&1));
    assert_eq!(fault.writes, 1);
    drop(fault);
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from folder where space_id=$1")
            .bind(org.id)
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );

    // Count and page stay consistent while the same directory is being mutated.
    let space = separate[0].0;
    let pool = e.pool.clone();
    let writer = tokio::spawn(async move {
        for i in 0..80 {
            let id = Uuid::new_v4();
            db::insert_folder(
                &pool,
                &Folder {
                    id,
                    space_id: space,
                    parent_id: None,
                    name: format!("race-{i}"),
                    path: format!("/{id}/"),
                    created_at: chrono::Utc::now(),
                },
            )
            .await
            .unwrap();
            db::delete_folder(&pool, id).await.unwrap();
        }
    });
    for _ in 0..80 {
        let page = db::folders(
            &e.pool,
            space,
            &domain::FolderQuery {
                limit: Some(200),
                ..Default::default()
            },
        )
        .await
        .unwrap();
        assert_eq!(page.total as usize, page.items.len());
    }
    writer.await.unwrap();
}
