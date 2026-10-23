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

use control_plane::{
    bootstrap, db,
    domain::{self, Document, Folder, Permission, Role, Space, SpaceKind},
    error::AppError,
    fga::{Fga, Scope},
    spaces,
};
use sqlx::{AssertSqlSafe, PgPool};
use uuid::Uuid;

#[path = "support/content_bucket.rs"]
mod content_bucket;
#[path = "support/document_storage.rs"]
mod document_storage;
#[path = "support/environment.rs"]
mod environment;
use environment::{Env, env, named_space};

/// Removes a tuple behind control-plane's back, as another admin or an operator would.
async fn delete_tuple(e: &Env, user: &str, relation: &str, object: &str) {
    let http = reqwest::Client::new();
    let id = e.fga.store_id();
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

/// Holds the advisory lock control-plane takes for `org`, until the transaction ends.
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
    let org = crate::support::member_organization(&e.pool, &e.fga, "TSN", "alice")
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
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        team.id,
        Role::Member,
        "alice",
    )
    .await
    .unwrap();
    (org, team)
}

async fn grant(e: &Env, space: Uuid, role: Role, user: &str) {
    spaces::grant(&e.pool, &e.fga, &e.subjects(), "alice", space, role, user)
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
        let subjects = e.subjects();
        let _ = tokio::join!(
            spaces::grant(
                &e.pool,
                &e.fga,
                &subjects,
                "alice",
                project.id,
                Role::Member,
                "bob"
            ),
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
        let (pool, fga, open) = (e.pool.clone(), e.fga.clone(), e.open_directory());
        tokio::spawn(async move {
            spaces::grant(
                &pool,
                &fga,
                &control_plane::users::Directory::Keycloak(Some(&open)),
                "bob",
                team.id,
                Role::Admin,
                "bob",
            )
            .await
        })
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
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        org.id,
        Role::PersonalSpaceCreator,
        "bob",
    )
    .await
    .unwrap();
    let personal = spaces::create_personal_space(&e.pool, &e.fga, "bob", org.id)
        .await
        .unwrap()
        .0;

    let blocked = spaces::revoke(&e.pool, &e.fga, "alice", org.id, Role::Member, "bob").await;
    assert!(matches!(blocked, Err(AppError::Conflict(_))));
    let widened = spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        personal.id,
        Role::Member,
        "carol",
    )
    .await;
    assert!(matches!(widened, Err(AppError::Conflict(_))));
    let by_owner = spaces::revoke(&e.pool, &e.fga, "bob", personal.id, Role::Editor, "bob").await;
    assert!(matches!(by_owner, Err(AppError::Forbidden)));

    for role in [Role::Editor, Role::Member] {
        spaces::revoke(&e.pool, &e.fga, "alice", personal.id, role, "bob")
            .await
            .unwrap();
    }
    spaces::revoke(
        &e.pool,
        &e.fga,
        "alice",
        org.id,
        Role::PersonalSpaceCreator,
        "bob",
    )
    .await
    .unwrap();
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
    assert!(e.fga.is_platform_owner("alice").await.unwrap());
    for user in ["bob", "alice"] {
        let again = bootstrap::grant_root(&e.pool, &e.fga, user).await;
        assert!(
            matches!(again, Err(AppError::Conflict(_))),
            "{user} must get 409"
        );
    }
    assert!(!e.fga.is_platform_owner("bob").await.unwrap());
}

// Proves: I9
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn a_finished_bootstrap_stays_closed_after_its_admin_is_removed() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "alice")
        .await
        .unwrap();
    delete_tuple(&e, "alice", "platform_owner", "platform:root").await;
    let again = bootstrap::grant_root(&e.pool, &e.fga, "alice").await;
    assert!(matches!(again, Err(AppError::Conflict(_))));
    assert!(!e.fga.is_platform_owner("alice").await.unwrap());
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
    assert!(e.fga.is_platform_owner("alice").await.unwrap());
    assert!(!e.fga.is_platform_owner("bob").await.unwrap());
}

fn document(space: Uuid, folder: Option<Uuid>, name: &str) -> Document {
    Document {
        retrievable: false,
        retrievable_pending: false,
        id: Uuid::new_v4(),
        space_id: space,
        folder_id: folder,
        name: name.into(),
        mime: "text/plain".into(),
        size: 1,
        sha256: "a".repeat(64),
        created_by: "alice".into(),
        created_at: chrono::Utc::now(),
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
        created_at: chrono::Utc::now(),
        id,
        space_id: team.id,
        parent_id: None,
        name: "Appels d'offres".into(),
        path: domain::folder_path(None, id),
    };
    db::insert_folder(&e.pool, &folder).await.unwrap();
    let doc = document(team.id, Some(folder.id), "cdc.pdf");
    crate::environment::insert_document(&e.pool, &doc)
        .await
        .unwrap();

    let moves = [
        format!(
            "update space set organization_id = '{}' where id = '{}'",
            team.id, team.id
        ),
        format!("update space set parent_id = null where id = '{}'", team.id),
        format!("update space set kind = 'project' where id = '{}'", team.id),
        format!(
            "update space set personal_owner = 'alice' where id = '{}'",
            team.id
        ),
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
        let error = refused.expect_err(&statement).to_string();
        assert!(
            error.contains("placement is immutable"),
            "{statement}: {error}"
        );
    }
    let elsewhere = document(org.id, Some(folder.id), "wrong-space.pdf");
    assert!(
        crate::environment::insert_document(&e.pool, &elsewhere)
            .await
            .is_err()
    );
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

// Proves: I8
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn complete_role_permission_matrix_and_space_isolation() {
    use control_plane::{
        fga::Tuple,
        roles::{PlatformPermission as PP, PlatformRole as P, SpacePermission as SP},
    };
    let e = env().await;
    let space = Uuid::new_v4();
    let other = Uuid::new_v4();
    // Enumerate every subset: cumulative grants must equal the union of their individual rights.
    let roles = [
        Role::Member,
        Role::Editor,
        Role::Admin,
        Role::Analyst,
        Role::OrganizationOwner,
        Role::PersonalSpaceCreator,
    ];
    for mask in 0..64 {
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
                    &mut e.fga.guard(&[Scope::Platform]).await.unwrap(),
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
                SP::OwnOrganization => *role == Role::OrganizationOwner,
                SP::CreatePersonalSpace => *role == Role::PersonalSpaceCreator,
            });
            assert_eq!(
                e.fga.check_space(&user, permission, space).await.unwrap(),
                expected,
                "{mask} {permission:?}"
            );
            assert!(!e.fga.check_space(&user, permission, other).await.unwrap());
        }
    }
    for mask in 0..16 {
        let user = format!("platform-{mask}");
        let held: Vec<_> = P::ALL
            .iter()
            .enumerate()
            .filter(|(i, _)| mask & (1 << i) != 0)
            .map(|(_, r)| *r)
            .collect();
        for role in &held {
            e.fga
                .write_platform(
                    &mut e.fga.guard(&[Scope::Platform]).await.unwrap(),
                    &user,
                    *role,
                    true,
                )
                .await
                .unwrap();
        }
        for permission in PP::ALL {
            let expected = held.iter().any(|role| {
                *role == P::PlatformOwner
                    || matches!(
                        (role, permission),
                        (P::PlatformObserver, PP::ObservePlatform)
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
            if held.contains(&P::PlatformOwner) {
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
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        org.id,
        Role::PersonalSpaceCreator,
        "analyst",
    )
    .await
    .unwrap();
    let personal = spaces::create_personal_space(&e.pool, &e.fga, "analyst", org.id)
        .await
        .unwrap()
        .0;
    assert!(matches!(
        spaces::grant(
            &e.pool,
            &e.fga,
            &e.subjects(),
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
        assert_eq!(
            e.fga.space_holders(space, Role::Admin).await.unwrap().len(),
            1
        );
    }
}

// Proves: I8
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn teams_are_created_by_organization_admins_only() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    // Platform ownership confers no business role in an organization.
    let by_root = spaces::create_space(
        &e.pool,
        &e.fga,
        "root",
        SpaceKind::Team,
        org.id,
        "Platform".into(),
        "alice",
    )
    .await;
    // The platform owner is outside the organization: the parent is not found for them.
    assert!(matches!(by_root, Err(AppError::NotFound)));
    let created = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Team,
        org.id,
        "Local".into(),
        "alice",
    )
    .await
    .unwrap();
    assert!(!reads(&e, "alice", created.id).await);
    assert!(matches!(
        spaces::create_space(
            &e.pool,
            &e.fga,
            "root",
            SpaceKind::Project,
            team.id,
            "Denied".into(),
            "alice"
        )
        .await,
        Err(AppError::NotFound)
    ));
    assert!(matches!(
        spaces::create_space(
            &e.pool,
            &e.fga,
            "alice",
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
async fn platform_owners_manage_each_other_and_keep_one() {
    use control_plane::{platform, roles::PlatformRole as P};
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
        P::PlatformOwner,
    )
    .await
    .unwrap();
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

    // Any owner hands over ownership, root included; the last owner stays.
    platform::revoke(&e.pool, &e.fga, "admin", "root", P::PlatformOwner)
        .await
        .unwrap();
    assert!(!e.fga.is_platform_owner("root").await.unwrap());
    assert!(matches!(
        platform::revoke(&e.pool, &e.fga, "admin", "admin", P::PlatformOwner).await,
        Err(AppError::Conflict(_))
    ));
    assert!(e.fga.is_platform_owner("admin").await.unwrap());
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

// A failed try-lock ends in ROLLBACK, leaving an idle connection between attempts.
async fn wait_for_write_retry(pool: &PgPool, since: chrono::DateTime<chrono::Utc>) {
    tokio::time::timeout(Duration::from_secs(3), async {
        let mut observer = pool.acquire().await.unwrap();
        loop {
            let retried: bool = sqlx::query_scalar(
                "select exists(select 1 from pg_stat_activity where datname=current_database() and state='idle' and query ilike 'rollback%' and state_change >= $1)",
            )
            .bind(since)
            .fetch_one(&mut *observer)
            .await
            .unwrap();
            if retried {
                break;
            }
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .expect("writer must roll back its failed try-lock before the competing mutation");
}

// Proves: I5
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn revoked_platform_actor_cannot_complete_a_waiting_platform_or_owner_grant() {
    use control_plane::{platform, roles::PlatformRole as P};
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    for owner_grant in [false, true] {
        e.fga
            .write_platform(
                &mut e.fga.guard(&[Scope::Platform]).await.unwrap(),
                "delegate",
                P::PlatformOwner,
                true,
            )
            .await
            .unwrap();
        let mut tx = e.pool.begin().await.unwrap();
        sqlx::query("select pg_advisory_xact_lock($1)")
            .bind(bootstrap::LOCK_KEY)
            .execute(&mut *tx)
            .await
            .unwrap();
        let (pool, fga, open) = (e.pool.clone(), e.fga.clone(), e.open_directory());
        let pending = tokio::spawn(async move {
            if owner_grant {
                spaces::grant(
                    &pool,
                    &fga,
                    &control_plane::users::Directory::Keycloak(Some(&open)),
                    "delegate",
                    org.id,
                    Role::OrganizationOwner,
                    "target",
                )
                .await
            } else {
                platform::grant(&pool, &fga, None, "delegate", "target", P::PromptEditor).await
            }
        });
        wait_for_advisory_waiter(&e.pool).await;
        e.fga
            .write_platform(
                &mut e.fga.guard(&[Scope::Platform]).await.unwrap(),
                "delegate",
                P::PlatformOwner,
                false,
            )
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
    use control_plane::{
        api::{AppState, routes},
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
    let app = routes(AppState {
        onboarding: Default::default(),
        lifecycle: Default::default(),
        auth: Arc::new(server.auth().await),
        pool: e.pool.clone(),
        fga: e.fga.clone(),
        directory: Some(server.directory()),
        content: None,
        processing: None,
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
    use control_plane::{
        api::{AppState, routes},
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
        let app = routes(AppState {
            onboarding: Default::default(),
            lifecycle: Default::default(),
            auth: Arc::new(
                Authenticator::start(config.security().unwrap())
                    .await
                    .unwrap(),
            ),
            pool: e.pool.clone(),
            fga: e.fga.clone(),
            content: None,
            processing: None,
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
// Records every event with its target, so tests can also prove the absence of duplicates.
impl<S: tracing::Subscriber> tracing_subscriber::Layer<S> for AuditCapture {
    fn on_event(&self, event: &tracing::Event<'_>, _: tracing_subscriber::layer::Context<'_, S>) {
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
        fields
            .0
            .insert("target".into(), event.metadata().target().into());
        event.record(&mut fields);
        self.0.lock().unwrap().push(fields.0.into());
    }
}

// Proves: I16
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn only_effective_role_changes_are_audited_once() {
    use tracing_subscriber::prelude::*;
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let capture = AuditCapture::default();
    let _thread =
        tracing::subscriber::set_default(tracing_subscriber::registry().with(capture.clone()));
    grant(&e, org.id, Role::Member, "bob").await;
    spaces::revoke(&e.pool, &e.fga, "alice", org.id, Role::Editor, "bob")
        .await
        .unwrap();
    spaces::revoke(&e.pool, &e.fga, "alice", org.id, Role::Member, "bob")
        .await
        .unwrap();
    let events = capture.0.lock().unwrap();
    for event in ["authz.relation.granted", "authz.relation.revoked"] {
        let named: Vec<_> = events
            .iter()
            .filter(|e| e["message"].as_str().is_some_and(|m| m.contains(event)))
            .collect();
        assert_eq!(named.len(), 1, "{event}: {named:?}");
        assert_eq!(named[0]["target"], "fred.security.audit");
        assert_eq!(
            (&named[0]["relation"], &named[0]["subject"]),
            (&"member".into(), &"user:bob".into())
        );
    }
}

// Proves: I16
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn durable_grants_are_audited_even_when_sql_commit_fails() {
    use tracing_subscriber::prelude::*;
    let e = env().await;
    let capture = AuditCapture::default();
    let subscriber = tracing_subscriber::registry().with(capture.clone());
    tracing::subscriber::set_global_default(subscriber).unwrap();
    let root = format!("audit-root-{}", Uuid::new_v4());
    {
        let (org, _) = org_and_team(&e).await;
        grant(&e, org.id, Role::Member, "delegate").await;
        grant(&e, org.id, Role::Admin, "delegate").await;
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
            e.fga.is_platform_owner(&root).await.unwrap(),
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

fn provisioning_bundle() -> control_plane::provisioning::Bundle {
    parse_blueprint(br#"{"users":[{"username":"alice","password":"private-password","first_name":"Alice","last_name":"Example"},{"username":"bob","password":"private-password","platform_roles":["platform_observer","feature_manager","prompt_editor"]},{"username":"platform-only","password":"private-password","platform_roles":["platform_owner"]}],"organizations":[{"ref":"org","name":"Provisioned","roles":{"alice":["admin","member","organization_owner"],"bob":["member"]}}],"teams":[{"ref":"BID","name":"BID","organization":"org","roles":{"alice":["admin"],"bob":["member","editor","analyst"]}}],"projects":[]}"#).unwrap()
}

// Proves: I4, I8, I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn provisioning_replays_every_role_without_updating_identities_or_implicit_content() {
    use control_plane::{provisioning::Importer, roles::PlatformRole};
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    db::require_initialized(&e.pool).await.unwrap();
    let fga = e.fga.clone();
    let bundle = provisioning_bundle();
    let importer = Importer {
        pool: &e.pool,
        fga: &fga,
        directory: &directory,
        operator: "root",
    };
    let first = importer.run(&bundle).await.unwrap();
    assert_eq!(first.identities_created, 3);
    let org = named_space(&e.pool, &e.fga, None, "Provisioned")
        .await
        .unwrap()
        .unwrap();
    let team = named_space(&e.pool, &e.fga, Some(org.id), "BID")
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
            if role == PlatformRole::PlatformOwner {
                platform.clone()
            } else {
                bob.clone()
            },
            role
        )));
    }
    // Undeclared roles survive; missing requested grants are repaired on committed IDs.
    fga.write(
        &mut fga.guard(&[Scope::Platform]).await.unwrap(),
        &[control_plane::fga::Tuple {
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
        named_space(&e.pool, &e.fga, Some(org.id), "BID")
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
    use control_plane::{provisioning::Importer, roles::PlatformRole};
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    e.fga
        .write_platform(
            &mut e.fga.guard(&[Scope::Platform]).await.unwrap(),
            "observer",
            PlatformRole::PlatformObserver,
            true,
        )
        .await
        .unwrap();
    let before = e.fga.platform_grants().await.unwrap();
    // Bearer validity is checked at admission (HTTP and CLI); here only authority.
    for operator in ["observer", "nobody"] {
        let result = Importer {
            pool: &e.pool,
            fga: &e.fga,
            directory: &directory,
            operator,
        }
        .run(&provisioning_bundle())
        .await;
        assert!(result.is_err());
    }
    for (users, teams) in [
        (
            serde_json::json!([{"username":"alice","password":"private-password"},{"username":"tail"}]),
            serde_json::json!([]),
        ),
        (
            serde_json::json!([{"username":"alice","password":"private-password"}]),
            serde_json::json!([{"ref":"bad","name":"uncreatable","organization":"org","roles":{"alice":["member"]}}]),
        ),
    ] {
        let bundle = parse_blueprint(&serde_json::to_vec(&serde_json::json!({"organizations":[{"ref":"org","name":"Provisioned","roles":{"alice":["admin","member","organization_owner"]}}],"users":users,"teams":teams,"projects":[]})).unwrap()).unwrap();
        let error = Importer {
            pool: &e.pool,
            fga: &e.fga,
            directory: &directory,
            operator: "root",
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
    use control_plane::provisioning::Importer;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let bundle = provisioning_bundle();
    let importer = Importer {
        pool: &e.pool,
        fga: &e.fga,
        directory: &directory,
        operator: "root",
    };
    server.control.lock().await.fail_create = true;
    assert!(importer.run(&bundle).await.is_err());
    server.control.lock().await.fail_create = false;
    sqlx::raw_sql("create function reject_space() returns trigger language plpgsql as $$ begin raise exception 'private-password'; end $$; create constraint trigger reject_space after insert on space deferrable initially deferred for each row execute function reject_space();").execute(&e.pool).await.unwrap();
    let error = importer.run(&bundle).await.err().unwrap();
    assert!(!format!("{error:?}").contains("private-password"));
    assert_eq!(server.users.lock().await.len(), 3);
    assert!(
        named_space(&e.pool, &e.fga, None, "Provisioned")
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
    use control_plane::provisioning::Importer;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let bundle = provisioning_bundle();
    let importer = Importer {
        pool: &e.pool,
        fga: &e.fga,
        directory: &directory,
        operator: "root",
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
async fn provisioning_waiter_rechecks_revocation_but_not_bearer_expiry() {
    use control_plane::{
        api::{AppState, routes},
        provisioning::Importer,
    };
    let bundle = br#"{"users":[{"username":"alice","password":"private-password"}],"organizations":[{"ref":"org","name":"new","roles":{"alice":["admin","member","organization_owner"]}}],"teams":[],"projects":[]}"#;
    for revoked in [true, false] {
        let e = env().await;
        let server = support::IdentityServer::start().await;
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
        let pending = if revoked {
            let (pool, fga) = (e.pool.clone(), e.fga.clone());
            tokio::spawn(async move {
                Importer {
                    pool: &pool,
                    fga: &fga,
                    directory: &directory,
                    operator: "root",
                }
                .run(&parse_blueprint(bundle).unwrap())
                .await
                .is_ok()
            })
        } else {
            // Admission accepts this bearer; it expires while the import waits.
            let app = routes(AppState {
                onboarding: Default::default(),
                lifecycle: Default::default(),
                auth: std::sync::Arc::new(server.auth().await),
                pool: e.pool.clone(),
                fga: e.fga.clone(),
                directory: Some(directory),
                content: None,
                processing: None,
            });
            let now = chrono::Utc::now().timestamp();
            let token = server.sign(
                serde_json::json!({"sub":"root","iss":server.realm,"aud":"app","iat":now,"exp":now+2}),
            );
            tokio::spawn(
                async move { http_import(&app, &token, &fixture_zip(bundle)).await.0 == 200 },
            )
        };
        wait_for_advisory_waiter(&e.pool).await;
        if revoked {
            delete_tuple(&e, "root", "platform_owner", "platform:root").await;
        } else {
            tokio::time::sleep(Duration::from_secs(3)).await;
        }
        tx.commit().await.unwrap();
        assert_eq!(pending.await.unwrap(), !revoked);
        assert_eq!(server.users.lock().await.is_empty(), revoked);
    }
}

// Proves: I18, I19, I21
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn import_cli_is_read_only_until_authorized_and_requires_initialized_state() {
    use control_plane::config::Configuration;
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
    config["security"]["rebac"]["token_env_var"] = "CONTROL_PLANE_IT_NO_TOKEN".into();
    let address =
        reqwest::Url::parse(&std::env::var("CONTROL_PLANE_IT_POSTGRES").unwrap()).unwrap();
    let database: String = sqlx::query_scalar("select current_database()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    config["storage"]["postgres"]["host"] = address.host_str().unwrap().into();
    config["storage"]["postgres"]["port"] = address.port().unwrap().into();
    config["storage"]["postgres"]["username"] = "postgres".into();
    config["storage"]["postgres"]["database"] = database.into();
    let _: Configuration = serde_json::from_value(config.clone()).unwrap();
    std::fs::write(temp.join("bundle.json"), fixture_zip(br#"{"users":[{"username":"alice","password":"private-password"}],"organizations":[{"ref":"org","name":"CLI","roles":{"alice":["admin","member","organization_owner"]}}],"teams":[],"projects":[]}"#)).unwrap();
    control_plane::onboarding::accept(&e.pool, Some("v1"), "root", "v1")
        .await
        .unwrap();
    control_plane::onboarding::accept(&e.pool, Some("v1"), "observer", "v1")
        .await
        .unwrap();
    let http = reqwest::Client::new();
    let store_id = e.fga.store_id();
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
        "no-consent",
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
        if case == "no-consent" {
            current["app"]["gcu_version"] = "v2".into();
        }
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
            std::fs::write(temp.join("bundle.json"), fixture_zip(br#"{"users":[{"username":"alice","password":"private-password"}],"organizations":[{"ref":"org","name":"CLI","roles":{"alice":["admin","member","organization_owner"]}}],"teams":[],"projects":[]}"#)).unwrap();
        }
        if case == "bad-config" {
            std::fs::write(temp.join("configuration.yaml"), "private-secret: [bad").unwrap();
        }
        let output = tokio::process::Command::new(env!("CARGO_BIN_EXE_control-plane"))
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
            .env("KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET", "private-secret")
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
        if case == "no-consent" {
            assert!(text.contains("user_not_accept_gcu"));
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
    server
        .users
        .lock()
        .await
        .insert("operator".into(), "operator".into());
    // Deployment credentials cannot create an organization via the removed CLI.
    std::fs::write(
        temp.join("configuration.yaml"),
        serde_yaml_ng::to_string(&config).unwrap(),
    )
    .unwrap();
    let before: i64 = sqlx::query_scalar("select count(*) from space")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    let output = tokio::process::Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .args(["create-org", "Operator", "operator"])
        .env("CONFIG_FILE", temp.join("configuration.yaml"))
        .env("ENV_FILE", temp.join("absent.env"))
        .env("FRED_POSTGRES_PASSWORD", "it")
        .env("KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET", "private-secret")
        .output()
        .await
        .unwrap();
    assert!(!output.status.success());
    let text = String::from_utf8_lossy(&output.stdout);
    assert!(text.contains("usage: control-plane"), "{text}");
    assert!(!text.contains("create-org"), "{text}");
    let after: i64 = sqlx::query_scalar("select count(*) from space")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(after, before);
    config["app"]["log_format"] = "json".into();
    let unavailable = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    config["security"]["rebac"]["api_url"] =
        format!("http://{}", unavailable.local_addr().unwrap()).into();
    drop(unavailable);
    std::fs::write(
        temp.join("configuration.yaml"),
        serde_yaml_ng::to_string(&config).unwrap(),
    )
    .unwrap();
    let output = tokio::process::Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .arg("serve")
        .env("CONFIG_FILE", temp.join("configuration.yaml"))
        .env("ENV_FILE", temp.join("absent.env"))
        .env("FRED_POSTGRES_PASSWORD", "it")
        .env("KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET", "private-secret")
        .output()
        .await
        .unwrap();
    assert!(!output.status.success());
    assert!(
        output.stderr.is_empty(),
        "migration failures use the structured logger"
    );
    let events: Vec<serde_json::Value> = String::from_utf8(output.stdout)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert!(
        events
            .iter()
            .any(|e| e["message"] == "control-plane stopped")
    );
    std::fs::remove_dir_all(temp).unwrap();
}

// Proves: I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn provisioning_batches_large_parent_and_child_grants_and_keeps_personal_spaces_apart() {
    use control_plane::provisioning::Importer;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let mut users = Vec::new();
    let mut org_roles = serde_json::Map::new();
    let mut team_roles = serde_json::Map::new();
    for i in 0..105 {
        let name = format!("user-{i}");
        server.users.lock().await.insert(name.clone(), name.clone());
        users.push(serde_json::json!({"username":name}));
        org_roles.insert(
            name.clone(),
            if i == 0 {
                serde_json::json!(["member", "admin", "organization_owner"])
            } else {
                serde_json::json!(["member"])
            },
        );
        team_roles.insert(name, serde_json::json!(["admin", "analyst"]));
    }
    let value = serde_json::json!({"users":users,"organizations":[{"ref":"org","name":"Many","roles":org_roles}],"teams":[{"ref":"bid","name":"BID","organization":"org","roles":team_roles}],"projects":[]});
    let bundle = parse_blueprint(&serde_json::to_vec(&value).unwrap()).unwrap();
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
    proxy.fault.lock().await.calls.clear();
    let importer = Importer {
        pool: &e.pool,
        fga: &fga,
        directory: &directory,
        operator: "root",
    };
    let report = importer.run(&bundle).await.unwrap();
    assert_eq!(report.grants_acknowledged, 317);
    {
        let fault = proxy.fault.lock().await;
        // U=105, B=5, G=0, new org/team=1 each; +3*105 context Reads.
        assert_eq!(fault.calls.get("check"), Some(&114));
        assert_eq!(fault.calls.get("read"), Some(&422));
        assert_eq!(fault.calls.get("write"), Some(&111));
        let operations: Vec<_> = fault
            .written
            .iter()
            .map(|body| {
                body["writes"]["tuple_keys"].as_array().map_or(0, Vec::len)
                    + body["deletes"]["tuple_keys"].as_array().map_or(0, Vec::len)
            })
            .collect();
        // Plus one `parent` link for the new team.
        assert_eq!(operations.iter().sum::<usize>(), 550);
        assert_eq!(operations.iter().max(), Some(&100));
    }
    let org = named_space(&e.pool, &e.fga, None, "Many")
        .await
        .unwrap()
        .unwrap();
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "user-0",
        org.id,
        Role::PersonalSpaceCreator,
        "user-0",
    )
    .await
    .unwrap();
    let personal = spaces::create_personal_space(&e.pool, &e.fga, "user-0", org.id)
        .await
        .unwrap()
        .0;
    // A personal space is not a child: a team may share its name and stays distinct.
    let homonym=parse_blueprint(br#"{"users":[{"username":"new","password":"private-password"}],"organizations":[{"ref":"org","name":"Many","roles":{"new":["admin","member","organization_owner"]}}],"teams":[{"ref":"user-0","name":"user-0","organization":"org","roles":{"new":["admin"]}}],"projects":[]}"#).unwrap();
    importer.run(&homonym).await.unwrap();
    let team = named_space(&e.pool, &e.fga, Some(org.id), "user-0")
        .await
        .unwrap()
        .unwrap();
    assert!(team.personal_owner.is_none() && team.id != personal.id);
    assert_eq!(team.parent_id, Some(org.id));
}

// Proves: I5, I17, I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn preflight_does_not_block_revocation_and_cancelled_identity_creation_replays() {
    use control_plane::provisioning::Importer;
    use std::sync::Arc;
    for cancel in [false, true] {
        let e = env().await;
        let server = support::IdentityServer::start().await;
        let directory = server.directory();
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
                operator: "root",
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
            let directory = server.directory();
            let result = Importer {
                pool: &e.pool,
                fga: &e.fga,
                directory: &directory,
                operator: "root",
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
                    &mut e.fga.guard(&[Scope::Platform]).await.unwrap(),
                    "root",
                    control_plane::roles::PlatformRole::PlatformOwner,
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

// Proves: I1, I4, I8, I17, I18
#[tokio::test]
#[ignore = "needs Postgres, OpenFGA and disposable Keycloak: make test-integration"]
async fn real_keycloak_service_account_provisions_complete_bundle() {
    use control_plane::{
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
    let directory = Directory::new(&realm, "control-plane", "it-manager".into()).unwrap();
    let importer = Importer {
        pool: &e.pool,
        fga: &e.fga,
        directory: &directory,
        operator: &root.uid,
    };
    // Predictable identity failures cannot create even the first account in a bundle.
    let declaration = serde_json::json!({"users":[{"username":"prefix","password":"private-password"},{"username":"tail","password":"private-password"}],"organizations":[{"ref":"o","name":"Preflight","roles":{"prefix":["organization_owner","admin"]}}],"teams":[],"projects":[]});
    let users_before = kc.get("/admin/realms/app/users").await;
    for invalid in ["Alice", " alice", "alice ", "ALICE"] {
        let mut value = declaration.clone();
        value["users"][1]["username"] = invalid.into();
        assert!(parse_blueprint(&serde_json::to_vec(&value).unwrap()).is_err());
    }
    for (first_email, second_email) in [
        (Some("shared@example.com"), "SHARED@example.com"),
        (None, "prefix@example.com"),
        (Some("unused@example.com"), "root@example.com"),
    ] {
        let mut value = declaration.clone();
        if let Some(email) = first_email {
            value["users"][0]["email"] = email.into();
        }
        value["users"][1]["email"] = second_email.into();
        let bundle = parse_blueprint(&serde_json::to_vec(&value).unwrap()).unwrap();
        let error = importer.run(&bundle).await.err().unwrap().to_string();
        assert!(error.contains("preflight"), "{error}");
        assert!(error.contains("identities_created=0"), "{error}");
        assert_eq!(kc.get("/admin/realms/app/users").await, users_before);
        assert_eq!(
            sqlx::query_scalar::<_, i64>("select count(*) from space")
                .fetch_one(&e.pool)
                .await
                .unwrap(),
            0
        );
    }
    let report = importer.run(&provisioning_bundle()).await.unwrap();
    assert_eq!(report.identities_created, 3);
    let alice = directory.find_username("alice").await.unwrap().unwrap();
    let bob = directory.find_username("bob").await.unwrap().unwrap();
    let org = named_space(&e.pool, &e.fga, None, "Provisioned")
        .await
        .unwrap()
        .unwrap();
    let team = named_space(&e.pool, &e.fga, Some(org.id), "BID")
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
    for role in control_plane::roles::PlatformRole::ALL {
        let subject = if role == control_plane::roles::PlatformRole::PlatformOwner {
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
    // Same IAM identities, separate Fred instance: one person cannot join a second
    // organization on the original instance. Identity preservation is still tested.
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, &root.uid)
        .await
        .unwrap();
    // Acceptance uses the artifact built by the actual public Make command over HTTP.
    let output = std::env::temp_dir().join(format!("manager-demo-{}.zip", Uuid::new_v4()));
    assert!(
        tokio::process::Command::new("make")
            .arg("build-demo-bundle")
            .env("DEMO_BUNDLE_FILE", &output)
            .status()
            .await
            .unwrap()
            .success()
    );
    let bytes = std::fs::read(&output).unwrap();
    std::fs::remove_file(output).unwrap();
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let observed_fga = Fga::connect(
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
    let app = control_plane::api::routes(control_plane::api::AppState {
        onboarding: Default::default(),
        lifecycle: Default::default(),
        auth: std::sync::Arc::new(auth),
        pool: e.pool.clone(),
        fga: observed_fga,
        directory: Some(directory.clone()),
        content: None,
        processing: None,
    });
    let (status, report) = http_import(&app, &token, &bytes).await;
    assert_eq!(status, 200, "{report}");
    assert_eq!(report["identities_created"], 13); // Alice and Bob already exist.
    assert_eq!(report["spaces_reconciled"], 4);
    {
        let fault = proxy.fault.lock().await;
        // Actual Make artifact: U=15, O=1, B=4, G=4, C=3; HTTP adds one owner Check.
        assert_eq!(fault.calls.get("check"), Some(&28));
        assert_eq!(fault.calls.get("read"), Some(&44));
        assert_eq!(fault.calls.get("write"), Some(&24));
        let operations: usize = fault
            .written
            .iter()
            .map(|body| {
                body["writes"]["tuple_keys"].as_array().map_or(0, Vec::len)
                    + body["deletes"]["tuple_keys"].as_array().map_or(0, Vec::len)
            })
            .sum();
        assert_eq!(operations, 91);
    }
    let demo = named_space(&e.pool, &e.fga, None, "Demo")
        .await
        .unwrap()
        .unwrap();
    let north = named_space(&e.pool, &e.fga, Some(demo.id), "northbridge")
        .await
        .unwrap()
        .unwrap();
    let sophia = directory.find_username("sophia").await.unwrap().unwrap();
    assert!(
        !e.fga
            .check(&sophia.id, Permission::Read, north.id)
            .await
            .unwrap()
    );
    assert!(
        e.fga
            .check(&sophia.id, Permission::Manage, north.id)
            .await
            .unwrap()
    );
    assert!(
        e.fga
            .check(&sophia.id, Permission::Read, demo.id)
            .await
            .unwrap()
    );
    for (username, role) in [
        ("alice", control_plane::roles::PlatformRole::PlatformOwner),
        (
            "gabriel",
            control_plane::roles::PlatformRole::PlatformObserver,
        ),
        ("nina", control_plane::roles::PlatformRole::FeatureManager),
        ("quinn", control_plane::roles::PlatformRole::PromptEditor),
    ] {
        let subject = directory.find_username(username).await.unwrap().unwrap();
        assert!(
            e.fga
                .platform_grants()
                .await
                .unwrap()
                .contains(&(subject.id, role))
        );
    }
    let (status, report) = http_import(&app, &token, &bytes).await;
    assert_eq!(status, 200, "{report}");
    assert_eq!(report["identities_created"], 0);
    assert_eq!(
        named_space(&e.pool, &e.fga, None, "Demo")
            .await
            .unwrap()
            .unwrap()
            .id,
        demo.id
    );
    assert_eq!(
        directory.find_username("alice").await.unwrap().unwrap().id,
        alice.id
    );
    let preserved = kc
        .get(&format!("/admin/realms/app/users/{}", alice.id))
        .await;
    assert_eq!(preserved["firstName"], "Alice");
    assert_eq!(preserved["lastName"], "Example");
    assert_eq!(preserved["email"], "alice@example.com");
    let alice_token = kc
        .password_token("app", "app", "alice", "private-password")
        .await;
    use tower::ServiceExt;
    let response = app
        .clone()
        .oneshot(
            axum::http::Request::builder()
                .uri("/me/spaces")
                .header("Authorization", format!("Bearer {alice_token}"))
                .body(axum::body::Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), 200);
    let visible: serde_json::Value = serde_json::from_slice(
        &axum::body::to_bytes(response.into_body(), 100_000)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(
        visible
            .as_array()
            .unwrap()
            .iter()
            .any(|s| s["id"] == demo.id.to_string())
    );
    // Variant declares a project and uses the same HTTP path and real directory.
    let variant = fixture_zip(br#"{"users":[{"username":"alice"},{"username":"bob"}],"organizations":[{"ref":"demo","name":"Demo","roles":{}}],"teams":[{"ref":"north","name":"northbridge","organization":"demo","roles":{"alice":["member"]}}],"projects":[{"ref":"project","name":"Project","team":"north","roles":{"alice":["admin"],"bob":["member","editor","analyst"]}}]}"#);
    {
        let mut fault = proxy.fault.lock().await;
        fault.calls.clear();
        fault.written.clear();
    }
    let (status, report) = http_import(&app, &token, &variant).await;
    assert_eq!(status, 200, "{report}");
    {
        let fault = proxy.fault.lock().await;
        // U=2, O=1, B=2, H=2 existing-parent fallbacks, E=2 existing parents whose
        // children resolve names, N=G=Z=0; HTTP adds one admin Check.
        // Two subjects: 3*(1+1) context Reads, with placement in SQL.
        assert_eq!(fault.calls.get("check"), Some(&9));
        assert_eq!(fault.calls.get("read"), Some(&20));
        assert_eq!(fault.calls.get("write"), Some(&4));
    }
    let project = named_space(&e.pool, &e.fga, Some(north.id), "Project")
        .await
        .unwrap()
        .unwrap();
    assert_eq!(project.path, vec![demo.id, north.id, project.id]);
    assert!(
        !e.fga
            .check(&alice.id, Permission::Read, project.id)
            .await
            .unwrap()
    );
    assert!(
        e.fga
            .check(&alice.id, Permission::Manage, project.id)
            .await
            .unwrap()
    );
    for role in [Role::Member, Role::Editor, Role::Analyst] {
        assert!(
            e.fga
                .roles_of(&bob.id)
                .await
                .unwrap()
                .contains(&(project.id, role))
        );
    }
}

// Proves: I4, I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn provisioning_repairs_every_fga_boundary_including_ambiguous_acknowledgments() {
    use control_plane::provisioning::Importer;
    for nth in 1..=10 {
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
        .unwrap()
        .load(&e.pool)
        .await
        .unwrap();
        {
            let mut fault = proxy.fault.lock().await;
            fault.fail_at = nth;
            fault.after = nth % 2 == 0;
        }
        let directory = server.directory();
        let importer = Importer {
            pool: &e.pool,
            fga: &fga,
            directory: &directory,
            operator: "root",
        };
        let error = importer
            .run(&provisioning_bundle())
            .await
            .expect_err("injected write failure");
        assert!(!format!("{error:?}").contains("private-password"));
        assert!(
            named_space(&e.pool, &e.fga, None, "Provisioned")
                .await
                .unwrap()
                .is_none()
        );
        let old: Vec<_> = proxy
            .fault
            .lock()
            .await
            .written
            .iter()
            .flat_map(|w| w["writes"]["tuple_keys"].as_array().unwrap())
            .filter_map(|k| {
                k["object"]
                    .as_str()
                    .filter(|o| o.starts_with("space:"))
                    .map(str::to_owned)
            })
            .collect();
        proxy.fault.lock().await.fail_at = 0;
        let report = importer.run(&provisioning_bundle()).await.unwrap();
        assert_eq!(report.identities_resolved, 3);
        let org = named_space(&e.pool, &e.fga, None, "Provisioned")
            .await
            .unwrap()
            .unwrap();
        assert!(
            !old.contains(&format!("space:{}", org.id)),
            "never reuse rolled-back UUID"
        );
        let team = named_space(&e.pool, &e.fga, Some(org.id), "BID")
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
    use control_plane::provisioning::Importer;
    use std::sync::Arc;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let gate = Arc::new(support::Gate::default());
    proxy.fault.lock().await.gate = Some(gate.clone());
    proxy.fault.lock().await.gate_role_write = true;
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
    let pool = e.pool.clone();
    let directory = server.directory();
    let pending = tokio::spawn(async move {
        Importer {
            pool: &pool,
            fga: &fga,
            directory: &directory,
            operator: "root",
        }
        .run(&provisioning_bundle())
        .await
    });
    tokio::time::timeout(Duration::from_secs(3), gate.entered.notified())
        .await
        .unwrap();
    assert!(
        proxy
            .fault
            .lock()
            .await
            .acknowledged
            .iter()
            .all(|s| *s == 200)
    );
    let old: Vec<_> = proxy
        .fault
        .lock()
        .await
        .written
        .iter()
        .flat_map(|w| w["writes"]["tuple_keys"].as_array().unwrap())
        .filter_map(|k| {
            k["object"]
                .as_str()
                .filter(|o| o.starts_with("space:"))
                .map(str::to_owned)
        })
        .collect();
    pending.abort();
    assert!(pending.await.unwrap_err().is_cancelled());
    assert!(
        named_space(&e.pool, &e.fga, None, "Provisioned")
            .await
            .unwrap()
            .is_none()
    );
    gate.release.notify_one();
    let directory = server.directory();
    let report = Importer {
        pool: &e.pool,
        fga: &e.fga,
        directory: &directory,
        operator: "root",
    }
    .run(&provisioning_bundle())
    .await
    .unwrap();
    let org = named_space(&e.pool, &e.fga, None, "Provisioned")
        .await
        .unwrap()
        .unwrap();
    assert!(!old.contains(&format!("space:{}", org.id)));
    assert_eq!(report.identities_created, 0);
    assert_eq!(report.spaces_reconciled, 2);
}

// Proves: I4, I5, I17
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn import_rechecks_parent_after_wait_and_repairs_existing_space_grants() {
    use control_plane::{provisioning::Importer, roles::PlatformRole};
    let e = env().await;
    let server = support::IdentityServer::start().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    e.fga
        .write_platform(
            &mut e.fga.guard(&[Scope::Platform]).await.unwrap(),
            "delegate",
            PlatformRole::PlatformOwner,
            true,
        )
        .await
        .unwrap();
    server
        .users
        .lock()
        .await
        .insert("alice".into(), "alice".into());
    server.users.lock().await.insert("bob".into(), "bob".into());
    let org = crate::support::member_organization(&e.pool, &e.fga, "Existing", "alice")
        .await
        .unwrap();
    e.fga
        .write(
            &mut e.fga.guard(&[Scope::Platform]).await.unwrap(),
            &[control_plane::fga::Tuple {
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
    let directory = server.directory();
    let bytes=br#"{"users":[{"username":"alice"},{"username":"bob","platform_roles":["platform_observer"]}],"organizations":[{"ref":"org","name":"Existing","roles":{"alice":["admin","member","organization_owner"],"bob":["member"]}}],"teams":[{"ref":"New","name":"New","organization":"org","roles":{"alice":["admin"],"bob":["analyst"]}}],"projects":[]}"#;
    let pending = tokio::spawn(async move {
        Importer {
            pool: &pool,
            fga: &fga,
            directory: &directory,
            operator: "delegate",
        }
        .run(&parse_blueprint(bytes).unwrap())
        .await
    });
    wait_for_advisory_waiter(&e.pool).await;
    delete_tuple(&e, "bob", "member", &format!("space:{}", org.id)).await;
    held.commit().await.unwrap();
    pending.await.unwrap().unwrap();
    // Import explicitly regrants the parent before granting the child, preserving I4.
    assert!(e.fga.check("bob", Permission::Read, org.id).await.unwrap());
    let team = named_space(&e.pool, &e.fga, Some(org.id), "New")
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
    .unwrap()
    .load(&e.pool)
    .await
    .unwrap();
    delete_tuple(&e, "bob", "analyst", &format!("space:{}", team.id)).await;
    proxy.fault.lock().await.fail_at = 2;
    let directory = server.directory();
    let importer = Importer {
        pool: &e.pool,
        fga: &fga,
        directory: &directory,
        operator: "delegate",
    };
    assert!(
        importer
            .run(&parse_blueprint(bytes).unwrap())
            .await
            .is_err()
    );
    proxy.fault.lock().await.fail_at = 0;
    importer
        .run(&parse_blueprint(bytes).unwrap())
        .await
        .unwrap();
    assert_eq!(
        named_space(&e.pool, &e.fga, Some(org.id), "New")
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
    let store = e.fga.store_id();
    let url = format!("{}/stores/{store}/authorization-models", e.openfga);
    let mut model: serde_json::Value =
        serde_json::from_str(include_str!("../openfga/model.json")).unwrap();
    model["type_definitions"][2]["relations"]["can_read"] =
        serde_json::json!({"computedUserset":{"relation":"admin"}});
    let published: serde_json::Value = http
        .post(&url)
        .json(&model)
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap()
        .json()
        .await
        .unwrap();
    sqlx::query("update authorization_store set model_id = $1")
        .bind(published["authorization_model_id"].as_str().unwrap())
        .execute(&e.pool)
        .await
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
    assert!(fga.load(&e.pool).await.is_err());
    let after: serde_json::Value = http.get(&url).send().await.unwrap().json().await.unwrap();
    assert_eq!(after["authorization_models"].as_array().unwrap().len(), 2);
}

// Proves: I4
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn a_timed_out_child_grant_cannot_arrive_after_parent_revocation() {
    interrupted_child_grant(false).await;
}

// Proves: I4
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn a_cancelled_child_grant_is_fenced_after_client_restart() {
    interrupted_child_grant(true).await;
}

async fn interrupted_child_grant(cancel: bool) {
    // A client timeout does not guarantee cancellation of an accepted request.
    // Hold that request before forwarding, revoke the parent after timeout, then
    // deliver it. This checks the actual invariant, not just a successful replay.
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "bob").await;
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let gate = std::sync::Arc::new(support::Gate::default());
    {
        let mut fault = proxy.fault.lock().await;
        fault.gate = Some(gate.clone());
        fault.gate_before = true;
    }
    let delayed_fga = Fga::connect(
        &proxy.base,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(1)),
    )
    .await
    .unwrap()
    .load(&e.pool)
    .await
    .unwrap();
    let (pool, open) = (e.pool.clone(), e.open_directory());
    let pending = tokio::spawn(async move {
        spaces::grant(
            &pool,
            &delayed_fga,
            &control_plane::users::Directory::Keycloak(Some(&open)),
            "alice",
            team.id,
            Role::Member,
            "bob",
        )
        .await
    });
    tokio::time::timeout(Duration::from_secs(3), gate.entered.notified())
        .await
        .expect("child write reached proxy");
    if cancel {
        pending.abort();
        assert!(pending.await.unwrap_err().is_cancelled());
    } else {
        let error = tokio::time::timeout(Duration::from_secs(3), pending)
            .await
            .expect("client request times out")
            .unwrap()
            .expect_err("unacknowledged child grant cannot report success");
        assert!(matches!(error, AppError::Internal(_)));
    }
    // Reconstruct both clients from persisted configuration/state. Recovery has no
    // in-memory pending-operation registry or retained revision to rely on.
    let restarted_pool = PgPool::connect_with((*e.pool.connect_options()).clone())
        .await
        .unwrap();
    let restarted = Fga::connect(
        &e.openfga,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap()
    .load(&restarted_pool)
    .await
    .unwrap();
    assert!(proxy.fault.lock().await.acknowledged.is_empty());

    tokio::time::timeout(
        Duration::from_secs(3),
        spaces::revoke(
            &restarted_pool,
            &restarted,
            "alice",
            org.id,
            Role::Member,
            "bob",
        ),
    )
    .await
    .expect("uncertain child write must not block revocation indefinitely")
    .expect("parent revocation sees no child grant after timeout");
    assert!(!reads(&e, "bob", org.id).await);
    gate.release.notify_one();
    tokio::time::timeout(Duration::from_secs(3), async {
        while proxy.fault.lock().await.acknowledged.is_empty() {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("delayed write has a real OpenFGA outcome");
    assert_eq!(proxy.fault.lock().await.acknowledged, vec![400]);
    let child = reads(&e, "bob", team.id).await;
    let parent = reads(&e, "bob", org.id).await;
    assert!(
        !child || parent,
        "I4 violated: delayed child grant is effective after parent revocation"
    );
}

// Proves: I5
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn a_timed_out_platform_grant_cannot_arrive_after_actor_revocation() {
    use control_plane::{platform, roles::PlatformRole as P};

    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    e.fga
        .write_platform(
            &mut e.fga.guard(&[Scope::Platform]).await.unwrap(),
            "delegate",
            P::PlatformOwner,
            true,
        )
        .await
        .unwrap();
    let directory = support::IdentityServer::start().await;
    directory
        .users
        .lock()
        .await
        .insert("target".into(), "target".into());
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let gate = std::sync::Arc::new(support::Gate::default());
    {
        let mut fault = proxy.fault.lock().await;
        fault.gate = Some(gate.clone());
        fault.gate_before = true;
    }
    let delayed_fga = Fga::connect(
        &proxy.base,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(1)),
    )
    .await
    .unwrap()
    .load(&e.pool)
    .await
    .unwrap();
    let pool = e.pool.clone();
    let client = directory.directory();
    let pending = tokio::spawn(async move {
        platform::grant(
            &pool,
            &delayed_fga,
            Some(&client),
            "delegate",
            "target",
            P::PromptEditor,
        )
        .await
    });
    tokio::time::timeout(Duration::from_secs(3), gate.entered.notified())
        .await
        .expect("platform write reached proxy");
    let error = tokio::time::timeout(Duration::from_secs(3), pending)
        .await
        .expect("client request times out")
        .unwrap()
        .expect_err("unacknowledged platform grant cannot report success");
    assert!(matches!(error, AppError::Internal(_)));
    assert!(proxy.fault.lock().await.acknowledged.is_empty());
    tokio::time::timeout(
        Duration::from_secs(3),
        platform::revoke(&e.pool, &e.fga, "root", "delegate", P::PlatformOwner),
    )
    .await
    .expect("uncertain platform write must not block revocation indefinitely")
    .unwrap();
    assert!(!e.fga.is_platform_owner("delegate").await.unwrap());
    gate.release.notify_one();
    tokio::time::timeout(Duration::from_secs(3), async {
        while proxy.fault.lock().await.acknowledged.is_empty() {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("delayed write has a real OpenFGA outcome");
    assert_eq!(proxy.fault.lock().await.acknowledged, vec![400]);
    assert!(
        !e.fga
            .effective_platform_roles("target")
            .await
            .unwrap()
            .contains(&P::PromptEditor),
        "I5 violated: delayed platform grant is effective after actor revocation"
    );
}

// Protocol-level coverage of OpenFGA atomicity, in addition to service regressions.
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn openfga_strict_guard_delete_rejects_an_entire_delayed_write() {
    use serde_json::{Value, json};

    let e = env().await;
    let http = reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
        .unwrap();
    let store = e.fga.store_id();
    let parent = Uuid::new_v4();
    let child = Uuid::new_v4();
    let key = |user: &str, relation: &str, object: String| json!({"user":user,"relation":relation,"object":object});
    let guard = |revision: &str| key(revision, "version", "guard:organization".into());
    let original = guard("revision:original");
    let retired = guard("revision:revocation");
    let stale = guard("revision:delayed");
    let parent_role = key("user:bob", "member", format!("space:{parent}"));
    let child_role = key("user:bob", "member", format!("space:{child}"));
    let write_url = format!("{}/stores/{store}/write", e.openfga);
    http.post(&write_url)
        .json(&json!({"writes":{"tuple_keys":[&original,&parent_role]}}))
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap();

    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let gate = std::sync::Arc::new(support::Gate::default());
    {
        let mut fault = proxy.fault.lock().await;
        fault.gate = Some(gate.clone());
        fault.gate_before = true;
    }
    let pending = http
        .post(format!("{}/stores/{store}/write", proxy.base))
        .timeout(Duration::from_secs(1))
        .json(&json!({
            "writes":{"tuple_keys":[&stale,&child_role],"on_duplicate":"ignore"},
            "deletes":{"tuple_keys":[&original],"on_missing":"error"}
        }));
    let pending = tokio::spawn(async move { pending.send().await });
    tokio::time::timeout(Duration::from_secs(3), gate.entered.notified())
        .await
        .expect("delayed write reached proxy");
    assert!(
        tokio::time::timeout(Duration::from_secs(3), pending)
            .await
            .unwrap()
            .unwrap()
            .unwrap_err()
            .is_timeout()
    );
    assert!(proxy.fault.lock().await.acknowledged.is_empty());

    http.post(&write_url)
        .json(&json!({
            "writes":{"tuple_keys":[&retired]},
            "deletes":{"tuple_keys":[&original,&parent_role],"on_missing":"error"}
        }))
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap();
    gate.release.notify_one();
    tokio::time::timeout(Duration::from_secs(3), async {
        while proxy.fault.lock().await.acknowledged.is_empty() {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("delayed write reaches real OpenFGA");
    assert_eq!(proxy.fault.lock().await.acknowledged, vec![400]);
    assert!(!e.fga.check("bob", Permission::Read, parent).await.unwrap());
    assert!(!e.fga.check("bob", Permission::Read, child).await.unwrap());

    // Both contenders target the same version. At most one
    // can change roles; the losing transaction must leave no role or guard behind.
    let winner_a = guard("revision:winner-a");
    let winner_b = guard("revision:winner-b");
    let role_a = key("user:alice", "member", format!("space:{child}"));
    let role_b = key("user:bob", "member", format!("space:{child}"));
    let body_a = json!({"writes":{"tuple_keys":[&winner_a,&role_a]},
        "deletes":{"tuple_keys":[&retired],"on_missing":"error"}});
    let body_b = json!({"writes":{"tuple_keys":[&winner_b,&role_b]},
        "deletes":{"tuple_keys":[&retired],"on_missing":"error"}});
    let (a, b) = tokio::join!(
        http.post(&write_url).json(&body_a).send(),
        http.post(&write_url).json(&body_b).send(),
    );
    let (a, b) = (a.unwrap().status(), b.unwrap().status());
    assert_ne!(
        a.is_success(),
        b.is_success(),
        "one guard consumer wins: {a}, {b}"
    );
    let loser = if a.is_success() { b } else { a };
    assert!(
        matches!(loser.as_u16(), 400 | 409),
        "losing guard consumer reports a conflict, not an unrelated failure: {loser}"
    );
    assert_eq!(
        e.fga.check("alice", Permission::Read, child).await.unwrap(),
        a.is_success()
    );
    assert_eq!(
        e.fga.check("bob", Permission::Read, child).await.unwrap(),
        b.is_success()
    );
    let versions: Value = http.post(format!("{}/stores/{store}/read", e.openfga))
        .json(&json!({"tuple_key":{"object":"guard:organization"},"consistency":"HIGHER_CONSISTENCY"}))
        .send().await.unwrap().error_for_status().unwrap().json().await.unwrap();
    assert_eq!(versions["tuples"].as_array().unwrap().len(), 1);
    let actual = &versions["tuples"][0]["key"];
    let expected = if a.is_success() { winner_a } else { winner_b };
    for field in ["user", "relation", "object"] {
        assert_eq!(actual[field], expected[field]);
    }
    assert!(actual["condition"].is_null());
}

// Proves: I4, I5
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn noop_revocation_and_multiple_scopes_fence_stale_attempts() {
    use control_plane::fga::Tuple;
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let mut stale = e.fga.guard(&[Scope::Organization(org.id)]).await.unwrap();
    // Bob does not hold this role: successful no-op still consumes the revision.
    spaces::revoke(&e.pool, &e.fga, "alice", team.id, Role::Member, "bob")
        .await
        .unwrap();
    assert!(
        e.fga
            .write(
                &mut stale,
                &[Tuple {
                    user: "bob",
                    role: Role::Member,
                    space: team.id
                }],
                &[]
            )
            .await
            .is_err()
    );
    assert!(!reads(&e, "bob", team.id).await);
    let mut combined = e
        .fga
        .guard(&[Scope::Platform, Scope::Organization(org.id)])
        .await
        .unwrap();
    let mut org_only = e.fga.guard(&[Scope::Organization(org.id)]).await.unwrap();
    e.fga
        .fence(&mut e.fga.guard(&[Scope::Platform]).await.unwrap())
        .await
        .unwrap();
    assert!(
        e.fga
            .write(
                &mut combined,
                &[Tuple {
                    user: "bob",
                    role: Role::Member,
                    space: team.id
                }],
                &[]
            )
            .await
            .is_err()
    );
    // Failure of either revision rolls back every guard and role, including org's.
    e.fga.fence(&mut org_only).await.unwrap();
    assert!(!reads(&e, "bob", team.id).await);
    assert!(
        e.fga.fence(&mut combined).await.is_err(),
        "failed decisions cannot reuse/refresh a guard"
    );
}

// Proves: I5
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn sql_mutation_loses_to_a_delayed_revocation_after_its_check() {
    use std::sync::Arc;
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Editor, "bob").await;
    let revoke_proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let revoke_gate = Arc::new(support::Gate::default());
    {
        let mut f = revoke_proxy.fault.lock().await;
        f.gate = Some(revoke_gate.clone());
        f.gate_before = true;
    }
    let revoker = Fga::connect(
        &revoke_proxy.base,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_millis(500)),
    )
    .await
    .unwrap()
    .load(&e.pool)
    .await
    .unwrap();
    let pool = e.pool.clone();
    let pending = tokio::spawn(async move {
        spaces::revoke(&pool, &revoker, "alice", team.id, Role::Editor, "bob").await
    });
    tokio::time::timeout(Duration::from_secs(3), revoke_gate.entered.notified())
        .await
        .unwrap();
    assert!(pending.await.unwrap().is_err());
    let sql_proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let sql_gate = Arc::new(support::Gate::default());
    {
        let mut f = sql_proxy.fault.lock().await;
        f.gate = Some(sql_gate.clone());
        f.gate_before = true;
    }
    let writer = Fga::connect(
        &sql_proxy.base,
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
    let pool = e.pool.clone();
    let id = Uuid::new_v4();
    let pending = tokio::spawn(async move {
        let mut tx = spaces::authorized_write(&pool, &writer, "bob", team.id).await?;
        db::insert_folder(
            &mut *tx,
            &Folder {
                created_at: chrono::Utc::now(),
                id,
                space_id: team.id,
                parent_id: None,
                name: "must-not-exist".into(),
                path: domain::folder_path(None, id),
            },
        )
        .await?;
        tx.commit().await?;
        Ok::<_, AppError>(())
    });
    // The local write has passed Check and reached its fence.
    tokio::time::timeout(Duration::from_secs(3), sql_gate.entered.notified())
        .await
        .unwrap();
    revoke_gate.release.notify_one();
    tokio::time::timeout(Duration::from_secs(3), async {
        while revoke_proxy.fault.lock().await.acknowledged.is_empty() {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();
    assert_eq!(revoke_proxy.fault.lock().await.acknowledged, vec![200]);
    sql_gate.release.notify_one();
    assert!(matches!(pending.await.unwrap(), Err(AppError::Conflict(_))));
    assert!(matches!(
        db::folder(&e.pool, id).await,
        Err(sqlx::Error::RowNotFound)
    ));
}

// Proves: I5
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn folder_creation_keeps_one_connection_through_placement_and_write() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let parent = spaces::create_folder(&e.pool, &e.fga, "alice", team.id, None, "parent".into())
        .await
        .unwrap();
    let pool = sqlx::postgres::PgPoolOptions::new()
        .max_connections(1)
        .connect_with((*e.pool.connect_options()).clone())
        .await
        .unwrap();
    let child = tokio::time::timeout(
        Duration::from_secs(3),
        spaces::create_folder(
            &pool,
            &e.fga,
            "alice",
            team.id,
            Some(parent.id),
            "child".into(),
        ),
    )
    .await
    .expect("folder mutation never waits for a second connection")
    .unwrap();
    assert_eq!(child.path, domain::folder_path(Some(&parent), child.id));
    assert_eq!(db::folder(&pool, child.id).await.unwrap().space_id, team.id);
    assert_eq!(db::space(&pool, org.id).await.unwrap().id, org.id);
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn waiting_content_writers_release_the_shared_pool() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let peer = crate::support::member_organization(&e.pool, &e.fga, "peer", "carol")
        .await
        .unwrap();
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "carol",
        peer.id,
        Role::Editor,
        "carol",
    )
    .await
    .unwrap();
    // One connection makes any connection retained by a waiter observable.
    let pool = sqlx::postgres::PgPoolOptions::new()
        .max_connections(1)
        .connect_with((*e.pool.connect_options()).clone())
        .await
        .unwrap();
    let held = hold_organization_lock(&e, org.id).await;
    let since = sqlx::query_scalar("select clock_timestamp()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    let mut writers = tokio::task::JoinSet::new();
    for index in 0..10 {
        let (pool, fga) = (pool.clone(), e.fga.clone());
        writers.spawn(async move {
            spaces::create_folder(
                &pool,
                &fga,
                "alice",
                team.id,
                None,
                format!("waiting-{index}"),
            )
            .await
        });
    }
    wait_for_write_retry(&e.pool, since).await;
    let peer_folder = tokio::time::timeout(
        Duration::from_secs(2),
        spaces::create_folder(&pool, &e.fga, "carol", peer.id, None, "unrelated".into()),
    )
    .await
    .expect("contended organization must not retain the shared connection")
    .unwrap();
    assert_eq!(peer_folder.space_id, peer.id);
    assert!(writers.try_join_next().is_none());
    held.commit().await.unwrap();
    while let Some(result) = writers.join_next().await {
        result.unwrap().unwrap();
    }
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn content_lock_deadline_and_cancellation_leave_no_mutation() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let held = hold_organization_lock(&e, org.id).await;
    let before = std::time::Instant::now();
    let result = tokio::time::timeout(
        Duration::from_secs(7),
        spaces::create_folder(&e.pool, &e.fga, "alice", team.id, None, "deadline".into()),
    )
    .await
    .expect("lock acquisition has a five-second deadline");
    assert!(before.elapsed() >= Duration::from_secs(5));
    assert!(matches!(result, Err(AppError::Unavailable(_))));
    let since = sqlx::query_scalar("select clock_timestamp()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    let (pool, fga) = (e.pool.clone(), e.fga.clone());
    let pending = tokio::spawn(async move {
        spaces::create_folder(&pool, &fga, "alice", team.id, None, "cancelled".into()).await
    });
    wait_for_write_retry(&e.pool, since).await;
    pending.abort();
    assert!(pending.await.unwrap_err().is_cancelled());
    held.commit().await.unwrap();
    let count: i64 =
        sqlx::query_scalar("select count(*) from folder where name in ('deadline', 'cancelled')")
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(count, 0);
    spaces::create_folder(
        &e.pool,
        &e.fga,
        "alice",
        team.id,
        None,
        "after-cancel".into(),
    )
    .await
    .unwrap();
}

// Proves: I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn competing_empty_initializers_converge_on_the_published_binding() {
    let e = env().await;
    sqlx::query("delete from authorization_store")
        .execute(&e.pool)
        .await
        .unwrap();
    // Deterministically reproduce name-discovery race: two source stores share a name.
    // Each initializer captured one before publication; the logical name is the binding.
    let source_a = Fga::connect(
        &e.openfga,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap();
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    proxy.fault.lock().await.hide_stores = true; // Second boot's stale empty discovery.
    let source_b = Fga::connect(
        &proxy.base,
        &e.store,
        true,
        false,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap();
    proxy.fault.lock().await.hide_stores = false;
    assert_ne!(
        source_a.store_id(),
        source_b.store_id(),
        "two boots captured distinct source stores"
    );
    let ambiguous = Fga::connect(
        &e.openfga,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap();
    assert!(
        ambiguous.clone().initialize(&e.pool).await.is_err(),
        "unbound ambiguity requires repair"
    );
    let (a, b) = tokio::join!(source_a.initialize(&e.pool), source_b.initialize(&e.pool));
    let (a, b) = (a.unwrap(), b.unwrap());
    assert_eq!(a.store_id(), b.store_id());
    assert_eq!(
        ambiguous.load(&e.pool).await.unwrap().store_id(),
        a.store_id(),
        "published destination wins over ambiguous legacy discovery"
    );
}

// Test data names the actual four ZIP sections; no legacy fixture conversion.
fn fixture_zip(bytes: &[u8]) -> Vec<u8> {
    use std::io::{Cursor, Write};
    let value: serde_json::Value = serde_json::from_slice(bytes).unwrap();
    let mut zip = zip::ZipWriter::new(Cursor::new(Vec::new()));
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);
    zip.start_file("manifest.json", options).unwrap();
    zip.write_all(br#"{"format_version":2,"users_schema_version":2,"source_platform":"swift"}"#)
        .unwrap();
    for section in ["users", "organizations", "teams", "projects"] {
        zip.start_file(format!("{section}.json"), options).unwrap();
        zip.write_all(&serde_json::to_vec(&value[section]).unwrap())
            .unwrap();
    }
    zip.finish().unwrap().into_inner()
}
fn parse_blueprint(
    bytes: &[u8],
) -> Result<control_plane::provisioning::Bundle, control_plane::blueprint::InputError> {
    control_plane::provisioning::Bundle::parse(&fixture_zip(bytes))
}

async fn http_import(
    app: &axum::Router,
    bearer: &str,
    zip: &[u8],
) -> (axum::http::StatusCode, serde_json::Value) {
    use tower::ServiceExt;
    let mut body=b"--manager-boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"bundle.zip\"\r\nContent-Type: application/zip\r\n\r\n".to_vec();
    body.extend_from_slice(zip);
    body.extend_from_slice(b"\r\n--manager-boundary--\r\n");
    let response = app
        .clone()
        .oneshot(
            axum::http::Request::builder()
                .method("POST")
                .uri("/import-export/import")
                .header("Authorization", format!("Bearer {bearer}"))
                .header(
                    "Content-Type",
                    "multipart/form-data; boundary=manager-boundary",
                )
                .body(axum::body::Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let bytes = axum::body::to_bytes(response.into_body(), 100_000)
        .await
        .unwrap();
    (status, serde_json::from_slice(&bytes).unwrap())
}

// Proves: I1, I4, I8, I15, I17, I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn blueprint_http_hierarchy_isolation_preflight_and_safe_errors() {
    use control_plane::api::{AppState, routes};
    use tower::ServiceExt;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let auth = std::sync::Arc::new(server.auth().await);
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let app = routes(AppState {
        onboarding: Default::default(),
        lifecycle: Default::default(),
        auth: auth.clone(),
        pool: e.pool.clone(),
        fga: e.fga.clone(),
        directory: Some(directory.clone()),
        content: None,
        processing: None,
    });
    let token = server.token("root");
    let mut value = serde_json::json!({"users":[{"username":"alice","password":"private-password"},{"username":"bob","password":"private-password"}],"organizations":[{"ref":"a","name":"A","roles":{"alice":["admin","member","organization_owner"]}},{"ref":"b","name":"B","roles":{"bob":["admin","member","organization_owner"]}}],"teams":[{"ref":"at","name":"Team","organization":"a","roles":{"alice":["admin","member"]}},{"ref":"bt","name":"Team","organization":"b","roles":{"bob":["admin","analyst"]}}],"projects":[{"ref":"ap","name":"Project","team":"at","roles":{"alice":["admin","editor"]}},{"ref":"bp","name":"Project","team":"bt","roles":{"bob":["admin"]}}]});
    // Malformed upload is never parsed for a caller lacking platform authority.
    for (bearer, status) in [("invalid".to_owned(), 401), (server.token("ordinary"), 403)] {
        let response = app
            .clone()
            .oneshot(
                axum::http::Request::builder()
                    .method("POST")
                    .uri("/import-export/import")
                    .header("Authorization", format!("Bearer {bearer}"))
                    .body(axum::body::Body::from("not multipart"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), status);
    }
    for body in [
        "--manager-boundary--\r\n",
        "--manager-boundary\r\nContent-Disposition: form-data; name=\"wrong\"\r\n\r\n{}\r\n--manager-boundary--\r\n",
        "--manager-boundary\r\nContent-Disposition: form-data; name=\"file\"\r\n\r\n{}\r\n--manager-boundary\r\nContent-Disposition: form-data; name=\"file\"\r\n\r\n{}\r\n--manager-boundary--\r\n",
    ] {
        let response = app
            .clone()
            .oneshot(
                axum::http::Request::builder()
                    .method("POST")
                    .uri("/import-export/import")
                    .header("Authorization", format!("Bearer {token}"))
                    .header(
                        "Content-Type",
                        "multipart/form-data; boundary=manager-boundary",
                    )
                    .body(axum::body::Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), 400);
        let detail: serde_json::Value = serde_json::from_slice(
            &axum::body::to_bytes(response.into_body(), 1000)
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(detail["detail"], "expected one multipart file");
    }
    assert!(server.users.lock().await.is_empty());
    for input in [b"{}".as_slice(), b"[old JSON]"] {
        let (s, b) = http_import(&app, &token, input).await;
        assert_eq!(s, 422);
        assert_eq!(b["detail"], "not_yet_supported");
    }
    let (s, b) = http_import(&app, &token, b"private-password malformed archive").await;
    assert_eq!(s, 422);
    assert!(!b.to_string().contains("private-password"));
    value["teams"][1]["roles"]["bob"] = serde_json::json!(["admin"]);
    let (s, b) = http_import(
        &app,
        &token,
        &fixture_zip(&serde_json::to_vec(&value).unwrap()),
    )
    .await;
    assert_eq!(s, 422, "{b}");
    assert!(server.users.lock().await.is_empty());
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );
    value["teams"][1]["roles"]["bob"] = serde_json::json!(["admin", "analyst"]);
    // Owner exists only on organizations; a team owner is rejected before identities.
    value["teams"][0]["roles"]["alice"] =
        serde_json::json!(["admin", "member", "organization_owner"]);
    let (s, b) = http_import(
        &app,
        &token,
        &fixture_zip(&serde_json::to_vec(&value).unwrap()),
    )
    .await;
    assert_eq!(s, 422, "{b}");
    assert!(server.users.lock().await.is_empty());
    value["teams"][0]["roles"]["alice"] = serde_json::json!(["admin", "member"]);
    // A new organization needs a declared owner as well as an admin.
    value["organizations"][0]["roles"]["alice"] = serde_json::json!(["admin", "member"]);
    let (s, b) = http_import(
        &app,
        &token,
        &fixture_zip(&serde_json::to_vec(&value).unwrap()),
    )
    .await;
    assert_eq!(s, 422, "{b}");
    assert!(server.users.lock().await.is_empty());
    value["organizations"][0]["roles"]["alice"] =
        serde_json::json!(["admin", "member", "organization_owner"]);
    server.control.lock().await.fail_create = true;
    let (s, b) = http_import(
        &app,
        &token,
        &fixture_zip(&serde_json::to_vec(&value).unwrap()),
    )
    .await;
    assert_eq!(s, 503, "{b}");
    assert!(b["detail"].as_str().unwrap().contains("identities"));
    assert!(!b.to_string().contains("private-password"));
    server.control.lock().await.fail_create = false;
    let bytes = fixture_zip(&serde_json::to_vec(&value).unwrap());
    for expected_created in [2, 0] {
        let (s, b) = http_import(&app, &token, &bytes).await;
        assert_eq!(s, 200, "{b}");
        assert_eq!(b["identities_created"], expected_created);
        assert_eq!(b["spaces_reconciled"], 6);
    }
    let alice = directory.find_username("alice").await.unwrap().unwrap().id;
    let bob = directory.find_username("bob").await.unwrap().unwrap().id;
    let mut ids = Vec::new();
    for (name, subject, other) in [("A", &alice, &bob), ("B", &bob, &alice)] {
        let org = named_space(&e.pool, &e.fga, None, name)
            .await
            .unwrap()
            .unwrap();
        let team = named_space(&e.pool, &e.fga, Some(org.id), "Team")
            .await
            .unwrap()
            .unwrap();
        let project = named_space(&e.pool, &e.fga, Some(team.id), "Project")
            .await
            .unwrap()
            .unwrap();
        assert_eq!(project.path, vec![org.id, team.id, project.id]);
        for space in [org.id, team.id, project.id] {
            assert!(
                e.fga
                    .check(subject, Permission::Manage, space)
                    .await
                    .unwrap()
            );
            assert!(!e.fga.check(other, Permission::Read, space).await.unwrap());
            assert!(!e.fga.check(other, Permission::Manage, space).await.unwrap());
        }
        ids.push(project.id);
    }
    assert_ne!(ids[0], ids[1]);
    // Internal SQL failures expose a phase and counters, never database diagnostics.
    sqlx::raw_sql("CREATE FUNCTION fail_import_fixture() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.name = 'Internal failure' THEN RAISE EXCEPTION 'private-password'; END IF; RETURN NEW; END $$; CREATE TRIGGER fail_import_fixture BEFORE INSERT ON space FOR EACH ROW EXECUTE FUNCTION fail_import_fixture();").execute(&e.pool).await.unwrap();
    let failing=fixture_zip(br#"{"users":[{"username":"failure-owner","password":"private-password"}],"organizations":[{"ref":"bad","name":"Internal failure","roles":{"failure-owner":["admin","organization_owner"]}}],"teams":[],"projects":[]}"#);
    let (status, body) = http_import(&app, &token, &failing).await;
    assert_eq!(status, 500, "{body}");
    assert!(body["detail"].as_str().unwrap().contains("roles/spaces"));
    assert!(!body.to_string().contains("private-password"));
    sqlx::raw_sql(
        "DROP TRIGGER fail_import_fixture ON space; DROP FUNCTION fail_import_fixture();",
    )
    .execute(&e.pool)
    .await
    .unwrap();
    // Oversized upload is rejected before parsing or writes.
    let (s, b) = http_import(
        &app,
        &token,
        &vec![0; control_plane::blueprint::MAX_ARCHIVE + 1],
    )
    .await;
    assert_eq!(s, 413, "{b}");
}

// Proves: I1, I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn blueprint_preflight_reads_child_names_after_organization_lock() {
    let e = env().await;
    let server = support::IdentityServer::start().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    server
        .users
        .lock()
        .await
        .insert("alice".into(), "alice".into());
    let org = crate::support::member_organization(&e.pool, &e.fga, "Existing", "alice")
        .await
        .unwrap();
    let mut held = hold_organization_lock(&e, org.id).await;
    let id = Uuid::new_v4();
    // An incompatible child kind, linked and inserted while the organization is locked.
    let row = control_plane::domain::SpaceRow {
        id,
        kind: SpaceKind::Project,
        name: "Collision".into(),
        personal_owner: None,
        parent_id: Some(org.id),
        organization_id: org.id,
    };
    db::insert_space(&mut held, &Space::from(row))
        .await
        .unwrap();
    let mut guard = e.fga.guard(&[Scope::Organization(org.id)]).await.unwrap();
    e.fga
        .write_created(
            &mut guard,
            &[control_plane::fga::Link::Parent {
                child: id,
                parent: org.id,
            }],
            &[],
        )
        .await
        .unwrap();
    let app = control_plane::api::routes(control_plane::api::AppState {
        onboarding: Default::default(),
        lifecycle: Default::default(),
        auth: std::sync::Arc::new(server.auth().await),
        pool: e.pool.clone(),
        fga: e.fga.clone(),
        directory: Some(server.directory()),
        content: None,
        processing: None,
    });
    let token = server.token("root");
    let pending = tokio::spawn(async move {
        http_import(&app,&token,&fixture_zip(br#"{"users":[{"username":"alice"},{"username":"tail","password":"private-password"}],"organizations":[{"ref":"org","name":"Existing","roles":{"tail":["member"]}}],"teams":[{"ref":"team","name":"Collision","organization":"org","roles":{"tail":["admin"]}}],"projects":[]}"#)).await
    });
    wait_for_advisory_waiter(&e.pool).await;
    held.commit().await.unwrap();
    let (status, body) = tokio::time::timeout(Duration::from_secs(5), pending)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(status, 409, "{body}");
    assert!(body["detail"].as_str().unwrap().contains("preflight"));
    assert!(!server.users.lock().await.contains_key("tail"));
    assert!(server.control.lock().await.created.is_empty());
}

// Proves: I9, I19
#[tokio::test]
#[ignore = "needs disposable services: make test-integration"]
async fn consent_and_root_bootstrap_are_personal_and_do_not_create_memberships() {
    use axum::{
        body::{Body, to_bytes},
        http::Request,
    };
    use control_plane::{
        api::{AppState, routes},
        onboarding::{self, Onboarding},
    };
    use serde_json::{Value, json};
    use std::sync::Arc;
    use tower::ServiceExt;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let state = AppState {
        auth: Arc::new(server.auth().await),
        pool: e.pool.clone(),
        fga: e.fga.clone(),
        directory: None,
        content: None,
        processing: None,
        lifecycle: Default::default(),
        onboarding: Onboarding {
            gcu_version: Some("v1".into()),
            bootstrap_token_env_var: Some("CONTROL_PLANE_TEST_BOOTSTRAP_TOKEN".into()),
            ..Default::default()
        },
    };
    let app = routes(state.clone());
    let request = |method: &str, path: &str, token: Option<String>, body: Value| {
        let mut req = Request::builder()
            .method(method)
            .uri(path)
            .header("content-type", "application/json");
        if let Some(token) = token {
            req = req.header("authorization", format!("Bearer {token}"));
        }
        req.body(Body::from(body.to_string())).unwrap()
    };
    let secret = json!({"token": std::env::var("CONTROL_PLANE_TEST_BOOTSTRAP_TOKEN").unwrap()});
    let public = app
        .clone()
        .oneshot(request("GET", "/frontend/config", None, Value::Null))
        .await
        .unwrap();
    assert_eq!(public.status(), 200);
    assert_eq!(public.headers()["cache-control"], "no-store");
    let config: Value =
        serde_json::from_slice(&to_bytes(public.into_body(), 65536).await.unwrap()).unwrap();
    assert_eq!(config["root_bootstrap_required"], true);
    for (method, path, body, expected) in [
        ("GET", "/me", Value::Null, 403),
        ("GET", "/me/spaces", Value::Null, 403),
        ("POST", "/import-export/import", Value::Null, 403),
        ("POST", "/bootstrap/platform-admin", secret.clone(), 403),
        ("POST", "/gcu", json!({"version":"old"}), 409),
        (
            "POST",
            "/gcu",
            json!({"version":"v1", "user_id":"bob"}),
            422,
        ),
        (
            "POST",
            "/gcu?on_behalf_of=bob",
            json!({"version":"v1"}),
            403,
        ),
    ] {
        assert_eq!(
            app.clone()
                .oneshot(request(method, path, Some(server.token("root")), body))
                .await
                .unwrap()
                .status(),
            expected,
            "{path}"
        );
    }
    assert!(!onboarding::bootstrap_completed(&e.pool).await.unwrap());
    assert!(
        onboarding::acceptance(&e.pool, "root")
            .await
            .unwrap()
            .is_none()
    );
    // Neither an anonymous caller nor a client-credentials principal can consent or claim root.
    let now = chrono::Utc::now().timestamp();
    let service = server.sign(json!({"sub":"service", "iss":server.realm,"aud":"app","iat":now,"exp":now+300,"preferred_username":"service-account-manager", "azp":"manager", "client_id":"manager"}));
    assert!(
        state
            .auth
            .authenticate(Some(&service))
            .await
            .unwrap()
            .service_account
    );
    let agent = server.sign(json!({"sub":"agent", "iss":server.realm,"aud":"app","iat":now,"exp":now+300,"resource_access":{"app":{"roles":["service_agent"]}}}));
    for token in [None, Some(service), Some(agent)] {
        for (path, body) in [
            ("/gcu", json!({"version":"v1"})),
            ("/bootstrap/platform-admin", secret.clone()),
        ] {
            assert_eq!(
                app.clone()
                    .oneshot(request("POST", path, token.clone(), body))
                    .await
                    .unwrap()
                    .status(),
                if token.is_some() { 403 } else { 401 }
            );
        }
    }
    assert_eq!(
        app.clone()
            .oneshot(request(
                "POST",
                "/gcu",
                Some(server.token("root")),
                json!({"version":"v1"})
            ))
            .await
            .unwrap()
            .status(),
        204
    );
    let first = onboarding::acceptance(&e.pool, "root")
        .await
        .unwrap()
        .unwrap();
    assert_eq!(
        app.clone()
            .oneshot(request(
                "POST",
                "/gcu",
                Some(server.token("root")),
                json!({"version":"v1"})
            ))
            .await
            .unwrap()
            .status(),
        204
    );
    assert_eq!(
        onboarding::acceptance(&e.pool, "root")
            .await
            .unwrap()
            .unwrap()
            .accepted_at,
        first.accepted_at
    );
    assert!(
        e.fga
            .effective_platform_roles("root")
            .await
            .unwrap()
            .is_empty()
    );
    assert_eq!(
        app.clone()
            .oneshot(request(
                "POST",
                "/bootstrap/platform-admin",
                Some(server.token("root")),
                json!({"token":"wrong-but-long-enough"})
            ))
            .await
            .unwrap()
            .status(),
        403
    );
    assert_eq!(
        app.clone()
            .oneshot(request(
                "POST",
                "/bootstrap/platform-admin",
                Some(server.token("root")),
                secret.clone()
            ))
            .await
            .unwrap()
            .status(),
        200
    );
    assert!(onboarding::bootstrap_completed(&e.pool).await.unwrap());
    assert_eq!(
        app.clone()
            .oneshot(request(
                "POST",
                "/bootstrap/platform-admin",
                Some(server.token("root")),
                secret
            ))
            .await
            .unwrap()
            .status(),
        409
    );
    assert!(
        onboarding::acceptance(&e.pool, "bob")
            .await
            .unwrap()
            .is_none()
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );
    let mut next = state.clone();
    next.onboarding.gcu_version = Some("v2".into());
    let upgraded = routes(next);
    assert_eq!(
        upgraded
            .clone()
            .oneshot(request(
                "GET",
                "/me",
                Some(server.token("root")),
                Value::Null
            ))
            .await
            .unwrap()
            .status(),
        403
    );
    assert_eq!(
        upgraded
            .clone()
            .oneshot(request(
                "POST",
                "/gcu",
                Some(server.token("root")),
                json!({"version":"v1"})
            ))
            .await
            .unwrap()
            .status(),
        409
    );
    assert_eq!(
        upgraded
            .clone()
            .oneshot(request(
                "POST",
                "/gcu",
                Some(server.token("root")),
                json!({"version":"v2"})
            ))
            .await
            .unwrap()
            .status(),
        204
    );
    assert_eq!(
        upgraded
            .oneshot(request(
                "GET",
                "/me",
                Some(server.token("root")),
                Value::Null
            ))
            .await
            .unwrap()
            .status(),
        200
    );
    let mut disabled = state;
    disabled.onboarding.gcu_version = None;
    assert_eq!(
        routes(disabled)
            .oneshot(request(
                "GET",
                "/me",
                Some(server.token("bob")),
                Value::Null
            ))
            .await
            .unwrap()
            .status(),
        200
    );
}

/// TSN > BID > project P, all administered by alice, who is a member of TSN and BID.
async fn tree(e: &Env) -> (Space, Space, Space) {
    let (org, team) = org_and_team(e).await;
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
    (org, team, project)
}

// Proves: I6, I8, I20
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn descending_roles_reach_projects_and_member_stays_local() {
    use control_plane::roles::SpacePermission as P;
    let e = env().await;
    let (org, team, project) = tree(&e).await;
    for (user, role) in [
        ("bob", Role::Editor),
        ("ana", Role::Analyst),
        ("max", Role::Member),
        ("claire", Role::Member),
        ("pat", Role::Member),
    ] {
        grant(&e, org.id, role, user).await;
    }
    for space in [org.id, team.id, project.id] {
        assert!(reads(&e, "bob", space).await);
        assert!(e.fga.check("bob", Permission::Write, space).await.unwrap());
        assert!(reads(&e, "ana", space).await);
        assert!(!e.fga.check("ana", Permission::Write, space).await.unwrap());
        for p in [
            P::RunEvaluations,
            P::ManageEvaluationCorpus,
            P::ReadConversationsForEvaluation,
        ] {
            assert!(e.fga.check_space("ana", p, space).await.unwrap());
            assert!(!e.fga.check_space("bob", p, space).await.unwrap());
        }
    }
    assert!(reads(&e, "max", org.id).await);
    assert!(!reads(&e, "max", team.id).await && !reads(&e, "max", project.id).await);

    // A team administrator manages its projects and reads none of their content.
    grant(&e, team.id, Role::Admin, "claire").await;
    assert!(
        e.fga
            .check("claire", Permission::Manage, project.id)
            .await
            .unwrap()
    );
    assert!(!reads(&e, "claire", team.id).await && !reads(&e, "claire", project.id).await);

    // A personal space inherits nothing, and its organization still manages it.
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        org.id,
        Role::PersonalSpaceCreator,
        "pat",
    )
    .await
    .unwrap();
    let personal = spaces::create_personal_space(&e.pool, &e.fga, "pat", org.id)
        .await
        .unwrap()
        .0;
    assert_eq!(
        (personal.parent_id, personal.path.clone()),
        (None, vec![personal.id])
    );
    for user in ["bob", "ana", "alice"] {
        assert!(!reads(&e, user, personal.id).await);
    }
    assert!(
        !e.fga
            .check("bob", Permission::Write, personal.id)
            .await
            .unwrap()
    );
    let again = spaces::create_personal_space(&e.pool, &e.fga, "pat", org.id).await;
    assert_eq!(again.unwrap().0.id, personal.id);
    spaces::revoke(&e.pool, &e.fga, "alice", personal.id, Role::Editor, "pat")
        .await
        .unwrap();
}

// Proves: I4
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn inherited_access_does_not_replace_parent_membership() {
    let e = env().await;
    let (org, team, project) = tree(&e).await;
    grant(&e, org.id, Role::Editor, "bob").await;
    assert!(reads(&e, "bob", team.id).await);
    let refused = spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        project.id,
        Role::Member,
        "bob",
    )
    .await;
    assert!(matches!(refused, Err(AppError::Conflict(_))));
    let nominated = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Project,
        team.id,
        "Q".into(),
        "bob",
    )
    .await;
    assert!(matches!(nominated, Err(AppError::Conflict(_))));

    grant(&e, team.id, Role::Member, "bob").await;
    grant(&e, project.id, Role::Member, "bob").await;
    // Editor is bob's only content role on TSN while he holds a role in BID.
    let blocked = spaces::revoke(&e.pool, &e.fga, "alice", org.id, Role::Editor, "bob").await;
    assert!(matches!(blocked, Err(AppError::Conflict(_))));
    grant(&e, org.id, Role::Member, "bob").await;
    spaces::revoke(&e.pool, &e.fga, "alice", org.id, Role::Editor, "bob")
        .await
        .unwrap();
    assert!(reads(&e, "bob", project.id).await);
    assert!(
        !e.fga
            .check("bob", Permission::Write, project.id)
            .await
            .unwrap()
    );
}

// Proves: I20
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn memberships_list_inherited_spaces_with_their_paths() {
    let e = env().await;
    let (org, team, project) = tree(&e).await;
    grant(&e, org.id, Role::Analyst, "ana").await;
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        org.id,
        Role::PersonalSpaceCreator,
        "ana",
    )
    .await
    .unwrap();
    let personal = spaces::create_personal_space(&e.pool, &e.fga, "ana", org.id)
        .await
        .unwrap()
        .0;
    let listed: std::collections::BTreeMap<Uuid, spaces::Membership> =
        spaces::memberships(&e.pool, &e.fga, "ana")
            .await
            .unwrap()
            .into_iter()
            .map(|m| (m.space.id, m))
            .collect();
    assert_eq!(listed.len(), 4);
    let expect = |id: Uuid, path: Vec<Uuid>, roles: Vec<Role>, inherited: Vec<Role>| {
        let m = &listed[&id];
        assert_eq!(m.space.path, path);
        assert_eq!(
            m.space.parent_id,
            path.len().checked_sub(2).map(|i| path[i])
        );
        assert_eq!((&m.roles, &m.inherited_roles), (&roles, &inherited));
    };
    expect(
        org.id,
        vec![org.id],
        vec![Role::Analyst, Role::PersonalSpaceCreator],
        vec![],
    );
    expect(
        team.id,
        vec![org.id, team.id],
        vec![Role::Analyst],
        vec![Role::Analyst],
    );
    expect(
        project.id,
        vec![org.id, team.id, project.id],
        vec![Role::Analyst],
        vec![Role::Analyst],
    );
    expect(
        personal.id,
        vec![personal.id],
        vec![Role::Member, Role::Editor],
        vec![],
    );

    // Direct and inherited admin collapse into one effective, non-inherited role.
    let alice = spaces::memberships(&e.pool, &e.fga, "alice").await.unwrap();
    let on_team = alice.iter().find(|m| m.space.id == team.id).unwrap();
    assert_eq!(on_team.roles, vec![Role::Member, Role::Admin]);
    assert!(on_team.inherited_roles.is_empty());
}

// Proves: I7
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn scope_follows_ancestors_and_levels_only_narrow_it() {
    use SpaceKind::*;
    let e = env().await;
    let (org, team, project) = tree(&e).await;
    for space in [org.id, team.id, project.id] {
        grant(&e, space, Role::Member, "bob").await;
    }
    let scope = |space: Uuid, levels: Option<Vec<SpaceKind>>| {
        let (pool, fga) = (e.pool.clone(), e.fga.clone());
        async move { spaces::scope(&pool, &fga, "bob", space, levels.as_deref()).await }
    };
    assert_eq!(
        scope(project.id, None).await.unwrap(),
        vec![org.id, team.id, project.id]
    );
    assert_eq!(scope(team.id, None).await.unwrap(), vec![org.id, team.id]);
    assert_eq!(
        scope(project.id, Some(vec![Project])).await.unwrap(),
        vec![project.id]
    );
    assert_eq!(
        scope(project.id, Some(vec![Organization, Project]))
            .await
            .unwrap(),
        vec![org.id, project.id]
    );
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        org.id,
        Role::PersonalSpaceCreator,
        "bob",
    )
    .await
    .unwrap();
    let personal = spaces::create_personal_space(&e.pool, &e.fga, "bob", org.id)
        .await
        .unwrap()
        .0;
    assert_eq!(scope(personal.id, None).await.unwrap(), vec![personal.id]);
    assert!(
        scope(personal.id, Some(vec![Organization]))
            .await
            .unwrap()
            .is_empty()
    );
    let denied = spaces::scope(&e.pool, &e.fga, "eve", project.id, None).await;
    assert!(matches!(denied, Err(AppError::NotFound)));
}

// Proves: I1
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn space_and_folder_names_are_unique_in_canonical_form() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "writer").await;
    // Surrounding whitespace and Unicode composition do not make a different name.
    for name in [" TSN", "TSN\u{a0}"] {
        let refused = crate::support::member_organization(&e.pool, &e.fga, name, "bob").await;
        assert_eq!(refused.unwrap_err().0, 409, "{name:?}");
    }
    let create_team = |name: &str| {
        spaces::create_space(
            &e.pool,
            &e.fga,
            "alice",
            SpaceKind::Team,
            org.id,
            name.into(),
            "alice",
        )
    };
    assert!(matches!(
        create_team(" BID ").await,
        Err(AppError::Conflict(_))
    ));
    let composed = create_team(" E\u{301}quipe ").await.unwrap();
    assert_eq!(composed.name, "\u{c9}quipe");
    assert!(matches!(
        create_team("\u{c9}quipe").await,
        Err(AppError::Conflict(_))
    ));
    let folder = spaces::create_folder(
        &e.pool,
        &e.fga,
        "writer",
        team.id,
        None,
        " E\u{301}te\u{301}\t".into(),
    )
    .await
    .unwrap();
    assert_eq!(folder.name, "\u{c9}t\u{e9}");
    assert!(matches!(
        spaces::create_folder(
            &e.pool,
            &e.fga,
            "writer",
            team.id,
            None,
            "\u{c9}t\u{e9}".into()
        )
        .await,
        Err(AppError::Conflict(_))
    ));
}

// Proves: I1
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn sibling_names_are_unique_and_uncommitted_links_are_ignored() {
    use control_plane::fga::{Link, Tuple};
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let duplicate = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Team,
        org.id,
        "BID".into(),
        "alice",
    )
    .await;
    assert!(matches!(duplicate, Err(AppError::Conflict(_))));
    let other = crate::support::member_organization(&e.pool, &e.fga, "Other", "carol")
        .await
        .unwrap();
    spaces::create_space(
        &e.pool,
        &e.fga,
        "carol",
        SpaceKind::Team,
        other.id,
        "BID".into(),
        "carol",
    )
    .await
    .unwrap();
    assert!(
        crate::support::member_organization(&e.pool, &e.fga, "TSN", "bob")
            .await
            .is_err()
    );

    // A creation whose OpenFGA write succeeded but whose SQL commit failed.
    let ghost = Uuid::new_v4();
    let mut guard = e.fga.guard(&[Scope::Organization(org.id)]).await.unwrap();
    e.fga
        .write_created(
            &mut guard,
            &[Link::Parent {
                child: ghost,
                parent: org.id,
            }],
            &[Tuple {
                user: "bob",
                role: Role::Member,
                space: ghost,
            }],
        )
        .await
        .unwrap();
    grant(&e, org.id, Role::Member, "bob").await;
    let listed = spaces::memberships(&e.pool, &e.fga, "bob").await.unwrap();
    assert_eq!(
        listed.iter().map(|m| m.space.id).collect::<Vec<_>>(),
        vec![org.id]
    );
    spaces::revoke(&e.pool, &e.fga, "alice", org.id, Role::Member, "bob")
        .await
        .unwrap();
}

// Proves: I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn startup_refuses_existing_state_without_a_publication() {
    let e = env().await;
    crate::support::member_organization(&e.pool, &e.fga, "TSN", "alice")
        .await
        .unwrap();
    sqlx::query("delete from authorization_store")
        .execute(&e.pool)
        .await
        .unwrap();
    let fresh = Fga::connect(
        &e.openfga,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_secs(5)),
    )
    .await
    .unwrap();
    let error = fresh.initialize(&e.pool).await.err().unwrap().to_string();
    assert!(error.contains("reset local Fred data"), "{error}");
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn hierarchy_reads_have_fixed_request_budgets() {
    let e = env().await;
    let (org, team, project) = tree(&e).await;
    grant(&e, org.id, Role::Analyst, "ana").await;
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        org.id,
        Role::PersonalSpaceCreator,
        "ana",
    )
    .await
    .unwrap();
    spaces::create_personal_space(&e.pool, &e.fga, "ana", org.id)
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
    .unwrap()
    .load(&e.pool)
    .await
    .unwrap();
    let budget = || async {
        let mut fault = proxy.fault.lock().await;
        let get = |name: &str| fault.calls.get(name).copied().unwrap_or(0);
        let counts = (get("check"), get("read"));
        fault.calls.clear();
        counts
    };
    budget().await;
    // Direct roles, then TSN's and BID's children; placement is SQL metadata.
    assert_eq!(
        spaces::memberships(&e.pool, &fga, "ana")
            .await
            .unwrap()
            .len(),
        4
    );
    assert_eq!(budget().await, (0, 3));
    // Context: direct roles only; target placement requires no FGA Read.
    spaces::scope(&e.pool, &fga, "ana", project.id, None)
        .await
        .unwrap();
    assert_eq!(budget().await, (1, 1));
    spaces::scope(&e.pool, &fga, "ana", team.id, None)
        .await
        .unwrap();
    assert_eq!(budget().await, (1, 1));
}

// Proves: I8, I14, I21
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn organization_owners_name_admins_and_read_nothing() {
    let e = env().await;
    let server = support::IdentityServer::start().await;
    server
        .users
        .lock()
        .await
        .insert("olga".into(), "olga".into());
    let directory = server.directory();
    let (org, team) = org_and_team(&e).await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    // Only a platform owner names organization owners, and only on organizations.
    let by_admin = spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        org.id,
        Role::OrganizationOwner,
        "olga",
    )
    .await;
    assert!(matches!(by_admin, Err(AppError::Forbidden)));
    spaces::grant(
        &e.pool,
        &e.fga,
        &control_plane::users::Directory::Keycloak(Some(&directory)),
        "root",
        org.id,
        Role::OrganizationOwner,
        "olga",
    )
    .await
    .unwrap();
    let on_team = spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "root",
        team.id,
        Role::OrganizationOwner,
        "olga",
    )
    .await;
    assert!(matches!(on_team, Err(AppError::Conflict(_))));

    // The owner names admins, whose role descends; the owner reads and manages nothing.
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "olga",
        org.id,
        Role::Admin,
        "bob",
    )
    .await
    .unwrap();
    assert!(
        e.fga
            .check("bob", Permission::Manage, team.id)
            .await
            .unwrap()
    );
    for space in [org.id, team.id] {
        assert!(!reads(&e, "olga", space).await);
        assert!(
            !e.fga
                .check("olga", Permission::Manage, space)
                .await
                .unwrap()
        );
    }
    let member = spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "olga",
        org.id,
        Role::Member,
        "carol",
    )
    .await;
    assert!(matches!(member, Err(AppError::Forbidden)));
    let created = spaces::create_space(
        &e.pool,
        &e.fga,
        "olga",
        SpaceKind::Team,
        org.id,
        "By owner".into(),
        "alice",
    )
    .await;
    assert!(matches!(created, Err(AppError::Forbidden)));

    // An organization keeps an owner.
    spaces::revoke(
        &e.pool,
        &e.fga,
        "root",
        org.id,
        Role::OrganizationOwner,
        "alice-owner",
    )
    .await
    .unwrap();
    let last = spaces::revoke(
        &e.pool,
        &e.fga,
        "root",
        org.id,
        Role::OrganizationOwner,
        "olga",
    )
    .await;
    assert!(matches!(last, Err(AppError::Conflict(_))));
    assert_eq!(
        e.fga
            .space_holders(org.id, Role::OrganizationOwner)
            .await
            .unwrap(),
        vec!["olga".to_string()]
    );
}

async fn content_app(e: &Env, identity: &support::IdentityServer) -> axum::Router {
    control_plane::api::router(
        control_plane::api::AppState {
            auth: std::sync::Arc::new(identity.auth().await),
            pool: e.pool.clone(),
            fga: e.fga.clone(),
            onboarding: Default::default(),
            lifecycle: Default::default(),
            directory: Some(identity.directory()),
            content: None,
            processing: None,
        },
        "/control-plane/v1",
        &[],
    )
}

// Proves: I11
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn a_stopped_lifecycle_worker_reports_only_its_stage() {
    use control_plane::lifecycle::{
        policy::{LifecycleConfig, TemporalConfig},
        worker,
    };
    let e = env().await;
    let config = LifecycleConfig {
        enabled: true,
        temporal: TemporalConfig {
            host: "127.0.0.1:1".into(),
            connect_timeout_seconds: 1,
            ..Default::default()
        },
        ..Default::default()
    };
    let error = worker::run(
        e.pool.clone(),
        e.fga.clone(),
        config,
        std::future::pending(),
    )
    .await
    .unwrap_err();
    assert_eq!(worker::stage(&error), "temporal_connect");
    assert!(!format!("{error:#}").contains("127.0.0.1"), "{error:#}");
    assert_eq!(worker::stage(&anyhow::anyhow!("other")), "unknown");
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn tree_walk_reads_stay_within_the_concurrency_bound() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    for n in 0..19 {
        spaces::create_space(
            &e.pool,
            &e.fga,
            "alice",
            SpaceKind::Team,
            org.id,
            format!("team-{n}"),
            "alice",
        )
        .await
        .unwrap();
    }
    grant(&e, org.id, Role::Analyst, "ana").await;
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
    proxy.fault.lock().await.read_delay = Some(Duration::from_millis(50));
    let listed = spaces::memberships(&e.pool, &observed, "ana")
        .await
        .unwrap();
    assert_eq!(
        listed
            .iter()
            .filter(|m| m.space.kind == SpaceKind::Team)
            .count(),
        20
    );
    let peak = proxy.fault.lock().await.peak_reads;
    // Twenty teams are read concurrently, never more than the named bound at once.
    assert!(
        (2..=control_plane::fga::READ_CONCURRENCY).contains(&peak),
        "peak {peak}"
    );
}

// Proves: I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn business_routes_share_one_authorization_answer() {
    use serde_json::{Value, json};
    use tower::ServiceExt;
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "writer").await;
    grant(&e, org.id, Role::Member, "bystander").await;
    crate::support::member_organization(&e.pool, &e.fga, "Other", "carol")
        .await
        .unwrap();
    let folder = spaces::create_folder(&e.pool, &e.fga, "writer", team.id, None, "kept".into())
        .await
        .unwrap();
    let retired = spaces::create_space(
        &e.pool,
        &e.fga,
        "alice",
        SpaceKind::Team,
        org.id,
        "Retired".into(),
        "alice",
    )
    .await
    .unwrap();
    let retired_folder =
        spaces::create_folder(&e.pool, &e.fga, "writer", retired.id, None, "old".into())
            .await
            .unwrap();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle
        .accept(&e.pool, &e.fga, "root", retired.id)
        .await
        .unwrap();

    let identity = support::IdentityServer::start().await;
    let app = content_app(&e, &identity).await;
    let call = |user: &str, method: &str, path: String, body: serde_json::Value| {
        let request = axum::http::Request::builder()
            .method(method)
            .uri(format!("/control-plane/v1{path}"))
            .header("authorization", format!("Bearer {}", identity.token(user)))
            .header("content-type", "application/json")
            .body(axum::body::Body::from(body.to_string()))
            .unwrap();
        let app = app.clone();
        async move {
            let response = app.oneshot(request).await.unwrap();
            let status = response.status().as_u16();
            let bytes = axum::body::to_bytes(response.into_body(), 65536)
                .await
                .unwrap();
            (
                status,
                serde_json::from_slice::<serde_json::Value>(&bytes).unwrap_or_default(),
            )
        }
    };
    let missing = Uuid::new_v4();
    // (case, user, space, folder, expected status)
    let table = [
        ("missing space", "writer", missing, None, 404),
        (
            "foreign organization",
            "carol",
            team.id,
            Some(folder.id),
            404,
        ),
        ("no permission", "bystander", team.id, Some(folder.id), 403),
        (
            "retired space",
            "writer",
            retired.id,
            Some(retired_folder.id),
            409,
        ),
    ];
    for (case, user, space, folder, expected) in table {
        let created = call(
            user,
            "POST",
            "/folders".into(),
            json!({"space_id": space, "name": "new"}),
        )
        .await;
        let listed = call(user, "GET", format!("/spaces/{space}/entries"), Value::Null).await;
        let mut answers = vec![("create folder", created), ("list documents", listed)];
        if let Some(folder) = folder {
            let renamed = call(
                user,
                "PATCH",
                format!("/folders/{folder}"),
                json!({"name": "renamed"}),
            )
            .await;
            answers.push(("rename folder", renamed));
        }
        for (route, (status, body)) in answers {
            assert_eq!(status, expected, "{case}: {route}: {body}");
            if expected == 409 {
                assert_eq!(body["code"], "space_pending_deletion", "{case}: {route}");
            }
        }
        // Probes answer the same refusals as a boolean.
        let (status, body) = call(
            user,
            "POST",
            "/authorize/space".into(),
            json!({"space_id": space, "permission": "read"}),
        )
        .await;
        assert_eq!(
            (status, &body["allowed"]),
            (200, &json!(false)),
            "{case}: probe"
        );
    }
    let (status, body) = call(
        "writer",
        "POST",
        "/authorize/space".into(),
        json!({"space_id": team.id, "permission": "write"}),
    )
    .await;
    assert_eq!((status, &body["allowed"]), (200, &json!(true)));
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn every_module_rejects_malformed_input_with_one_json_error_format() {
    use tower::ServiceExt;
    let e = env().await;
    org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let app = content_app(&e, &identity).await;
    let token = identity.token("alice");
    let unknown = Uuid::new_v4();
    let cases = [
        // api: path, query and body
        (
            "PUT",
            "/spaces/not-a-uuid/roles/member/bob".to_string(),
            "",
            422,
            "invalid_fields",
        ),
        (
            "GET",
            "/admin/teams?after=not-a-uuid".into(),
            "",
            422,
            "invalid_fields",
        ),
        ("POST", "/folders".into(), "{", 400, "invalid_json"),
        (
            "POST",
            "/folders".into(),
            r#"{"name":1}"#,
            422,
            "invalid_fields",
        ),
        // documents
        (
            "GET",
            "/spaces/not-a-uuid/entries".into(),
            "",
            422,
            "invalid_fields",
        ),
        // processing
        (
            "GET",
            "/documents/not-a-uuid/processing".into(),
            "",
            422,
            "invalid_fields",
        ),
        (
            "GET",
            format!("/documents/{unknown}/processing?before=x"),
            "",
            422,
            "invalid_fields",
        ),
    ];
    for (method, path, body, status, code) in cases {
        let request = axum::http::Request::builder()
            .method(method)
            .uri(format!("/control-plane/v1{path}"))
            .header("authorization", format!("Bearer {token}"))
            .header("content-type", "application/json")
            .body(axum::body::Body::from(body))
            .unwrap();
        let response = app.clone().oneshot(request).await.unwrap();
        assert_eq!(response.status(), status, "{method} {path}");
        assert_eq!(
            response.headers()["content-type"],
            "application/json",
            "{method} {path}"
        );
        let bytes = axum::body::to_bytes(response.into_body(), 4096)
            .await
            .unwrap();
        let error: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(error["code"], code, "{method} {path}");
        assert!(error["detail"].is_string(), "{method} {path}");
    }
}

async fn content_request(
    app: axum::Router,
    token: &str,
    method: &str,
    path: &str,
    body: &str,
) -> u16 {
    use tower::ServiceExt;
    let request = axum::http::Request::builder()
        .method(method)
        .uri(format!("/control-plane/v1{path}"))
        .header("authorization", format!("Bearer {token}"))
        .header("content-type", "application/json")
        .body(axum::body::Body::from(body.to_owned()))
        .unwrap();
    app.oneshot(request).await.unwrap().status().as_u16()
}

// Proves: I22
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn content_http_waiters_recheck_existence_after_deletion() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let app = content_app(&e, &identity).await;
    for method in ["PATCH", "DELETE", "POST"] {
        let folder = spaces::create_folder(&e.pool, &e.fga, "alice", org.id, None, "folder".into())
            .await
            .unwrap();
        let mut deleting = hold_organization_lock(&e, org.id).await;
        let since = sqlx::query_scalar("select clock_timestamp()")
            .fetch_one(&e.pool)
            .await
            .unwrap();
        let (app, token) = (app.clone(), identity.token("alice"));
        let pending = tokio::spawn(async move {
            let (path, body) = if method == "POST" {
                (
                    "/folders".into(),
                    serde_json::json!({"space_id":org.id,"parent_id":folder.id,"name":"child"})
                        .to_string(),
                )
            } else {
                (
                    format!("/folders/{}", folder.id),
                    r#"{"name":"renamed"}"#.into(),
                )
            };
            content_request(app, &token, method, &path, &body).await
        });
        wait_for_write_retry(&e.pool, since).await;
        db::delete_folder(&mut *deleting, folder.id).await.unwrap();
        deleting.commit().await.unwrap();
        assert_eq!(pending.await.unwrap(), 404);
    }
}

// Proves: I14, I21
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn owner_grants_require_directory_identity_and_deleted_owners_can_be_revoked() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let app = content_app(&e, &identity).await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let token = identity.token("root");
    let before = e
        .fga
        .space_holders(org.id, Role::OrganizationOwner)
        .await
        .unwrap();
    for (subject, expected) in [("missing", 422), ("unavailable", 500)] {
        assert_eq!(
            content_request(
                app.clone(),
                &token,
                "PUT",
                &format!("/spaces/{}/roles/organization_owner/{subject}", org.id),
                ""
            )
            .await,
            expected
        );
        assert_eq!(
            e.fga
                .space_holders(org.id, Role::OrganizationOwner)
                .await
                .unwrap(),
            before
        );
    }
    assert!(matches!(
        spaces::grant(
            &e.pool,
            &e.fga,
            &control_plane::users::Directory::Keycloak(None),
            "root",
            org.id,
            Role::OrganizationOwner,
            "missing"
        )
        .await,
        Err(AppError::Unavailable(_))
    ));
    identity
        .users
        .lock()
        .await
        .insert("olga".into(), "olga".into());
    let path = format!("/spaces/{}/roles/organization_owner/olga", org.id);
    assert_eq!(
        content_request(app.clone(), &token, "PUT", &path, "").await,
        204
    );
    identity.users.lock().await.remove("olga");
    assert_eq!(
        content_request(app.clone(), &token, "DELETE", &path, "").await,
        204
    );
    assert_eq!(
        content_request(
            app,
            &token,
            "DELETE",
            &format!("/spaces/{}/roles/organization_owner/alice-owner", org.id),
            ""
        )
        .await,
        409
    );
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn local_candidate_search_matches_a_literal_prefix_in_order_with_a_limit() {
    let e = env().await;
    let profiles = [
        ("pat", "pat@x.org", "Patricia", "Smith"),
        ("50%off", "deals@x.org", "Fifty", "Percent"),
        ("a_b", "ab@x.org", "Under", "Score"),
        ("axb", "axb@x.org", "Ex", "Bee"),
        ("olivia", "o@x.org", "Olivia", "Patel"),
    ];
    for (username, email, first, last) in profiles {
        sqlx::query("insert into user_identity (id, username, email, first_name, last_name) values ($1,$2,$3,$4,$5)")
            .bind(Uuid::new_v4()).bind(username).bind(email).bind(first).bind(last)
            .execute(&e.pool).await.unwrap();
    }
    for n in 0..25 {
        sqlx::query("insert into user_identity (id, username) values ($1, $2)")
            .bind(Uuid::new_v4())
            .bind(format!("user{n:02}"))
            .execute(&e.pool)
            .await
            .unwrap();
    }
    let directory = control_plane::users::Directory::Local(&e.pool);
    let names = |query: &'static str| {
        let directory = &directory;
        async move {
            directory
                .search(query)
                .await
                .unwrap()
                .into_iter()
                .filter_map(|u| u.username)
                .collect::<Vec<_>>()
        }
    };
    // Any field's prefix, case-insensitively: username, first or last name, email.
    assert_eq!(names("PA").await, ["olivia", "pat"]);
    assert_eq!(names("deal").await, ["50%off"]);
    // Wildcards are literal: "%" and "_" no longer match everything.
    assert_eq!(names("50%").await, ["50%off"]);
    assert!(names("%%").await.is_empty());
    assert_eq!(names("a_").await, ["a_b"]);
    // A prefix, not a substring.
    assert!(names("tricia").await.is_empty());
    let page = names("user").await;
    assert_eq!(page.len(), 20);
    assert_eq!(page.first().map(String::as_str), Some("user00"));
    assert!(page.windows(2).all(|w| w[0] < w[1]));
}

// Proves: I27
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn grants_require_a_known_valid_subject_and_classify_openfga_errors() {
    use control_plane::fga::{Conflict, InvalidTuple, Tuple};
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let app = content_app(&e, &identity).await;
    let token = identity.token("alice");
    // Unknown to the configured directory, or unusable as an OpenFGA user: nothing is written.
    for subject in ["nobody", "a:b", "a%23b", "a%20b"] {
        let path = format!("/spaces/{}/roles/member/{subject}", org.id);
        assert_eq!(
            content_request(app.clone(), &token, "PUT", &path, "").await,
            422,
            "{subject}"
        );
    }
    assert!(e.fga.roles_of("nobody").await.unwrap().is_empty());
    identity
        .users
        .lock()
        .await
        .insert("known".into(), "known".into());
    let path = format!("/spaces/{}/roles/member/known", org.id);
    assert_eq!(content_request(app, &token, "PUT", &path, "").await, 204);
    // A consumed guard is a conflict; a malformed tuple under a fresh guard is invalid input.
    let mut stale = e.fga.guard(&[Scope::Organization(org.id)]).await.unwrap();
    e.fga
        .fence(&mut e.fga.guard(&[Scope::Organization(org.id)]).await.unwrap())
        .await
        .unwrap();
    let member = |user| Tuple {
        user,
        role: Role::Member,
        space: team.id,
    };
    let stale_write = e.fga.write(&mut stale, &[member("bob")], &[]).await;
    assert!(stale_write.unwrap_err().is::<Conflict>());
    let mut fresh = e.fga.guard(&[Scope::Organization(org.id)]).await.unwrap();
    let malformed = e.fga.write(&mut fresh, &[member("a b")], &[]).await;
    assert!(malformed.unwrap_err().is::<InvalidTuple>());
}

// Proves: I21
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn import_rechecks_owner_identity_before_publishing_spaces() {
    use std::{sync::Arc, time::Duration};
    let e = env().await;
    let server = support::IdentityServer::start().await;
    server
        .users
        .lock()
        .await
        .insert("alice-sub".into(), "alice".into());
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let directory = server.directory();
    let gate = Arc::new(support::Gate::default());
    server.control.lock().await.create_gate = Some(gate.clone());
    let bundle = parse_blueprint(br#"{"users":[{"username":"alice"},{"username":"bob","password":"fixture-password"}],"organizations":[{"ref":"org","name":"Race","roles":{"alice":["organization_owner","admin"]}}],"teams":[],"projects":[]}"#).unwrap();
    let pool = e.pool.clone();
    let fga = e.fga.clone();
    let pending = tokio::spawn(async move {
        control_plane::provisioning::Importer {
            pool: &pool,
            fga: &fga,
            directory: &directory,
            operator: "root",
        }
        .run(&bundle)
        .await
    });
    tokio::time::timeout(Duration::from_secs(3), gate.entered.notified())
        .await
        .unwrap();
    server.users.lock().await.remove("alice-sub");
    gate.release.notify_one();
    let error = pending.await.unwrap().unwrap_err();
    assert_eq!(
        error
            .downcast_ref::<control_plane::provisioning::Failure>()
            .unwrap()
            .status,
        axum::http::StatusCode::SERVICE_UNAVAILABLE
    );
    assert!(error.to_string().contains("roles/spaces"));
    let spaces: i64 = sqlx::query_scalar("select count(*) from space")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    assert_eq!(spaces, 0);
    assert!(e.fga.roles_of("alice-sub").await.unwrap().is_empty());
}

// Proves: I21
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn import_checks_distinct_owners_once_with_bounded_concurrency() {
    let e = env().await;
    let server = support::IdentityServer::start().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let mut roles = serde_json::Map::new();
    let mut users = Vec::new();
    for i in 0..12 {
        let name = format!("owner{i}");
        server.users.lock().await.insert(name.clone(), name.clone());
        users.push(serde_json::json!({"username":name}));
        roles.insert(name, serde_json::json!(["organization_owner", "admin"]));
    }
    server.control.lock().await.subject_delay = true;
    let bundle = parse_blueprint(&serde_json::to_vec(&serde_json::json!({
        "users":users,"organizations":[{"ref":"a","name":"A","roles":roles}],"teams":[],"projects":[]
    })).unwrap()).unwrap();
    let directory = server.directory();
    control_plane::provisioning::Importer {
        pool: &e.pool,
        fga: &e.fga,
        directory: &directory,
        operator: "root",
    }
    .run(&bundle)
    .await
    .unwrap();
    let control = server.control.lock().await;
    assert_eq!(control.subject_lookups.len(), 12);
    let unique: std::collections::BTreeSet<_> = control.subject_lookups.iter().collect();
    assert_eq!(unique.len(), 12);
    assert!(
        control.subject_peak > 1 && control.subject_peak <= 8,
        "{} concurrent lookups",
        control.subject_peak
    );
}

// Proves: I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn concurrent_attachments_choose_one_organization_and_creation_cannot_bypass_it() {
    let e = env().await;
    let a = crate::support::member_organization(&e.pool, &e.fga, "A", "alice")
        .await
        .unwrap();
    let b = crate::support::member_organization(&e.pool, &e.fga, "B", "carol")
        .await
        .unwrap();
    let subjects = e.subjects();
    let (first, second) = tokio::join!(
        spaces::grant(
            &e.pool,
            &e.fga,
            &subjects,
            "alice",
            a.id,
            Role::Admin,
            "bob"
        ),
        spaces::grant(
            &e.pool,
            &e.fga,
            &subjects,
            "carol",
            b.id,
            Role::Member,
            "bob"
        ),
    );
    assert_ne!(first.is_ok(), second.is_ok());
    let (winner, loser) = if first.is_ok() {
        (a.id, second)
    } else {
        (b.id, first)
    };
    assert!(matches!(loser, Err(AppError::Conflict(_))));
    assert_eq!(
        spaces::organization(&e.pool, &e.fga, "bob").await.unwrap(),
        Some(winner)
    );
    assert!(matches!(
        crate::support::member_organization(&e.pool, &e.fga, "Third", "bob").await,
        Err((409, _))
    ));
    assert!(
        named_space(&e.pool, &e.fga, None, "Third")
            .await
            .unwrap()
            .is_none()
    );
    assert_eq!(
        spaces::organization(&e.pool, &e.fga, "unattached")
            .await
            .unwrap(),
        None
    );
    // Governance-only attachment is still an attachment, never content permission.
    assert!(
        !spaces::in_organization(
            &e.pool,
            &e.fga,
            "bob",
            if winner == a.id { b.id } else { a.id }
        )
        .await
        .unwrap()
    );
}

// Proves: I23, I5
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn a_late_attachment_cannot_publish_after_assignment_elsewhere() {
    let e = env().await;
    let a = crate::support::member_organization(&e.pool, &e.fga, "A", "alice")
        .await
        .unwrap();
    let b = crate::support::member_organization(&e.pool, &e.fga, "B", "carol")
        .await
        .unwrap();
    let proxy = support::fga_proxy::Proxy::start(&e.openfga).await;
    let gate = std::sync::Arc::new(support::Gate::default());
    {
        let mut fault = proxy.fault.lock().await;
        fault.gate = Some(gate.clone());
        fault.gate_before = true;
    }
    let delayed = Fga::connect(
        &proxy.base,
        &e.store,
        false,
        false,
        None,
        Some(Duration::from_millis(500)),
    )
    .await
    .unwrap()
    .load(&e.pool)
    .await
    .unwrap();
    let (pool, open) = (e.pool.clone(), e.open_directory());
    let pending = tokio::spawn(async move {
        spaces::grant(
            &pool,
            &delayed,
            &control_plane::users::Directory::Keycloak(Some(&open)),
            "alice",
            a.id,
            Role::Member,
            "bob",
        )
        .await
    });
    tokio::time::timeout(Duration::from_secs(3), gate.entered.notified())
        .await
        .unwrap();
    assert!(pending.await.unwrap().is_err());
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "carol",
        b.id,
        Role::Member,
        "bob",
    )
    .await
    .unwrap();
    gate.release.notify_one();
    tokio::time::timeout(Duration::from_secs(3), async {
        while proxy.fault.lock().await.acknowledged.is_empty() {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();
    assert_eq!(proxy.fault.lock().await.acknowledged, vec![400]);
    assert_eq!(
        spaces::organization(&e.pool, &e.fga, "bob").await.unwrap(),
        Some(b.id)
    );
}

// Proves: I23, I8
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn ambiguous_context_fails_closed_and_remains_repairable() {
    use control_plane::fga::Tuple;
    let e = env().await;
    let (a, _, project) = tree(&e).await;
    let b = crate::support::member_organization(&e.pool, &e.fga, "B", "carol")
        .await
        .unwrap();
    grant(&e, a.id, Role::Admin, "bob").await;
    assert_eq!(
        spaces::organization(&e.pool, &e.fga, "bob").await.unwrap(),
        Some(a.id)
    );
    assert!(!reads(&e, "bob", a.id).await);
    // Context resolution agrees with direct FGA grants; it does not repair missing parent roles.
    e.fga
        .write(
            &mut e.fga.guard(&[Scope::Organization(a.id)]).await.unwrap(),
            &[Tuple {
                user: "orphan",
                role: Role::Editor,
                space: project.id,
            }],
            &[],
        )
        .await
        .unwrap();
    assert_eq!(
        spaces::organization(&e.pool, &e.fga, "orphan")
            .await
            .unwrap(),
        Some(a.id)
    );
    let memberships = spaces::memberships(&e.pool, &e.fga, "orphan")
        .await
        .unwrap();
    assert_eq!(memberships.len(), 1);
    assert_eq!(memberships[0].space.id, project.id);
    assert_eq!(memberships[0].space.path, project.path);
    assert_eq!(memberships[0].space.organization, a.id);
    assert_eq!(
        e.fga.roles_of("orphan").await.unwrap(),
        vec![(project.id, Role::Editor)]
    );
    // Simulate a corrupt second organization attachment.
    e.fga
        .write(
            &mut e.fga.guard(&[Scope::Organization(b.id)]).await.unwrap(),
            &[Tuple {
                user: "bob",
                role: Role::Member,
                space: b.id,
            }],
            &[],
        )
        .await
        .unwrap();
    {
        let subject = "bob";
        assert!(matches!(
            spaces::organization(&e.pool, &e.fga, subject).await,
            Err(AppError::Conflict(_))
        ));
        assert!(matches!(
            spaces::memberships(&e.pool, &e.fga, subject).await,
            Err(AppError::Conflict(_))
        ));
        assert!(matches!(
            spaces::scope(&e.pool, &e.fga, subject, b.id, None).await,
            Err(AppError::Conflict(_))
        ));
        assert!(matches!(
            spaces::authorized_write(&e.pool, &e.fga, subject, b.id).await,
            Err(AppError::Conflict(_))
        ));
        spaces::revoke(&e.pool, &e.fga, "carol", b.id, Role::Member, subject)
            .await
            .unwrap();
        assert_eq!(
            spaces::organization(&e.pool, &e.fga, subject)
                .await
                .unwrap(),
            Some(a.id)
        );
    }
}

// Proves: I23, I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn import_rejects_cross_organization_declarations_before_identity_writes() {
    use control_plane::provisioning::Importer;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let value = serde_json::json!({"users":[{"username":"bob","password":"private-password"}],"organizations":[{"ref":"a","name":"A","roles":{"bob":["admin","organization_owner","member"]}},{"ref":"b","name":"B","roles":{"bob":["admin","organization_owner","member"]}}],"teams":[],"projects":[]});
    let bundle = parse_blueprint(&serde_json::to_vec(&value).unwrap()).unwrap();
    let importer = Importer {
        pool: &e.pool,
        fga: &e.fga,
        directory: &directory,
        operator: "root",
    };
    let failure = importer.run(&bundle).await.unwrap_err();
    assert!(failure.to_string().contains("preflight"));
    assert!(server.users.lock().await.is_empty());
    assert!(server.control.lock().await.created.is_empty());
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );
    server.users.lock().await.insert("bob".into(), "bob".into());
    crate::support::member_organization(&e.pool, &e.fga, "Existing", "bob")
        .await
        .unwrap();
    let mut other = value;
    other["organizations"].as_array_mut().unwrap().truncate(1);
    let bundle = parse_blueprint(&serde_json::to_vec(&other).unwrap()).unwrap();
    assert!(
        importer
            .run(&bundle)
            .await
            .unwrap_err()
            .to_string()
            .contains("preflight")
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        1
    );
}

// Proves: I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn organization_context_exhausts_pages_and_grant_budget_includes_global_fencing() {
    let e = env().await;
    let a = crate::support::member_organization(&e.pool, &e.fga, "A", "alice")
        .await
        .unwrap();
    grant(&e, a.id, Role::Editor, "alice").await;
    grant(&e, a.id, Role::Analyst, "alice").await;
    grant(&e, a.id, Role::PersonalSpaceCreator, "alice").await;
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
        fault.read_page_size = Some(2);
    }
    // Five direct roles, two per page: 3 role Reads, no placement lookup for a root.
    assert_eq!(
        spaces::organization(&e.pool, &fga, "alice").await.unwrap(),
        Some(a.id)
    );
    {
        let mut fault = proxy.fault.lock().await;
        assert_eq!(fault.calls.get("read"), Some(&3));
        assert!(fault.reads.iter().all(
            |r| r["tuple_key"]["user"] == "user:alice" && r["tuple_key"]["object"] == "space:"
        ));
        assert!(
            fault.reads[1]["continuation_token"]
                .as_str()
                .is_some_and(|s| !s.is_empty())
        );
        fault.calls.clear();
        fault.reads.clear();
        fault.written.clear();
    }
    spaces::grant(
        &e.pool,
        &fga,
        &e.subjects(),
        "alice",
        a.id,
        Role::Member,
        "bob",
    )
    .await
    .unwrap();
    {
        let fault = proxy.fault.lock().await;
        // Platform/org guards (2), caller context (3), target context empty (1).
        assert_eq!(fault.calls.get("read"), Some(&6));
        assert_eq!(fault.calls.get("check"), Some(&1));
        assert_eq!(fault.calls.get("write"), Some(&1));
        assert_eq!(
            fault.written[0]["writes"]["tuple_keys"]
                .as_array()
                .unwrap()
                .len(),
            3
        );
        assert_eq!(
            fault.written[0]["deletes"]["tuple_keys"]
                .as_array()
                .unwrap()
                .len(),
            2
        );
    }
    // An uncommitted ghost grant cannot manufacture a second organization.
    e.fga
        .write(
            &mut e.fga.guard(&[Scope::Organization(a.id)]).await.unwrap(),
            &[control_plane::fga::Tuple {
                user: "bob",
                role: Role::Member,
                space: Uuid::new_v4(),
            }],
            &[],
        )
        .await
        .unwrap();
    assert_eq!(
        spaces::organization(&e.pool, &fga, "bob").await.unwrap(),
        Some(a.id)
    );
}

// Proves: I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn business_http_checks_context_while_platform_metadata_stays_available() {
    use serde_json::json;
    use tower::ServiceExt;
    let e = env().await;
    let a = crate::support::member_organization(&e.pool, &e.fga, "A", "alice")
        .await
        .unwrap();
    let b = crate::support::member_organization(&e.pool, &e.fga, "B", "carol")
        .await
        .unwrap();
    grant(&e, a.id, Role::Editor, "bob").await;
    let identity = support::IdentityServer::start().await;
    let app = content_app(&e, &identity).await;
    let doc = document(b.id, None, "foreign.pdf");
    crate::environment::insert_document(&e.pool, &doc)
        .await
        .unwrap();
    let token = identity.token("bob");
    assert_eq!(
        content_request(
            app.clone(),
            &token,
            "GET",
            &format!("/spaces/{}/entries", Uuid::new_v4()),
            ""
        )
        .await,
        404
    );
    // A corrupt legacy second grant must not make either organization readable.
    e.fga
        .write(
            &mut e.fga.guard(&[Scope::Organization(b.id)]).await.unwrap(),
            &[control_plane::fga::Tuple {
                user: "bob",
                role: Role::Editor,
                space: b.id,
            }],
            &[],
        )
        .await
        .unwrap();
    for (path, body) in [
        (
            "/authorize/document",
            json!({"document_id":doc.id,"permission":"read"}),
        ),
        (
            "/authorize/space",
            json!({"space_id":b.id,"permission":"read"}),
        ),
        ("/authorize/scope", json!({"space_id":a.id})),
    ] {
        assert_eq!(
            content_request(app.clone(), &token, "POST", path, &body.to_string()).await,
            409,
            "{path}"
        );
    }
    assert_eq!(
        content_request(app.clone(), &token, "GET", "/me/spaces", "").await,
        409
    );
    // /me exposes platform-role metadata independently; no content or tenant choice.
    let response = app
        .oneshot(
            axum::http::Request::builder()
                .uri("/control-plane/v1/me")
                .header("authorization", format!("Bearer {token}"))
                .body(axum::body::Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), 200);
}

// Proves: I23, I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn import_rechecks_attachment_after_preflight_against_a_waiting_grant() {
    let e = env().await;
    let a = crate::support::member_organization(&e.pool, &e.fga, "A", "alice")
        .await
        .unwrap();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let server = support::IdentityServer::start().await;
    server.users.lock().await.insert("bob".into(), "bob".into());
    let gate = std::sync::Arc::new(support::Gate::default());
    server.control.lock().await.create_gate = Some(gate.clone());
    let directory = server.directory();
    let bundle = parse_blueprint(br#"{"users":[{"username":"carol","password":"private-password"},{"username":"bob"}],"organizations":[{"ref":"b","name":"B","roles":{"carol":["organization_owner","admin"],"bob":["member"]}}],"teams":[],"projects":[]}"#).unwrap();
    let (pool, fga) = (e.pool.clone(), e.fga.clone());
    let import = tokio::spawn(async move {
        control_plane::provisioning::Importer {
            pool: &pool,
            fga: &fga,
            directory: &directory,
            operator: "root",
        }
        .run(&bundle)
        .await
    });
    // Preflight has passed; identity dispatch holds platform lock. Queue a grant
    // before reconciliation can acquire it, then release the identity dispatch.
    tokio::time::timeout(Duration::from_secs(3), gate.entered.notified())
        .await
        .unwrap();
    let (pool, fga, open) = (e.pool.clone(), e.fga.clone(), e.open_directory());
    let grant = tokio::spawn(async move {
        spaces::grant(
            &pool,
            &fga,
            &control_plane::users::Directory::Keycloak(Some(&open)),
            "alice",
            a.id,
            Role::Member,
            "bob",
        )
        .await
    });
    wait_for_advisory_waiter(&e.pool).await;
    gate.release.notify_one();
    grant.await.unwrap().unwrap();
    let failure = import.await.unwrap().unwrap_err();
    assert!(failure.to_string().contains("roles/spaces"), "{failure}");
    assert_eq!(
        spaces::organization(&e.pool, &e.fga, "bob").await.unwrap(),
        Some(a.id)
    );
    assert!(
        named_space(&e.pool, &e.fga, None, "B")
            .await
            .unwrap()
            .is_none()
    );
}

// Proves: I4, I6, I20, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn personal_open_requires_explicit_eligibility_and_never_repairs_revocation() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "priya").await;
    assert!(matches!(
        spaces::create_personal_space(&e.pool, &e.fga, "priya", org.id).await,
        Err(AppError::Forbidden)
    ));
    assert!(
        spaces::grant(
            &e.pool,
            &e.fga,
            &e.subjects(),
            "alice",
            org.id,
            Role::PersonalSpaceCreator,
            "outsider"
        )
        .await
        .is_err()
    );
    assert!(
        spaces::grant(
            &e.pool,
            &e.fga,
            &e.subjects(),
            "alice",
            team.id,
            Role::PersonalSpaceCreator,
            "priya"
        )
        .await
        .is_err()
    );
    grant(&e, org.id, Role::PersonalSpaceCreator, "priya").await;
    assert!(
        !e.fga
            .check_space(
                "priya",
                control_plane::roles::SpacePermission::CreatePersonalSpace,
                team.id
            )
            .await
            .unwrap()
    );
    assert!(matches!(
        spaces::revoke(&e.pool, &e.fga, "alice", org.id, Role::Member, "priya").await,
        Err(AppError::Conflict(_))
    ));
    let (a, b) = tokio::join!(
        spaces::create_personal_space(&e.pool, &e.fga, "priya", org.id),
        spaces::create_personal_space(&e.pool, &e.fga, "priya", org.id)
    );
    let ((personal, created_a), (other, created_b)) = (a.unwrap(), b.unwrap());
    assert_eq!(personal.id, other.id);
    assert_ne!(created_a, created_b);
    assert_eq!(personal.path, vec![personal.id]);
    assert!(!reads(&e, "alice", personal.id).await);
    spaces::revoke(
        &e.pool,
        &e.fga,
        "alice",
        org.id,
        Role::PersonalSpaceCreator,
        "priya",
    )
    .await
    .unwrap();
    spaces::revoke(&e.pool, &e.fga, "alice", personal.id, Role::Editor, "priya")
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
    let (again, created) = spaces::create_personal_space(&e.pool, &observed, "priya", org.id)
        .await
        .unwrap();
    assert!(!created);
    assert_eq!(again.id, personal.id);
    assert_eq!(proxy.fault.lock().await.writes, 0);
    assert!(
        !e.fga
            .check("priya", Permission::Write, personal.id)
            .await
            .unwrap()
    );
    spaces::revoke(&e.pool, &e.fga, "alice", personal.id, Role::Member, "priya")
        .await
        .unwrap();
    grant(&e, org.id, Role::PersonalSpaceCreator, "priya").await;
    assert!(matches!(
        spaces::create_personal_space(&e.pool, &observed, "priya", org.id).await,
        Err(AppError::Forbidden)
    ));
    assert_eq!(proxy.fault.lock().await.writes, 0);
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space where personal_owner = 'priya'")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        1
    );
    grant(&e, org.id, Role::Admin, "governor").await;
    assert!(matches!(
        spaces::create_personal_space(&e.pool, &e.fga, "governor", org.id).await,
        Err(AppError::Forbidden)
    ));
    let foreign = crate::support::member_organization(&e.pool, &e.fga, "Other", "carol")
        .await
        .unwrap();
    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "carol",
        foreign.id,
        Role::PersonalSpaceCreator,
        "carol",
    )
    .await
    .unwrap();
    let (private, _) = spaces::create_personal_space(&e.pool, &e.fga, "carol", foreign.id)
        .await
        .unwrap();
    assert_ne!(private.id, personal.id);
    assert_eq!(private.path, vec![private.id]);
    assert_eq!(private.organization, foreign.id);
    assert!(matches!(
        spaces::create_personal_space(&e.pool, &e.fga, "priya", foreign.id).await,
        Err(AppError::NotFound)
    ));
    let listed = spaces::memberships(&e.pool, &e.fga, "carol").await.unwrap();
    assert!(listed.iter().all(|m| m.space.organization == foreign.id));
    assert!(listed.iter().all(|m| m.space.id != personal.id));
}

// Proves: I6, I23
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn personal_open_budgets_exhaust_pages_and_recheck_after_lock_wait() {
    let e = env().await;
    let org = crate::support::member_organization(&e.pool, &e.fga, "TSN", "alice")
        .await
        .unwrap();
    for user in ["priya", "bob", "carol"] {
        grant(&e, org.id, Role::Member, user).await;
        grant(&e, org.id, Role::PersonalSpaceCreator, user).await;
        if user != "priya" {
            spaces::create_personal_space(&e.pool, &e.fga, user, org.id)
                .await
                .unwrap();
        }
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
    // The other members' personal spaces never enter the budget.
    for (existing, others) in [(false, 2), (true, 2), (true, 5)] {
        for user in ["dan", "eve", "fay"].iter().take(others - 2) {
            grant(&e, org.id, Role::Member, user).await;
            grant(&e, org.id, Role::PersonalSpaceCreator, user).await;
            spaces::create_personal_space(&e.pool, &e.fga, user, org.id)
                .await
                .unwrap();
        }
        *proxy.fault.lock().await = support::fga_proxy::Fault {
            read_page_size: Some(1),
            ..Default::default()
        };
        let (_, created) = spaces::create_personal_space(&e.pool, &observed, "priya", org.id)
            .await
            .unwrap();
        assert_eq!(created, !existing);
        let fault = proxy.fault.lock().await;
        assert_eq!(fault.calls.get("check"), Some(&2));
        assert_eq!(fault.writes, if existing { 0 } else { 1 });
        // Exact guard: 1 page; roles: 2 then 4 pages; reuse reads its own link: 1 page.
        // SQL finds the candidate; no empty terminal page.
        assert_eq!(
            fault.calls.get("read"),
            Some(&(if existing { 6 } else { 3 })),
            "existing={existing}, others={others}"
        );
        assert!(fault.reads.iter().any(|r| {
            r["continuation_token"]
                .as_str()
                .is_some_and(|s| !s.is_empty())
        }));
        if !existing {
            let body = &fault.written[0];
            assert_eq!(
                body["writes"]["tuple_keys"].as_array().unwrap().len()
                    + body["deletes"]["tuple_keys"].as_array().unwrap().len(),
                5
            );
        }
    }
    // SQL also refuses a second active personal space for one owner and organization.
    let duplicate = sqlx::query("insert into space (id, kind, name, personal_owner, organization_id) values ($1, 'team', 'priya', 'priya', $2)")
        .bind(Uuid::new_v4())
        .bind(org.id)
        .execute(&e.pool)
        .await
        .unwrap_err();
    assert!(duplicate.as_database_error().unwrap().is_unique_violation());
    let held = hold_organization_lock(&e, org.id).await;
    let pool = e.pool.clone();
    let fga = observed.clone();
    let pending =
        tokio::spawn(
            async move { spaces::create_personal_space(&pool, &fga, "priya", org.id).await },
        );
    wait_for_advisory_waiter(&e.pool).await;
    delete_tuple(&e, "priya", "member", &format!("space:{}", org.id)).await;
    held.commit().await.unwrap();
    assert!(matches!(pending.await.unwrap(), Err(AppError::Forbidden)));
}

// Proves: I4, I17, I18
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn import_orders_personal_eligibility_after_content_across_failed_batches() {
    let e = env().await;
    let org = crate::support::member_organization(&e.pool, &e.fga, "TSN", "alice")
        .await
        .unwrap();
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    let mut users = Vec::new();
    let mut roles = serde_json::Map::new();
    for i in 0..96 {
        let user = format!("user-{i:03}");
        server.users.lock().await.insert(user.clone(), user.clone());
        users.push(serde_json::json!({"username":user}));
        roles.insert(
            user,
            if i == 95 {
                serde_json::json!(["personal_space_creator", "member"])
            } else {
                serde_json::json!(["member"])
            },
        );
    }
    let mut value = serde_json::json!({"users":users,"organizations":[{"ref":"tsn","name":"TSN","roles":roles}],"teams":[],"projects":[]});
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
    let importer = control_plane::provisioning::Importer {
        pool: &e.pool,
        fga: &observed,
        directory: &directory,
        operator: "root",
    };
    value["organizations"][0]["roles"]["user-095"] = serde_json::json!(["personal_space_creator"]);
    let invalid = parse_blueprint(&serde_json::to_vec(&value).unwrap()).unwrap();
    assert!(importer.run(&invalid).await.is_err());
    assert_eq!(proxy.fault.lock().await.writes, 0);
    value["organizations"][0]["roles"]["user-095"] =
        serde_json::json!(["personal_space_creator", "member"]);
    let bundle = parse_blueprint(&serde_json::to_vec(&value).unwrap()).unwrap();
    proxy.fault.lock().await.fail_at = 98; // 96 identity fences, then two role batches.
    assert!(importer.run(&bundle).await.is_err());
    assert_eq!(proxy.fault.lock().await.writes, 98);
    assert!(reads(&e, "user-095", org.id).await);
    assert!(
        !e.fga
            .check_space(
                "user-095",
                control_plane::roles::SpacePermission::CreatePersonalSpace,
                org.id
            )
            .await
            .unwrap()
    );
    proxy.fault.lock().await.fail_at = 0;
    importer.run(&bundle).await.unwrap();
    assert!(
        e.fga
            .check_space(
                "user-095",
                control_plane::roles::SpacePermission::CreatePersonalSpace,
                org.id
            )
            .await
            .unwrap()
    );
}

// Proves: I4, I6
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn personal_grant_budget_and_failed_creation_preserve_authority() {
    let e = env().await;
    let org = crate::support::member_organization(&e.pool, &e.fga, "TSN", "alice")
        .await
        .unwrap();
    grant(&e, org.id, Role::Member, "priya").await;
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
    spaces::grant(
        &e.pool,
        &observed,
        &e.subjects(),
        "alice",
        org.id,
        Role::PersonalSpaceCreator,
        "priya",
    )
    .await
    .unwrap();
    {
        let fault = proxy.fault.lock().await;
        assert_eq!(fault.calls.get("check"), Some(&1));
        assert_eq!(fault.calls.get("read"), Some(&5));
        assert_eq!(fault.writes, 1);
    }
    *proxy.fault.lock().await = support::fga_proxy::Fault {
        fail_at: 1,
        ..Default::default()
    };
    assert!(
        spaces::create_personal_space(&e.pool, &observed, "priya", org.id)
            .await
            .is_err()
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space where personal_owner = 'priya'")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );
    proxy.fault.lock().await.fail_at = 0;
    let (personal, created) = spaces::create_personal_space(&e.pool, &observed, "priya", org.id)
        .await
        .unwrap();
    assert!(created && reads(&e, "priya", personal.id).await);
}

#[path = "support/resource_browsing.rs"]
mod resource_browsing;

#[path = "support/space_deletion.rs"]
mod space_deletion;

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn api_starts_without_temporal_and_keeps_storage_optional() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let doc = document(org.id, None, "kept.pdf");
    crate::environment::insert_document(&e.pool, &doc)
        .await
        .unwrap();
    let unavailable_temporal = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let api_port = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = api_port.local_addr().unwrap().port();
    drop(api_port);
    let pg = reqwest::Url::parse(&std::env::var("CONTROL_PLANE_IT_POSTGRES").unwrap()).unwrap();
    let database: String = sqlx::query_scalar("select current_database()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    let config = serde_json::json!({
        "app":{"base_url":"/control-plane/v1","address":"127.0.0.1","port":port},
        "security":{"user":{"realm_url":identity.realm,"client_id":"app"},"rebac":{"api_url":e.openfga,"store_name":e.store,"create_store_if_needed":false,"sync_schema_on_init":false}},
        "storage":{"postgres":{"host":pg.host_str(),"port":pg.port(),"username":"postgres","database":database}},
        "scheduler":{"lifecycle":{"enabled":true,"temporal":{"host":unavailable_temporal.local_addr().unwrap().to_string()}}}
    });
    let path = std::env::temp_dir().join(format!("manager-read-only-{}.json", Uuid::new_v4()));
    std::fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
    let mut child = tokio::process::Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .arg("serve")
        .env("CONFIG_FILE", &path)
        .env("ENV_FILE", "/nonexistent")
        .env("FRED_POSTGRES_PASSWORD", "it")
        .env_remove("OPENFGA_API_TOKEN")
        .kill_on_drop(true)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .unwrap();
    let http = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .unwrap();
    let base = format!("http://127.0.0.1:{port}/control-plane/v1");
    tokio::time::timeout(Duration::from_secs(20), async {
        loop {
            assert!(
                child.try_wait().unwrap().is_none(),
                "serve exited before binding HTTP"
            );
            if http
                .get(format!("{base}/healthz"))
                .send()
                .await
                .is_ok_and(|r| r.status().is_success())
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
    })
    .await
    .unwrap();
    let token = identity.token("alice");
    assert_eq!(
        http.get(format!("{base}/spaces/{}/entries", org.id))
            .bearer_auth(&token)
            .send()
            .await
            .unwrap()
            .status(),
        200
    );
    assert_eq!(
        http.get(format!("{base}/spaces/{}/storage", org.id))
            .bearer_auth(&token)
            .send()
            .await
            .unwrap()
            .status(),
        503
    );
    assert_eq!(
        http.get(format!("{base}/documents/{}/content", doc.id))
            .bearer_auth(&token)
            .send()
            .await
            .unwrap()
            .status(),
        503
    );
    for (method, suffix, status) in [
        (reqwest::Method::POST, "/documents".into(), 404),
        (
            reqwest::Method::PATCH,
            format!("/documents/{}", doc.id),
            404,
        ),
        (
            reqwest::Method::DELETE,
            format!("/documents/{}", doc.id),
            404,
        ),
        (
            reqwest::Method::POST,
            format!("/documents/{}/ingest", doc.id),
            404,
        ),
    ] {
        assert_eq!(
            http.request(method, format!("{base}{suffix}"))
                .bearer_auth(&token)
                .json(&serde_json::json!({"name":"changed"}))
                .send()
                .await
                .unwrap()
                .status(),
            status
        );
    }
    assert_eq!(
        db::document(&e.pool, doc.id).await.unwrap().name,
        "kept.pdf"
    );
    assert_eq!(
        http.post(format!("{base}/folders"))
            .bearer_auth(&token)
            .json(&serde_json::json!({"space_id":org.id,"name":"Folder"}))
            .send()
            .await
            .unwrap()
            .status(),
        201
    );
    // The supervised worker connects independently; HTTP stays available while
    // its Temporal peer never completes the protocol handshake.
    let (_connection, _) =
        tokio::time::timeout(Duration::from_secs(5), unavailable_temporal.accept())
            .await
            .unwrap()
            .unwrap();
    assert_eq!(
        http.get(format!("{base}/healthz"))
            .send()
            .await
            .unwrap()
            .status(),
        200
    );
    child.kill().await.unwrap();
    child.wait().await.unwrap();
    std::fs::remove_file(path).unwrap();
}

#[path = "support/organization_console.rs"]
mod organization_console;

#[path = "support/folder_scaling.rs"]
mod folder_scaling;
