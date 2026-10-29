// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use control_plane::processing::{
    Processing, config::ProcessingConfig, models::*, store, worker_contract::WorkerContract,
};

async fn setup() -> (Documents, Arc<Processing>) {
    setup_with_lifecycle(Default::default()).await
}

async fn setup_with_lifecycle(
    lifecycle: control_plane::lifecycle::Lifecycle,
) -> (Documents, Arc<Processing>) {
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
            agent_catalog: Default::default(),
            pool: d.e.pool.clone(),
            fga: observed,
            auth: Arc::new(d.identity.auth().await),
            content: Some(d.storage.clone()),
            processing: Some(processing.clone()),
            directory: None,
            onboarding: Default::default(),
            lifecycle,
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
async fn published(pool: &sqlx::PgPool, document: Uuid) -> (store::Generation, Manifest) {
    let g: store::Generation = sqlx::query_as(
        "select g.* from document d join generation g on g.id=d.published_generation where d.id=$1",
    )
    .bind(document)
    .fetch_one(pool)
    .await
    .unwrap();
    let manifest = store::manifest(pool, &g).await.unwrap();
    (g, manifest)
}
async fn expire_generations(pool: &sqlx::PgPool, processing: Uuid) {
    sqlx::query("update generation set expires_at=clock_timestamp()-interval '2 minutes',cleanup_after=clock_timestamp()-interval '1 minute' where processing_id=$1")
        .bind(processing).execute(pool).await.unwrap();
}
async fn commit(p: &Processing, d: &Descriptor, files: &[(&str, &[u8])], chunks: i64) -> Summary {
    let mut artifacts = vec![];
    for (name, bytes) in files {
        let metadata = json!({"identity":{"document_uid":d.work.document_id},"source":{"retrievable":chunks>0},"processing":{"stages":{"vector":if chunks>0 {"done"} else {"not_started"}}}}).to_string();
        let bytes = if *name == "metadata.json" && *bytes == b"{}" {
            metadata.as_bytes()
        } else {
            *bytes
        };
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
    let (published_generation, saved) = published(&d.e.pool, work.document_id).await;
    let generation = saved.generation;
    let mut restarted = Processing {
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
    use control_plane::processing::retrievable::{RetrievalConfirmation, SetRetrievable};
    let row = store::row(&d.e.pool, work.processing_id).await.unwrap();
    let mut inconsistent = saved.clone();
    inconsistent.vectors = 0;
    assert!(
        p.published_retrievable(
            work.document_id,
            &published_generation.prefix,
            &inconsistent
        )
        .await
        .is_err()
    );
    assert!(
        p.set_retrievable(
            "unknown-user",
            work.document_id,
            SetRetrievable { retrievable: false }
        )
        .await
        .is_err()
    );
    use control_plane::processing::retrievable::RetrievalStep;
    restarted.config.temporal.host = "127.0.0.1:1".into();
    restarted.config.temporal.connect_timeout_seconds = 1;
    // Admit through production code, with delivery unavailable. Another service
    // instance must recover the same command from SQL, without any local memory.
    assert!(
        restarted
            .set_retrievable(
                &row.actor,
                work.document_id,
                SetRetrievable { retrievable: false }
            )
            .await
            .is_err()
    );
    let operation: Uuid = sqlx::query_scalar("select retrieval_id from document where id=$1")
        .bind(work.document_id)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert!(
        restarted
            .set_retrievable(
                &row.actor,
                work.document_id,
                SetRetrievable { retrievable: false }
            )
            .await
            .is_err()
    );
    let recovered = p.retrieval_work(work.document_id, operation).await.unwrap();
    assert!(!recovered.confirmed);
    let callback = |step| RetrievalConfirmation {
        operation_id: operation,
        retrievable: false,
        step,
    };
    assert!(
        p.confirm_retrievable(work.document_id, callback(RetrievalStep::Confirm))
            .await
            .is_err()
    );
    p.confirm_retrievable(work.document_id, callback(RetrievalStep::Claim))
        .await
        .unwrap();
    assert!(
        restarted
            .confirm_retrievable(work.document_id, callback(RetrievalStep::Claim))
            .await
            .is_err()
    );
    assert!(
        restarted
            .confirm_retrievable(work.document_id, callback(RetrievalStep::Confirm))
            .await
            .is_err()
    );
    let current = control_plane::db::document(&d.e.pool, work.document_id)
        .await
        .unwrap();
    assert!(current.retrievable && current.retrievable_pending);
    assert!(
        p.set_retrievable(
            &row.actor,
            work.document_id,
            SetRetrievable { retrievable: true }
        )
        .await
        .is_err()
    );
    assert!(
        p.confirm_retrievable(
            work.document_id,
            RetrievalConfirmation {
                step: RetrievalStep::Confirm,
                operation_id: Uuid::new_v4(),
                retrievable: false
            }
        )
        .await
        .is_err()
    );
    restarted
        .confirm_retrievable(work.document_id, callback(RetrievalStep::Applied))
        .await
        .unwrap();
    restarted
        .confirm_retrievable(work.document_id, callback(RetrievalStep::Applied))
        .await
        .unwrap();
    p.confirm_retrievable(
        work.document_id,
        RetrievalConfirmation {
            step: RetrievalStep::Confirm,
            operation_id: operation,
            retrievable: false,
        },
    )
    .await
    .unwrap();
    let excluded = control_plane::db::document(&d.e.pool, work.document_id)
        .await
        .unwrap();
    assert!(!excluded.retrievable && !excluded.retrievable_pending);
    // A lost HTTP response is recovered without contacting Temporal or creating a command.
    let repeated = restarted
        .set_retrievable(
            &row.actor,
            work.document_id,
            SetRetrievable { retrievable: false },
        )
        .await
        .unwrap();
    assert!(!repeated.retrievable && !repeated.retrievable_pending);
    p.confirm_retrievable(work.document_id, callback(RetrievalStep::Confirm))
        .await
        .unwrap();
    // A newer command rejects every late callback from the old operation.
    assert!(
        restarted
            .set_retrievable(
                &row.actor,
                work.document_id,
                SetRetrievable { retrievable: true }
            )
            .await
            .is_err()
    );
    for step in [
        RetrievalStep::Claim,
        RetrievalStep::Applied,
        RetrievalStep::Confirm,
    ] {
        assert!(
            p.confirm_retrievable(work.document_id, callback(step))
                .await
                .is_err()
        );
    }
    // A replayed ingestion callback cannot undo this confirmed exclusion.
    let replay = Box::pin(restarted.commit(Commit {
        work: work.clone(),
        stage: Stage::Indexing,
        manifest: saved.clone(),
    }))
    .await
    .unwrap();
    assert!(
        !control_plane::db::document(&d.e.pool, work.document_id)
            .await
            .unwrap()
            .retrievable
    );
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
    let work = row.work(p.installation);
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
    // The next stage restores from the stored prefix, never one rebuilt from identifiers.
    let relocated = format!("{}relocated/", current.output_prefix);
    sqlx::query("update generation set prefix=$2 where id=$1")
        .bind(current.generation)
        .bind(&relocated)
        .execute(&d.e.pool)
        .await
        .unwrap();
    let extracted = p
        .claim(claim(&work, Stage::Extraction, Uuid::new_v4(), 1))
        .await
        .unwrap();
    let predecessor = extracted.predecessor.as_ref().unwrap();
    assert_eq!(predecessor.prefix, relocated);
    assert_eq!(predecessor.manifest.generation, current.generation);
    assert_eq!(
        extracted.output_prefix,
        format!(
            "{}{}/",
            store::document_output(&p.config.derived.prefix, work.document_id),
            extracted.generation
        )
    );
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
    let pointer = "select published_generation from document where id=$1";
    let unpublished: Option<Uuid> = sqlx::query_scalar(pointer)
        .bind(work.document_id)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert!(unpublished.is_none());
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
    assert_eq!((done.chunks, done.vectors), (1, 1));
    let pointer: Option<Uuid> = sqlx::query_scalar(pointer)
        .bind(work.document_id)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(pointer, Some(indexed.generation));
    assert!(
        control_plane::db::document(&d.e.pool, work.document_id)
            .await
            .unwrap()
            .retrievable
    );
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
    // A fenced attempt writes only below its own prefix and cannot replace published bytes.
    assert_ne!(first.output_prefix, indexed.output_prefix);
    let zombie = tempfile::NamedTempFile::new().unwrap();
    std::fs::write(zombie.path(), b"zombie text").unwrap();
    assert!(
        Box::pin(p.derived.put_verified(
            &format!("{}output.md", indexed.output_prefix),
            zombie.path(),
            11,
            &Sha256::digest(b"zombie text").into(),
        ))
        .await
        .is_err()
    );
    // Cleanup releases abandoned stages, and protects the published ordinal even
    // when adaptive indexing planned more identifiers than it ultimately used.
    expire_generations(&d.e.pool, work.processing_id).await;
    let all = store::generations(&d.e.pool, work.processing_id)
        .await
        .unwrap();
    assert_eq!(all.len(), 4);
    let candidates = p.cleanup_candidates().await.unwrap();
    assert_eq!(candidates.len(), all.len());
    for candidate in candidates {
        let stored = all.iter().find(|g| g.id == candidate.generation).unwrap();
        assert_eq!(candidate.output_prefix, stored.prefix);
        assert!(!candidate.purge_document);
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
            purge_document: false,
        })
        .await
        .unwrap();
    }
    // Every generation is finished: the queue no longer returns it.
    assert!(p.cleanup_candidates().await.unwrap().is_empty());
    assert!(
        store::generations(&d.e.pool, work.processing_id)
            .await
            .unwrap()
            .iter()
            .all(|g| g.cleaned_at.is_some())
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
    // Preview reads the stored prefix: relocating it in SQL relocates the read.
    let relocated = format!("{}relocated/", indexed.output_prefix);
    let moved = tempfile::NamedTempFile::new().unwrap();
    std::fs::write(moved.path(), b"HELLO WORLD").unwrap();
    Box::pin(p.derived.put_verified(
        &format!("{relocated}output.md"),
        moved.path(),
        11,
        &Sha256::digest(b"HELLO WORLD").into(),
    ))
    .await
    .unwrap();
    sqlx::query("update generation set prefix=$2 where id=$1")
        .bind(indexed.generation)
        .bind(&relocated)
        .execute(&d.e.pool)
        .await
        .unwrap();
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
    assert_eq!(
        to_bytes(preview.into_body(), 100).await.unwrap(),
        "HELLO WORLD"
    );
    let (status, error) = d
        .json(
            "writer",
            "PUT",
            &format!("/documents/{id}/retrievable"),
            json!({"retrievable": null}),
        )
        .await;
    assert_eq!(status, 422, "{error}");
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
        if name.ends_with("csv") || name.ends_with("xlsx") {
            let published = control_plane::db::document(&d.e.pool, id).await.unwrap();
            assert!(
                published.retrievable,
                "published tables are included without requiring vectors"
            );
            let tables: i64 = sqlx::query_scalar("select count(*) from document d join artifact a on a.generation_id=d.published_generation where d.id=$1 and a.path like 'datasets/%.parquet'")
                .bind(id).fetch_one(&d.e.pool).await.unwrap();
            assert!(tables > 0);
            if outcome.vectors == 0 {
                use control_plane::processing::retrievable::SetRetrievable;
                for retrievable in [false, true] {
                    let changed = p
                        .set_retrievable("writer", id, SetRetrievable { retrievable })
                        .await
                        .unwrap();
                    assert_eq!(changed.retrievable, retrievable);
                    assert!(!changed.retrievable_pending);
                }
                assert!(
                    p.set_retrievable("reader", id, SetRetrievable { retrievable: false })
                        .await
                        .is_err()
                );
            }
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
        p.claim(claim(
            &failed.work(p.installation),
            Stage::Preparation,
            Uuid::new_v4(),
            1
        ))
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
    let work = store::row(&d.e.pool, summary.id)
        .await
        .unwrap()
        .work(p.installation);
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
    let extraction: store::Generation = sqlx::query_as("select * from generation where id=$1")
        .bind(extracted.generation)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    let mut manifest = store::manifest(&d.e.pool, &extraction).await.unwrap();
    manifest.generation = indexed.generation;
    let metadata = json!({"identity":{"document_uid":work.document_id},"source":{"retrievable":false},"processing":{"stages":{}}}).to_string();
    for (name, bytes) in [
        ("metadata.json", metadata.as_bytes()),
        ("output.md", b"kept".as_slice()),
    ] {
        if let Some(artifact) = manifest.artifacts.iter_mut().find(|a| a.path == name) {
            artifact.size = bytes.len() as i64;
            artifact.sha256 = format!("{:x}", Sha256::digest(bytes));
        }
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
    let org: Uuid = sqlx::query_scalar("select s.organization_id from document_processing p join document d on d.id=p.document_id join space s on s.id=d.space_id where p.id=$1")
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
            .published_generation
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

#[tokio::test]
#[ignore = "needs disposable PostgreSQL, OpenFGA and SeaweedFS"]
async fn stage_claims_lock_only_their_own_processing() {
    let (d, p) = Box::pin(setup()).await;
    let busy = admit(&d, &p, "busy.txt").await;
    let free = admit(&d, &p, "free.txt").await;
    // Hold the former global budget lock and another document's processing row.
    let mut held = d.e.pool.begin().await.unwrap();
    sqlx::query("select singleton from document_storage where singleton for update")
        .execute(&mut *held)
        .await
        .unwrap();
    sqlx::query("select id from document_processing where id=$1 for update")
        .bind(busy)
        .execute(&mut *held)
        .await
        .unwrap();
    let work = store::row(&d.e.pool, free)
        .await
        .unwrap()
        .work(p.installation);
    let claimed = tokio::time::timeout(
        Duration::from_secs(5),
        p.claim(claim(&work, Stage::Preparation, Uuid::new_v4(), 1)),
    )
    .await
    .expect("a claim must not wait for another document")
    .unwrap();
    assert_eq!(claimed.work.processing_id, free);
    held.rollback().await.unwrap();
}

/// An abandoned attempt whose lease expired; `due` is its queue time relative to now.
async fn abandoned_generation(pool: &sqlx::PgPool, processing: Uuid, due: &str) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query("insert into generation(id,processing_id,stage,execution_id,activity_id,attempt,expires_at,prefix,cleanup_after) values($1,$2,'preparation',$1,$1,1,clock_timestamp()-interval '2 minutes','fixture/'||$1||'/',clock_timestamp()+$3::interval)")
        .bind(id).bind(processing).bind(due).execute(pool).await.unwrap();
    id
}
async fn report_cleaned(p: &Processing, candidate: control_plane::processing::cleanup::Cleanup) {
    p.cleaned(control_plane::processing::cleanup::Cleaned {
        work: candidate.work,
        generation: candidate.generation,
        cursor: candidate.cursor,
        next_cursor: candidate.chunks,
        objects_empty: true,
        purge_document: candidate.purge_document,
    })
    .await
    .unwrap();
}
/// Concurrent polls; every claimed candidate appears in exactly one batch.
async fn poll_concurrently(
    p: &Arc<Processing>,
) -> Vec<control_plane::processing::cleanup::Cleanup> {
    let pollers: Vec<_> = (0..4)
        .map(|_| {
            let p = p.clone();
            tokio::spawn(async move { p.cleanup_candidates().await.unwrap() })
        })
        .collect();
    let mut all = Vec::new();
    for poller in pollers {
        all.extend(poller.await.unwrap());
    }
    let mut ids: Vec<Uuid> = all.iter().map(|c| c.generation).collect();
    ids.sort();
    ids.dedup();
    assert_eq!(ids.len(), all.len(), "pollers received overlapping batches");
    all
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
#[ignore = "needs disposable PostgreSQL, OpenFGA and SeaweedFS"]
async fn cleanup_queues_lease_disjoint_batches_past_failing_candidates() {
    let (d, p) = Box::pin(setup()).await;
    let processing = admit(&d, &p, "swept.txt").await;
    let batch = p.config.limits.batch as usize;
    let mut failing = Vec::new();
    for _ in 0..batch {
        failing.push(abandoned_generation(&d.e.pool, processing, "-10 minutes").await);
    }
    let first = abandoned_generation(&d.e.pool, processing, "-1 minute").await;
    let claimed = poll_concurrently(&p).await;
    assert_eq!(claimed.len(), batch + 1);

    // The head batch keeps failing: its sweep never reports. Later work still completes.
    for candidate in claimed {
        if candidate.generation == first {
            report_cleaned(&p, candidate).await;
        }
    }
    let later = abandoned_generation(&d.e.pool, processing, "-1 minute").await;
    let next = poll_concurrently(&p).await;
    assert_eq!(
        next.iter().map(|c| c.generation).collect::<Vec<_>>(),
        vec![later]
    );
    for candidate in next {
        report_cleaned(&p, candidate).await;
    }

    // Once their claims lapse, the failing candidates return and finish.
    sqlx::query("update generation set cleanup_after=clock_timestamp() where id=any($1)")
        .bind(&failing)
        .execute(&d.e.pool)
        .await
        .unwrap();
    let retried = poll_concurrently(&p).await;
    let mut ids: Vec<Uuid> = retried.iter().map(|c| c.generation).collect();
    ids.sort();
    failing.sort();
    assert_eq!(ids, failing);
    for candidate in retried {
        report_cleaned(&p, candidate).await;
    }
    assert!(p.cleanup_candidates().await.unwrap().is_empty());

    // The purge queue leases the same way and closes every generation of the document.
    let pending = abandoned_generation(&d.e.pool, processing, "-1 minute").await;
    sqlx::query(
        "update document_processing set status='failed',completed_at=clock_timestamp() where id=$1",
    )
    .bind(processing)
    .execute(&d.e.pool)
    .await
    .unwrap();
    mark_document_team(&d).await;
    let purge = poll_concurrently(&p).await;
    assert_eq!(purge.len(), 1);
    assert!(purge[0].purge_document);
    assert!(p.cleanup_candidates().await.unwrap().is_empty());
    for candidate in purge {
        report_cleaned(&p, candidate).await;
    }
    let (purged, open): (bool, i64) = sqlx::query_as("select d.purged_at is not null, (select count(*) from generation where processing_id=p.id and cleaned_at is null) from document d join document_processing p on p.document_id=d.id where p.id=$1")
        .bind(processing)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert!(purged);
    assert_eq!(
        open, 0,
        "generation {pending} stayed queued after the purge"
    );
    sqlx::query("update generation set cleanup_after=clock_timestamp()-interval '1 minute'")
        .execute(&d.e.pool)
        .await
        .unwrap();
    sqlx::query("update document set purge_after=clock_timestamp()-interval '1 minute' where deletion_id is not null")
        .execute(&d.e.pool)
        .await
        .unwrap();
    assert!(p.cleanup_candidates().await.unwrap().is_empty());
}

// Proves: I25, I26
#[tokio::test]
#[ignore = "needs disposable PostgreSQL, OpenFGA, SeaweedFS and Temporal"]
async fn retrieval_delivery_restarts_closed_failure_and_preserves_running_execution() {
    use control_plane::processing::dispatch::deliver_retrieval;
    use temporalio_client::{grpc::WorkflowService, tonic::Request};
    use temporalio_common::protos::temporal::api::{
        common::v1::WorkflowExecution,
        workflowservice::v1::{
            DescribeWorkflowExecutionRequest, TerminateWorkflowExecutionRequest,
        },
    };
    let (_d, p) = Box::pin(setup()).await;
    let (_temporal, host) = start_temporal();
    let mut client = ready_temporal(&host).await;
    let mut config = p.config.clone();
    config.temporal.host = host;
    let operation = Uuid::new_v4();
    let document = Uuid::new_v4();
    let execution = WorkflowExecution {
        workflow_id: format!("manager-retrievable-{}-{operation}", p.installation),
        run_id: String::new(),
    };
    let describe = DescribeWorkflowExecutionRequest {
        namespace: config.temporal.namespace.clone(),
        execution: Some(execution.clone()),
    };
    deliver_retrieval(&config, p.installation, document, operation)
        .await
        .unwrap();
    let first = client
        .describe_workflow_execution(Request::new(describe.clone()))
        .await
        .unwrap()
        .into_inner()
        .workflow_execution_info
        .unwrap()
        .execution
        .unwrap()
        .run_id;
    deliver_retrieval(&config, p.installation, document, operation)
        .await
        .unwrap();
    let running = client
        .describe_workflow_execution(Request::new(describe.clone()))
        .await
        .unwrap()
        .into_inner()
        .workflow_execution_info
        .unwrap()
        .execution
        .unwrap()
        .run_id;
    assert_eq!(first, running);
    client
        .terminate_workflow_execution(Request::new(TerminateWorkflowExecutionRequest {
            namespace: config.temporal.namespace.clone(),
            workflow_execution: Some(execution),
            reason: "fixture closed failure".into(),
            ..Default::default()
        }))
        .await
        .unwrap();
    deliver_retrieval(&config, p.installation, document, operation)
        .await
        .unwrap();
    let resumed = client
        .describe_workflow_execution(Request::new(describe))
        .await
        .unwrap()
        .into_inner()
        .workflow_execution_info
        .unwrap()
        .execution
        .unwrap()
        .run_id;
    assert_ne!(first, resumed);
}

#[tokio::test]
#[ignore = "needs disposable PostgreSQL, OpenFGA and SeaweedFS"]
async fn retired_folders_and_documents_are_absent_from_reads_and_producers() {
    let (mut d, _processing) = Box::pin(setup()).await;
    let space = d.folder.space_id;
    let prefix = if d.storage.config.prefix.is_empty() {
        String::new()
    } else {
        format!("{}/", d.storage.config.prefix)
    };
    db::rename_folder(&d.e.pool, d.folder.id, "A")
        .await
        .unwrap();
    let a = d.folder.clone();
    let b = control_plane::spaces::create_folder(
        &d.e.pool,
        &d.e.fga,
        "writer",
        space,
        Some(a.id),
        "B".into(),
    )
    .await
    .unwrap();
    let c = control_plane::spaces::create_folder(
        &d.e.pool,
        &d.e.fga,
        "writer",
        space,
        None,
        "C".into(),
    )
    .await
    .unwrap();
    let ids = [
        Uuid::new_v4(),
        Uuid::new_v4(),
        Uuid::new_v4(),
        Uuid::new_v4(),
    ];
    let bytes = b"%PDF";
    let file = tempfile::NamedTempFile::new().unwrap();
    std::fs::write(file.path(), bytes).unwrap();
    let hash: [u8; 32] = Sha256::digest(bytes).into();
    for (id, folder, name) in [
        (ids[0], Some(a.id), "a.pdf"),
        (ids[1], Some(b.id), "b.pdf"),
        (ids[2], Some(c.id), "c.pdf"),
        (ids[3], Some(c.id), "r.pdf"),
    ] {
        let key = format!("{prefix}{id}/input/{name}");
        Box::pin(d.storage.objects.put_verified(&key, file.path(), 4, &hash))
            .await
            .unwrap();
        sqlx::query("insert into document (id,space_id,folder_id,name,mime,size,sha256,created_by,object_key,quota_owner) values ($1,$2,$3,$4,'application/pdf',4,$5,'writer',$6,$2)")
            .bind(id).bind(space).bind(folder).bind(name)
            .bind(format!("{:x}", Sha256::digest(bytes))).bind(key)
            .execute(&d.e.pool).await.unwrap();
    }
    let (status, before) = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{space}/storage"),
            Value::Null,
        )
        .await;
    assert_eq!(status, 200, "{before}");
    assert_eq!(before["used_bytes"], 16);
    assert_eq!(before["documents"], 4);

    // Fixture only: folder/document target kinds arrive in P4; no production path marks rows.
    // The future deadline keeps this receipt out of lifecycle sweeps.
    let receipt = Uuid::new_v4();
    sqlx::query("insert into deletion (id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at) select $1,$2,'team',organization_id,organization_id,'writer',now(),now()+interval '1 year' from space where id=$2")
        .bind(receipt).bind(space).execute(&d.e.pool).await.unwrap();
    let mut tx = d.e.pool.begin().await.unwrap();
    sqlx::query("update folder set deletion_id=$1 where id=any($2)")
        .bind(receipt)
        .bind(&[a.id, b.id][..])
        .execute(&mut *tx)
        .await
        .unwrap();
    sqlx::query(
        "update document set deletion_id=$1,purge_after=clock_timestamp() where id=any($2)",
    )
    .bind(receipt)
    .bind(&[ids[0], ids[1], ids[3]][..])
    .execute(&mut *tx)
    .await
    .unwrap();
    tx.commit().await.unwrap();

    for suffix in ["", "&search=C", "&search=A", "&search=B", "&search=r.pdf"] {
        let (status, page) = d
            .json(
                "reader",
                "GET",
                &format!("/spaces/{space}/entries?limit=50{suffix}"),
                Value::Null,
            )
            .await;
        assert_eq!(status, 200, "{page}");
        let expected = if suffix.is_empty() || suffix == "&search=C" {
            1
        } else {
            0
        };
        assert_eq!(page["total"], expected, "{page}");
        assert_eq!(page["items"].as_array().unwrap().len(), expected as usize);
        if expected == 1 {
            assert_eq!(page["items"][0]["data"]["id"], c.id.to_string());
        }
    }
    for suffix in [
        "",
        "&search=c.pdf",
        "&search=a.pdf",
        "&search=b.pdf",
        "&search=r.pdf",
    ] {
        let (status, page) = d
            .json(
                "reader",
                "GET",
                &format!("/spaces/{space}/entries?parent_id={}{suffix}", c.id),
                Value::Null,
            )
            .await;
        assert_eq!(status, 200, "{page}");
        let expected = if suffix.is_empty() || suffix == "&search=c.pdf" {
            1
        } else {
            0
        };
        assert_eq!(page["total"], expected, "{page}");
        assert_eq!(page["items"].as_array().unwrap().len(), expected as usize);
        if expected == 1 {
            assert_eq!(page["items"][0]["data"]["id"], ids[2].to_string());
        }
        assert_eq!(page["ancestors"][0]["id"], c.id.to_string());
    }
    for folder in [a.id, b.id] {
        assert_eq!(
            d.json(
                "reader",
                "GET",
                &format!("/spaces/{space}/entries?parent_id={folder}"),
                Value::Null,
            )
            .await
            .0,
            404
        );
    }
    let (status, summary) = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{space}/storage"),
            Value::Null,
        )
        .await;
    assert_eq!(status, 200, "{summary}");
    for field in ["used_bytes", "bytes"] {
        assert_eq!(summary[field], 4);
    }
    assert_eq!(summary["documents"], 1);
    assert_eq!(summary["reserved_bytes"], 0);
    assert_eq!(
        summary["types"],
        json!([{"mime":"application/pdf","documents":1,"bytes":4}])
    );
    for id in [ids[0], ids[1], ids[3], Uuid::new_v4()] {
        for endpoint in [
            "content",
            "preview?artifact=native",
            "preview",
            "processing",
        ] {
            let (status, error) = d
                .json(
                    "reader",
                    "GET",
                    &format!("/documents/{id}/{endpoint}"),
                    Value::Null,
                )
                .await;
            assert_eq!(status, 404, "{endpoint}: {error}");
            assert_eq!(error["code"], "not_found");
        }
        assert_eq!(
            d.json(
                "reader",
                "POST",
                "/authorize/document",
                json!({"document_id":id,"permission":"read"}),
            )
            .await,
            (200, json!({"allowed":false}))
        );
    }
    for (method, body) in [
        ("PATCH", json!({"name":"renamed"})),
        ("DELETE", Value::Null),
    ] {
        let (status, error) = d
            .json("writer", method, &format!("/folders/{}", a.id), body)
            .await;
        assert_eq!(status, 404, "{error}");
        assert_eq!(error["code"], "not_found");
    }
    d.folder = b;
    assert_eq!(
        d.upload("writer", "new.pdf", bytes, Uuid::new_v4(), None)
            .await
            .0,
        404
    );
    assert_eq!(
        d.json(
            "writer",
            "POST",
            "/folders",
            json!({"space_id":space,"parent_id":a.id,"name":"child"}),
        )
        .await
        .0,
        404
    );
    let response = d
        .request(
            "writer",
            "POST",
            &format!("/documents/{}/processing", ids[1]),
            Body::from(json!({"profile":"fast"}).to_string()),
            "application/json",
            Some(Uuid::new_v4()),
        )
        .await;
    let (status, error) = json_response(response).await;
    assert_eq!(status, 404, "{error}");
    assert_eq!(error["code"], "not_found");
    assert_eq!(
        d.json(
            "writer",
            "PUT",
            &format!("/documents/{}/retrievable", ids[0]),
            json!({"retrievable":true}),
        )
        .await
        .0,
        404
    );

    d.storage.cleanup_tick().await.unwrap();
    let completed: bool = sqlx::query_scalar(
        "select inventory_completed_at is not null from document_storage where singleton",
    )
    .fetch_one(&d.e.pool)
    .await
    .unwrap();
    assert!(completed);
    let original = d
        .storage
        .objects
        .get(&format!("{}{}/input/a.pdf", prefix, ids[0]))
        .await
        .unwrap()
        .body
        .collect()
        .await
        .unwrap()
        .into_bytes();
    assert_eq!(original.as_ref(), bytes);

    let (status, replacement) = d
        .json(
            "writer",
            "POST",
            "/folders",
            json!({"space_id":space,"name":"A"}),
        )
        .await;
    assert_eq!(status, 201, "{replacement}");
    assert_ne!(replacement["id"], a.id.to_string());
    assert_eq!(
        d.json(
            "writer",
            "POST",
            "/folders",
            json!({"space_id":space,"name":"A"}),
        )
        .await
        .0,
        409
    );

    let remaining = (d.storage.config.limits.team_bytes - 4) as usize;
    let (status, preflight) = d
        .json(
            "writer",
            "POST",
            &format!("/folders/{}/documents/preflight", c.id),
            json!({"files":[{"name":"r.pdf","size":remaining}]}),
        )
        .await;
    assert_eq!(status, 200, "{preflight}");
    assert_eq!(preflight["conflicts"], json!([]));
    d.folder = c.clone();
    let (status, uploaded) = d
        .upload(
            "writer",
            "r.pdf",
            &vec![b'x'; remaining],
            Uuid::new_v4(),
            None,
        )
        .await;
    assert_eq!(status, 201, "{uploaded}");
    assert_ne!(uploaded["document_id"], ids[3].to_string());
    assert_eq!(
        d.upload("writer", "r.pdf", bytes, Uuid::new_v4(), None)
            .await
            .0,
        409
    );
    assert_eq!(
        d.upload("writer", "over-quota.pdf", bytes, Uuid::new_v4(), None)
            .await
            .0,
        422
    );
    let (status, summary) = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{space}/storage"),
            Value::Null,
        )
        .await;
    assert_eq!(status, 200, "{summary}");
    assert_eq!(summary["used_bytes"], summary["quota_bytes"]);
    for endpoint in ["content", "preview?artifact=native"] {
        let response = d
            .request(
                "reader",
                "GET",
                &format!("/documents/{}/{endpoint}", ids[2]),
                Body::empty(),
                "",
                None,
            )
            .await;
        assert_eq!(response.status(), 200);
        assert_eq!(
            to_bytes(response.into_body(), 1024).await.unwrap().as_ref(),
            bytes
        );
    }
    let (status, witness) = d
        .json(
            "reader",
            "GET",
            &format!("/spaces/{space}/entries?parent_id={}", c.id),
            Value::Null,
        )
        .await;
    assert_eq!(status, 200, "{witness}");
    assert_eq!(witness["total"], 2);
    assert_eq!(witness["items"][0]["data"]["id"], ids[2].to_string());
    assert_eq!(witness["items"][1]["data"]["id"], uploaded["document_id"]);
    assert_eq!(db::folder(&d.e.pool, c.id).await.unwrap().name, "C");
    assert_eq!(db::document(&d.e.pool, ids[2]).await.unwrap().name, "c.pdf");
    assert_eq!(
        d.json(
            "reader",
            "GET",
            &format!("/documents/{}/processing", ids[2]),
            Value::Null,
        )
        .await,
        (200, json!([]))
    );
    assert_eq!(
        d.json(
            "reader",
            "POST",
            "/authorize/document",
            json!({"document_id":ids[2],"permission":"read"}),
        )
        .await,
        (200, json!({"allowed":true}))
    );
}

// Acceptance will set these marks in P3b; this fixture alone bypasses its document guard.
async fn mark_document_team(d: &Documents) -> Uuid {
    let id = Uuid::new_v4();
    let mut tx = d.e.pool.begin().await.unwrap();
    sqlx::query("insert into deletion (id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at) select $1,id,'team',parent_id,organization_id,'writer',now(),now() from space where id=$2")
        .bind(id).bind(d.folder.space_id).execute(&mut *tx).await.unwrap();
    sqlx::query("update space set deletion_id=$1 where id=$2")
        .bind(id)
        .bind(d.folder.space_id)
        .execute(&mut *tx)
        .await
        .unwrap();
    sqlx::query("update folder set deletion_id=$1 where space_id=$2")
        .bind(id)
        .bind(d.folder.space_id)
        .execute(&mut *tx)
        .await
        .unwrap();
    sqlx::query(
        "update document set deletion_id=$1,purge_after=clock_timestamp() where space_id=$2",
    )
    .bind(id)
    .bind(d.folder.space_id)
    .execute(&mut *tx)
    .await
    .unwrap();
    tx.commit().await.unwrap();
    id
}

// Proves: I25, I26
#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn lifecycle_purges_retired_documents_after_derived_cleanup() {
    use control_plane::domain::SpaceKind;
    use control_plane::error::AppError;
    use control_plane::lifecycle::{Receipt, Status, cleanup};
    use control_plane::spaces;
    let (mut d, p) = Box::pin(setup()).await;
    let processing = admit(&d, &p, "D1.txt").await;
    let work = store::row(&d.e.pool, processing)
        .await
        .unwrap()
        .work(p.installation);
    let preparation = p
        .claim(claim(&work, Stage::Preparation, Uuid::new_v4(), 1))
        .await
        .unwrap();
    commit(&p, &preparation, &[("policy.json", b"{}")], 0).await;
    let extraction = p
        .claim(claim(&work, Stage::Extraction, Uuid::new_v4(), 1))
        .await
        .unwrap();
    commit(
        &p,
        &extraction,
        &[("output.md", b"kept"), ("metadata.json", b"{}")],
        0,
    )
    .await;
    let indexing = p
        .claim(claim(&work, Stage::Indexing, Uuid::new_v4(), 1))
        .await
        .unwrap();
    p.plan_vectors(control_plane::processing::cleanup::VectorPlan {
        work: work.clone(),
        generation: indexing.generation,
        count: 400,
    })
    .await
    .unwrap();
    let done = commit(
        &p,
        &indexing,
        &[
            ("output.md", b"kept"),
            ("metadata.json", b"{}"),
            ("chunks.jsonl", b"{}"),
        ],
        400,
    )
    .await;
    assert_eq!(done.status, ProcessingStatus::Succeeded);
    let (status, upload) = d
        .upload("writer", "D2.txt", b"unprocessed", Uuid::new_v4(), None)
        .await;
    assert_eq!(status, 201, "{upload}");
    let d2: Uuid = upload["document_id"].as_str().unwrap().parse().unwrap();
    let originals: Vec<String> =
        sqlx::query_scalar("select object_key from document where id=any($1)")
            .bind(&[work.document_id, d2][..])
            .fetch_all(&d.e.pool)
            .await
            .unwrap();
    assert_eq!(originals.len(), 2);

    let target = d.folder.clone();
    let organization: Uuid = sqlx::query_scalar("select organization_id from space where id=$1")
        .bind(target.space_id)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    let other = spaces::create_space(
        &d.e.pool,
        &d.e.fga,
        "alice",
        SpaceKind::Team,
        organization,
        "Witness".into(),
        "alice",
    )
    .await
    .unwrap();
    crate::grant(&d.e, other.id, Role::Editor, "writer").await;
    d.folder = spaces::create_folder(
        &d.e.pool,
        &d.e.fga,
        "writer",
        other.id,
        None,
        "Witness".into(),
    )
    .await
    .unwrap();
    let (status, witness) = d
        .upload("writer", "W.txt", b"witness", Uuid::new_v4(), None)
        .await;
    assert_eq!(status, 201, "{witness}");
    let witness: Uuid = witness["document_id"].as_str().unwrap().parse().unwrap();
    let witness_key: String = sqlx::query_scalar("select object_key from document where id=$1")
        .bind(witness)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    d.folder = target.clone();
    expire_generations(&d.e.pool, processing).await;
    sqlx::query("update generation set cleanup_cursor=200 where id=$1")
        .bind(indexing.generation)
        .execute(&d.e.pool)
        .await
        .unwrap();
    assert!(matches!(
        p.cleaned(control_plane::processing::cleanup::Cleaned {
            work: work.clone(),
            generation: indexing.generation,
            cursor: 0,
            next_cursor: 0,
            objects_empty: true,
            purge_document: true,
        })
        .await,
        Err(AppError::Problem {
            code: "stale_generation",
            ..
        })
    ));
    let operation = mark_document_team(&d).await;
    assert!(matches!(
        p.cleaned(control_plane::processing::cleanup::Cleaned {
            work: work.clone(),
            generation: indexing.generation,
            cursor: 200,
            next_cursor: 400,
            objects_empty: true,
            purge_document: false,
        })
        .await,
        Err(AppError::Problem {
            code: "stale_generation",
            ..
        })
    ));
    let (cursor, purged): (i32, bool) = sqlx::query_as("select g.cleanup_cursor, d.purged_at is not null from generation g, document d where g.id=$1 and d.id=$2")
        .bind(indexing.generation)
        .bind(work.document_id)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!((cursor, purged), (200, false));

    cleanup::batch(&d.e.pool, &d.e.fga, operation)
        .await
        .unwrap();
    let receipt: Receipt = sqlx::query_as("select * from deletion where id=$1")
        .bind(operation)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(receipt.status, Status::Running);
    assert_eq!(receipt.documents_deleted, 1);
    assert!(receipt.error_code.is_none());
    let remaining: Vec<Uuid> = sqlx::query_scalar("select id from document where deletion_id=$1")
        .bind(operation)
        .fetch_all(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(remaining, vec![work.document_id]);
    cleanup::batch(&d.e.pool, &d.e.fga, operation)
        .await
        .unwrap();
    let receipt: Receipt = sqlx::query_as("select * from deletion where id=$1")
        .bind(operation)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(receipt.status, Status::Running);
    assert_eq!(receipt.documents_deleted, 1);
    assert!(receipt.error_code.is_none());

    let candidates = p.cleanup_candidates().await.unwrap();
    assert_eq!(candidates.len(), 1);
    let candidate = candidates.into_iter().next().unwrap();
    assert!(candidate.purge_document);
    assert_eq!(candidate.generation, indexing.generation);
    assert_eq!(
        candidate.output_prefix,
        store::document_output(&p.config.derived.prefix, work.document_id)
    );
    assert_eq!(
        (candidate.chunks, candidate.cursor, candidate.batch),
        (0, 0, 200)
    );
    assert!(!candidate.preserve_objects);
    assert!(candidate.protected_ordinals.is_empty());
    let objects = p
        .derived
        .list(&candidate.output_prefix, None, 1000)
        .await
        .unwrap();
    assert!(objects.next.is_none());
    assert!(!objects.objects.is_empty());
    for (key, _, _) in objects.objects {
        p.derived.delete(&key).await.unwrap();
    }
    // The purge sweeps `{document}/output/` only; the original below `input/` remains.
    for key in &originals {
        assert!(d.storage.objects.get(key).await.is_ok());
    }
    p.cleaned(control_plane::processing::cleanup::Cleaned {
        work: candidate.work,
        generation: candidate.generation,
        cursor: 0,
        next_cursor: 0,
        objects_empty: true,
        purge_document: true,
    })
    .await
    .unwrap();
    let purged: bool = sqlx::query_scalar("select purged_at is not null from document where id=$1")
        .bind(work.document_id)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert!(purged);
    assert!(p.cleanup_candidates().await.unwrap().is_empty());
    for _ in 0..20 {
        cleanup::batch(&d.e.pool, &d.e.fga, operation)
            .await
            .unwrap();
        let receipt: Receipt = sqlx::query_as("select * from deletion where id=$1")
            .bind(operation)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
        if receipt.status == Status::Completed {
            break;
        }
    }
    let receipt: Receipt = sqlx::query_as("select * from deletion where id=$1")
        .bind(operation)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(receipt.status, Status::Completed);
    assert_eq!(receipt.documents_deleted, 2);
    assert_eq!(receipt.folders_deleted, 1);
    assert_eq!(receipt.spaces_deleted, 1);
    assert!(receipt.error_code.is_none());
    let leftovers: bool = sqlx::query_scalar("select exists(select 1 from document where id=any($1)) or exists(select 1 from document_processing where document_id=any($1)) or exists(select 1 from document_upload where id=any($1)) or exists(select 1 from folder where id=$2) or exists(select 1 from space where id=$3)")
        .bind(&[work.document_id, d2][..]).bind(target.id).bind(target.space_id).fetch_one(&d.e.pool).await.unwrap();
    assert!(!leftovers);
    d.storage.cleanup_tick().await.unwrap();
    for key in originals {
        assert!(d.storage.objects.get(&key).await.is_err());
    }
    assert!(d.storage.objects.get(&witness_key).await.is_ok());
    let response = d
        .request(
            "writer",
            "GET",
            &format!("/documents/{witness}/content"),
            Body::empty(),
            "",
            None,
        )
        .await;
    assert_eq!(response.status(), 200);
    assert_eq!(
        to_bytes(response.into_body(), 100).await.unwrap().as_ref(),
        b"witness"
    );
}

#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn lifecycle_waits_for_running_retired_document() {
    use control_plane::lifecycle::{Receipt, Status, cleanup};
    let (d, p) = Box::pin(setup()).await;
    let processing = admit(&d, &p, "running.txt").await;
    let work = store::row(&d.e.pool, processing)
        .await
        .unwrap()
        .work(p.installation);
    p.claim(claim(&work, Stage::Preparation, Uuid::new_v4(), 1))
        .await
        .unwrap();
    let operation = mark_document_team(&d).await;
    let row = store::row(&d.e.pool, processing).await.unwrap();
    assert_eq!(row.summary.status, ProcessingStatus::Running);
    sqlx::query("update generation set expires_at=clock_timestamp()-interval '2 minutes',cleanup_after=clock_timestamp()-interval '1 minute',cleaned_at=clock_timestamp() where processing_id=$1")
        .bind(processing).execute(&d.e.pool).await.unwrap();
    assert!(p.cleanup_candidates().await.unwrap().is_empty());
    for _ in 0..2 {
        cleanup::batch(&d.e.pool, &d.e.fga, operation)
            .await
            .unwrap();
        let receipt: Receipt = sqlx::query_as("select * from deletion where id=$1")
            .bind(operation)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
        assert_eq!(receipt.status, Status::Running);
        assert_eq!(receipt.documents_deleted, 0);
        assert!(receipt.error_code.is_none());
        let present: bool = sqlx::query_scalar("select exists(select 1 from document where id=$1)")
            .bind(work.document_id)
            .fetch_one(&d.e.pool)
            .await
            .unwrap();
        assert!(present);
        assert_eq!(
            store::row(&d.e.pool, processing)
                .await
                .unwrap()
                .summary
                .status,
            ProcessingStatus::Running
        );
    }
}

#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and S3: make test-integration"]
async fn editor_deletes_document_without_retiring_its_folder() {
    use control_plane::lifecycle::{Lifecycle, Receipt, Status, TargetKind, cleanup};
    let mut lifecycle = Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.catalog.space_policies.purge.default.retention =
        serde_yaml_ng::from_str("PT0S").unwrap();
    let (d, p) = Box::pin(setup_with_lifecycle(lifecycle)).await;
    db::rename_folder(&d.e.pool, d.folder.id, "F")
        .await
        .unwrap();
    let processing = admit(&d, &p, "D1.txt").await;
    let work = store::row(&d.e.pool, processing)
        .await
        .unwrap()
        .work(p.installation);
    let preparation = p
        .claim(claim(&work, Stage::Preparation, Uuid::new_v4(), 1))
        .await
        .unwrap();
    commit(&p, &preparation, &[("policy.json", b"{}")], 0).await;
    let extraction = p
        .claim(claim(&work, Stage::Extraction, Uuid::new_v4(), 1))
        .await
        .unwrap();
    commit(
        &p,
        &extraction,
        &[("output.md", b"kept"), ("metadata.json", b"{}")],
        0,
    )
    .await;
    let indexing = p
        .claim(claim(&work, Stage::Indexing, Uuid::new_v4(), 1))
        .await
        .unwrap();
    p.plan_vectors(control_plane::processing::cleanup::VectorPlan {
        work: work.clone(),
        generation: indexing.generation,
        count: 400,
    })
    .await
    .unwrap();
    let done = commit(
        &p,
        &indexing,
        &[
            ("output.md", b"kept"),
            ("metadata.json", b"{}"),
            ("chunks.jsonl", b"{}"),
        ],
        400,
    )
    .await;
    assert_eq!(done.status, ProcessingStatus::Succeeded);

    let (status, d2) = d
        .upload("writer", "D2.txt", b"unprocessed", Uuid::new_v4(), None)
        .await;
    assert_eq!(status, 201, "{d2}");
    let d2: Uuid = d2["document_id"].as_str().unwrap().parse().unwrap();
    let (status, witness) = d
        .upload("writer", "W.txt", b"witness", Uuid::new_v4(), None)
        .await;
    assert_eq!(status, 201, "{witness}");
    let witness: Uuid = witness["document_id"].as_str().unwrap().parse().unwrap();
    let original: String = sqlx::query_scalar("select object_key from document where id=$1")
        .bind(work.document_id)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    let witness_key: String = sqlx::query_scalar("select object_key from document where id=$1")
        .bind(witness)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    let path = format!("/documents/{}", work.document_id);
    assert_eq!(
        d.request("reader", "DELETE", &path, Body::empty(), "", None)
            .await
            .status(),
        403
    );
    assert_eq!(
        d.request(
            "writer",
            "DELETE",
            &format!("/documents/{}", Uuid::new_v4()),
            Body::empty(),
            "",
            None
        )
        .await
        .status(),
        404
    );
    let (status, accepted) = json_response(
        d.request("writer", "DELETE", &path, Body::empty(), "", None)
            .await,
    )
    .await;
    assert_eq!(status, 202, "{accepted}");
    assert_eq!(accepted["target_kind"], "document");
    assert_eq!(accepted["target_parent_id"], d.folder.space_id.to_string());
    let operation: Uuid = accepted["id"].as_str().unwrap().parse().unwrap();
    let (status, replay) = json_response(
        d.request("writer", "DELETE", &path, Body::empty(), "", None)
            .await,
    )
    .await;
    assert_eq!(status, 202);
    assert_eq!(replay, accepted);
    assert_eq!(
        d.request("reader", "DELETE", &path, Body::empty(), "", None)
            .await
            .status(),
        403
    );
    let (status, directory) = json_response(
        d.request(
            "writer",
            "GET",
            &format!(
                "/spaces/{}/entries?parent_id={}",
                d.folder.space_id, d.folder.id
            ),
            Body::empty(),
            "",
            None,
        )
        .await,
    )
    .await;
    assert_eq!(status, 200);
    let directory = directory.to_string();
    assert!(!directory.contains(&work.document_id.to_string()));
    assert!(directory.contains(&witness.to_string()));
    assert_eq!(
        d.request(
            "writer",
            "GET",
            &format!("{path}/content"),
            Body::empty(),
            "",
            None
        )
        .await
        .status(),
        404
    );
    let (status, replacement) = d
        .upload("writer", "D1.txt", b"replacement", Uuid::new_v4(), None)
        .await;
    assert_eq!(status, 201, "{replacement}");
    assert_eq!(
        d.request(
            "writer",
            "DELETE",
            &format!("/folders/{}", d.folder.id),
            Body::empty(),
            "",
            None
        )
        .await
        .status(),
        409
    );

    let active = admit(&d, &p, "running.txt").await;
    let active_work = store::row(&d.e.pool, active)
        .await
        .unwrap()
        .work(p.installation);
    p.claim(claim(&active_work, Stage::Preparation, Uuid::new_v4(), 1))
        .await
        .unwrap();
    assert_eq!(
        store::row(&d.e.pool, active).await.unwrap().summary.status,
        ProcessingStatus::Running
    );
    let (status, conflict) = json_response(
        d.request(
            "writer",
            "DELETE",
            &format!("/documents/{}", active_work.document_id),
            Body::empty(),
            "",
            None,
        )
        .await,
    )
    .await;
    assert_eq!(status, 409, "{conflict}");
    assert_eq!(conflict["code"], "processing_active");
    let untouched: bool = sqlx::query_scalar("select deletion_id is null and not exists(select 1 from deletion where target_id=$1) from document where id=$1")
        .bind(active_work.document_id).fetch_one(&d.e.pool).await.unwrap();
    assert!(untouched);

    cleanup::batch(&d.e.pool, &d.e.fga, operation)
        .await
        .unwrap();
    let waiting: Receipt = sqlx::query_as("select * from deletion where id=$1")
        .bind(operation)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(waiting.status, Status::Running);
    assert_eq!(waiting.documents_deleted, 0);
    assert!(waiting.error_code.is_none());
    expire_generations(&d.e.pool, processing).await;
    let candidates = p.cleanup_candidates().await.unwrap();
    let candidate = candidates
        .into_iter()
        .find(|c| c.work.document_id == work.document_id)
        .unwrap();
    assert!(candidate.purge_document);
    let objects = p
        .derived
        .list(&candidate.output_prefix, None, 1000)
        .await
        .unwrap();
    assert!(objects.next.is_none());
    for (key, _, _) in objects.objects {
        p.derived.delete(&key).await.unwrap();
    }
    p.cleaned(control_plane::processing::cleanup::Cleaned {
        work: candidate.work,
        generation: candidate.generation,
        cursor: 0,
        next_cursor: 0,
        objects_empty: true,
        purge_document: true,
    })
    .await
    .unwrap();
    cleanup::batch(&d.e.pool, &d.e.fga, operation)
        .await
        .unwrap();
    let completed: Receipt = sqlx::query_as("select * from deletion where id=$1")
        .bind(operation)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(completed.target_kind, TargetKind::Document);
    assert_eq!(completed.status, Status::Completed);
    assert_eq!(completed.documents_deleted, 1);
    assert_eq!(
        (completed.folders_deleted, completed.spaces_deleted),
        (0, 0)
    );
    let remains: bool = sqlx::query_scalar("select exists(select 1 from document where id=$1) or exists(select 1 from document_processing where document_id=$1) or exists(select 1 from document_upload where id=$1)")
        .bind(work.document_id).fetch_one(&d.e.pool).await.unwrap();
    assert!(!remains);
    assert!(db::folder(&d.e.pool, d.folder.id).await.is_ok());
    let (status, replay) = json_response(
        d.request("writer", "DELETE", &path, Body::empty(), "", None)
            .await,
    )
    .await;
    assert_eq!(status, 200);
    assert_eq!(replay["id"], accepted["id"]);
    d.storage.cleanup_tick().await.unwrap();
    assert!(d.storage.objects.get(&original).await.is_err());
    assert!(d.storage.objects.get(&witness_key).await.is_ok());
    assert_eq!(
        d.request(
            "writer",
            "GET",
            &format!("/documents/{witness}/content"),
            Body::empty(),
            "",
            None
        )
        .await
        .status(),
        200
    );

    let (status, accepted) = json_response(
        d.request(
            "writer",
            "DELETE",
            &format!("/documents/{d2}"),
            Body::empty(),
            "",
            None,
        )
        .await,
    )
    .await;
    assert_eq!(status, 202, "{accepted}");
    let operation: Uuid = accepted["id"].as_str().unwrap().parse().unwrap();
    cleanup::batch(&d.e.pool, &d.e.fga, operation)
        .await
        .unwrap();
    let completed: Receipt = sqlx::query_as("select * from deletion where id=$1")
        .bind(operation)
        .fetch_one(&d.e.pool)
        .await
        .unwrap();
    assert_eq!(completed.status, Status::Completed);
    assert_eq!(completed.documents_deleted, 1);
    assert!(db::folder(&d.e.pool, d.folder.id).await.is_ok());
}

#[path = "conversation_attachments.rs"]
mod attachments;
