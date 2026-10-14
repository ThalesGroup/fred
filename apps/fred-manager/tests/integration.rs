// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! Regression tests against a real Postgres and a real OpenFGA, both throwaway
//! containers started by `make test-integration`. Each test gets its own database and
//! its own OpenFGA store.

use std::time::Duration;

use fred_manager::{
    bootstrap, db,
    domain::{self, Document, Folder, Permission, Role, Space, SpaceKind},
    error::AppError,
    fga::Fga,
    spaces,
};
use sqlx::{AssertSqlSafe, PgPool};
use uuid::Uuid;

const IGNORE: &str = "needs Postgres and OpenFGA: make test-integration";

struct Env {
    pool: PgPool,
    fga: Fga,
    openfga: String,
    store: String,
}

async fn env() -> Env {
    let postgres = std::env::var("FRED_MANAGER_IT_POSTGRES").expect(IGNORE);
    let openfga = std::env::var("FRED_MANAGER_IT_OPENFGA").expect(IGNORE);
    let name = format!("t_{}", Uuid::new_v4().simple());
    let admin = PgPool::connect(&format!("{postgres}/postgres"))
        .await
        .unwrap();
    sqlx::query(AssertSqlSafe(format!("create database {name}")))
        .execute(&admin)
        .await
        .unwrap();
    let pool = PgPool::connect(&format!("{postgres}/{name}"))
        .await
        .unwrap();
    sqlx::migrate!().run(&pool).await.unwrap();
    let fga = Fga::connect(
        &openfga,
        &name,
        true,
        true,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap();
    Env {
        pool,
        fga,
        openfga,
        store: name,
    }
}

/// Removes a tuple behind fred-manager's back, as another admin or an operator would.
async fn delete_tuple(e: &Env, user: &str, relation: &str, object: &str) {
    let http = reqwest::Client::new();
    let stores: serde_json::Value = http
        .get(format!("{}/stores?name={}", e.openfga, e.store))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    let id = stores["stores"][0]["id"].as_str().unwrap();
    let body = serde_json::json!({ "deletes": { "tuple_keys": [
        { "user": format!("user:{user}"), "relation": relation, "object": object }
    ] } });
    let status = http
        .post(format!("{}/stores/{id}/write", e.openfga))
        .json(&body)
        .send()
        .await
        .unwrap()
        .status();
    assert!(status.is_success(), "delete tuple: {status}");
}

/// Holds the advisory lock fred-manager takes for `org`, until the transaction ends.
async fn hold_organization_lock(e: &Env, org: Uuid) -> sqlx::Transaction<'static, sqlx::Postgres> {
    let key = i64::from_be_bytes(org.as_bytes()[..8].try_into().unwrap());
    let mut tx = e.pool.begin().await.unwrap();
    sqlx::query("select pg_advisory_xact_lock($1)")
        .bind(key)
        .execute(&mut *tx)
        .await
        .unwrap();
    tx
}

/// Organization TSN administered by alice, team BID under it, alice member of both.
async fn org_and_team(e: &Env) -> (Space, Space) {
    let org = spaces::create_organization(&e.pool, &e.fga, "TSN", "alice")
        .await
        .unwrap();
    let team = spaces::create_space(
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
    spaces::grant(&e.pool, &e.fga, "alice", team.id, Role::Member, "alice")
        .await
        .unwrap();
    (org, team)
}

async fn grant(e: &Env, space: Uuid, role: Role, user: &str) {
    spaces::grant(&e.pool, &e.fga, "alice", space, role, user)
        .await
        .unwrap();
}

async fn reads(e: &Env, user: &str, space: Uuid) -> bool {
    e.fga.check(user, Permission::Read, space).await.unwrap()
}

// Proves: I4
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn concurrent_revocations_keep_parent_access() {
    let e = env().await;
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
    grant(&e, org.id, Role::Member, "bob").await;
    for round in 0..10 {
        grant(&e, team.id, Role::Member, "bob").await;
        grant(&e, team.id, Role::Editor, "bob").await;
        grant(&e, project.id, Role::Member, "bob").await;
        let (a, b) = tokio::join!(
            spaces::revoke(&e.pool, &e.fga, "alice", team.id, Role::Member, "bob"),
            spaces::revoke(&e.pool, &e.fga, "alice", team.id, Role::Editor, "bob"),
        );
        assert!(
            a.is_ok() != b.is_ok(),
            "round {round}: exactly one revocation passes"
        );
        assert!(
            reads(&e, "bob", team.id).await,
            "round {round}: bob still reads the team"
        );
    }
}

// Proves: I4
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn concurrent_grant_and_revoke_keep_the_invariant() {
    let e = env().await;
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
    grant(&e, org.id, Role::Member, "bob").await;
    for round in 0..10 {
        grant(&e, team.id, Role::Member, "bob").await;
        let _ = tokio::join!(
            spaces::grant(&e.pool, &e.fga, "alice", project.id, Role::Member, "bob"),
            spaces::revoke(&e.pool, &e.fga, "alice", team.id, Role::Member, "bob"),
        );
        if reads(&e, "bob", project.id).await {
            assert!(
                reads(&e, "bob", team.id).await,
                "round {round}: project role without team access"
            );
        }
        let _ = spaces::revoke(&e.pool, &e.fga, "alice", project.id, Role::Member, "bob").await;
    }
}

// Proves: I5
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn a_revoked_admin_cannot_finish_a_waiting_request() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Admin, "bob").await;

    let held = hold_organization_lock(&e, org.id).await;
    let pending = {
        let (pool, fga) = (e.pool.clone(), e.fga.clone());
        tokio::spawn(
            async move { spaces::grant(&pool, &fga, "bob", team.id, Role::Admin, "bob").await },
        )
    };
    // Let bob's request reach the lock, then revoke him while it waits.
    tokio::time::sleep(Duration::from_millis(300)).await;
    delete_tuple(&e, "bob", "admin", &format!("space:{}", team.id)).await;
    held.commit().await.unwrap();

    assert!(matches!(pending.await.unwrap(), Err(AppError::Forbidden)));
    assert!(
        !e.fga
            .check("bob", Permission::Manage, team.id)
            .await
            .unwrap()
    );
}

// Proves: I6
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn a_member_with_a_personal_space_can_leave_the_organization() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "bob").await;
    let personal = spaces::create_personal_space(&e.pool, &e.fga, "bob", org.id)
        .await
        .unwrap();

    let blocked = spaces::revoke(&e.pool, &e.fga, "alice", org.id, Role::Member, "bob").await;
    assert!(matches!(blocked, Err(AppError::Conflict(_))));
    let widened = spaces::grant(&e.pool, &e.fga, "alice", personal.id, Role::Member, "carol").await;
    assert!(matches!(widened, Err(AppError::Conflict(_))));
    let by_owner = spaces::revoke(&e.pool, &e.fga, "bob", personal.id, Role::Editor, "bob").await;
    assert!(matches!(by_owner, Err(AppError::Forbidden)));

    for role in [Role::Editor, Role::Member] {
        spaces::revoke(&e.pool, &e.fga, "alice", personal.id, role, "bob")
            .await
            .unwrap();
    }
    spaces::revoke(&e.pool, &e.fga, "alice", org.id, Role::Member, "bob")
        .await
        .unwrap();
    assert!(!reads(&e, "bob", org.id).await);
    assert!(!reads(&e, "bob", personal.id).await);
}

// Proves: I9
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn bootstrap_promotes_one_person_once() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "alice")
        .await
        .unwrap();
    assert!(e.fga.is_platform_admin("alice").await.unwrap());
    for user in ["bob", "alice"] {
        let again = bootstrap::grant_root(&e.pool, &e.fga, user).await;
        assert!(
            matches!(again, Err(AppError::Conflict(_))),
            "{user} must get 409"
        );
    }
    assert!(!e.fga.is_platform_admin("bob").await.unwrap());
}

// Proves: I9
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn a_finished_bootstrap_stays_closed_after_its_admin_is_removed() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "alice")
        .await
        .unwrap();
    delete_tuple(&e, "alice", "admin", "platform:root").await;
    let again = bootstrap::grant_root(&e.pool, &e.fga, "alice").await;
    assert!(matches!(again, Err(AppError::Conflict(_))));
    assert!(!e.fga.is_platform_admin("alice").await.unwrap());
}

// Proves: I9
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn concurrent_retries_finish_a_bootstrap_once() {
    let e = env().await;
    // Both calls wait on the bootstrap lock, so both pass the reservation step.
    let mut held = e.pool.begin().await.unwrap();
    sqlx::query("select pg_advisory_xact_lock($1)")
        .bind(bootstrap::LOCK_KEY)
        .execute(&mut *held)
        .await
        .unwrap();
    let call = || {
        let (pool, fga) = (e.pool.clone(), e.fga.clone());
        tokio::spawn(async move { bootstrap::grant_root(&pool, &fga, "alice").await })
    };
    let (first, second) = (call(), call());
    tokio::time::sleep(Duration::from_millis(300)).await;
    held.commit().await.unwrap();

    let results = [first.await.unwrap(), second.await.unwrap()];
    assert_eq!(
        results.iter().filter(|r| r.is_ok()).count(),
        1,
        "{results:?}"
    );
    assert!(
        results
            .iter()
            .any(|r| matches!(r, Err(AppError::Conflict(_))))
    );
}

// Proves: I9
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn an_interrupted_bootstrap_is_finished_by_its_caller_only() {
    let e = env().await;
    // The marker committed, then the OpenFGA write never happened.
    sqlx::query("insert into platform_bootstrap (completed_by) values ('alice')")
        .execute(&e.pool)
        .await
        .unwrap();
    let other = bootstrap::grant_root(&e.pool, &e.fga, "bob").await;
    assert!(matches!(other, Err(AppError::Conflict(_))));
    bootstrap::grant_root(&e.pool, &e.fga, "alice")
        .await
        .unwrap();
    assert!(e.fga.is_platform_admin("alice").await.unwrap());
    assert!(!e.fga.is_platform_admin("bob").await.unwrap());
}

fn document(space: Uuid, folder: Option<Uuid>, name: &str) -> Document {
    Document {
        id: Uuid::new_v4(),
        space_id: space,
        folder_id: folder,
        name: name.into(),
        mime: "text/plain".into(),
        size: 1,
        sha256: "x".into(),
        created_by: "alice".into(),
    }
}

// Proves: I2, I3
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn placement_is_immutable_and_folders_stay_in_their_space() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let id = Uuid::new_v4();
    let folder = Folder {
        id,
        space_id: team.id,
        parent_id: None,
        name: "Appels d'offres".into(),
        path: domain::folder_path(None, id),
    };
    db::insert_folder(&e.pool, &folder).await.unwrap();
    let doc = document(team.id, Some(folder.id), "cdc.pdf");
    db::insert_document(&e.pool, &doc).await.unwrap();

    let moves = [
        format!("update space set parent_id = null where id = '{}'", team.id),
        format!(
            "update folder set space_id = '{}' where id = '{}'",
            org.id, folder.id
        ),
        format!(
            "update document set folder_id = null where id = '{}'",
            doc.id
        ),
    ];
    for statement in moves {
        let refused = sqlx::query(AssertSqlSafe(statement.clone()))
            .execute(&e.pool)
            .await;
        assert!(refused.is_err(), "{statement} must be refused");
    }
    let elsewhere = document(org.id, Some(folder.id), "wrong-space.pdf");
    assert!(db::insert_document(&e.pool, &elsewhere).await.is_err());
    db::rename_document(&e.pool, doc.id, "cdc-v2.pdf")
        .await
        .unwrap();
    db::rename_folder(&e.pool, folder.id, "AO").await.unwrap();
}

// Proves: I8
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn admin_roles_grant_no_content_access() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "carol").await;
    let team = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Team,
        org.id,
        "OPS".into(),
        "carol",
    )
    .await
    .unwrap();
    assert!(
        e.fga
            .check("carol", Permission::Manage, team.id)
            .await
            .unwrap()
    );
    assert!(
        !reads(&e, "carol", team.id).await,
        "a space admin is not a reader"
    );
    bootstrap::grant_root(&e.pool, &e.fga, "dave")
        .await
        .unwrap();
    assert!(
        !reads(&e, "dave", org.id).await,
        "a platform admin is not a reader"
    );
}

// Proves: I12
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn pagination_survives_deleting_the_cursor_row() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let mut docs = Vec::new();
    for name in ["a", "b", "c"] {
        let d = document(org.id, None, name);
        db::insert_document(&e.pool, &d).await.unwrap();
        docs.push(d);
    }
    let names = |page: Vec<Document>| page.into_iter().map(|d| d.name).collect::<Vec<_>>();
    let first = db::documents(&e.pool, org.id, None, None, 1).await.unwrap();
    assert_eq!(names(first), ["a"]);
    db::delete_document(&e.pool, docs[0].id).await.unwrap();
    let next = db::documents(&e.pool, org.id, None, Some(("a", docs[0].id)), 2)
        .await
        .unwrap();
    assert_eq!(names(next), ["b", "c"]);
    let end = db::documents(&e.pool, org.id, None, Some(("c", docs[2].id)), 2)
        .await
        .unwrap();
    assert!(end.is_empty());
}

// Proves: I8
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn complete_role_permission_matrix_and_space_isolation() {
    use fred_manager::{
        fga::Tuple,
        roles::{PlatformPermission as PP, PlatformRole as P, SpacePermission as SP},
    };
    let e = env().await;
    let space = Uuid::new_v4();
    let other = Uuid::new_v4();
    // Enumerate every subset: cumulative grants must equal the union of their individual rights.
    let roles = [Role::Member, Role::Editor, Role::Admin, Role::Analyst];
    for mask in 0..16 {
        let user = format!("space-{mask}");
        let held: Vec<_> = roles
            .iter()
            .enumerate()
            .filter(|(i, _)| mask & (1 << i) != 0)
            .map(|(_, r)| *r)
            .collect();
        if !held.is_empty() {
            e.fga
                .write(
                    &held
                        .iter()
                        .map(|r| Tuple {
                            user: &user,
                            role: *r,
                            space,
                        })
                        .collect::<Vec<_>>(),
                    &[],
                )
                .await
                .unwrap();
        }
        for permission in SP::ALL {
            let expected = held.iter().any(|role| match permission {
                SP::Read => matches!(role, Role::Member | Role::Editor | Role::Analyst),
                SP::Write => *role == Role::Editor,
                SP::Manage => *role == Role::Admin,
                SP::RunEvaluations | SP::ManageEvaluationCorpus => {
                    matches!(role, Role::Admin | Role::Analyst)
                }
                SP::ReadConversationsForEvaluation => *role == Role::Analyst,
            });
            assert_eq!(
                e.fga.check_space(&user, permission, space).await.unwrap(),
                expected,
                "{mask} {permission:?}"
            );
            assert!(!e.fga.check_space(&user, permission, other).await.unwrap());
        }
    }
    for mask in 0..32 {
        let user = format!("platform-{mask}");
        let held: Vec<_> = P::ALL
            .iter()
            .enumerate()
            .filter(|(i, _)| mask & (1 << i) != 0)
            .map(|(_, r)| *r)
            .collect();
        for role in &held {
            e.fga.write_platform(&user, *role, true).await.unwrap();
        }
        for permission in PP::ALL {
            let expected = held.iter().any(|role| {
                *role == P::PlatformAdmin
                    || matches!(
                        (role, permission),
                        (P::PlatformObserver, PP::ObservePlatform)
                            | (P::TeamManager, PP::CreateTeam | PP::ListAllTeams)
                            | (P::FeatureManager, PP::ManageCapabilities | PP::ListAllTeams)
                            | (P::PromptEditor, PP::EditPlatformPrompt)
                    )
            });
            assert_eq!(
                e.fga.check_platform(&user, permission).await.unwrap(),
                expected,
                "{mask} {permission:?}"
            );
        }
        for permission in SP::ALL {
            assert!(!e.fga.check_space(&user, permission, space).await.unwrap());
        }
        let effective = e.fga.effective_platform_roles(&user).await.unwrap();
        assert_eq!(
            effective,
            if held.contains(&P::PlatformAdmin) {
                P::ALL.to_vec()
            } else {
                held
            }
        );
    }
}

// Proves: I4, I6
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn analyst_membership_is_content_and_personal_roles_remain_fixed() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Analyst, "analyst").await;
    grant(&e, team.id, Role::Admin, "analyst").await;
    assert!(matches!(
        spaces::revoke(&e.pool, &e.fga, "alice", org.id, Role::Analyst, "analyst").await,
        Err(AppError::Conflict(_))
    ));
    grant(&e, org.id, Role::Member, "analyst").await;
    spaces::revoke(&e.pool, &e.fga, "alice", org.id, Role::Analyst, "analyst")
        .await
        .unwrap();
    let personal = spaces::create_personal_space(&e.pool, &e.fga, "analyst", org.id)
        .await
        .unwrap();
    assert!(matches!(
        spaces::grant(
            &e.pool,
            &e.fga,
            "alice",
            personal.id,
            Role::Analyst,
            "alice"
        )
        .await,
        Err(AppError::Conflict(_))
    ));
    spaces::revoke(&e.pool, &e.fga, "alice", team.id, Role::Admin, "analyst")
        .await
        .unwrap();
    assert!(
        !reads(&e, "analyst", team.id).await,
        "revoking governance must not create content rights"
    );
}

// Proves: I14
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn concurrent_admin_revocations_leave_one_admin_at_every_level() {
    let e = env().await;
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
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Member, "bob").await;
    for space in [project.id, team.id, org.id] {
        grant(&e, space, Role::Admin, "bob").await;
        let (a, b) = tokio::join!(
            spaces::revoke(&e.pool, &e.fga, "alice", space, Role::Admin, "alice"),
            spaces::revoke(&e.pool, &e.fga, "bob", space, Role::Admin, "bob"),
        );
        assert_eq!(usize::from(a.is_ok()) + usize::from(b.is_ok()), 1);
        assert_eq!(e.fga.space_admins(space).await.unwrap().len(), 1);
    }
}

// Proves: I8
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn delegated_creation_is_team_only_and_never_grants_caller_membership() {
    use fred_manager::roles::PlatformRole;
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    e.fga
        .write_platform("manager", PlatformRole::TeamManager, true)
        .await
        .unwrap();
    let created = spaces::create_space(
        &e.pool,
        &e.fga,
        "manager",
        SpaceKind::Team,
        org.id,
        "Delegated".into(),
        "alice",
    )
    .await
    .unwrap();
    assert!(e.fga.roles_of("manager").await.unwrap().is_empty());
    assert!(!reads(&e, "alice", created.id).await);
    assert!(matches!(
        spaces::create_space(
            &e.pool,
            &e.fga,
            "manager",
            SpaceKind::Project,
            team.id,
            "Denied".into(),
            "alice"
        )
        .await,
        Err(AppError::Forbidden)
    ));
    assert!(matches!(
        spaces::grant(
            &e.pool,
            &e.fga,
            "manager",
            created.id,
            Role::Member,
            "manager"
        )
        .await,
        Err(AppError::Forbidden)
    ));
    assert!(matches!(
        spaces::create_space(
            &e.pool,
            &e.fga,
            "manager",
            SpaceKind::Team,
            org.id,
            "No parent".into(),
            "unknown"
        )
        .await,
        Err(AppError::Conflict(_))
    ));
}

mod support;

// Proves: I15
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn platform_roles_enforce_root_identity_and_direct_grant_semantics() {
    use fred_manager::{platform, roles::PlatformRole as P};
    let e = env().await;
    let server = support::IdentityServer::start().await;
    for user in ["root", "admin", "observer"] {
        server.users.lock().await.insert(user.into(), user.into());
    }
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    platform::grant(
        &e.pool,
        &e.fga,
        Some(&directory),
        "root",
        "admin",
        P::PlatformAdmin,
    )
    .await
    .unwrap();
    assert!(matches!(
        platform::grant(
            &e.pool,
            &e.fga,
            Some(&directory),
            "admin",
            "observer",
            P::PlatformAdmin
        )
        .await,
        Err(AppError::Forbidden)
    ));
    for target in ["missing", "unavailable"] {
        assert!(
            platform::grant(
                &e.pool,
                &e.fga,
                Some(&directory),
                "root",
                target,
                P::PlatformObserver
            )
            .await
            .is_err()
        );
        assert!(
            e.fga
                .effective_platform_roles(target)
                .await
                .unwrap()
                .is_empty()
        );
    }
    assert!(matches!(
        platform::revoke(&e.pool, &e.fga, "root", "root", P::PlatformAdmin).await,
        Err(AppError::Forbidden)
    ));
    assert!(matches!(
        platform::revoke(&e.pool, &e.fga, "root", "admin", P::PlatformObserver).await,
        Err(AppError::NotFound)
    ));
    platform::grant(
        &e.pool,
        &e.fga,
        Some(&directory),
        "admin",
        "observer",
        P::PlatformObserver,
    )
    .await
    .unwrap();
    assert!(matches!(
        platform::grant(
            &e.pool,
            &e.fga,
            Some(&directory),
            "observer",
            "observer",
            P::PromptEditor
        )
        .await,
        Err(AppError::Forbidden)
    ));
    server.users.lock().await.remove("observer");
    platform::revoke(&e.pool, &e.fga, "admin", "observer", P::PlatformObserver)
        .await
        .unwrap();
    assert_eq!(platform::list(&e.fga, "root").await.unwrap().len(), 2);
}

async fn wait_for_advisory_waiter(pool: &PgPool) {
    tokio::time::timeout(Duration::from_secs(5), async {
        loop {
            let waiting: i64 = sqlx::query_scalar("select count(*) from pg_locks where locktype = 'advisory' and not granted and database = (select oid from pg_database where datname = current_database())")
                .fetch_one(pool).await.unwrap();
            if waiting > 0 { break; }
            tokio::task::yield_now().await;
        }
    }).await.expect("mutation must reach its lock before revocation");
}

// Proves: I5
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn revoked_platform_actor_cannot_complete_waiting_role_or_team_creation() {
    use fred_manager::{platform, roles::PlatformRole as P};
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    for create_team in [false, true] {
        e.fga
            .write_platform("delegate", P::PlatformAdmin, true)
            .await
            .unwrap();
        let mut tx = e.pool.begin().await.unwrap();
        sqlx::query("select pg_advisory_xact_lock($1)")
            .bind(bootstrap::LOCK_KEY)
            .execute(&mut *tx)
            .await
            .unwrap();
        let (pool, fga) = (e.pool.clone(), e.fga.clone());
        let pending = tokio::spawn(async move {
            if create_team {
                spaces::create_space(
                    &pool,
                    &fga,
                    "delegate",
                    SpaceKind::Team,
                    org.id,
                    "waiting".into(),
                    "alice",
                )
                .await
                .map(|_| ())
            } else {
                platform::grant(&pool, &fga, None, "delegate", "target", P::PromptEditor).await
            }
        });
        wait_for_advisory_waiter(&e.pool).await;
        e.fga
            .write_platform("delegate", P::PlatformAdmin, false)
            .await
            .unwrap();
        tx.commit().await.unwrap();
        assert!(matches!(pending.await.unwrap(), Err(AppError::Forbidden)));
    }
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn governance_http_reports_effective_roles_and_checks_only_its_caller() {
    use axum::{
        body::{Body, to_bytes},
        http::{Request, StatusCode},
    };
    use fred_manager::{
        api::{GovernanceState, governance_router},
        roles::PlatformRole as P,
    };
    use std::sync::Arc;
    use tower::ServiceExt;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    server
        .users
        .lock()
        .await
        .insert("observer".into(), "observer".into());
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let app = governance_router(GovernanceState {
        auth: Arc::new(server.auth().await),
        pool: e.pool.clone(),
        fga: e.fga.clone(),
        directory: Some(server.directory()),
    });
    let request = |method: &str, path: &str, actor: Option<&str>, body: &str| {
        let mut builder = Request::builder()
            .method(method)
            .uri(path)
            .header("content-type", "application/json");
        if let Some(actor) = actor {
            builder = builder.header("authorization", format!("Bearer {}", server.token(actor)));
        }
        builder.body(Body::from(body.to_owned())).unwrap()
    };
    let response = app
        .clone()
        .oneshot(request("GET", "/me", Some("root"), ""))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let me: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body(), 65536).await.unwrap()).unwrap();
    assert_eq!(me["platform_roles"], serde_json::to_value(P::ALL).unwrap());
    assert_eq!(
        app.clone()
            .oneshot(request("GET", "/me", None, ""))
            .await
            .unwrap()
            .status(),
        StatusCode::UNAUTHORIZED
    );
    assert_eq!(
        app.clone()
            .oneshot(request(
                "PUT",
                "/users/observer/platform-roles/platform_observer",
                Some("root"),
                ""
            ))
            .await
            .unwrap()
            .status(),
        StatusCode::NO_CONTENT
    );
    assert_eq!(
        app.clone()
            .oneshot(request("GET", "/admin/teams", Some("observer"), ""))
            .await
            .unwrap()
            .status(),
        StatusCode::FORBIDDEN
    );
    let response = app
        .clone()
        .oneshot(request(
            "POST",
            "/authorize/platform",
            Some("observer"),
            r#"{"permission":"manage_platform","user":"root"}"#,
        ))
        .await
        .unwrap();
    let result: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body(), 65536).await.unwrap()).unwrap();
    assert_eq!(result["allowed"], false);
    let direct = app
        .oneshot(request("GET", "/users/platform-roles", Some("root"), ""))
        .await
        .unwrap();
    let direct: serde_json::Value =
        serde_json::from_slice(&to_bytes(direct.into_body(), 65536).await.unwrap()).unwrap();
    assert_eq!(direct.as_array().unwrap().len(), 2);
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn directory_grants_refuse_non_subject_mapping_and_other_realms() {
    use axum::{
        body::Body,
        http::{Request, StatusCode},
    };
    use fred_manager::{
        api::{GovernanceState, governance_router},
        auth::Authenticator,
        config::Configuration,
        roles::PlatformRole,
    };
    use std::sync::Arc;
    use tower::ServiceExt;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let other = support::IdentityServer::start().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    server
        .users
        .lock()
        .await
        .insert("bob-sub".into(), "bob".into());
    for other_realm in [false, true] {
        let mut config: Configuration =
            serde_yaml_ng::from_str(include_str!("../config/configuration.yaml")).unwrap();
        config.security.user.realm_url = server.realm.clone();
        config.security.m2m = None;
        if !other_realm {
            config.security.user.claims.uid = Some("preferred_username".into());
        }
        let app = governance_router(GovernanceState {
            auth: Arc::new(
                Authenticator::start(config.security().unwrap())
                    .await
                    .unwrap(),
            ),
            pool: e.pool.clone(),
            fga: e.fga.clone(),
            directory: Some(if other_realm {
                other.directory()
            } else {
                server.directory()
            }),
        });
        let response = app
            .oneshot(
                Request::builder()
                    .method("PUT")
                    .uri("/users/bob-sub/platform-roles/platform_observer")
                    .header("authorization", format!("Bearer {}", server.token("root")))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert!(
            !e.fga
                .platform_grants()
                .await
                .unwrap()
                .contains(&("bob-sub".into(), PlatformRole::PlatformObserver))
        );
    }
}

#[derive(Clone, Default)]
struct AuditCapture(std::sync::Arc<std::sync::Mutex<Vec<serde_json::Value>>>);
impl<S: tracing::Subscriber> tracing_subscriber::Layer<S> for AuditCapture {
    fn on_event(&self, event: &tracing::Event<'_>, _: tracing_subscriber::layer::Context<'_, S>) {
        if event.metadata().target() != "fred.security.audit" {
            return;
        }
        struct Fields(serde_json::Map<String, serde_json::Value>);
        impl tracing::field::Visit for Fields {
            fn record_str(&mut self, field: &tracing::field::Field, value: &str) {
                self.0.insert(field.name().into(), value.into());
            }
            fn record_debug(&mut self, field: &tracing::field::Field, value: &dyn std::fmt::Debug) {
                self.0
                    .insert(field.name().into(), format!("{value:?}").into());
            }
        }
        let mut fields = Fields(serde_json::Map::new());
        event.record(&mut fields);
        self.0.lock().unwrap().push(fields.0.into());
    }
}

// Proves: I16
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn durable_grants_are_audited_even_when_sql_commit_fails() {
    use fred_manager::roles::PlatformRole;
    use tracing_subscriber::prelude::*;
    let e = env().await;
    let capture = AuditCapture::default();
    let subscriber = tracing_subscriber::registry().with(capture.clone());
    tracing::subscriber::set_global_default(subscriber).unwrap();
    let root = format!("audit-root-{}", Uuid::new_v4());
    {
        let (org, _) = org_and_team(&e).await;
        e.fga
            .write_platform("delegate", PlatformRole::TeamManager, true)
            .await
            .unwrap();
        let team = spaces::create_space(
            &e.pool,
            &e.fga,
            "delegate",
            SpaceKind::Team,
            org.id,
            "audit-team".into(),
            "alice",
        )
        .await
        .unwrap();
        assert!(
            capture
                .0
                .lock()
                .unwrap()
                .iter()
                .any(|e| e["actor_uid"] == "delegate"
                    && e["relation"] == "admin"
                    && e["resource"] == format!("space:{}", team.id))
        );
        sqlx::raw_sql("create function reject_completion() returns trigger language plpgsql as $$ begin raise exception 'forced deferred failure'; end $$; create constraint trigger reject_completion after update on platform_bootstrap deferrable initially deferred for each row execute function reject_completion();").execute(&e.pool).await.unwrap();
        assert!(bootstrap::grant_root(&e.pool, &e.fga, &root).await.is_err());
        assert!(
            e.fga.is_platform_admin(&root).await.unwrap(),
            "FGA grant survives failed SQL completion"
        );
    }
    let events = capture.0.lock().unwrap();
    assert_eq!(
        events
            .iter()
            .filter(|e| e["actor_uid"] == root
                && e["subject"] == format!("user:{root}")
                && e["resource"] == "platform:root"
                && e["audit_event"] == "authz.relation.granted")
            .count(),
        1
    );
}

fn provisioning_bundle() -> fred_manager::provisioning::Bundle {
    fred_manager::provisioning::Bundle::parse(br#"{
      "organization":{"name":"Provisioned","admins":["alice"]},
      "users":[
        {"username":"alice","password":"private-password","first_name":"Alice","last_name":"Example","teams":["BID"],"team_roles":{"team_admin":["BID"]}},
        {"username":"bob","password":"private-password","team_roles":{"team_member":["BID"],"team_editor":["BID"],"team_analyst":["BID"]},"platform_roles":["observer","team_manager","feature_manager","prompt_editor"]},
        {"username":"platform-only","password":"private-password","platform_roles":["admin"]}
      ]}"#).unwrap()
}

// Proves: I4, I8, I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn provisioning_replays_every_role_without_updating_identities_or_implicit_content() {
    use fred_manager::{provisioning::Importer, roles::PlatformRole};
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let auth = server.auth().await;
    let directory = server.directory();
    let token = server.token("root");
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    db::require_initialized(&e.pool).await.unwrap();
    let fga = e.fga.clone().require_compatible_model().await.unwrap();
    let bundle = provisioning_bundle();
    let importer = Importer {
        pool: &e.pool,
        fga: &fga,
        directory: &directory,
        auth: &auth,
        bearer: &token,
    };
    let first = importer.run(&bundle).await.unwrap();
    assert_eq!(first.identities_created, 3);
    let org = db::named_space(&e.pool, None, "Provisioned")
        .await
        .unwrap()
        .unwrap();
    let team = db::named_space(&e.pool, Some(org.id), "BID")
        .await
        .unwrap()
        .unwrap();
    let alice = directory.find_username("alice").await.unwrap().unwrap().id;
    let bob = directory.find_username("bob").await.unwrap().unwrap().id;
    let platform = directory
        .find_username("platform-only")
        .await
        .unwrap()
        .unwrap()
        .id;
    assert!(fga.roles_of("root").await.unwrap().is_empty());
    assert!(fga.roles_of(&platform).await.unwrap().is_empty());
    assert!(!fga.check(&alice, Permission::Read, team.id).await.unwrap());
    assert!(
        fga.roles_of(&alice)
            .await
            .unwrap()
            .contains(&(org.id, Role::Member))
    );
    for role in [Role::Member, Role::Editor, Role::Analyst] {
        assert!(fga.roles_of(&bob).await.unwrap().contains(&(team.id, role)));
    }
    for role in PlatformRole::ALL {
        assert!(fga.platform_grants().await.unwrap().contains(&(
            if role == PlatformRole::PlatformAdmin {
                platform.clone()
            } else {
                bob.clone()
            },
            role
        )));
    }
    // Undeclared roles survive; missing requested grants are repaired on committed IDs.
    fga.write(
        &[fred_manager::fga::Tuple {
            user: "unrelated",
            role: Role::Member,
            space: org.id,
        }],
        &[],
    )
    .await
    .unwrap();
    delete_tuple(&e, &bob, "analyst", &format!("space:{}", team.id)).await;
    let replay = importer.run(&bundle).await.unwrap();
    assert_eq!(replay.identities_created, 0);
    assert_eq!(server.control.lock().await.created.len(), 3);
    let body = server.control.lock().await.created[0].clone();
    assert_eq!(body["email"], "alice@example.com");
    assert_eq!(body["enabled"], true);
    assert_eq!(body["credentials"][0]["temporary"], false);
    assert_eq!(
        db::named_space(&e.pool, Some(org.id), "BID")
            .await
            .unwrap()
            .unwrap()
            .id,
        team.id
    );
    assert!(
        fga.roles_of(&bob)
            .await
            .unwrap()
            .contains(&(team.id, Role::Analyst))
    );
    assert!(
        fga.roles_of("unrelated")
            .await
            .unwrap()
            .contains(&(org.id, Role::Member))
    );
}

// Proves: I15, I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn provisioning_preflight_failures_have_no_identity_space_or_role_writes() {
    use fred_manager::{
        provisioning::{Bundle, Importer},
        roles::PlatformRole,
    };
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let auth = server.auth().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    e.fga
        .write_platform("delegate", PlatformRole::PlatformAdmin, true)
        .await
        .unwrap();
    e.fga
        .write_platform("observer", PlatformRole::PlatformObserver, true)
        .await
        .unwrap();
    let before = e.fga.platform_grants().await.unwrap();
    for token in [
        "invalid".into(),
        server.token("observer"),
        server.token("delegate"),
        server
            .sign(serde_json::json!({"sub":"root","iss":server.realm,"aud":"app","iat":1,"exp":2})),
    ] {
        let result = Importer {
            pool: &e.pool,
            fga: &e.fga,
            directory: &directory,
            auth: &auth,
            bearer: &token,
        }
        .run(&provisioning_bundle())
        .await;
        assert!(result.is_err());
    }
    let token = server.token("root");
    for users in [
        serde_json::json!([{"username":"alice","password":"private-password"},{"username":"tail"}]),
        serde_json::json!([{"username":"alice","password":"private-password","teams":["uncreatable"]}]),
    ] {
        let bundle = Bundle::parse(&serde_json::to_vec(&serde_json::json!({"organization":{"name":"Provisioned","admins":["alice"]},"users":users})).unwrap()).unwrap();
        let error = Importer {
            pool: &e.pool,
            fga: &e.fga,
            directory: &directory,
            auth: &auth,
            bearer: &token,
        }
        .run(&bundle)
        .await
        .err()
        .unwrap();
        assert!(!format!("{error:?}").contains("private-password"));
    }
    assert!(server.users.lock().await.is_empty());
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );
    assert_eq!(e.fga.platform_grants().await.unwrap(), before);
}

// Proves: I11, I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn directory_creation_conflict_pagination_preservation_and_failures() {
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    server.control.lock().await.conflict_create = true;
    let (user, created) = directory
        .ensure_user(
            "a&b",
            Some("private-password"),
            Some(""),
            Some("First"),
            Some("Last"),
        )
        .await
        .unwrap();
    assert!(!created); // Another writer's creation, resolved after 409.
    let (again, created) = directory
        .ensure_user(
            "a&b",
            Some("replacement"),
            Some("changed@example.org"),
            None,
            None,
        )
        .await
        .unwrap();
    assert_eq!(again.id, user.id);
    assert!(!created);
    assert_eq!(server.control.lock().await.created.len(), 1);
    assert_eq!(
        server.control.lock().await.created[0]["email"],
        "a&b@example.com"
    );
    server.control.lock().await.lookup_ambiguous = true;
    assert!(directory.find_username("a&b").await.is_err()); // Ambiguity is on second short page.
    server.control.lock().await.lookup_ambiguous = false;
    server.control.lock().await.lookup_inexact = true;
    assert!(directory.find_username("a&b").await.is_err());
    server.control.lock().await.lookup_inexact = false;
    server.control.lock().await.fail_create = true;
    let error = directory
        .ensure_user("other", Some("private-password"), None, None, None)
        .await
        .err()
        .unwrap();
    assert!(!format!("{error:?}").contains("private-password"));
    server.control.lock().await.lookup_slow = true;
    assert!(directory.find_username("other").await.is_err());
}

// Proves: I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn provisioning_replay_after_identity_and_sql_failures_reuses_committed_state() {
    use fred_manager::provisioning::Importer;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let auth = server.auth().await;
    let directory = server.directory();
    let token = server.token("root");
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let bundle = provisioning_bundle();
    let importer = Importer {
        pool: &e.pool,
        fga: &e.fga,
        directory: &directory,
        auth: &auth,
        bearer: &token,
    };
    server.control.lock().await.fail_create = true;
    assert!(importer.run(&bundle).await.is_err());
    server.control.lock().await.fail_create = false;
    sqlx::raw_sql("create function reject_space() returns trigger language plpgsql as $$ begin raise exception 'private-password'; end $$; create constraint trigger reject_space after insert on space deferrable initially deferred for each row execute function reject_space();").execute(&e.pool).await.unwrap();
    let error = importer.run(&bundle).await.err().unwrap();
    assert!(!format!("{error:?}").contains("private-password"));
    assert_eq!(server.users.lock().await.len(), 3);
    assert!(
        db::named_space(&e.pool, None, "Provisioned")
            .await
            .unwrap()
            .is_none()
    );
    sqlx::raw_sql("drop trigger reject_space on space")
        .execute(&e.pool)
        .await
        .unwrap();
    let report = importer.run(&bundle).await.unwrap();
    assert_eq!(report.identities_created, 0);
    assert_eq!(report.spaces_reconciled, 2);
}

// Proves: I5, I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn simultaneous_imports_reuse_usernames_and_space_names() {
    use fred_manager::provisioning::Importer;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let auth = server.auth().await;
    let directory = server.directory();
    let token = server.token("root");
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let bundle = provisioning_bundle();
    let importer = Importer {
        pool: &e.pool,
        fga: &e.fga,
        directory: &directory,
        auth: &auth,
        bearer: &token,
    };
    let (one, two) = tokio::join!(importer.run(&bundle), importer.run(&bundle));
    one.unwrap();
    two.unwrap();
    assert_eq!(server.control.lock().await.created.len(), 3);
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        2
    );
}

// Proves: I5, I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn provisioning_waiter_rechecks_revoked_or_expired_operator() {
    use fred_manager::provisioning::{Bundle, Importer};
    for expired in [false, true] {
        let e = env().await;
        let server = support::IdentityServer::start().await;
        let auth = server.auth().await;
        let directory = server.directory();
        bootstrap::grant_root(&e.pool, &e.fga, "root")
            .await
            .unwrap();
        let mut tx = e.pool.begin().await.unwrap();
        sqlx::query("select pg_advisory_xact_lock($1)")
            .bind(bootstrap::LOCK_KEY)
            .execute(&mut *tx)
            .await
            .unwrap();
        let now = chrono::Utc::now().timestamp();
        let token = if expired {
            server.sign(serde_json::json!({"sub":"root","iss":server.realm,"aud":"app","iat":now,"exp":now+1}))
        } else {
            server.token("root")
        };
        let pool = e.pool.clone();
        let fga = e.fga.clone();
        let pending = tokio::spawn(async move {
            let bundle = Bundle::parse(br#"{"organization":{"name":"new","admins":["alice"]},"users":[{"username":"alice","password":"private-password"}]}"#).unwrap();
            Importer {
                pool: &pool,
                fga: &fga,
                directory: &directory,
                auth: &auth,
                bearer: &token,
            }
            .run(&bundle)
            .await
        });
        wait_for_advisory_waiter(&e.pool).await;
        if expired {
            tokio::time::sleep(Duration::from_secs(2)).await;
        } else {
            delete_tuple(&e, "root", "admin", "platform:root").await;
        }
        tx.commit().await.unwrap();
        assert!(pending.await.unwrap().is_err());
        assert!(server.users.lock().await.is_empty());
    }
}

// Proves: I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn import_cli_is_read_only_until_authorized_and_requires_initialized_state() {
    use fred_manager::config::Configuration;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let temp = std::env::temp_dir().join(format!("manager-cli-{}", Uuid::new_v4()));
    std::fs::create_dir(&temp).unwrap();
    let mut config: serde_json::Value =
        serde_yaml_ng::from_str(include_str!("../config/configuration.yaml")).unwrap();
    config["security"]["user"]["realm_url"] = server.realm.clone().into();
    config["security"]["m2m"]["realm_url"] = server.realm.clone().into();
    config["security"]["rebac"]["api_url"] = e.openfga.clone().into();
    config["security"]["rebac"]["store_name"] = e.store.clone().into();
    config["security"]["rebac"]["token_env_var"] = "FRED_MANAGER_IT_NO_TOKEN".into();
    let address = reqwest::Url::parse(&std::env::var("FRED_MANAGER_IT_POSTGRES").unwrap()).unwrap();
    let database: String = sqlx::query_scalar("select current_database()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    config["storage"]["postgres"]["host"] = address.host_str().unwrap().into();
    config["storage"]["postgres"]["port"] = address.port().unwrap().into();
    config["storage"]["postgres"]["username"] = "postgres".into();
    config["storage"]["postgres"]["database"] = database.into();
    let _: Configuration = serde_json::from_value(config.clone()).unwrap();
    std::fs::write(temp.join("bundle.json"),br#"{"organization":{"name":"CLI","admins":["alice"]},"users":[{"username":"alice","password":"private-password"}]}"#).unwrap();
    let http = reqwest::Client::new();
    let store_list: serde_json::Value = http
        .get(format!("{}/stores", e.openfga))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    let store_id = store_list["stores"]
        .as_array()
        .unwrap()
        .iter()
        .find(|s| s["name"] == e.store)
        .unwrap()["id"]
        .as_str()
        .unwrap();
    let model_url = format!("{}/stores/{store_id}/authorization-models", e.openfga);
    let models_before: serde_json::Value = http
        .get(&model_url)
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    for case in [
        "invalid",
        "expired",
        "observer",
        "disabled",
        "mapping",
        "schema",
        "missing-token",
        "missing-bundle",
        "malformed",
        "bad-config",
        "bad-log-level",
        "valid",
    ] {
        let mut current = config.clone();
        let token = match case {
            "invalid" => "private-bearer".into(),
            "expired" => server.sign(
                serde_json::json!({"sub":"root","iss":server.realm,"aud":"app","iat":1,"exp":2}),
            ),
            "observer" => server.token("observer"),
            _ => server.token("root"),
        };
        if case == "disabled" {
            current["security"]["profile"] = serde_json::Value::Null;
            current["security"]["user"]["enabled"] = false.into();
        }
        if case == "mapping" {
            current["security"]["user"]["claims"] = serde_json::json!({"uid":"preferred_username"});
        }
        if case == "schema" {
            sqlx::query("alter table _sqlx_migrations rename to saved_migrations")
                .execute(&e.pool)
                .await
                .unwrap();
        }
        if case == "bad-log-level" {
            current["app"]["log_level"] = "private-secret".into();
        }
        std::fs::write(
            temp.join("configuration.yaml"),
            serde_yaml_ng::to_string(&current).unwrap(),
        )
        .unwrap();
        std::fs::write(temp.join("token"), token).unwrap();
        if case == "missing-token" {
            std::fs::remove_file(temp.join("token")).unwrap();
        }
        if case == "malformed" {
            std::fs::write(temp.join("bundle.json"), br#"{"private-password":true}"#).unwrap();
        }
        if case == "valid" {
            std::fs::write(temp.join("bundle.json"), br#"{"organization":{"name":"CLI","admins":["alice"]},"users":[{"username":"alice","password":"private-password"}]}"#).unwrap();
        }
        if case == "bad-config" {
            std::fs::write(temp.join("configuration.yaml"), "private-secret: [bad").unwrap();
        }
        let output = tokio::process::Command::new(env!("CARGO_BIN_EXE_fred-manager"))
            .args(["import-provisioning"])
            .arg(temp.join(if case == "missing-bundle" {
                "absent.json"
            } else {
                "bundle.json"
            }))
            .arg("--token-file")
            .arg(temp.join("token"))
            .env("CONFIG_FILE", temp.join("configuration.yaml"))
            .env("ENV_FILE", temp.join("absent.env"))
            .env("FRED_POSTGRES_PASSWORD", "it")
            .env("KEYCLOAK_FRED_MANAGER_CLIENT_SECRET", "private-secret")
            .output()
            .await
            .unwrap();
        let text = format!(
            "{}{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        assert!(
            !text.contains("private-password")
                && !text.contains("private-bearer")
                && !text.contains("private-secret"),
            "secret leaked"
        );
        assert_eq!(
            output.status.success(),
            case == "valid",
            "case {case}: {text}"
        );
        let models_after: serde_json::Value = http
            .get(&model_url)
            .send()
            .await
            .unwrap()
            .json()
            .await
            .unwrap();
        assert_eq!(
            models_after, models_before,
            "CLI must never sync model, including on success"
        );
        let stores_after: serde_json::Value = http
            .get(format!("{}/stores?name={}", e.openfga, e.store))
            .send()
            .await
            .unwrap()
            .json()
            .await
            .unwrap();
        assert_eq!(stores_after["stores"].as_array().unwrap().len(), 1);
        if case == "schema" {
            let exists: bool =
                sqlx::query_scalar("select to_regclass('_sqlx_migrations') is not null")
                    .fetch_one(&e.pool)
                    .await
                    .unwrap();
            assert!(!exists, "CLI must not migrate");
            sqlx::query("alter table saved_migrations rename to _sqlx_migrations")
                .execute(&e.pool)
                .await
                .unwrap();
        }
        if case != "valid" {
            assert!(
                text.contains("provisioning initialization/validation failed"),
                "case {case}, status {:?}: {text}",
                output.status
            );
            for counter in [
                "identities_resolved=0",
                "identities_created=0",
                "spaces_reconciled=0",
                "grants_acknowledged=0",
            ] {
                assert!(text.contains(counter), "{text}");
            }
            assert!(server.users.lock().await.is_empty());
        }
    }
    std::fs::remove_dir_all(temp).unwrap();
}

// Proves: I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn provisioning_batches_large_parent_and_child_grants_and_rejects_personal_collision() {
    use fred_manager::provisioning::{Bundle, Importer};
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let auth = server.auth().await;
    let directory = server.directory();
    let token = server.token("root");
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let mut users = Vec::new();
    for i in 0..105 {
        let name = format!("user-{i}");
        server.users.lock().await.insert(name.clone(), name.clone());
        users.push(serde_json::json!({"username":name,"team_roles":{"team_admin":["BID"],"team_analyst":["BID"]}}));
    }
    let value =
        serde_json::json!({"organization":{"name":"Many","admins":["user-0"]},"users":users});
    let bundle = Bundle::parse(&serde_json::to_vec(&value).unwrap()).unwrap();
    let importer = Importer {
        pool: &e.pool,
        fga: &e.fga,
        directory: &directory,
        auth: &auth,
        bearer: &token,
    };
    let report = importer.run(&bundle).await.unwrap();
    assert_eq!(report.grants_acknowledged, 316);
    let org = db::named_space(&e.pool, None, "Many")
        .await
        .unwrap()
        .unwrap();
    spaces::create_personal_space(&e.pool, &e.fga, "user-0", org.id)
        .await
        .unwrap();
    let collision=Bundle::parse(br#"{"organization":{"name":"Many","admins":["new"]},"users":[{"username":"new","password":"private-password","team_roles":{"team_admin":["user-0"]}}]}"#).unwrap();
    assert!(importer.run(&collision).await.is_err());
    assert!(directory.find_username("new").await.unwrap().is_none());
}

// Proves: I5, I17, I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn preflight_does_not_block_revocation_and_cancelled_identity_creation_replays() {
    use fred_manager::provisioning::Importer;
    use std::sync::Arc;
    for cancel in [false, true] {
        let e = env().await;
        let server = support::IdentityServer::start().await;
        let auth = server.auth().await;
        let directory = server.directory();
        let token = server.token("root");
        bootstrap::grant_root(&e.pool, &e.fga, "root")
            .await
            .unwrap();
        let gate = Arc::new(support::Gate::default());
        if cancel {
            server.control.lock().await.create_gate = Some(gate.clone());
        } else {
            server.control.lock().await.lookup_gate = Some(gate.clone());
        }
        let pool = e.pool.clone();
        let fga = e.fga.clone();
        let pending = tokio::spawn(async move {
            Importer {
                pool: &pool,
                fga: &fga,
                directory: &directory,
                auth: &auth,
                bearer: &token,
            }
            .run(&provisioning_bundle())
            .await
        });
        tokio::time::timeout(Duration::from_secs(3), gate.entered.notified())
            .await
            .unwrap();
        if cancel {
            pending.abort();
            assert!(pending.await.unwrap_err().is_cancelled());
            gate.release.notify_one();
            let auth = server.auth().await;
            let directory = server.directory();
            let token = server.token("root");
            let result = Importer {
                pool: &e.pool,
                fga: &e.fga,
                directory: &directory,
                auth: &auth,
                bearer: &token,
            }
            .run(&provisioning_bundle())
            .await
            .unwrap();
            assert_eq!(result.identities_created, 2);
            assert_eq!(server.control.lock().await.created.len(), 3);
        } else {
            // Acquire the actual platform mutation lock while the directory request is paused.
            let tx = tokio::time::timeout(Duration::from_secs(1), async {
                let mut tx = e.pool.begin().await.unwrap();
                sqlx::query("select pg_advisory_xact_lock($1)")
                    .bind(bootstrap::LOCK_KEY)
                    .execute(&mut *tx)
                    .await
                    .unwrap();
                tx
            })
            .await
            .expect("read-only directory preflight must not hold platform lock");
            e.fga
                .write_platform(
                    "root",
                    fred_manager::roles::PlatformRole::PlatformAdmin,
                    false,
                )
                .await
                .unwrap();
            tx.commit().await.unwrap();
            gate.release.notify_one();
            assert!(pending.await.unwrap().is_err());
            assert!(server.users.lock().await.is_empty());
        }
    }
}

// Proves: I17, I18
#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and disposable Keycloak: make test-integration"]
async fn real_keycloak_service_account_provisions_complete_bundle() {
    use fred_manager::{
        auth::Authenticator, config::Configuration, keycloak::Directory, provisioning::Importer,
    };
    let e = env().await;
    let kc = support::real_keycloak::Keycloak::start().await;
    let realm = kc.configure().await;
    let mut config: Configuration =
        serde_yaml_ng::from_str(include_str!("../config/configuration.yaml")).unwrap();
    config.security.user.realm_url = realm.clone();
    config.security.m2m = None;
    let auth = Authenticator::start(config.security().unwrap())
        .await
        .unwrap();
    let token = kc.password_token("app", "app", "root", "it-root").await;
    let root = auth.authenticate(Some(&token)).await.unwrap();
    bootstrap::grant_root(&e.pool, &e.fga, &root.uid)
        .await
        .unwrap();
    let directory = Directory::new(&realm, "fred-manager", "it-manager".into()).unwrap();
    let importer = Importer {
        pool: &e.pool,
        fga: &e.fga,
        directory: &directory,
        auth: &auth,
        bearer: &token,
    };
    let report = importer.run(&provisioning_bundle()).await.unwrap();
    assert_eq!(report.identities_created, 3);
    let alice = directory.find_username("alice").await.unwrap().unwrap();
    let bob = directory.find_username("bob").await.unwrap().unwrap();
    let org = db::named_space(&e.pool, None, "Provisioned")
        .await
        .unwrap()
        .unwrap();
    let team = db::named_space(&e.pool, Some(org.id), "BID")
        .await
        .unwrap()
        .unwrap();
    assert!(
        !e.fga
            .check(&alice.id, Permission::Read, team.id)
            .await
            .unwrap()
    );
    for role in [Role::Member, Role::Editor, Role::Analyst] {
        assert!(
            e.fga
                .roles_of(&bob.id)
                .await
                .unwrap()
                .contains(&(team.id, role))
        );
    }
    assert_eq!(
        importer
            .run(&provisioning_bundle())
            .await
            .unwrap()
            .identities_created,
        0
    );
    // Password is real, non-temporary, and replay preserves it.
    assert!(
        !kc.password_token("app", "app", "alice", "private-password")
            .await
            .is_empty()
    );
    let grants = e.fga.platform_grants().await.unwrap();
    for role in fred_manager::roles::PlatformRole::ALL {
        let subject = if role == fred_manager::roles::PlatformRole::PlatformAdmin {
            directory
                .find_username("platform-only")
                .await
                .unwrap()
                .unwrap()
                .id
        } else {
            bob.id.clone()
        };
        assert!(grants.contains(&(subject, role)));
    }
}

// Proves: I4, I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn provisioning_repairs_every_fga_boundary_including_ambiguous_acknowledgments() {
    use fred_manager::provisioning::Importer;
    for nth in 1..=7 {
        let e = env().await;
        let server = support::IdentityServer::start().await;
        bootstrap::grant_root(&e.pool, &e.fga, "root")
            .await
            .unwrap();
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
        .unwrap();
        {
            let mut fault = proxy.fault.lock().await;
            fault.fail_at = nth;
            fault.after = nth % 2 == 0;
        }
        let auth = server.auth().await;
        let directory = server.directory();
        let token = server.token("root");
        let importer = Importer {
            pool: &e.pool,
            fga: &fga,
            directory: &directory,
            auth: &auth,
            bearer: &token,
        };
        let error = importer
            .run(&provisioning_bundle())
            .await
            .expect_err("injected write failure");
        assert!(!format!("{error:?}").contains("private-password"));
        assert!(
            db::named_space(&e.pool, None, "Provisioned")
                .await
                .unwrap()
                .is_none()
        );
        let old = proxy.fault.lock().await.written[0]["writes"]["tuple_keys"][0]["object"].clone();
        proxy.fault.lock().await.fail_at = 0;
        let report = importer.run(&provisioning_bundle()).await.unwrap();
        assert_eq!(report.identities_created, 0);
        let org = db::named_space(&e.pool, None, "Provisioned")
            .await
            .unwrap()
            .unwrap();
        assert_ne!(
            old,
            serde_json::json!(format!("space:{}", org.id)),
            "never reuse rolled-back UUID"
        );
        let team = db::named_space(&e.pool, Some(org.id), "BID")
            .await
            .unwrap()
            .unwrap();
        for name in ["alice", "bob"] {
            let user = directory.find_username(name).await.unwrap().unwrap();
            assert!(
                e.fga
                    .check(&user.id, Permission::Read, org.id)
                    .await
                    .unwrap()
            );
            assert!(
                e.fga
                    .roles_of(&user.id)
                    .await
                    .unwrap()
                    .iter()
                    .any(|(id, _)| *id == team.id)
            );
        }
    }
}

// Proves: I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn cancellation_after_fga_write_rolls_back_new_space_and_replays() {
    use fred_manager::provisioning::Importer;
    use std::sync::Arc;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let gate = Arc::new(support::Gate::default());
    proxy.fault.lock().await.gate = Some(gate.clone());
    let fga = Fga::connect(
        &proxy.base,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap();
    let pool = e.pool.clone();
    let auth = server.auth().await;
    let directory = server.directory();
    let token = server.token("root");
    let pending = tokio::spawn(async move {
        Importer {
            pool: &pool,
            fga: &fga,
            directory: &directory,
            auth: &auth,
            bearer: &token,
        }
        .run(&provisioning_bundle())
        .await
    });
    tokio::time::timeout(Duration::from_secs(3), gate.entered.notified())
        .await
        .unwrap();
    assert_eq!(proxy.fault.lock().await.acknowledged, vec![200]);
    let old = proxy.fault.lock().await.written[0]["writes"]["tuple_keys"][0]["object"].clone();
    pending.abort();
    assert!(pending.await.unwrap_err().is_cancelled());
    assert!(
        db::named_space(&e.pool, None, "Provisioned")
            .await
            .unwrap()
            .is_none()
    );
    gate.release.notify_one();
    let auth = server.auth().await;
    let directory = server.directory();
    let token = server.token("root");
    let report = Importer {
        pool: &e.pool,
        fga: &e.fga,
        directory: &directory,
        auth: &auth,
        bearer: &token,
    }
    .run(&provisioning_bundle())
    .await
    .unwrap();
    let org = db::named_space(&e.pool, None, "Provisioned")
        .await
        .unwrap()
        .unwrap();
    assert_ne!(old, serde_json::json!(format!("space:{}", org.id)));
    assert_eq!(report.identities_created, 0);
    assert_eq!(report.spaces_reconciled, 2);
}

// Proves: I4, I5, I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn import_rechecks_parent_after_wait_and_repairs_existing_space_grants() {
    use fred_manager::{
        provisioning::{Bundle, Importer},
        roles::PlatformRole,
    };
    let e = env().await;
    let server = support::IdentityServer::start().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    e.fga
        .write_platform("delegate", PlatformRole::PlatformAdmin, true)
        .await
        .unwrap();
    server
        .users
        .lock()
        .await
        .insert("alice".into(), "alice".into());
    server.users.lock().await.insert("bob".into(), "bob".into());
    let org = spaces::create_organization(&e.pool, &e.fga, "Existing", "alice")
        .await
        .unwrap();
    e.fga
        .write(
            &[fred_manager::fga::Tuple {
                user: "bob",
                space: org.id,
                role: Role::Member,
            }],
            &[],
        )
        .await
        .unwrap();
    let held = hold_organization_lock(&e, org.id).await;
    let pool = e.pool.clone();
    let fga = e.fga.clone();
    let auth = server.auth().await;
    let directory = server.directory();
    let token = server.token("delegate");
    let bytes=br#"{"organization":{"name":"Existing","admins":["alice"]},"users":[{"username":"alice","team_roles":{"team_admin":["New"]}},{"username":"bob","team_roles":{"team_analyst":["New"]},"platform_roles":["observer"]}]}"#;
    let pending = tokio::spawn(async move {
        Importer {
            pool: &pool,
            fga: &fga,
            directory: &directory,
            auth: &auth,
            bearer: &token,
        }
        .run(&Bundle::parse(bytes).unwrap())
        .await
    });
    wait_for_advisory_waiter(&e.pool).await;
    delete_tuple(&e, "bob", "member", &format!("space:{}", org.id)).await;
    held.commit().await.unwrap();
    pending.await.unwrap().unwrap();
    // Import explicitly regrants the parent before granting the child, preserving I4.
    assert!(e.fga.check("bob", Permission::Read, org.id).await.unwrap());
    let team = db::named_space(&e.pool, Some(org.id), "New")
        .await
        .unwrap()
        .unwrap();
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
    .unwrap();
    delete_tuple(&e, "bob", "analyst", &format!("space:{}", team.id)).await;
    proxy.fault.lock().await.fail_at = 2;
    let auth = server.auth().await;
    let directory = server.directory();
    let token = server.token("delegate");
    let importer = Importer {
        pool: &e.pool,
        fga: &fga,
        directory: &directory,
        auth: &auth,
        bearer: &token,
    };
    assert!(importer.run(&Bundle::parse(bytes).unwrap()).await.is_err());
    proxy.fault.lock().await.fail_at = 0;
    importer.run(&Bundle::parse(bytes).unwrap()).await.unwrap();
    assert_eq!(
        db::named_space(&e.pool, Some(org.id), "New")
            .await
            .unwrap()
            .unwrap()
            .id,
        team.id
    );
    assert!(
        e.fga
            .roles_of("bob")
            .await
            .unwrap()
            .contains(&(team.id, Role::Analyst))
    );
}

// Proves: I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn import_rejects_incompatible_model_without_syncing_it() {
    let e = env().await;
    let http = reqwest::Client::new();
    let stores: serde_json::Value = http
        .get(format!("{}/stores?name={}", e.openfga, e.store))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    let store = stores["stores"][0]["id"].as_str().unwrap();
    let url = format!("{}/stores/{store}/authorization-models", e.openfga);
    let mut model: serde_json::Value =
        serde_json::from_str(include_str!("../openfga/model.json")).unwrap();
    model["type_definitions"][2]["relations"]["can_read"] =
        serde_json::json!({"computedUserset":{"relation":"admin"}});
    http.post(&url)
        .json(&model)
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap();
    let fga = Fga::connect(
        &e.openfga,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap();
    assert!(fga.require_compatible_model().await.is_err());
    let after: serde_json::Value = http.get(&url).send().await.unwrap().json().await.unwrap();
    assert_eq!(after["authorization_models"].as_array().unwrap().len(), 2);
}
