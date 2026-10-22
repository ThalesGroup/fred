// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use control_plane::processing::{
    Processing, config::ProcessingConfig, models::*, store, worker_contract::WorkerContract,
};

async fn setup() -> (Documents, Arc<Processing>) {
    let mut d = Box::pin(Documents::start(1024 * 1024)).await;
    let derived = d.storage.config.clone();
    let config: ProcessingConfig = serde_json::from_value(json!({
        "enabled":true,"temporal":{"host":"localhost:7233","namespace":"default","task_queue":"ingestion"},
        "worker_contract_file":"tests/fixtures/processing/worker-contract.json",
        "worker":{"issuer":d.identity.realm,"audience":"app","client_id":"manager-worker"},
        "derived":{"endpoint":derived.endpoint,"bucket":derived.bucket,"allow_insecure":true}
    })).unwrap();
    config.validate(&d.storage.config).unwrap();
    let installation: Uuid =
        sqlx::query_scalar("select namespace from document_storage where singleton")
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    let observed = control_plane::fga::Fga::connect(
        &d.fga_proxy.base,
        &d.e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap()
    .load(&d.e.pool)
    .await
    .unwrap();
    let processing = Arc::new(Processing {
        pool: d.e.pool.clone(),
        fga: observed.clone(),
        terms: None,
        installation,
        auth: d.identity.auth().await,
        originals: d.storage.clone(),
        derived: control_plane::documents::object_store::ObjectStore::new(
            &derived,
            "fixture-access".into(),
            "fixture-secret".into(),
        )
        .unwrap(),
        contract: WorkerContract::load(&config.worker_contract_file, "ingestion").unwrap(),
        config,
    });
    d.app = api::router(
        api::AppState {
            pool: d.e.pool.clone(),
            fga: observed,
            auth: Arc::new(d.identity.auth().await),
            content: Some(d.storage.clone()),
            processing: Some(processing.clone()),
            directory: None,
            onboarding: Default::default(),
            lifecycle: Default::default(),
        },
        "/v1",
        &[],
    );
    (d, processing)
}
fn claim(work: &Work, stage: Stage, activity: Uuid, attempt: u32) -> Claim {
    Claim {
        work: work.clone(),
        stage,
        activity_id: activity,
        execution_id: Uuid::new_v4(),
        attempt,
    }
}
async fn commit(p: &Processing, d: &Descriptor, files: &[(&str, &[u8])], chunks: i64) -> Summary {
    let mut artifacts = vec![];
    for (name, bytes) in files {
        let file = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(file.path(), bytes).unwrap();
        let hash: [u8; 32] = Sha256::digest(bytes).into();
        Box::pin(p.derived.put_verified(
            &format!("{}{}", d.output_prefix, name),
            file.path(),
            bytes.len() as i64,
            &hash,
        ))
        .await
        .unwrap();
        artifacts.push(Artifact {
            path: (*name).into(),
            size: bytes.len() as i64,
            sha256: format!("{:x}", Sha256::digest(bytes)),
        });
    }
    Box::pin(p.commit(Commit {
        work: d.work.clone(),
        stage: d.stage,
        manifest: Manifest {
            generation: d.generation,
            artifacts,
            chunks,
            vectors: chunks,
            vector_ordinals: (0..chunks as u32).collect(),
            rows: None,
        },
    }))
    .await
    .unwrap()
}

async fn verify_terminal_replay(d: &Documents, p: &Processing, work: &Work, done: &Summary) {
    let saved = store::row(&d.e.pool, work.processing_id)
        .await
        .unwrap()
        .manifest
        .unwrap()
        .0;
    let generation = saved.generation;
    let restarted = Processing {
        pool: sqlx::PgPool::connect_with(p.pool.connect_options().as_ref().clone())
            .await
            .unwrap(),
        fga: p.fga.clone(),
        terms: p.terms.clone(),
        installation: p.installation,
        config: p.config.clone(),
        auth: d.identity.auth().await,
        originals: p.originals.clone(),
        derived: p.derived.clone(),
        contract: WorkerContract::load(&p.config.worker_contract_file, "ingestion").unwrap(),
    };
    let replay = Box::pin(restarted.commit(Commit {
        work: work.clone(),
        stage: Stage::Indexing,
        manifest: saved.clone(),
    }))
    .await
    .unwrap();
    assert_eq!(replay.revision, done.revision);
    assert_eq!(replay.status, ProcessingStatus::Succeeded);
    let mut conflicting = saved;
    conflicting.artifacts[0].sha256 = "0".repeat(64);
    assert!(
        Box::pin(restarted.commit(Commit {
            work: work.clone(),
            stage: Stage::Indexing,
            manifest: conflicting
        }))
        .await
        .is_err()
    );
    assert!(
        restarted
            .abandon(Failure {
                work: work.clone(),
                stage: Stage::Indexing,
                generation: Some(generation),
                code: FailureCode::WorkerFailed,
            })
            .await
            .is_err()
    );
    assert_eq!(
        store::row(&d.e.pool, work.processing_id)
            .await
            .unwrap()
            .summary
            .status,
        ProcessingStatus::Succeeded
    );
    restarted.pool.close().await;
}

// Proves: I2, I3, I22, I25, I26
#[tokio::test]
#[ignore = "needs disposable PostgreSQL, OpenFGA and SeaweedFS"]
async fn processing_admission_fences_publication_and_original_survival() {
    let (d, p) = Box::pin(setup()).await;
    let (status, receipt) = d
        .upload("writer", "hello.txt", b"Hello world", Uuid::new_v4(), None)
        .await;
    assert_eq!(status, 201, "{receipt}");
    let id: Uuid = receipt["document_id"].as_str().unwrap().parse().unwrap();
    let key = Uuid::new_v4();
    let start = Start {
        profile: Profile::Fast,
        retry_of: None,
    };
    assert!(p.start("reader", key, id, start.clone()).await.is_err());
    let (a, b) = tokio::join!(
        p.start("writer", key, id, start.clone()),
        p.start("writer", key, id, start.clone())
    );
    let a = a.unwrap();
    assert_eq!(a.id, b.unwrap().id);
    assert!(
        p.start("writer", Uuid::new_v4(), id, start.clone())
            .await
            .is_err()
    );
    assert!(
        p.start(
            "writer",
            key,
            id,
            Start {
                profile: Profile::Rich,
                retry_of: None
            }
        )
        .await
        .is_err()
    );
    let row = store::row(&d.e.pool, a.id).await.unwrap();
    let work = row.work();
    let activity = Uuid::new_v4();
    let c = claim(&work, Stage::Preparation, activity, 1);
    let first = p.claim(c.clone()).await.unwrap();
    assert_eq!(first.generation, p.claim(c).await.unwrap().generation);
    let mut forged = work.clone();
    forged.original_sha256 = "0".repeat(64);
    assert!(
        p.claim(claim(&forged, Stage::Preparation, activity, 2))
            .await
            .is_err()
    );
    let current = p
        .claim(claim(&work, Stage::Preparation, activity, 2))
        .await
        .unwrap();
    assert_ne!(first.generation, current.generation);
    let obsolete = Commit {
        work: work.clone(),
        stage: Stage::Preparation,
        manifest: Manifest {
            generation: first.generation,
            artifacts: vec![],
            chunks: 0,
            vectors: 0,
            vector_ordinals: vec![],
            rows: None,
        },
    };
    assert!(Box::pin(p.commit(obsolete)).await.is_err());
    commit(&p, &current, &[("policy.json", b"{}")], 0).await;
    let replay = p
        .claim(claim(&work, Stage::Preparation, activity, 3))
        .await
        .unwrap();
    assert!(replay.committed.is_some());
    assert_eq!(replay.generation, current.generation);
    let extracted = p
        .claim(claim(&work, Stage::Extraction, Uuid::new_v4(), 1))
        .await
        .unwrap();
    commit(
        &p,
        &extracted,
        &[("output.md", b"Hello world"), ("metadata.json", b"{}")],
        0,
    )
    .await;
    let indexed = p
        .claim(claim(&work, Stage::Indexing, Uuid::new_v4(), 1))
        .await
        .unwrap();
    p.plan_vectors(control_plane::processing::cleanup::VectorPlan {
        work: work.clone(),
        generation: indexed.generation,
        count: 3,
    })
    .await
    .unwrap();
    *d.fga_proxy.fault.lock().await = crate::support::fga_proxy::Fault {
        read_page_size: Some(1),
        ..Default::default()
    };
    let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let (ready, rx) = tokio::sync::oneshot::channel();
    let samples = tokio::spawn(crate::folder_scaling::sample_locks(
        d.e.pool.clone(),
        stop.clone(),
        ready,
    ));
    rx.await.unwrap();
    let done = commit(
        &p,
        &indexed,
        &[
            ("output.md", b"Hello world"),
            ("metadata.json", b"{}"),
            ("chunks.jsonl", b"{}"),
        ],
        1,
    )
    .await;
    assert_eq!(done.status, ProcessingStatus::Succeeded);
    stop.store(true, std::sync::atomic::Ordering::Relaxed);
    let locks = samples.await.unwrap();
    let observed = d.fga_proxy.fault.lock().await;
    assert_eq!(
        observed.calls,
        [("check".into(), 1), ("read".into(), 3), ("write".into(), 1)].into()
    );
    println!(
        "processing publication: FGA={:?}, locks={locks}",
        observed.calls
    );
    drop(observed);
    Box::pin(verify_terminal_replay(&d, &p, &work, &done)).await;
    // Cleanup releases abandoned stages, and protects the published ordinal even
    // when adaptive indexing planned more identifiers than it ultimately used.
    let mut completed = store::row(&d.e.pool, work.processing_id).await.unwrap();
    for generation in completed.generations.iter_mut() {
        generation.expires_at = chrono::Utc::now() - chrono::Duration::minutes(2);
    }
    sqlx::query("update document_processing set generations=$2,cleanup_due_at=clock_timestamp() where id=$1")
        .bind(work.processing_id).bind(&completed.generations).execute(&d.e.pool).await.unwrap();
    let mut seen = std::collections::HashSet::new();
    for _ in 0..completed.generations.len() * 2 {
        sqlx::query("update document_processing set cleanup_due_at=clock_timestamp() where id=$1")
            .bind(work.processing_id)
            .execute(&d.e.pool)
            .await
            .unwrap();
        let candidates = p.cleanup_candidates().await.unwrap();
        assert_eq!(candidates.len(), 1);
        let candidate = &candidates[0];
        seen.insert(candidate.generation);
        if candidate.generation == indexed.generation {
            assert!(candidate.preserve_objects);
            assert_eq!(candidate.protected_ordinals, vec![0]);
        } else {
            assert!(!candidate.preserve_objects);
        }
        p.cleaned(control_plane::processing::cleanup::Cleaned {
            work: work.clone(),
            generation: candidate.generation,
            cursor: candidate.cursor,
            next_cursor: candidate.chunks,
            objects_empty: !candidate.preserve_objects,
        })
        .await
        .unwrap();
    }
    assert_eq!(seen.len(), completed.generations.len());
    assert!(
        store::row(&d.e.pool, work.processing_id)
            .await
            .unwrap()
            .generations
            .iter()
            .find(|g| g.id == indexed.generation)
            .unwrap()
            .reserved_bytes
            > 0
    );

    assert!(p.start("writer", Uuid::new_v4(), id, start).await.is_err());
    let preview = d
        .request(
            "reader",
            "GET",
            &format!("/documents/{id}/preview?artifact=raw"),
            Body::empty(),
            "",
            None,
        )
        .await;
    assert_eq!(preview.status(), 200);
    assert_eq!(
        to_bytes(preview.into_body(), 100).await.unwrap(),
        "Hello world"
    );
    assert_eq!(
        d.request(
            "reader",
            "GET",
            &format!("/documents/{id}/content"),
            Body::empty(),
            "",
            None
        )
        .await
        .status(),
        200
    );
    assert_eq!(
        d.json(
            "writer",
            "GET",
            &format!("/document-processing/{}/work", work.processing_id),
            Value::Null
        )
        .await
        .0,
        403
    );
    let (_, usage) = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{}/storage", d.folder.space_id),
            Value::Null,
        )
        .await;
    assert_eq!(usage["used_bytes"], 11);
}

struct TemporalFixture(String);
impl Drop for TemporalFixture {
    fn drop(&mut self) {
        let _ = std::process::Command::new("docker")
            .args(["rm", "-f", &self.0])
            .output();
    }
}
fn start_temporal() -> (TemporalFixture, String) {
    let name = format!("fred-processing-temporal-{}", Uuid::new_v4().simple());
    let temporal = TemporalFixture(name.clone());
    let result = std::process::Command::new("docker")
        .args([
            "run",
            "-d",
            "--name",
            &name,
            "-p",
            "127.0.0.1::7233",
            "--entrypoint",
            "temporal",
            "mirror.gcr.io/temporalio/admin-tools:1.28",
            "server",
            "start-dev",
            "--ip",
            "0.0.0.0",
            "--headless",
        ])
        .output()
        .unwrap();
    assert!(result.status.success());
    let port = std::process::Command::new("docker")
        .args(["port", &name, "7233/tcp"])
        .output()
        .unwrap();
    let host = String::from_utf8(port.stdout).unwrap().trim().to_owned();
    (temporal, host)
}
// Proves: I22, I25, I26, I28
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
#[ignore = "needs disposable pgvector, OpenFGA, S3, Temporal and the KF Python environment"]
async fn processing_existing_worker_journey_without_kf_http() {
    if std::env::var_os("CONTROL_PLANE_IT_PROCESSING").is_none() {
        return;
    }
    let (d, p) = Box::pin(setup()).await;
    let (temporal, host) = start_temporal();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}/v1", listener.local_addr().unwrap());
    let app = d.app.clone();
    let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let folder = tempfile::tempdir().unwrap();
    let now = chrono::Utc::now().timestamp();
    let token=d.identity.sign(json!({"sub":"worker","preferred_username":"service-account-manager-worker","iss":d.identity.realm,"aud":"app","azp":"manager-worker","client_id":"manager-worker","iat":now,"exp":now+600}));
    d.identity.control.lock().await.worker_token = Some(token);
    let database: String = sqlx::query_scalar("select current_database()")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    let fixture = json!({"manager":url,"issuer":d.identity.realm,"object_endpoint":d.bucket.config.endpoint,"postgres":format!("{}/{}",std::env::var("CONTROL_PLANE_IT_POSTGRES").unwrap(),database),"temporal":host,"contract":std::fs::canonicalize("tests/fixtures/processing/worker-contract.json").unwrap()});
    let input = folder.path().join("fixture.json");
    std::fs::write(&input, fixture.to_string()).unwrap();
    async fn spawn_worker(input: &std::path::Path) -> tokio::process::Child {
        let folder = input.parent().unwrap();
        let log = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(folder.join("worker.log"))
            .unwrap();
        let mut child = tokio::process::Command::new("../knowledge-flow-backend/.venv/bin/python")
            .arg(std::fs::canonicalize("tests/support/processing_worker.py").unwrap())
            .arg(input)
            .current_dir("../knowledge-flow-backend")
            .stdout(log.try_clone().unwrap())
            .stderr(log)
            .kill_on_drop(true)
            .spawn()
            .unwrap();
        for _ in 0..180 {
            if folder.join("ready").exists() {
                return child;
            }
            if let Some(status) = child.try_wait().unwrap() {
                panic!(
                    "worker stopped {status}: {}",
                    std::fs::read_to_string(folder.join("worker.log")).unwrap()
                );
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
        panic!(
            "worker did not start: {}",
            std::fs::read_to_string(folder.join("worker.log")).unwrap()
        );
    }
    let mut child = spawn_worker(&input).await;
    let mut dispatch_config = p.config.clone();
    dispatch_config.temporal.host = host;
    dispatch_config.limits.poll_seconds = 1;
    dispatch_config.enabled = false; // Previously admitted work still drains.
    // A real refused connection retains the intent, then expires it without a consumer.
    let (_, receipt) = d
        .upload("writer", "outage.txt", b"kept", Uuid::new_v4(), None)
        .await;
    let outage_document = receipt["document_id"].as_str().unwrap().parse().unwrap();
    let outage = p
        .start(
            "writer",
            Uuid::new_v4(),
            outage_document,
            Start {
                profile: Profile::Fast,
                retry_of: None,
            },
        )
        .await
        .unwrap();
    let mut offline = dispatch_config.clone();
    offline.temporal.host = "127.0.0.1:1".into();
    offline.temporal.connect_timeout_seconds = 1;
    let disconnected = tokio::spawn(control_plane::processing::dispatch::run(
        d.e.pool.clone(),
        offline,
    ));
    tokio::time::sleep(Duration::from_secs(2)).await;
    assert!(
        store::row(&d.e.pool, outage.id)
            .await
            .unwrap()
            .run_id
            .is_none()
    );
    sqlx::query(
        "update document_processing set created_at=clock_timestamp()-interval '2 days' where id=$1",
    )
    .bind(outage.id)
    .execute(&d.e.pool)
    .await
    .unwrap();
    tokio::time::sleep(Duration::from_secs(2)).await;
    assert_eq!(
        store::row(&d.e.pool, outage.id)
            .await
            .unwrap()
            .summary
            .error_code
            .as_deref(),
        Some("delivery_unknown")
    );
    disconnected.abort();
    let mut dispatch = tokio::spawn(control_plane::processing::dispatch::run(
        d.e.pool.clone(),
        dispatch_config.clone(),
    ));
    let (_, receipt) = d
        .upload("writer", "no-consumer.txt", b"kept", Uuid::new_v4(), None)
        .await;
    let waiting_document = receipt["document_id"].as_str().unwrap().parse().unwrap();
    let waiting = p
        .start(
            "writer",
            Uuid::new_v4(),
            waiting_document,
            Start {
                profile: Profile::Fast,
                retry_of: None,
            },
        )
        .await
        .unwrap();
    for _ in 0..40 {
        if store::row(&d.e.pool, waiting.id)
            .await
            .unwrap()
            .run_id
            .is_some()
        {
            break;
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
    }
    assert!(
        store::row(&d.e.pool, waiting.id)
            .await
            .unwrap()
            .run_id
            .is_some()
    );
    // A missing acknowledged history must never be replaced by a fresh execution.
    let absent_run = Uuid::new_v4().to_string();
    sqlx::query(
        "update document_processing set run_id=$2,delivery_due_at=clock_timestamp() where id=$1",
    )
    .bind(waiting.id)
    .bind(&absent_run)
    .execute(&d.e.pool)
    .await
    .unwrap();
    tokio::time::sleep(Duration::from_secs(2)).await;
    assert_eq!(
        store::row(&d.e.pool, waiting.id)
            .await
            .unwrap()
            .run_id
            .as_deref(),
        Some(absent_run.as_str())
    );
    sqlx::query(
        "update document_processing set created_at=clock_timestamp()-interval '2 days' where id=$1",
    )
    .bind(waiting.id)
    .execute(&d.e.pool)
    .await
    .unwrap();
    tokio::time::sleep(Duration::from_secs(2)).await;
    assert_eq!(
        store::row(&d.e.pool, waiting.id)
            .await
            .unwrap()
            .summary
            .status,
        ProcessingStatus::Failed
    );
    for (profile, name) in [
        (Profile::Fast, "fast.txt"),
        (Profile::Medium, "medium.txt"),
        (Profile::Rich, "rich.txt"),
        (Profile::Fast, "dataset.csv"),
        (Profile::Fast, "report.pdf"),
        (Profile::Fast, "report.docx"),
        (Profile::Fast, "report.pptx"),
        (Profile::Fast, "report.doc"),
        (Profile::Fast, "report.odt"),
        (Profile::Fast, "report.ppt"),
        (Profile::Fast, "dataset.xlsx"),
        (Profile::Fast, "model-retry.txt"),
        (Profile::Fast, "render-retry.docx"),
    ] {
        let fault = match name {
            "model-retry.txt" => Some("fail-model"),
            "render-retry.docx" => Some("fail-render"),
            _ => None,
        };
        if let Some(marker) = fault {
            std::fs::write(folder.path().join(marker), "fail").unwrap();
        }
        let source = if name == "render-retry.docx" {
            "report.docx"
        } else {
            name
        };
        let generated = std::fs::read(folder.path().join(source)).ok();
        let body = if let Some(bytes) = generated.as_ref() {
            bytes.as_slice()
        } else if name.ends_with("csv") {
            b"name,value\na,1\nb,2\n".as_slice()
        } else {
            b"Manager ingestion keeps the existing processing pipeline. This original is preserved while the worker produces chunks and vectors.".as_slice()
        };
        let (status, receipt) = d.upload("writer", name, body, Uuid::new_v4(), None).await;
        assert_eq!(status, 201, "{receipt}");
        let id = receipt["document_id"].as_str().unwrap().parse().unwrap();
        let summary = p
            .start(
                "writer",
                Uuid::new_v4(),
                id,
                Start {
                    profile,
                    retry_of: None,
                },
            )
            .await
            .unwrap();
        let mut initial_run = None;
        if name == "fast.txt" {
            for _ in 0..40 {
                initial_run = store::row(&d.e.pool, summary.id).await.unwrap().run_id;
                if initial_run.is_some() {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(250)).await;
            }
            assert!(initial_run.is_some());
            dispatch.abort();
            // Model a lost durable acknowledgment, then restart the actual dispatcher.
            sqlx::query("update document_processing set run_id=null,delivered_at=null,dispatch_until=null,delivery_due_at=clock_timestamp() where id=$1").bind(summary.id).execute(&d.e.pool).await.unwrap();
            dispatch = tokio::spawn(control_plane::processing::dispatch::run(
                d.e.pool.clone(),
                dispatch_config.clone(),
            ));
            for _ in 0..40 {
                if store::row(&d.e.pool, summary.id).await.unwrap().run_id == initial_run {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(250)).await;
            }
            assert_eq!(
                store::row(&d.e.pool, summary.id).await.unwrap().run_id,
                initial_run
            );
            // No worker has polled yet: reconciliation is proved before publication.
            std::fs::write(folder.path().join("release-worker"), "ready").unwrap();
        }
        let mut outcome = summary;
        for _ in 0..240 {
            outcome = store::row(&d.e.pool, outcome.id).await.unwrap().summary;
            if outcome.status.terminal() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
        if let Some(marker) = fault {
            assert_eq!(
                outcome.status,
                ProcessingStatus::Failed,
                "{name} {outcome:?}"
            );
            if name == "render-retry.docx" {
                assert_eq!(outcome.error_code.as_deref(), Some("preview_failed"));
            }
            let original = d
                .request(
                    "reader",
                    "GET",
                    &format!("/documents/{id}/content"),
                    Body::empty(),
                    "",
                    None,
                )
                .await;
            assert_eq!(
                to_bytes(original.into_body(), body.len())
                    .await
                    .unwrap()
                    .as_ref(),
                body
            );
            std::fs::remove_file(folder.path().join(marker)).unwrap();
            let failed_id = outcome.id;
            outcome = p
                .start(
                    "writer",
                    Uuid::new_v4(),
                    id,
                    Start {
                        profile,
                        retry_of: Some(failed_id),
                    },
                )
                .await
                .unwrap();
            for _ in 0..240 {
                outcome = store::row(&d.e.pool, outcome.id).await.unwrap().summary;
                if outcome.status.terminal() {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(500)).await;
            }
            assert_eq!(outcome.retry_of, Some(failed_id));
        }
        assert_eq!(
            outcome.status,
            ProcessingStatus::Succeeded,
            "{name} {outcome:?}\n{}",
            std::fs::read_to_string(folder.path().join("worker.log")).unwrap()
        );
        if let Some(run) = initial_run {
            assert_eq!(
                store::row(&d.e.pool, outcome.id)
                    .await
                    .unwrap()
                    .run_id
                    .as_deref(),
                Some(run.as_str())
            );
        }
        if name == "fast.txt" {
            // A new OS process rebuilds all worker clients from persisted state.
            child.kill().await.unwrap();
            child.wait().await.unwrap();
            std::fs::remove_file(folder.path().join("ready")).unwrap();
            child = spawn_worker(&input).await;
            assert_eq!(
                store::row(&d.e.pool, outcome.id)
                    .await
                    .unwrap()
                    .summary
                    .status,
                ProcessingStatus::Succeeded
            );
        }
        if name.ends_with("csv") {
            assert_eq!(outcome.rows, Some(2));
        } else if !name.ends_with("xlsx") {
            assert!(outcome.chunks > 0);
            assert_eq!(outcome.chunks, outcome.vectors);
        }
        if ["pdf", "docx", "pptx", "doc", "odt", "ppt"]
            .iter()
            .any(|suffix| name.ends_with(suffix))
        {
            let response = d
                .request(
                    "reader",
                    "GET",
                    &format!("/documents/{id}/preview?artifact=native"),
                    Body::empty(),
                    "",
                    None,
                )
                .await;
            assert_eq!(response.status(), 200);
            let bytes = to_bytes(response.into_body(), 1_000_000).await.unwrap();
            assert!(bytes.starts_with(b"%PDF-"));
        }
        let preview = d
            .request(
                "reader",
                "GET",
                &format!("/documents/{id}/preview?artifact=raw"),
                Body::empty(),
                "",
                None,
            )
            .await;
        assert_eq!(preview.status(), 200);
        assert!(
            !to_bytes(preview.into_body(), 100000)
                .await
                .unwrap()
                .is_empty()
        );
        let original = d
            .request(
                "reader",
                "GET",
                &format!("/documents/{id}/content"),
                Body::empty(),
                "",
                None,
            )
            .await;
        assert_eq!(
            to_bytes(original.into_body(), body.len())
                .await
                .unwrap()
                .as_ref(),
            body
        );
    }
    // Reconcile a completed workflow whose durable start ACK was lost.
    dispatch.abort();
    dispatch.await.unwrap_err();
    use temporalio_client::{
        Client, ClientOptions, ConnectionOptions, Url, grpc::WorkflowService,
        tonic::Request as TemporalRequest,
    };
    use temporalio_common::protos::temporal::api::{
        common::v1::WorkflowExecution, workflowservice::v1::DescribeWorkflowExecutionRequest,
    };
    let mut temporal_client = Client::connect(
        ConnectionOptions::new(
            Url::parse(&format!("http://{}", dispatch_config.temporal.host)).unwrap(),
        )
        .build(),
        ClientOptions::new("default").build(),
    )
    .await
    .unwrap();
    let (_, receipt) = d
        .upload(
            "writer",
            "unsupported.bin",
            b"unsupported",
            Uuid::new_v4(),
            None,
        )
        .await;
    let document = receipt["document_id"].as_str().unwrap().parse().unwrap();
    let pending = p
        .start(
            "writer",
            Uuid::new_v4(),
            document,
            Start {
                profile: Profile::Fast,
                retry_of: None,
            },
        )
        .await
        .unwrap();
    control_plane::processing::dispatch::tick(&d.e.pool, &dispatch_config, &temporal_client)
        .await
        .unwrap();
    let accepted = store::row(&d.e.pool, pending.id).await.unwrap();
    assert!(accepted.run_id.is_some());
    let describe_request = DescribeWorkflowExecutionRequest {
        namespace: "default".into(),
        execution: Some(WorkflowExecution {
            workflow_id: accepted.workflow_id.clone(),
            run_id: accepted.run_id.clone().unwrap(),
        }),
    };
    let mut closed = false;
    for _ in 0..180 {
        let info = temporal_client
            .describe_workflow_execution(TemporalRequest::new(describe_request.clone()))
            .await
            .unwrap()
            .into_inner()
            .workflow_execution_info
            .unwrap();
        if info.status != 1 {
            assert_eq!(info.status, 2);
            closed = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    assert!(
        closed,
        "unsupported input must close without publishing success"
    );
    sqlx::query("update document_processing set run_id=null,delivered_at=null,dispatch_until=null,delivery_due_at=clock_timestamp() where id=$1").bind(pending.id).execute(&d.e.pool).await.unwrap();
    control_plane::processing::dispatch::tick(&d.e.pool, &dispatch_config, &temporal_client)
        .await
        .unwrap();
    let reconciled = store::row(&d.e.pool, pending.id).await.unwrap();
    assert_eq!(reconciled.run_id, accepted.run_id);
    assert_eq!(reconciled.summary.status, ProcessingStatus::Failed);
    assert_eq!(
        d.request(
            "reader",
            "GET",
            &format!("/documents/{document}/content"),
            Body::empty(),
            "",
            None
        )
        .await
        .status(),
        200
    );
    // Old ambiguity without a durable ACK expires before Start, even with Temporal available.
    let expired = p
        .start(
            "writer",
            Uuid::new_v4(),
            document,
            Start {
                profile: Profile::Fast,
                retry_of: Some(pending.id),
            },
        )
        .await
        .unwrap();
    sqlx::query("update document_processing set created_at=clock_timestamp()-interval '2 days',first_dispatch_at=clock_timestamp()-interval '2 days' where id=$1").bind(expired.id).execute(&d.e.pool).await.unwrap();
    control_plane::processing::dispatch::tick(&d.e.pool, &dispatch_config, &temporal_client)
        .await
        .unwrap();
    let expired = store::row(&d.e.pool, expired.id).await.unwrap();
    assert_eq!(
        expired.summary.error_code.as_deref(),
        Some("delivery_unknown")
    );
    assert!(expired.run_id.is_none());
    let absent = temporal_client
        .describe_workflow_execution(TemporalRequest::new(DescribeWorkflowExecutionRequest {
            namespace: "default".into(),
            execution: Some(WorkflowExecution {
                workflow_id: expired.workflow_id,
                run_id: String::new(),
            }),
        }))
        .await;
    assert_eq!(
        absent.unwrap_err().code(),
        temporalio_client::tonic::Code::NotFound
    );
    std::fs::write(folder.path().join("stop"), "stop").unwrap();
    assert!(
        tokio::time::timeout(Duration::from_secs(10), child.wait())
            .await
            .unwrap()
            .unwrap()
            .success()
    );
    assert!(d.identity.control.lock().await.worker_token_requests > 0);
    server.abort();
    drop(temporal);
}

async fn ready_temporal(host: &str) -> temporalio_client::Client {
    use temporalio_client::{
        Client, ClientOptions, ConnectionOptions, Url, grpc::WorkflowService, tonic::Request,
    };
    use temporalio_common::protos::temporal::api::workflowservice::v1::DescribeNamespaceRequest;
    for _ in 0..120 {
        let connected = Client::connect(
            ConnectionOptions::new(Url::parse(&format!("http://{host}")).unwrap()).build(),
            ClientOptions::new("default").build(),
        )
        .await;
        if let Ok(mut client) = connected {
            let namespace = DescribeNamespaceRequest {
                namespace: "default".into(),
                ..Default::default()
            };
            if client
                .describe_namespace(Request::new(namespace))
                .await
                .is_ok()
            {
                return client;
            }
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    panic!("Temporal did not become ready");
}
async fn admit(d: &Documents, p: &Processing, name: &str) -> Uuid {
    let (status, receipt) = d
        .upload("writer", name, b"kept", Uuid::new_v4(), None)
        .await;
    assert_eq!(status, 201, "{receipt}");
    let document = receipt["document_id"].as_str().unwrap().parse().unwrap();
    let start = Start {
        profile: Profile::Fast,
        retry_of: None,
    };
    p.start("writer", Uuid::new_v4(), document, start)
        .await
        .unwrap()
        .id
}
async fn run_id_within(pool: &sqlx::PgPool, id: Uuid, within: Duration) -> Option<String> {
    let deadline = tokio::time::Instant::now() + within;
    loop {
        let run = store::row(pool, id).await.unwrap().run_id;
        if run.is_some() || tokio::time::Instant::now() >= deadline {
            return run;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
}

// No KF worker polls the queue here, so delivered workflows stay running.
// Proves: I28
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
#[ignore = "needs disposable PostgreSQL, OpenFGA, SeaweedFS and Temporal"]
async fn processing_dispatch_wakes_on_commit_and_prefers_new_intents() {
    if std::env::var_os("CONTROL_PLANE_IT_PROCESSING").is_none() {
        return;
    }
    use control_plane::processing::dispatch;
    let (d, p) = Box::pin(setup()).await;
    let (temporal, host) = start_temporal();
    let client = ready_temporal(&host).await;
    let mut config = p.config.clone();
    config.temporal.host = host;

    // The commit wakes the dispatcher long before its safety-net poll.
    let mut slow = config.clone();
    slow.limits.poll_seconds = 60;
    let dispatcher = tokio::spawn(dispatch::run(d.e.pool.clone(), slow));
    let first = admit(&d, &p, "first.txt").await;
    assert!(
        run_id_within(&d.e.pool, first, Duration::from_secs(30))
            .await
            .is_some()
    );
    tokio::time::sleep(Duration::from_secs(1)).await;
    let woken = admit(&d, &p, "woken.txt").await;
    assert!(
        run_id_within(&d.e.pool, woken, Duration::from_secs(5))
            .await
            .is_some(),
        "admission commit must wake the dispatcher"
    );
    dispatcher.abort();
    dispatcher.await.unwrap_err();

    // A new intent is leased before running work due for reconciliation.
    let mut narrow = config.clone();
    narrow.limits.batch = 2;
    let running = [
        admit(&d, &p, "running-a.txt").await,
        admit(&d, &p, "running-b.txt").await,
    ];
    dispatch::tick(&d.e.pool, &narrow, &client).await.unwrap();
    for id in running {
        assert!(store::row(&d.e.pool, id).await.unwrap().run_id.is_some());
    }
    sqlx::query("update document_processing set delivery_due_at=clock_timestamp()-interval '1 minute' where id=any($1)")
        .bind(&running[..]).execute(&d.e.pool).await.unwrap();
    let fresh = admit(&d, &p, "fresh.txt").await;
    assert_eq!(
        dispatch::tick(&d.e.pool, &narrow, &client).await.unwrap(),
        2
    );
    assert!(store::row(&d.e.pool, fresh).await.unwrap().run_id.is_some());

    // A notification lost while stopped is delivered at startup, and a due row
    // without any notification is reconciled by the poll.
    let missed = admit(&d, &p, "missed.txt").await;
    let mut fast = config.clone();
    fast.limits.poll_seconds = 1;
    let dispatcher = tokio::spawn(dispatch::run(d.e.pool.clone(), fast));
    let delivered = run_id_within(&d.e.pool, missed, Duration::from_secs(10)).await;
    assert!(delivered.is_some());
    sqlx::query("update document_processing set run_id=null,delivered_at=null,dispatch_until=null,delivery_due_at=clock_timestamp() where id=$1")
        .bind(missed).execute(&d.e.pool).await.unwrap();
    assert_eq!(
        run_id_within(&d.e.pool, missed, Duration::from_secs(5)).await,
        delivered
    );
    dispatcher.abort();
    drop(temporal);
}

// Proves: I2, I3, I22, I25, I26
#[tokio::test]
#[ignore = "needs disposable PostgreSQL, OpenFGA and SeaweedFS"]
async fn processing_upload_atomic_intent_and_retry_without_new_original() {
    let (d, p) = Box::pin(setup()).await;
    let key = Uuid::new_v4();
    async fn upload(d: &Documents, key: Uuid, profile: &str) -> (u16, Value) {
        let body = "--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"atomic.txt\"\r\nContent-Type: text/plain\r\n\r\nbytes\r\n--fixture--\r\n";
        json_response(
            d.request(
                "writer",
                "POST",
                &format!("/folders/{}/documents?profile={profile}", d.folder.id),
                Body::from(body),
                "multipart/form-data; boundary=fixture",
                Some(key),
            )
            .await,
        )
        .await
    }
    let (status, receipt) = upload(&d, key, "fast").await;
    assert_eq!(status, 201, "{receipt}");
    let original: Uuid = receipt["document_id"].as_str().unwrap().parse().unwrap();
    let op: Uuid = receipt["processing"]["id"]
        .as_str()
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(upload(&d, key, "fast").await.0, 200);
    assert_eq!(upload(&d, key, "rich").await.0, 409);
    let attempts: i64 =
        sqlx::query_scalar("select count(*) from document_processing where document_id=$1")
            .bind(original)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    assert_eq!(attempts, 1);
    let ack = d
        .request(
            "writer",
            "PUT",
            &format!("/document-uploads/{key}/acknowledgment"),
            Body::empty(),
            "",
            None,
        )
        .await;
    assert_eq!(ack.status(), 409);
    sqlx::query("update document_processing set deadline_at=clock_timestamp()-interval '1 second' where id=$1").bind(op).execute(&d.e.pool).await.unwrap();
    control_plane::processing::dispatch::expire(&d.e.pool, &p.config)
        .await
        .unwrap();
    let failed = store::row(&d.e.pool, op).await.unwrap();
    assert_eq!(failed.summary.status, ProcessingStatus::Failed);
    let retry = Start {
        profile: Profile::Medium,
        retry_of: Some(op),
    };
    let retry_key = Uuid::new_v4();
    let (first, second) = tokio::join!(
        p.start("writer", retry_key, original, retry.clone()),
        p.start("writer", retry_key, original, retry.clone())
    );
    let first = first.unwrap();
    assert_eq!(first.id, second.unwrap().id);
    assert!(
        p.start("writer", Uuid::new_v4(), original, retry)
            .await
            .is_err()
    );
    assert!(
        p.claim(claim(&failed.work(), Stage::Preparation, Uuid::new_v4(), 1))
            .await
            .is_err()
    );
    let (_, usage) = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{}/storage", d.folder.space_id),
            Value::Null,
        )
        .await;
    assert_eq!(usage["used_bytes"], 5);
    assert_eq!(
        d.request(
            "reader",
            "GET",
            &format!("/documents/{original}/content"),
            Body::empty(),
            "",
            None
        )
        .await
        .status(),
        200
    );
}

// Proves: I2, I3, I22, I25, I26
#[tokio::test]
#[ignore = "needs disposable PostgreSQL, OpenFGA and SeaweedFS"]
async fn processing_workload_identity_and_revoked_publication() {
    let (d, p) = Box::pin(setup()).await;
    let (_, receipt) = d
        .upload("writer", "revocation.txt", b"kept", Uuid::new_v4(), None)
        .await;
    let id = receipt["document_id"].as_str().unwrap().parse().unwrap();
    let summary = p
        .start(
            "writer",
            Uuid::new_v4(),
            id,
            Start {
                profile: Profile::Fast,
                retry_of: None,
            },
        )
        .await
        .unwrap();
    let now = chrono::Utc::now().timestamp();
    let valid = json!({"sub":"worker","preferred_username":"service-account-manager-worker","iss":d.identity.realm,"aud":"app","azp":"manager-worker","client_id":"manager-worker","iat":now,"exp":now+600});
    for (field, value, allowed) in [
        ("aud", "wrong", false),
        ("iss", "https://wrong.invalid", false),
        ("client_id", "other-worker", false),
        ("preferred_username", "writer", false),
        ("client_id", "manager-worker", true),
    ] {
        let mut claims = valid.clone();
        claims[field] = value.into();
        let token = d.identity.sign(claims);
        let response = d
            .app
            .clone()
            .oneshot(
                Request::builder()
                    .uri(format!("/v1/document-processing/{}/work", summary.id))
                    .header("authorization", format!("Bearer {token}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status().is_success(), allowed, "{field}");
    }
    assert_eq!(
        d.request(
            "writer",
            "GET",
            &format!("/document-processing/{}/work", summary.id),
            Body::empty(),
            "",
            None
        )
        .await
        .status(),
        403
    );
    let work = store::row(&d.e.pool, summary.id).await.unwrap().work();
    let prepared = p
        .claim(claim(&work, Stage::Preparation, Uuid::new_v4(), 1))
        .await
        .unwrap();
    commit(&p, &prepared, &[("policy.json", b"{}")], 0).await;
    let extracted = p
        .claim(claim(&work, Stage::Extraction, Uuid::new_v4(), 1))
        .await
        .unwrap();
    commit(
        &p,
        &extracted,
        &[("metadata.json", b"{}"), ("output.md", b"kept")],
        0,
    )
    .await;
    let indexed = p
        .claim(claim(&work, Stage::Indexing, Uuid::new_v4(), 1))
        .await
        .unwrap();
    let mut manifest = store::row(&d.e.pool, summary.id)
        .await
        .unwrap()
        .generations
        .iter()
        .find(|g| g.id == extracted.generation)
        .unwrap()
        .manifest
        .clone()
        .unwrap();
    manifest.generation = indexed.generation;
    for (name, bytes) in [
        ("metadata.json", b"{}".as_slice()),
        ("output.md", b"kept".as_slice()),
    ] {
        let file = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(file.path(), bytes).unwrap();
        Box::pin(p.derived.put_verified(
            &format!("{}{name}", indexed.output_prefix),
            file.path(),
            bytes.len() as i64,
            &Sha256::digest(bytes).into(),
        ))
        .await
        .unwrap();
    }
    *d.fga_proxy.fault.lock().await = crate::support::fga_proxy::Fault {
        read_page_size: Some(1),
        ..Default::default()
    };
    let org: Uuid =
        sqlx::query_scalar("select organization_id from document_processing where id=$1")
            .bind(summary.id)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
    let held = crate::hold_organization_lock(&d.e, org).await;
    let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let (ready, rx) = tokio::sync::oneshot::channel();
    let samples = tokio::spawn(crate::folder_scaling::sample_locks(
        d.e.pool.clone(),
        stop.clone(),
        ready,
    ));
    rx.await.unwrap();
    let pool = d.e.pool.clone();
    let fga = p.fga.clone();
    let space = d.folder.space_id;
    let revoke = tokio::spawn(async move {
        control_plane::spaces::revoke(&pool, &fga, "alice", space, Role::Editor, "writer").await
    });
    async fn waiting(pool: &sqlx::PgPool, count: i64) {
        tokio::time::timeout(Duration::from_secs(5), async {
            loop {
                let n: i64 = sqlx::query_scalar("select count(*) from pg_locks where locktype='advisory' and not granted and database=(select oid from pg_database where datname=current_database())").fetch_one(pool).await.unwrap();
                if n >= count { break; }
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        }).await.unwrap();
    }
    waiting(&d.e.pool, 1).await;
    let since = sqlx::query_scalar("select clock_timestamp()")
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    let publishing = p.clone();
    let pending_work = work.clone();
    let publish = tokio::spawn(async move {
        publishing
            .commit(Commit {
                work: pending_work,
                stage: Stage::Indexing,
                manifest,
            })
            .await
    });
    crate::wait_for_write_retry(&d.e.pool, since).await;
    held.rollback().await.unwrap();
    revoke.await.unwrap().unwrap();
    assert!(publish.await.unwrap().is_err());
    stop.store(true, std::sync::atomic::Ordering::Relaxed);
    let locks = samples.await.unwrap();
    println!(
        "processing concurrent revoke/publication: FGA={:?}, locks={locks}",
        d.fga_proxy.fault.lock().await.calls
    );
    // The service identity can fence its failed attempt after the human loses access.
    p.abandon(Failure {
        work: work.clone(),
        stage: Stage::Indexing,
        generation: Some(indexed.generation),
        code: FailureCode::AccessChanged,
    })
    .await
    .unwrap();
    assert!(
        store::row(&d.e.pool, summary.id)
            .await
            .unwrap()
            .manifest
            .is_none()
    );
    assert_eq!(
        d.request(
            "reader",
            "GET",
            &format!("/documents/{id}/content"),
            Body::empty(),
            "",
            None
        )
        .await
        .status(),
        200
    );
}

// Proves: I2, I22
#[tokio::test]
#[ignore = "needs disposable PostgreSQL, OpenFGA and SeaweedFS"]
async fn processing_admission_request_budget_at_one_and_one_hundred_documents() {
    use futures::{StreamExt, stream};
    let (d, p) = Box::pin(setup()).await;
    let (_, receipt) = d
        .upload("writer", "budget.txt", b"kept", Uuid::new_v4(), None)
        .await;
    let id: Uuid = receipt["document_id"].as_str().unwrap().parse().unwrap();
    let mut baseline = None;
    for count in [1, 100] {
        if count == 100 {
            // Metadata cardinality fixture; only the real original above is processed.
            sqlx::query("insert into document(id,space_id,folder_id,name,mime,size,sha256,created_by,object_key,quota_owner) select gen_random_uuid(),space_id,folder_id,'fixture-'||n,mime,size,sha256,created_by,'fixture/'||gen_random_uuid(),quota_owner from document cross join generate_series(1,99) as n where id=$1").bind(id).execute(&d.e.pool).await.unwrap();
        }
        for concurrency in [1, 8] {
            *d.fga_proxy.fault.lock().await = crate::support::fga_proxy::Fault {
                read_page_size: Some(1),
                ..Default::default()
            };
            let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
            let (ready, rx) = tokio::sync::oneshot::channel();
            let samples = tokio::spawn(crate::folder_scaling::sample_locks(
                d.e.pool.clone(),
                stop.clone(),
                ready,
            ));
            rx.await.unwrap();
            let key = Uuid::new_v4();
            let results = stream::iter(0..concurrency)
                .map(|_| {
                    p.start(
                        "writer",
                        key,
                        id,
                        Start {
                            profile: Profile::Fast,
                            retry_of: None,
                        },
                    )
                })
                .buffer_unordered(concurrency)
                .collect::<Vec<_>>()
                .await;
            let first = results[0].as_ref().unwrap();
            assert!(results.iter().all(|r| r.as_ref().unwrap().id == first.id));
            stop.store(true, std::sync::atomic::Ordering::Relaxed);
            let locks = samples.await.unwrap();
            let observed = d.fga_proxy.fault.lock().await;
            let per_request: std::collections::BTreeMap<_, _> = observed
                .calls
                .iter()
                .map(|(k, v)| (k.clone(), v / concurrency))
                .collect();
            if let Some(expected) = &baseline {
                assert_eq!(&per_request, expected);
            } else {
                baseline = Some(per_request);
            }
            println!(
                "processing admission: documents={count}, concurrency={concurrency}, writer_memberships=2, FGA={:?}, reads={:?}, writes={:?}, locks={locks}",
                observed.calls, observed.reads, observed.written
            );
            drop(observed);
            // Reuse only the real original for another independent admission measurement.
            sqlx::query("delete from document_processing where document_id=$1")
                .bind(id)
                .execute(&d.e.pool)
                .await
                .unwrap();
        }
    }
}
