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
