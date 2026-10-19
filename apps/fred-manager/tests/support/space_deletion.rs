// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use fred_manager::lifecycle::{Lifecycle, Status, cleanup, policy::Mode, store};
fn immediate() -> Lifecycle {
    let mut lifecycle = Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.catalog.space_policies.purge.default.mode = Mode::ImmediateDelete;
    lifecycle
}
async fn drain(e: &Env, id: Uuid) {
    for _ in 0..100 {
        if store::status(&e.pool, &e.fga, "root", id)
            .await
            .unwrap()
            .status
            == Status::Completed
        {
            return;
        }
        cleanup::batch(&e.pool, &e.fga, id).await.unwrap();
    }
    panic!("cleanup did not converge");
}

// Proves: I24, I1, I4, I8, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn lifecycle_authority_retirement_documents_and_durable_receipts() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let (org, team) = org_and_team(&e).await;
    let project = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Project,
        team.id,
        "P".into(),
        "alice",
    )
    .await
    .unwrap();
    let l = immediate();
    assert!(matches!(
        l.accept(&e.pool, &e.fga, "alice", org.id).await,
        Err(AppError::Forbidden)
    ));
    assert!(matches!(
        Lifecycle::default()
            .accept(&e.pool, &e.fga, "root", team.id)
            .await,
        Err(AppError::Unavailable(_))
    ));
    let document = Document {
        id: Uuid::new_v4(),
        space_id: project.id,
        folder_id: None,
        name: "d".into(),
        mime: "text/plain".into(),
        size: 0,
        sha256: "a".repeat(64),
        created_by: "alice".into(),
        created_at: chrono::Utc::now(),
    };
    crate::environment::insert_document(&e.pool, &document)
        .await
        .unwrap();
    assert!(matches!(
        l.accept(&e.pool, &e.fga, "root", team.id).await,
        Err(AppError::Conflict(_))
    ));
    let count: i64 = sqlx::query_scalar("select count(*) from space_deletion")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(count, 0);
    store::require_active(&e.pool, team.id).await.unwrap();
    sqlx::query("delete from document where id=$1")
        .bind(document.id)
        .execute(&e.pool)
        .await
        .unwrap();
    let receipt = l.accept(&e.pool, &e.fga, "root", team.id).await.unwrap();
    assert_eq!(receipt.due_at, receipt.requested_at);
    assert_eq!(
        Lifecycle::default()
            .accept(&e.pool, &e.fga, "root", team.id)
            .await
            .unwrap()
            .id,
        receipt.id
    );
    assert!(spaces::load(&e.pool, &e.fga, project.id).await.is_err());
    assert!(
        spaces::create_folder(&e.pool, &e.fga, "alice", team.id, None, "blocked".into())
            .await
            .is_err()
    );
    assert!(
        spaces::grant(
            &e.pool,
            &e.fga,
            None,
            "alice",
            team.id,
            Role::Member,
            "alice"
        )
        .await
        .is_err()
    );
    assert!(l.accept(&e.pool, &e.fga, "root", org.id).await.is_err());
    assert!(
        !spaces::memberships(&e.pool, &e.fga, "alice")
            .await
            .unwrap()
            .iter()
            .any(|m| m.space.id == team.id || m.space.id == project.id)
    );
    drain(&e, receipt.id).await;
    let done = l.accept(&e.pool, &e.fga, "root", team.id).await.unwrap();
    assert_eq!(done.status, Status::Completed);
    assert_eq!(done.spaces_deleted, 2);
    assert!(db::space(&e.pool, team.id).await.is_err());
    assert!(
        e.fga
            .roles_of("alice")
            .await
            .unwrap()
            .iter()
            .all(|(id, _)| *id == org.id)
    );
    assert!(e.fga.is_platform_owner("root").await.unwrap());
    let recreated = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Team,
        org.id,
        "BID".into(),
        "alice",
    )
    .await
    .unwrap();
    cleanup::batch(&e.pool, &e.fga, receipt.id).await.unwrap();
    assert!(spaces::load(&e.pool, &e.fga, recreated.id).await.is_ok());
}

// Proves: I24, I1, I4, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn lifecycle_partial_link_loss_reserves_name_and_organization() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let (org, team) = org_and_team(&e).await;
    let p = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Project,
        team.id,
        "P".into(),
        "alice",
    )
    .await
    .unwrap();
    for id in [org.id, team.id, p.id] {
        grant(&e, id, Role::Member, "bob").await;
    }
    let l = immediate();
    let r = l.accept(&e.pool, &e.fga, "root", p.id).await.unwrap();
    // Partial cross-store failure: link disappeared while roles and the manifest remain.
    let response = reqwest::Client::new().post(format!("{}/stores/{}/write",e.openfga,e.fga.store_id())).json(&serde_json::json!({"deletes":{"tuple_keys":[{"object":format!("space:{}",p.id),"relation":"parent","user":format!("space:{}",team.id)}]}})).send().await.unwrap();
    assert!(response.status().is_success());
    assert!(l.accept(&e.pool, &e.fga, "root", team.id).await.is_err());
    assert!(
        spaces::create_space(
            &e.pool,
            &e.fga,
            "alice",
            SpaceKind::Project,
            team.id,
            "P".into(),
            "alice"
        )
        .await
        .is_err()
    );
    assert_eq!(
        spaces::organization(&e.pool, &e.fga, "alice")
            .await
            .unwrap(),
        Some(org.id)
    );
    // Receipt snapshots preserve the last-parent-content-role constraint after
    // a lost FGA link; role revocation itself remains immediate and unpurged.
    assert!(matches!(
        spaces::revoke(&e.pool, &e.fga, "alice", team.id, Role::Member, "bob").await,
        Err(AppError::Conflict(_))
    ));
    drain(&e, r.id).await;
    spaces::revoke(&e.pool, &e.fga, "alice", team.id, Role::Member, "bob")
        .await
        .unwrap();
    spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Project,
        team.id,
        "P".into(),
        "alice",
    )
    .await
    .unwrap();
}

// Proves: I24, I4, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn lifecycle_retention_personal_scope_and_final_guard_commit_failure() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let (org, _) = org_and_team(&e).await;
    grant(&e, org.id, Role::PersonalSpaceCreator, "alice").await;
    let (personal, _) = spaces::create_personal_space(&e.pool, &e.fga, "alice", org.id)
        .await
        .unwrap();
    assert!(
        immediate()
            .accept(&e.pool, &e.fga, "root", personal.id)
            .await
            .is_err()
    );
    let mut l = Lifecycle::default();
    l.config.enabled = true;
    let r = l.accept(&e.pool, &e.fga, "root", org.id).await.unwrap();
    assert_eq!((r.due_at - r.requested_at).num_days(), 7);
    cleanup::batch(&e.pool, &e.fga, r.id).await.unwrap();
    assert!(cleanup::candidates(&e.pool, 100).await.unwrap().is_empty());
    assert!(
        spaces::memberships(&e.pool, &e.fga, "alice")
            .await
            .unwrap()
            .is_empty()
    );
    assert!(
        spaces::create_organization(&e.pool, &e.fga, "Other", "alice")
            .await
            .is_err()
    );
    sqlx::query("update space_deletion set requested_at=now(), due_at=now() where id=$1")
        .bind(r.id)
        .execute(&e.pool)
        .await
        .unwrap();
    // Let child manifests and references drain, but fail the root SQL deletion once.
    sqlx::query("create function fail_root_delete() returns trigger language plpgsql as $$ begin if old.kind='organization' then raise exception 'fixture failure'; end if; return old; end $$").execute(&e.pool).await.unwrap();
    sqlx::query("create trigger fail_root_delete before delete on space for each row execute function fail_root_delete()").execute(&e.pool).await.unwrap();
    let mut failed = false;
    for _ in 0..20 {
        if cleanup::batch(&e.pool, &e.fga, r.id).await.is_err() {
            failed = true;
            break;
        }
    }
    assert!(failed);
    assert_ne!(
        store::status(&e.pool, &e.fga, "root", r.id)
            .await
            .unwrap()
            .status,
        Status::Completed
    );
    sqlx::query("drop trigger fail_root_delete on space")
        .execute(&e.pool)
        .await
        .unwrap();
    drain(&e, r.id).await;
    assert_eq!(
        spaces::organization(&e.pool, &e.fga, "alice")
            .await
            .unwrap(),
        None
    );
    assert!(e.fga.is_platform_owner("root").await.unwrap());
}

// Proves: I24, I4, I8
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn lifecycle_filtered_batches_lost_ack_and_unrelated_state() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let (org, team) = org_and_team(&e).await;
    let other = spaces::create_organization(&e.pool, &e.fga, "Other", "bob")
        .await
        .unwrap();
    sqlx::query("insert into folder (id,space_id,name,path) select gen_random_uuid(),$1,'folder-'||n,'/' from generate_series(1,1001) n").bind(team.id).execute(&e.pool).await.unwrap();
    // Bulk fixture roles use real guard writes, unrelated role count must not affect cleanup reads.
    for (target, prefix) in [(team.id, "target"), (other.id, "other")] {
        for chunk in 0..3 {
            let users: Vec<_> = (0..80).map(|n| format!("{prefix}-{chunk}-{n}")).collect();
            let tuples: Vec<_> = users
                .iter()
                .map(|user| fred_manager::fga::Tuple {
                    user,
                    role: Role::Member,
                    space: target,
                })
                .collect();
            let mut g = e
                .fga
                .guard(&[Scope::Organization(if target == team.id {
                    org.id
                } else {
                    other.id
                })])
                .await
                .unwrap();
            e.fga.write(&mut g, &tuples, &[]).await.unwrap();
        }
    }
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let fga = Fga::connect(
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
    {
        let mut fault = proxy.fault.lock().await;
        fault.calls.clear();
        fault.reads.clear();
    }
    let started = std::time::Instant::now();
    let r = immediate()
        .accept(&e.pool, &fga, "root", team.id)
        .await
        .unwrap();
    {
        let fault = proxy.fault.lock().await;
        assert_eq!(fault.calls.get("check"), Some(&1));
        assert_eq!(fault.calls.get("write"), Some(&1));
        assert_eq!(fault.calls.get("read"), Some(&4));
    }
    println!(
        "lifecycle acceptance: actors=1 spaces=3 target_tuples=243 unrelated_members=241 folders=1001 elapsed_us={}",
        started.elapsed().as_micros()
    );
    let cleanup_started = std::time::Instant::now();
    cleanup::batch(&e.pool, &fga, r.id).await.unwrap();
    assert_eq!(
        store::status(&e.pool, &e.fga, "root", r.id)
            .await
            .unwrap()
            .folders_deleted,
        1000
    );
    cleanup::batch(&e.pool, &fga, r.id).await.unwrap();
    {
        let mut fault = proxy.fault.lock().await;
        fault.fail_at = fault.writes + 1;
        fault.after = true;
    }
    assert!(cleanup::batch(&e.pool, &fga, r.id).await.is_err());
    for _ in 0..10 {
        cleanup::batch(&e.pool, &fga, r.id).await.unwrap();
        if store::status(&e.pool, &e.fga, "root", r.id)
            .await
            .unwrap()
            .status
            == Status::Completed
        {
            break;
        }
    }
    let done = store::status(&e.pool, &e.fga, "root", r.id).await.unwrap();
    assert_eq!(done.status, Status::Completed);
    assert_eq!(done.folders_deleted, 1001);
    assert_eq!(
        e.fga
            .space_holders(other.id, Role::Member)
            .await
            .unwrap()
            .len(),
        241
    );
    println!(
        "lifecycle cleanup: actors=1 spaces=3 target_tuples=243 unrelated_members=241 folders=1001 elapsed_ms={}",
        cleanup_started.elapsed().as_millis()
    );
    let fault = proxy.fault.lock().await;
    println!(
        "lifecycle total RPCs including acceptance and injected lost ack: {:?}",
        fault.calls
    );
    // Six cleanup batches: two folder batches, three tuple batches (one lost
    // acknowledgment), then final metadata removal; five filtered Reads each.
    assert_eq!(fault.calls.get("read"), Some(&34));
    assert_eq!(fault.calls.get("write"), Some(&7));
    for write in &fault.written {
        let count = ["writes", "deletes"]
            .iter()
            .map(|k| write[k]["tuple_keys"].as_array().map_or(0, Vec::len))
            .sum::<usize>();
        assert!(count <= 100);
    }
    for read in &fault.reads {
        assert!(read.get("tuple_key").is_some());
        assert_ne!(read["tuple_key"], serde_json::json!({}));
    }
}

// Proves: I24, I4, I22, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn lifecycle_waiters_recheck_retirement_and_authority_and_accept_once() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let (org, team) = org_and_team(&e).await;
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let fga = Fga::connect(
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
    let identity = support::IdentityServer::start().await;
    let directory = identity.directory();
    let identity_auth = identity.auth().await;
    let token = identity.token("root");
    let bundle = parse_blueprint(br#"{"users":[{"username":"alice","password":"private-password"}],"organizations":[{"ref":"org","name":"TSN","roles":{"alice":["admin","member","owner"]}}],"teams":[{"ref":"team","name":"BID","organization":"org","roles":{"alice":["admin"]}}],"projects":[]}"#).unwrap();
    let gate = std::sync::Arc::new(support::Gate::default());
    proxy.fault.lock().await.gate = Some(gate.clone());
    let pool = e.pool.clone();
    let auth = fga.clone();
    let id = team.id;
    let accept = tokio::spawn(async move { immediate().accept(&pool, &auth, "root", id).await });
    gate.entered.notified().await;
    let pool = e.pool.clone();
    let auth = e.fga.clone();
    let create = tokio::spawn(async move {
        spaces::create_folder(&pool, &auth, "alice", id, None, "late".into()).await
    });
    let pool = e.pool.clone();
    let grant_fga = e.fga.clone();
    let grant = tokio::spawn(async move {
        spaces::grant(&pool, &grant_fga, None, "alice", id, Role::Analyst, "alice").await
    });
    let pool = e.pool.clone();
    let import_fga = e.fga.clone();
    let import_directory = directory.clone();
    let import = tokio::spawn(async move {
        fred_manager::provisioning::Importer {
            pool: &pool,
            fga: &import_fga,
            directory: &import_directory,
            auth: &identity_auth,
            bearer: &token,
        }
        .run(&bundle)
        .await
    });
    tokio::time::timeout(Duration::from_secs(5), async {
        loop {
            let waiting: i64 = sqlx::query_scalar("select count(*) from pg_locks where locktype='advisory' and not granted and database=(select oid from pg_database where datname=current_database())")
                .fetch_one(&e.pool).await.unwrap();
            if waiting >= 3 { break; }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    }).await.expect("create, grant and import wait behind retirement");
    gate.release.notify_one();
    let accepted = accept.await.unwrap().unwrap();
    assert!(matches!(create.await.unwrap(), Err(AppError::Conflict(_))));
    assert!(matches!(grant.await.unwrap(), Err(AppError::Conflict(_))));
    assert_eq!(
        import
            .await
            .unwrap()
            .unwrap_err()
            .downcast_ref::<fred_manager::provisioning::Failure>()
            .unwrap()
            .status,
        axum::http::StatusCode::CONFLICT
    );
    assert!(directory.find_username("alice").await.unwrap().is_none());
    assert!(
        !e.fga
            .roles_of("alice")
            .await
            .unwrap()
            .contains(&(id, Role::Analyst))
    );
    let mut pending = tokio::task::JoinSet::new();
    let started = std::time::Instant::now();
    for _ in 0..8 {
        let pool = e.pool.clone();
        let fga = e.fga.clone();
        pending.spawn(async move { immediate().accept(&pool, &fga, "root", id).await });
    }
    while let Some(result) = pending.join_next().await {
        assert_eq!(result.unwrap().unwrap().id, accepted.id);
    }
    println!(
        "lifecycle receipt retries: actors=8 spaces=2 elapsed_ms={}",
        started.elapsed().as_millis()
    );
    // Losing platform authority while waiting for the lock invalidates acceptance.
    let mut held = e.pool.begin().await.unwrap();
    sqlx::query("select pg_advisory_xact_lock($1)")
        .bind(bootstrap::LOCK_KEY)
        .execute(&mut *held)
        .await
        .unwrap();
    let pool = e.pool.clone();
    let auth = e.fga.clone();
    let id = org.id;
    let pending = tokio::spawn(async move { immediate().accept(&pool, &auth, "root", id).await });
    let mut guard = e.fga.guard(&[Scope::Platform]).await.unwrap();
    e.fga
        .write_platform(
            &mut guard,
            "root",
            fred_manager::roles::PlatformRole::PlatformOwner,
            false,
        )
        .await
        .unwrap();
    held.commit().await.unwrap();
    assert!(matches!(pending.await.unwrap(), Err(AppError::Forbidden)));
}

// Proves: I24, I4, I8
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn lifecycle_blocked_scope_is_visible_and_does_not_starve_candidates() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let (org, team) = org_and_team(&e).await;
    let sibling = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Team,
        org.id,
        "Other".into(),
        "alice",
    )
    .await
    .unwrap();
    let l = immediate();
    let first = l.accept(&e.pool, &e.fga, "root", team.id).await.unwrap();
    let second = l.accept(&e.pool, &e.fga, "root", sibling.id).await.unwrap();
    let doc = Document {
        id: Uuid::new_v4(),
        space_id: team.id,
        folder_id: None,
        name: "unexpected".into(),
        mime: "text/plain".into(),
        size: 0,
        sha256: "a".repeat(64),
        created_by: "fixture".into(),
        created_at: chrono::Utc::now(),
    };
    crate::environment::insert_document(&e.pool, &doc)
        .await
        .unwrap();
    assert_eq!(cleanup::candidates(&e.pool, 1).await.unwrap(), [first.id]);
    cleanup::batch(&e.pool, &e.fga, first.id).await.unwrap();
    let blocked = store::status(&e.pool, &e.fga, "root", first.id)
        .await
        .unwrap();
    assert_eq!(blocked.status, Status::Blocked);
    assert_eq!(blocked.error_code.as_deref(), Some("unsupported_documents"));
    assert_eq!(cleanup::candidates(&e.pool, 1).await.unwrap(), [second.id]);
    drain(&e, second.id).await;
    sqlx::query("delete from document where id=$1")
        .bind(doc.id)
        .execute(&e.pool)
        .await
        .unwrap();
    drain(&e, first.id).await;
}

// Proves: I24, I2
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn lifecycle_migration_preserves_existing_spaces_and_folders() {
    let postgres = std::env::var("FRED_MANAGER_IT_POSTGRES").unwrap();
    let admin = sqlx::PgPool::connect(&format!("{postgres}/postgres"))
        .await
        .unwrap();
    let database = format!("upgrade_{}", Uuid::new_v4().simple());
    sqlx::query(sqlx::AssertSqlSafe(format!("create database {database}")))
        .execute(&admin)
        .await
        .unwrap();
    let pool = sqlx::PgPool::connect(&format!("{postgres}/{database}"))
        .await
        .unwrap();
    let migrations = sqlx::migrate!();
    migrations.run_to(6, &pool).await.unwrap();
    assert!(db::require_initialized(&pool).await.is_err());
    let id = Uuid::new_v4();
    let folder = Uuid::new_v4();
    sqlx::query("insert into space (id,kind,name) values ($1,'organization','existing')")
        .bind(id)
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("insert into folder (id,space_id,name,path) values ($1,$2,'existing','/')")
        .bind(folder)
        .bind(id)
        .execute(&pool)
        .await
        .unwrap();
    migrations.run(&pool).await.unwrap();
    db::require_initialized(&pool).await.unwrap();
    store::require_active(&pool, id).await.unwrap();
    assert_eq!(db::space(&pool, id).await.unwrap().name, "existing");
    assert_eq!(
        sqlx::query_scalar::<_, Uuid>("select space_id from folder where id=$1")
            .bind(folder)
            .fetch_one(&pool)
            .await
            .unwrap(),
        id
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space_deletion")
            .fetch_one(&pool)
            .await
            .unwrap(),
        0
    );
}

// Proves: I24
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn lifecycle_aborted_creation_graph_does_not_block_cleanup() {
    use fred_manager::fga::{Link, Tuple};
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let (org, team) = org_and_team(&e).await;
    let ghost_team = Uuid::new_v4();
    let ghost_project = Uuid::new_v4();
    let ghost_personal = Uuid::new_v4();
    let ghost_child = Uuid::new_v4();
    let ghosts = [ghost_team, ghost_project, ghost_personal, ghost_child];
    let mut guard = e.fga.guard(&[Scope::Organization(org.id)]).await.unwrap();
    // A failed import can roll back several SQL rows after all FGA writes land.
    e.fga
        .write_created(
            &mut guard,
            &[
                Link::Parent {
                    child: ghost_team,
                    parent: org.id,
                },
                Link::Parent {
                    child: ghost_project,
                    parent: ghost_team,
                },
                Link::Organization {
                    personal: ghost_personal,
                    organization: org.id,
                },
                Link::Parent {
                    child: ghost_child,
                    parent: team.id,
                },
            ],
            &ghosts
                .iter()
                .map(|id| Tuple {
                    user: "aborted",
                    role: Role::Member,
                    space: *id,
                })
                .collect::<Vec<_>>(),
        )
        .await
        .unwrap();
    let receipt = immediate()
        .accept(&e.pool, &e.fga, "root", org.id)
        .await
        .unwrap();
    assert!(
        e.fga
            .write_created(
                &mut guard,
                &[Link::Parent {
                    child: Uuid::new_v4(),
                    parent: team.id
                }],
                &[],
            )
            .await
            .is_err()
    );
    drain(&e, receipt.id).await;
    assert_eq!(
        store::status(&e.pool, &e.fga, "root", receipt.id)
            .await
            .unwrap()
            .spaces_deleted,
        2
    );
    assert!(e.fga.roles_of("aborted").await.unwrap().is_empty());
    for id in ghosts {
        assert!(e.fga.linked_to(id, false).await.unwrap().is_empty());
        assert!(e.fga.links_of(&[id], false).await.unwrap()[0].1.is_none());
        assert!(e.fga.links_of(&[id], true).await.unwrap()[0].1.is_none());
    }
}

// Proves: I24
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn lifecycle_orphan_pages_keep_anchors_through_lost_acknowledgments() {
    use fred_manager::fga::{Link, Tuple};
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let org = spaces::create_organization(&e.pool, &e.fga, "TSN", "alice")
        .await
        .unwrap();
    let ghost = Uuid::new_v4();
    let projects: Vec<_> = (0..100).map(|_| Uuid::new_v4()).collect();
    let mut guard = e.fga.guard(&[Scope::Organization(org.id)]).await.unwrap();
    e.fga
        .write_created(
            &mut guard,
            &[Link::Parent {
                child: ghost,
                parent: org.id,
            }],
            &[],
        )
        .await
        .unwrap();
    for chunk in projects.chunks(80) {
        let links: Vec<_> = chunk
            .iter()
            .map(|id| Link::Parent {
                child: *id,
                parent: ghost,
            })
            .collect();
        e.fga.write_created(&mut guard, &links, &[]).await.unwrap();
    }
    for chunk in 0..3 {
        let users: Vec<_> = (0..80).map(|n| format!("orphan-{chunk}-{n}")).collect();
        let tuples: Vec<_> = users
            .iter()
            .map(|user| Tuple {
                user,
                role: Role::Member,
                space: projects[0],
            })
            .collect();
        e.fga.write(&mut guard, &tuples, &[]).await.unwrap();
    }
    let receipt = immediate()
        .accept(&e.pool, &e.fga, "root", org.id)
        .await
        .unwrap();
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
    {
        let mut fault = proxy.fault.lock().await;
        fault.calls.clear();
        fault.reads.clear();
    }
    let started = std::time::Instant::now();
    let mut completed = false;
    let mut lost_grant_batch = false;
    let mut lost_anchor_batch = false;
    for pass in 0..220 {
        // Lose every other FGA acknowledgment, including grant and anchor batches.
        // The following pass must rediscover work from the surviving hierarchy.
        if pass % 2 == 0 {
            let mut fault = proxy.fault.lock().await;
            fault.fail_at = fault.writes + 1;
            fault.after = true;
        }
        let result = cleanup::batch(&e.pool, &observed, receipt.id).await;
        if pass == 0 {
            let fault = proxy.fault.lock().await;
            assert_eq!(fault.calls.get("read"), Some(&13));
            assert_eq!(fault.calls.get("write"), Some(&1));
        }
        if result.is_err() {
            let fault = proxy.fault.lock().await;
            let keys = fault.written.last().unwrap()["deletes"]["tuple_keys"]
                .as_array()
                .unwrap();
            lost_grant_batch |= keys.iter().any(|k| k["relation"] == "member");
            lost_anchor_batch |= keys.iter().any(|k| k["relation"] == "parent");
        }
        if !e
            .fga
            .space_holders(projects[0], Role::Member)
            .await
            .unwrap()
            .is_empty()
        {
            assert_eq!(
                e.fga.link_of(projects[0], false).await.unwrap(),
                Some(ghost)
            );
            assert_eq!(e.fga.link_of(ghost, false).await.unwrap(), Some(org.id));
        }
        let status = store::status(&e.pool, &e.fga, "root", receipt.id)
            .await
            .unwrap();
        if status.status == Status::Completed {
            assert_eq!(status.spaces_deleted, 1);
            completed = true;
            break;
        }
    }
    assert!(completed && lost_grant_batch && lost_anchor_batch);
    assert!(
        e.fga
            .space_holders(projects[0], Role::Member)
            .await
            .unwrap()
            .is_empty()
    );
    assert!(e.fga.linked_to(ghost, false).await.unwrap().is_empty());
    assert!(e.fga.linked_to(org.id, false).await.unwrap().is_empty());
    let fault = proxy.fault.lock().await;
    for write in &fault.written {
        let count: usize = ["writes", "deletes"]
            .iter()
            .map(|k| write[k]["tuple_keys"].as_array().map_or(0, Vec::len))
            .sum();
        assert!(count <= 100);
    }
    for read in &fault.reads {
        assert!(read.get("tuple_key").is_some());
        assert_ne!(read["tuple_key"], serde_json::json!({}));
    }
    println!(
        "orphan cleanup: concurrency=1 committed_spaces=1 ghost_teams=1 ghost_projects=100 ghost_grants=240 alternating_lost_acks=true elapsed_ms={} RPCs={:?}",
        started.elapsed().as_millis(),
        fault.calls
    );
}

// Proves: I24
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn lifecycle_orphans_cannot_expand_the_committed_manifest_or_depth() {
    use fred_manager::fga::{Link, Tuple};
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let (org, team) = org_and_team(&e).await;
    let foreign = spaces::create_organization(&e.pool, &e.fga, "Other", "bob")
        .await
        .unwrap();
    let ghost = Uuid::new_v4();
    let mut guard = e.fga.guard(&[Scope::Organization(org.id)]).await.unwrap();
    e.fga
        .write_created(
            &mut guard,
            &[Link::Parent {
                child: ghost,
                parent: team.id,
            }],
            &[Tuple {
                user: "orphan",
                role: Role::Member,
                space: ghost,
            }],
        )
        .await
        .unwrap();
    let receipt = immediate()
        .accept(&e.pool, &e.fga, "root", team.id)
        .await
        .unwrap();
    // Simulate an unexpected external link added after retirement. SQL existence
    // must be checked before considering this object an abandoned creation.
    let mut guard = e.fga.guard(&[Scope::Organization(org.id)]).await.unwrap();
    let foreign_link = Link::Parent {
        child: foreign.id,
        parent: ghost,
    };
    e.fga
        .write_created(&mut guard, &[foreign_link], &[])
        .await
        .unwrap();
    cleanup::batch(&e.pool, &e.fga, receipt.id).await.unwrap();
    let blocked = store::status(&e.pool, &e.fga, "root", receipt.id)
        .await
        .unwrap();
    assert_eq!(blocked.status, Status::Blocked);
    assert_eq!(blocked.error_code.as_deref(), Some("unexpected_reference"));
    assert_eq!(
        e.fga.space_holders(foreign.id, Role::Member).await.unwrap(),
        ["bob"]
    );
    assert_eq!(
        e.fga.space_holders(ghost, Role::Member).await.unwrap(),
        ["orphan"]
    );
    assert_eq!(e.fga.link_of(foreign.id, false).await.unwrap(), Some(ghost));
    // Unsupported depth under an absent project is bounded and leaves all tuples.
    let response = reqwest::Client::new().post(format!("{}/stores/{}/write",e.openfga,e.fga.store_id())).json(&serde_json::json!({"deletes":{"tuple_keys":[{"object":format!("space:{}",foreign.id),"relation":"parent","user":format!("space:{ghost}")}]}})).send().await.unwrap();
    assert!(response.status().is_success());
    e.fga
        .write_created(
            &mut guard,
            &[Link::Parent {
                child: Uuid::new_v4(),
                parent: ghost,
            }],
            &[],
        )
        .await
        .unwrap();
    cleanup::batch(&e.pool, &e.fga, receipt.id).await.unwrap();
    let blocked = store::status(&e.pool, &e.fga, "root", receipt.id)
        .await
        .unwrap();
    assert_eq!(blocked.status, Status::Blocked);
    assert_eq!(blocked.error_code.as_deref(), Some("unexpected_hierarchy"));
    assert_eq!(
        e.fga.space_holders(ghost, Role::Member).await.unwrap(),
        ["orphan"]
    );
    // Malformed placement spanning several pages must be rejected using only
    // the first page, rather than scanning arbitrary tuple volume under locks.
    for _ in 0..2 {
        let links: Vec<_> = (0..80)
            .map(|_| Link::Parent {
                child: ghost,
                parent: Uuid::new_v4(),
            })
            .collect();
        e.fga.write_created(&mut guard, &links, &[]).await.unwrap();
    }
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
    proxy.fault.lock().await.calls.clear();
    cleanup::batch(&e.pool, &observed, receipt.id)
        .await
        .unwrap();
    let fault = proxy.fault.lock().await;
    assert_eq!(fault.calls.get("read"), Some(&6));
    assert_eq!(fault.calls.get("write"), None);
    let blocked = store::status(&e.pool, &e.fga, "root", receipt.id)
        .await
        .unwrap();
    assert_eq!(blocked.error_code.as_deref(), Some("unexpected_hierarchy"));
    assert_eq!(
        e.fga.space_holders(ghost, Role::Member).await.unwrap(),
        ["orphan"]
    );
}
