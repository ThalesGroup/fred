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

//! Regression tests against a real Postgres, both throwaway
//! containers started by `make test-integration`. Each test gets its own database and
//! its own isolated SQL state.

use std::time::Duration;

use control_plane::{
    bootstrap, db,
    domain::{self, Document, Folder, Permission, Role, Space, SpaceKind},
    error::AppError,
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
#[path = "support/sql_boundary.rs"]
mod sql_boundary;
use environment::{Env, env, named_space};

/// Removes a tuple behind control-plane's back, as another admin or an operator would.
async fn delete_tuple(e: &Env, user: &str, relation: &str, object: &str) {
    if let Some(id) = object.strip_prefix("space:") {
        sqlx::query("delete from space_role_grant where space_id=$1 and subject=$2 and role=$3")
            .bind(Uuid::parse_str(id).unwrap())
            .bind(user)
            .bind(relation)
            .execute(&e.pool)
            .await
            .unwrap();
    } else {
        sqlx::query("delete from platform_role_grant where subject=$1 and role=$2")
            .bind(user)
            .bind(relation)
            .execute(&e.pool)
            .await
            .unwrap();
    }
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
    let org = crate::support::member_organization(&e.pool, "TSN", "alice")
        .await
        .unwrap();
    let team = spaces::create_space(
        &e.pool,
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
    spaces::grant(&e.pool, &e.subjects(), "alice", space, role, user)
        .await
        .unwrap();
}

async fn reads(e: &Env, user: &str, space: Uuid) -> bool {
    control_plane::authorization::authorize(&e.pool, user, space, Permission::Read)
        .await
        .is_ok()
}

// Proves: I4
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn concurrent_revocations_keep_parent_access() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let project = spaces::create_space(
        &e.pool,
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
            spaces::revoke(&e.pool, "alice", team.id, Role::Member, "bob"),
            spaces::revoke(&e.pool, "alice", team.id, Role::Editor, "bob"),
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
#[ignore = "needs Postgres: make test-integration"]
async fn concurrent_grant_and_revoke_keep_the_invariant() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let project = spaces::create_space(
        &e.pool,
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
            spaces::grant(&e.pool, &subjects, "alice", project.id, Role::Member, "bob"),
            spaces::revoke(&e.pool, "alice", team.id, Role::Member, "bob"),
        );
        if reads(&e, "bob", project.id).await {
            assert!(
                reads(&e, "bob", team.id).await,
                "round {round}: project role without team access"
            );
        }
        let _ = spaces::revoke(&e.pool, "alice", project.id, Role::Member, "bob").await;
    }
}

// Proves: I5
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn a_revoked_admin_cannot_finish_a_waiting_request() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Owner, "bob").await;

    let held = hold_organization_lock(&e, org.id).await;
    let pending = {
        let (pool, open) = (e.pool.clone(), e.open_directory());
        tokio::spawn(async move {
            spaces::grant(
                &pool,
                &control_plane::users::Directory::Keycloak(Some(&open)),
                "bob",
                team.id,
                Role::Owner,
                "bob",
            )
            .await
        })
    };
    // Let bob's request reach the lock, then revoke him while it waits.
    tokio::time::sleep(Duration::from_millis(300)).await;
    delete_tuple(&e, "bob", "owner", &format!("space:{}", team.id)).await;
    held.commit().await.unwrap();

    assert!(matches!(pending.await.unwrap(), Err(AppError::Forbidden)));
    assert!(
        control_plane::authorization::authorize(&e.pool, "bob", team.id, Permission::Manage)
            .await
            .is_err()
    );
}

// Proves: I6
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn a_member_with_a_personal_space_can_leave_the_organization() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, org.id, Role::Owner, "bob").await;
    let personal = spaces::create_personal_space(&e.pool, "bob", org.id)
        .await
        .unwrap()
        .0;

    spaces::revoke(&e.pool, "alice", org.id, Role::Owner, "bob")
        .await
        .unwrap();
    let blocked = spaces::revoke(&e.pool, "alice", org.id, Role::Member, "bob").await;
    assert!(matches!(blocked, Err(AppError::Conflict(_))));
    let widened = spaces::grant(
        &e.pool,
        &e.subjects(),
        "alice",
        personal.id,
        Role::Member,
        "carol",
    )
    .await;
    assert!(matches!(widened, Err(AppError::Conflict(_))));
    let by_owner = spaces::revoke(&e.pool, "bob", personal.id, Role::Editor, "bob").await;
    assert!(matches!(by_owner, Err(AppError::Forbidden)));

    for role in [Role::Editor, Role::Member] {
        spaces::revoke(&e.pool, "alice", personal.id, role, "bob")
            .await
            .unwrap();
    }
    spaces::revoke(&e.pool, "alice", org.id, Role::Member, "bob")
        .await
        .unwrap();
    assert!(!reads(&e, "bob", org.id).await);
    assert!(!reads(&e, "bob", personal.id).await);
}

// Proves: I9
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn bootstrap_promotes_one_person_once() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "alice").await.unwrap();
    assert!(
        control_plane::authorization::is_platform_admin(&e.pool, "alice")
            .await
            .unwrap()
    );
    for user in ["bob", "alice"] {
        let again = bootstrap::grant_root(&e.pool, user).await;
        assert!(
            matches!(again, Err(AppError::Conflict(_))),
            "{user} must get 409"
        );
    }
    assert!(
        !control_plane::authorization::is_platform_admin(&e.pool, "bob")
            .await
            .unwrap()
    );
}

// Proves: I9
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn a_finished_bootstrap_stays_closed_after_its_admin_is_removed() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "alice").await.unwrap();
    delete_tuple(&e, "alice", "platform_admin", "platform:root").await;
    let again = bootstrap::grant_root(&e.pool, "alice").await;
    assert!(matches!(again, Err(AppError::Conflict(_))));
    assert!(
        !control_plane::authorization::is_platform_admin(&e.pool, "alice")
            .await
            .unwrap()
    );
}

// Proves: I9
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
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
        let pool = e.pool.clone();
        tokio::spawn(async move { bootstrap::grant_root(&pool, "alice").await })
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
#[ignore = "needs Postgres: make test-integration"]
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
#[ignore = "needs Postgres: make test-integration"]
async fn owner_roles_grant_no_content_access() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "dave").await.unwrap();
    let (org, _) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "carol").await;
    let team = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Team,
        org.id,
        "OPS".into(),
        "carol",
    )
    .await
    .unwrap();
    assert!(
        control_plane::authorization::authorize(&e.pool, "carol", team.id, Permission::Manage)
            .await
            .is_ok()
    );
    assert!(
        !reads(&e, "carol", team.id).await,
        "a space owner is not a reader"
    );
    assert!(
        !reads(&e, "dave", org.id).await,
        "a platform admin is not a reader"
    );
}

// Proves: I8
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn complete_role_permission_matrix_and_space_isolation() {
    use control_plane::roles::{
        PlatformPermission as PP, PlatformRole as P, SpacePermission as SP,
    };
    let e = env().await;
    let space = Uuid::new_v4();
    let other = Uuid::new_v4();
    sqlx::query(
        "insert into space(id,kind,name,organization_id) values($1,'organization','Matrix',$1)",
    )
    .bind(space)
    .execute(&e.pool)
    .await
    .unwrap();
    // Enumerate every subset: cumulative grants must equal the union of their individual rights.
    let roles = Role::ALL;
    for mask in 0..(1 << roles.len()) {
        let user = format!("space-{mask}");
        let held: Vec<_> = roles
            .iter()
            .enumerate()
            .filter(|(i, _)| mask & (1 << i) != 0)
            .map(|(_, r)| *r)
            .collect();
        for role in &held {
            control_plane::authorization::write_role(
                &mut e.pool.acquire().await.unwrap(),
                &user,
                *role,
                space,
                true,
            )
            .await
            .unwrap();
        }
        let facts = control_plane::authorization::load_facts(&e.pool, &user, space)
            .await
            .unwrap();
        for permission in SP::ALL {
            let expected = held.iter().any(|role| match permission {
                SP::Read => matches!(role, Role::Member | Role::Editor | Role::Analyst),
                SP::Write => *role == Role::Editor,
                SP::Manage => *role == Role::Owner,
                SP::RunEvaluations | SP::ManageEvaluationCorpus | SP::ReadUsage => {
                    matches!(role, Role::Owner | Role::Analyst)
                }
                SP::ReadConversationsForEvaluation => *role == Role::Analyst,
                SP::AdministerOrganization => *role == Role::OrganizationAdmin,
                SP::CreatePersonalSpace => matches!(
                    role,
                    Role::Owner | Role::Member | Role::Editor | Role::Analyst
                ),
            });
            assert_eq!(
                control_plane::authorization::authorize(&e.pool, &user, space, permission)
                    .await
                    .is_ok(),
                expected,
                "{mask} {permission:?}"
            );
            assert_eq!(
                control_plane::authorization::decide(&facts, permission).is_ok(),
                expected,
                "loaded facts: {mask} {permission:?}"
            );
            assert!(
                control_plane::authorization::authorize(&e.pool, &user, other, permission)
                    .await
                    .is_err()
            );
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
            control_plane::authorization::write_platform(
                &mut e.pool.acquire().await.unwrap(),
                &user,
                *role,
                true,
            )
            .await
            .unwrap();
        }
        for permission in PP::ALL {
            let expected = held.iter().any(|role| {
                (*role == P::PlatformAdmin
                    && matches!(
                        permission,
                        PP::DeleteTeam
                            | PP::DeleteSpace
                            | PP::RescueTeamOwner
                            | PP::EditAgentClassPath
                            | PP::AdministerUsers
                            | PP::ManagePlatform
                    ))
                    || matches!(
                        (role, permission),
                        (P::PlatformObserver, PP::ObservePlatform)
                            | (P::FeatureManager, PP::ManageCapabilities | PP::ListAllTeams)
                            | (P::PromptEditor, PP::EditPlatformPrompt)
                    )
            });
            assert_eq!(
                control_plane::authorization::check_platform(&e.pool, &user, permission)
                    .await
                    .unwrap(),
                expected,
                "{mask} {permission:?}"
            );
        }
        for permission in SP::ALL {
            assert!(
                control_plane::authorization::authorize(&e.pool, &user, space, permission)
                    .await
                    .is_err()
            );
        }
        let effective = control_plane::authorization::platform_roles(&e.pool, &user)
            .await
            .unwrap();
        assert_eq!(effective, held);
    }
}

// Proves: I4, I6
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn analyst_membership_is_content_and_personal_roles_remain_fixed() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Analyst, "analyst").await;
    grant(&e, team.id, Role::Owner, "analyst").await;
    assert!(matches!(
        spaces::revoke(&e.pool, "alice", org.id, Role::Analyst, "analyst").await,
        Err(AppError::Conflict(_))
    ));
    grant(&e, org.id, Role::Member, "analyst").await;
    spaces::revoke(&e.pool, "alice", org.id, Role::Analyst, "analyst")
        .await
        .unwrap();
    let personal = spaces::create_personal_space(&e.pool, "analyst", org.id)
        .await
        .unwrap()
        .0;
    assert!(matches!(
        spaces::grant(
            &e.pool,
            &e.subjects(),
            "alice",
            personal.id,
            Role::Analyst,
            "alice"
        )
        .await,
        Err(AppError::Conflict(_))
    ));
    spaces::revoke(&e.pool, "alice", team.id, Role::Owner, "analyst")
        .await
        .unwrap();
    assert!(
        !reads(&e, "analyst", team.id).await,
        "revoking governance must not create content rights"
    );
}

// Proves: I14
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn concurrent_owner_revocations_leave_one_owner_at_every_level() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let project = spaces::create_space(
        &e.pool,
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
        grant(&e, space, Role::Owner, "bob").await;
        let (a, b) = tokio::join!(
            spaces::revoke(&e.pool, "alice", space, Role::Owner, "alice"),
            spaces::revoke(&e.pool, "bob", space, Role::Owner, "bob"),
        );
        assert_eq!(usize::from(a.is_ok()) + usize::from(b.is_ok()), 1);
        assert_eq!(
            control_plane::authorization::space_holders(&e.pool, space, Role::Owner)
                .await
                .unwrap()
                .len(),
            1
        );
    }
}

// Proves: I8
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn teams_are_created_by_organization_owners_only() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    // Platform adminship confers no business role in an organization.
    let by_root = spaces::create_space(
        &e.pool,
        "root",
        SpaceKind::Team,
        org.id,
        "Platform".into(),
        "alice",
    )
    .await;
    // The platform admin is outside the organization: the parent is not found for them.
    assert!(matches!(by_root, Err(AppError::NotFound)));
    let created = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Team,
        org.id,
        "Local".into(),
        "alice",
    )
    .await
    .unwrap();
    assert!(!reads(&e, "alice", created.id).await);
    grant(&e, org.id, Role::Owner, "organization_owner").await;
    let owned = spaces::create_space(
        &e.pool,
        "organization_owner",
        SpaceKind::Team,
        org.id,
        "Delegated".into(),
        "alice",
    )
    .await
    .unwrap();
    assert!(
        control_plane::authorization::direct_roles_on(&e.pool, "organization_owner", owned.id)
            .await
            .unwrap()
            .is_empty()
    );
    assert!(matches!(
        spaces::create_space(
            &e.pool,
            "organization_owner",
            SpaceKind::Project,
            team.id,
            "Denied owner".into(),
            "alice"
        )
        .await,
        Err(AppError::Forbidden)
    ));
    assert!(matches!(
        spaces::create_space(
            &e.pool,
            "alice-owner",
            SpaceKind::Team,
            org.id,
            "Denied admin".into(),
            "alice"
        )
        .await,
        Err(AppError::Forbidden)
    ));
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "Allowed project".into(),
        "alice",
    )
    .await
    .unwrap();
    assert_eq!(project.parent_id, Some(team.id));
    assert!(matches!(
        spaces::create_space(
            &e.pool,
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
#[ignore = "needs Postgres: make test-integration"]
async fn platform_admins_manage_each_other_and_keep_one() {
    use control_plane::{platform, roles::PlatformRole as P};
    let e = env().await;
    let server = support::IdentityServer::start().await;
    for user in ["root", "owner", "observer"] {
        server.users.lock().await.insert(user.into(), user.into());
    }
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    platform::grant(&e.pool, Some(&directory), "root", "owner", P::PlatformAdmin)
        .await
        .unwrap();
    for target in ["missing", "unavailable"] {
        assert!(
            platform::grant(
                &e.pool,
                Some(&directory),
                "root",
                target,
                P::PlatformObserver
            )
            .await
            .is_err()
        );
        assert!(
            control_plane::authorization::platform_roles(&e.pool, target)
                .await
                .unwrap()
                .is_empty()
        );
    }
    assert!(matches!(
        platform::revoke(&e.pool, "root", "owner", P::PlatformObserver).await,
        Err(AppError::NotFound)
    ));
    platform::grant(
        &e.pool,
        Some(&directory),
        "owner",
        "observer",
        P::PlatformObserver,
    )
    .await
    .unwrap();
    assert!(matches!(
        platform::grant(
            &e.pool,
            Some(&directory),
            "observer",
            "observer",
            P::PromptEditor
        )
        .await,
        Err(AppError::Forbidden)
    ));
    server.users.lock().await.remove("observer");
    platform::revoke(&e.pool, "owner", "observer", P::PlatformObserver)
        .await
        .unwrap();
    assert_eq!(platform::list(&e.pool, "root").await.unwrap().len(), 2);

    // Any owner hands over ownership, root included; the last owner stays.
    platform::revoke(&e.pool, "owner", "root", P::PlatformAdmin)
        .await
        .unwrap();
    assert!(
        !control_plane::authorization::is_platform_admin(&e.pool, "root")
            .await
            .unwrap()
    );
    assert!(matches!(
        platform::revoke(&e.pool, "owner", "owner", P::PlatformAdmin).await,
        Err(AppError::Conflict(_))
    ));
    assert!(
        control_plane::authorization::is_platform_admin(&e.pool, "owner")
            .await
            .unwrap()
    );
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
#[ignore = "needs Postgres: make test-integration"]
async fn revoked_platform_actor_cannot_complete_a_waiting_platform_or_owner_grant() {
    use control_plane::{platform, roles::PlatformRole as P};
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, _) = org_and_team(&e).await;
    for owner_grant in [false, true] {
        control_plane::authorization::write_platform(
            &mut e.pool.acquire().await.unwrap(),
            "delegate",
            P::PlatformAdmin,
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
        let (pool, open) = (e.pool.clone(), e.open_directory());
        let pending = tokio::spawn(async move {
            if owner_grant {
                spaces::grant(
                    &pool,
                    &control_plane::users::Directory::Keycloak(Some(&open)),
                    "delegate",
                    org.id,
                    Role::OrganizationAdmin,
                    "target",
                )
                .await
            } else {
                platform::grant(&pool, None, "delegate", "target", P::PromptEditor).await
            }
        });
        wait_for_advisory_waiter(&e.pool).await;
        control_plane::authorization::write_platform(
            &mut e.pool.acquire().await.unwrap(),
            "delegate",
            P::PlatformAdmin,
            false,
        )
        .await
        .unwrap();
        tx.commit().await.unwrap();
        assert!(matches!(pending.await.unwrap(), Err(AppError::Forbidden)));
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
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
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let app = routes(AppState {
        agent_catalog: Default::default(),
        onboarding: Default::default(),
        lifecycle: Default::default(),
        auth: Arc::new(server.auth().await),
        pool: e.pool.clone(),
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
    assert_eq!(
        me["platform_roles"],
        serde_json::to_value([P::PlatformAdmin]).unwrap()
    );
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
    assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
    let result: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body(), 65536).await.unwrap()).unwrap();
    assert_eq!(result["code"], "invalid_fields");
    // A valid probe evaluates the authenticated caller, never a body-supplied user.
    for (actor, allowed) in [("observer", false), ("root", true)] {
        let response = app
            .clone()
            .oneshot(request(
                "POST",
                "/authorize/platform",
                Some(actor),
                r#"{"permission":"manage_platform"}"#,
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let result: serde_json::Value =
            serde_json::from_slice(&to_bytes(response.into_body(), 65536).await.unwrap()).unwrap();
        assert_eq!(result["allowed"], allowed);
    }
    let direct = app
        .oneshot(request("GET", "/users/platform-roles", Some("root"), ""))
        .await
        .unwrap();
    let direct: serde_json::Value =
        serde_json::from_slice(&to_bytes(direct.into_body(), 65536).await.unwrap()).unwrap();
    assert_eq!(direct.as_array().unwrap().len(), 2);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
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
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
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
            agent_catalog: Default::default(),
            onboarding: Default::default(),
            lifecycle: Default::default(),
            auth: Arc::new(
                Authenticator::start(config.security().unwrap())
                    .await
                    .unwrap(),
            ),
            pool: e.pool.clone(),
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
            !control_plane::authorization::platform_grants(&e.pool)
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
#[ignore = "needs Postgres: make test-integration"]
async fn only_effective_role_changes_are_audited_once() {
    use tracing_subscriber::prelude::*;
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let capture = AuditCapture::default();
    let _thread =
        tracing::subscriber::set_default(tracing_subscriber::registry().with(capture.clone()));
    grant(&e, org.id, Role::Member, "bob").await;
    spaces::revoke(&e.pool, "alice", org.id, Role::Editor, "bob")
        .await
        .unwrap();
    spaces::revoke(&e.pool, "alice", org.id, Role::Member, "bob")
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

fn provisioning_bundle() -> control_plane::provisioning::Bundle {
    parse_blueprint(br#"{"users":[{"username":"alice","password":"private-password","first_name":"Alice","last_name":"Example"},{"username":"bob","password":"private-password","platform_roles":["platform_observer","feature_manager","prompt_editor"]},{"username":"platform-only","password":"private-password","platform_roles":["platform_admin"]}],"organizations":[{"ref":"org","name":"Provisioned","roles":{"alice":["owner","member","organization_admin"],"bob":["member"]}}],"teams":[{"ref":"BID","name":"BID","organization":"org","roles":{"alice":["owner"],"bob":["member","editor","analyst"]}}],"projects":[]}"#).unwrap()
}

// Proves: I4, I8, I17
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn provisioning_replays_every_role_without_updating_identities_or_implicit_content() {
    use control_plane::{provisioning::Importer, roles::PlatformRole};
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    db::require_initialized(&e.pool).await.unwrap();
    let authorization_pool = e.pool.clone();
    let bundle = provisioning_bundle();
    let importer = Importer {
        pool: &e.pool,
        directory: &directory,
        operator: "root",
    };
    let first = importer.run(&bundle).await.unwrap();
    assert_eq!(first.identities_created, 3);
    let org = named_space(&e.pool, None, "Provisioned")
        .await
        .unwrap()
        .unwrap();
    let team = named_space(&e.pool, Some(org.id), "BID")
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
    assert!(
        control_plane::authorization::roles_of(&authorization_pool, "root")
            .await
            .unwrap()
            .is_empty()
    );
    assert!(
        control_plane::authorization::roles_of(&authorization_pool, &platform)
            .await
            .unwrap()
            .is_empty()
    );
    assert!(
        control_plane::authorization::authorize(
            &authorization_pool,
            &alice,
            team.id,
            Permission::Read
        )
        .await
        .is_err()
    );
    assert!(
        control_plane::authorization::roles_of(&authorization_pool, &alice)
            .await
            .unwrap()
            .contains(&(org.id, Role::Member))
    );
    for role in [Role::Member, Role::Editor, Role::Analyst] {
        assert!(
            control_plane::authorization::roles_of(&authorization_pool, &bob)
                .await
                .unwrap()
                .contains(&(team.id, role))
        );
    }
    for role in PlatformRole::ALL {
        assert!(
            control_plane::authorization::platform_grants(&authorization_pool)
                .await
                .unwrap()
                .contains(&(
                    if role == PlatformRole::PlatformAdmin {
                        platform.clone()
                    } else {
                        bob.clone()
                    },
                    role
                ))
        );
    }
    // Undeclared roles survive; missing requested grants are repaired on committed IDs.
    control_plane::authorization::write_role(
        &mut e.pool.acquire().await.unwrap(),
        "unrelated",
        Role::Member,
        org.id,
        true,
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
        named_space(&e.pool, Some(org.id), "BID")
            .await
            .unwrap()
            .unwrap()
            .id,
        team.id
    );
    assert!(
        control_plane::authorization::roles_of(&authorization_pool, &bob)
            .await
            .unwrap()
            .contains(&(team.id, Role::Analyst))
    );
    assert!(
        control_plane::authorization::roles_of(&authorization_pool, "unrelated")
            .await
            .unwrap()
            .contains(&(org.id, Role::Member))
    );
}

// Proves: I15, I18
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn provisioning_preflight_failures_have_no_identity_space_or_role_writes() {
    use control_plane::{provisioning::Importer, roles::PlatformRole};
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    control_plane::authorization::write_platform(
        &mut e.pool.acquire().await.unwrap(),
        "observer",
        PlatformRole::PlatformObserver,
        true,
    )
    .await
    .unwrap();
    let before = control_plane::authorization::platform_grants(&e.pool)
        .await
        .unwrap();
    // Bearer validity is checked at admission (HTTP and CLI); here only authority.
    for operator in ["observer", "nobody"] {
        let result = Importer {
            pool: &e.pool,
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
        let bundle = parse_blueprint(&serde_json::to_vec(&serde_json::json!({"organizations":[{"ref":"org","name":"Provisioned","roles":{"alice":["owner","member","organization_admin"]}}],"users":users,"teams":teams,"projects":[]})).unwrap()).unwrap();
        let error = Importer {
            pool: &e.pool,
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
    assert_eq!(
        control_plane::authorization::platform_grants(&e.pool)
            .await
            .unwrap(),
        before
    );
}

// Proves: I11, I17
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
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
#[ignore = "needs Postgres: make test-integration"]
async fn provisioning_replay_after_identity_and_sql_failures_reuses_committed_state() {
    use control_plane::provisioning::Importer;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let bundle = provisioning_bundle();
    let importer = Importer {
        pool: &e.pool,
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
        named_space(&e.pool, None, "Provisioned")
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
#[ignore = "needs Postgres: make test-integration"]
async fn simultaneous_imports_reuse_usernames_and_space_names() {
    use control_plane::provisioning::Importer;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let bundle = provisioning_bundle();
    let importer = Importer {
        pool: &e.pool,
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
#[ignore = "needs Postgres: make test-integration"]
async fn provisioning_waiter_rechecks_revocation_but_not_bearer_expiry() {
    use control_plane::{
        api::{AppState, routes},
        provisioning::Importer,
    };
    let bundle = br#"{"users":[{"username":"alice","password":"private-password"}],"organizations":[{"ref":"org","name":"new","roles":{"alice":["owner","member","organization_admin"]}}],"teams":[],"projects":[]}"#;
    for revoked in [true, false] {
        let e = env().await;
        let server = support::IdentityServer::start().await;
        let directory = server.directory();
        bootstrap::grant_root(&e.pool, "root").await.unwrap();
        let mut tx = e.pool.begin().await.unwrap();
        sqlx::query("select pg_advisory_xact_lock($1)")
            .bind(bootstrap::LOCK_KEY)
            .execute(&mut *tx)
            .await
            .unwrap();
        let pending = if revoked {
            let pool = e.pool.clone();
            tokio::spawn(async move {
                Importer {
                    pool: &pool,
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
                agent_catalog: Default::default(),
                onboarding: Default::default(),
                lifecycle: Default::default(),
                auth: std::sync::Arc::new(server.auth().await),
                pool: e.pool.clone(),
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
            delete_tuple(&e, "root", "platform_admin", "platform:root").await;
        } else {
            tokio::time::sleep(Duration::from_secs(3)).await;
        }
        tx.commit().await.unwrap();
        assert_eq!(pending.await.unwrap(), !revoked);
        assert_eq!(server.users.lock().await.is_empty(), revoked);
    }
}

// Proves: I5, I17, I18
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn preflight_does_not_block_revocation_and_cancelled_identity_creation_replays() {
    use control_plane::provisioning::Importer;
    use std::sync::Arc;
    for cancel in [false, true] {
        let e = env().await;
        let server = support::IdentityServer::start().await;
        let directory = server.directory();
        bootstrap::grant_root(&e.pool, "root").await.unwrap();
        let gate = Arc::new(support::Gate::default());
        if cancel {
            server.control.lock().await.create_gate = Some(gate.clone());
        } else {
            server.control.lock().await.lookup_gate = Some(gate.clone());
        }
        let pool = e.pool.clone();

        let pending = tokio::spawn(async move {
            Importer {
                pool: &pool,
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
            control_plane::authorization::write_platform(
                &mut e.pool.acquire().await.unwrap(),
                "root",
                control_plane::roles::PlatformRole::PlatformAdmin,
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
#[ignore = "needs Postgres and disposable Keycloak: make test-integration"]
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
    bootstrap::grant_root(&e.pool, &root.uid).await.unwrap();
    let directory = Directory::new(&realm, "control-plane", "it-manager".into()).unwrap();
    let importer = Importer {
        pool: &e.pool,
        directory: &directory,
        operator: &root.uid,
    };
    // Predictable identity failures cannot create even the first account in a bundle.
    let declaration = serde_json::json!({"users":[{"username":"prefix","password":"private-password"},{"username":"tail","password":"private-password"}],"organizations":[{"ref":"o","name":"Preflight","roles":{"prefix":["organization_admin","owner"]}}],"teams":[],"projects":[]});
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
    let org = named_space(&e.pool, None, "Provisioned")
        .await
        .unwrap()
        .unwrap();
    let team = named_space(&e.pool, Some(org.id), "BID")
        .await
        .unwrap()
        .unwrap();
    assert!(
        control_plane::authorization::authorize(&e.pool, &alice.id, team.id, Permission::Read)
            .await
            .is_err()
    );
    for role in [Role::Member, Role::Editor, Role::Analyst] {
        assert!(
            control_plane::authorization::roles_of(&e.pool, &bob.id)
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
    let grants = control_plane::authorization::platform_grants(&e.pool)
        .await
        .unwrap();
    for role in control_plane::roles::PlatformRole::ALL {
        let subject = if role == control_plane::roles::PlatformRole::PlatformAdmin {
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
    bootstrap::grant_root(&e.pool, &root.uid).await.unwrap();
    // Acceptance uses the artifact built by the actual public Make command over HTTP.
    let output = std::env::temp_dir().join(format!("manager-demo-{}.zip", Uuid::new_v4()));
    assert!(
        tokio::process::Command::new("make")
            .arg("bundle-demo")
            .env("DEMO_BUNDLE_FILE", &output)
            .status()
            .await
            .unwrap()
            .success()
    );
    let bytes = std::fs::read(&output).unwrap();
    std::fs::remove_file(output).unwrap();

    let app = control_plane::api::routes(control_plane::api::AppState {
        agent_catalog: Default::default(),
        onboarding: Default::default(),
        lifecycle: Default::default(),
        auth: std::sync::Arc::new(auth),
        pool: e.pool.clone(),
        directory: Some(directory.clone()),
        content: None,
        processing: None,
    });
    let (status, report) = http_import(&app, &token, &bytes).await;
    assert_eq!(status, 200, "{report}");
    assert_eq!(report["identities_created"], 9); // Alice and Bob already exist.
    assert_eq!(report["spaces_reconciled"], 5);
    let acme = named_space(&e.pool, None, "Acme").await.unwrap().unwrap();
    let research = named_space(&e.pool, Some(acme.id), "Research")
        .await
        .unwrap()
        .unwrap();
    let carl = directory.find_username("carl").await.unwrap().unwrap();
    assert!(
        control_plane::authorization::authorize(&e.pool, &carl.id, research.id, Permission::Read)
            .await
            .is_err()
    );
    assert!(
        control_plane::authorization::authorize(&e.pool, &carl.id, research.id, Permission::Manage)
            .await
            .is_ok()
    );
    assert!(
        control_plane::authorization::authorize(&e.pool, &carl.id, acme.id, Permission::Read)
            .await
            .is_ok()
    );
    // Demo provisioning adds platform authority only to the `boss` convenience account.
    let boss = directory.find_username("boss").await.unwrap().unwrap();
    let mut platform = control_plane::authorization::platform_grants(&e.pool)
        .await
        .unwrap();
    platform.sort();
    let mut expected: Vec<_> = control_plane::roles::PlatformRole::ALL
        .into_iter()
        .map(|role| (boss.id.clone(), role))
        .chain([(
            root.uid.clone(),
            control_plane::roles::PlatformRole::PlatformAdmin,
        )])
        .collect();
    expected.sort();
    assert_eq!(platform, expected);
    let globex = named_space(&e.pool, None, "Globex").await.unwrap().unwrap();
    let support = named_space(&e.pool, Some(globex.id), "Support")
        .await
        .unwrap()
        .unwrap();
    assert!(
        control_plane::authorization::authorize(&e.pool, &bob.id, support.id, Permission::Read)
            .await
            .is_err()
    );
    let (status, report) = http_import(&app, &token, &bytes).await;
    assert_eq!(status, 200, "{report}");
    assert_eq!(report["identities_created"], 0);
    assert_eq!(
        named_space(&e.pool, None, "Acme")
            .await
            .unwrap()
            .unwrap()
            .id,
        acme.id
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
            .any(|s| s["id"] == acme.id.to_string())
    );
    // Variant declares a project and uses the same HTTP path and real directory.
    let variant = fixture_zip(br#"{"users":[{"username":"carl"},{"username":"bob"}],"organizations":[{"ref":"acme","name":"Acme","roles":{}}],"teams":[{"ref":"research","name":"Research","organization":"acme","roles":{"carl":["member"]}}],"projects":[{"ref":"project","name":"Project","team":"research","roles":{"carl":["owner"],"bob":["member","editor","analyst"]}}]}"#);
    let (status, report) = http_import(&app, &token, &variant).await;
    assert_eq!(status, 200, "{report}");
    let project = named_space(&e.pool, Some(research.id), "Project")
        .await
        .unwrap()
        .unwrap();
    assert_eq!(project.path, vec![acme.id, research.id, project.id]);
    assert!(
        control_plane::authorization::authorize(&e.pool, &carl.id, project.id, Permission::Read)
            .await
            .is_err()
    );
    assert!(
        control_plane::authorization::authorize(&e.pool, &carl.id, project.id, Permission::Manage)
            .await
            .is_ok()
    );
    for role in [Role::Member, Role::Editor, Role::Analyst] {
        assert!(
            control_plane::authorization::roles_of(&e.pool, &bob.id)
                .await
                .unwrap()
                .contains(&(project.id, role))
        );
    }
}

// Proves: I5
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn folder_creation_keeps_one_connection_through_placement_and_write() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let parent = spaces::create_folder(&e.pool, "alice", team.id, None, "parent".into())
        .await
        .unwrap();
    let pool = sqlx::postgres::PgPoolOptions::new()
        .max_connections(1)
        .connect_with((*e.pool.connect_options()).clone())
        .await
        .unwrap();
    let child = tokio::time::timeout(
        Duration::from_secs(3),
        spaces::create_folder(&pool, "alice", team.id, Some(parent.id), "child".into()),
    )
    .await
    .expect("folder mutation never waits for a second connection")
    .unwrap();
    assert_eq!(child.path, domain::folder_path(Some(&parent), child.id));
    assert_eq!(db::folder(&pool, child.id).await.unwrap().space_id, team.id);
    assert_eq!(db::space(&pool, org.id).await.unwrap().id, org.id);
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn waiting_content_writers_release_the_shared_pool() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let peer = crate::support::member_organization(&e.pool, "peer", "carol")
        .await
        .unwrap();
    spaces::grant(
        &e.pool,
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
        let pool = pool.clone();
        writers.spawn(async move {
            spaces::create_folder(&pool, "alice", team.id, None, format!("waiting-{index}")).await
        });
    }
    wait_for_write_retry(&e.pool, since).await;
    let peer_folder = tokio::time::timeout(
        Duration::from_secs(2),
        spaces::create_folder(&pool, "carol", peer.id, None, "unrelated".into()),
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
#[ignore = "needs Postgres: make test-integration"]
async fn content_lock_deadline_and_cancellation_leave_no_mutation() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let held = hold_organization_lock(&e, org.id).await;
    let before = std::time::Instant::now();
    let result = tokio::time::timeout(
        Duration::from_secs(7),
        spaces::create_folder(&e.pool, "alice", team.id, None, "deadline".into()),
    )
    .await
    .expect("lock acquisition has a five-second deadline");
    assert!(before.elapsed() >= Duration::from_secs(5));
    assert!(matches!(result, Err(AppError::Unavailable(_))));
    let since = sqlx::query_scalar("select clock_timestamp()")
        .fetch_one(&e.pool)
        .await
        .unwrap();
    let pool = e.pool.clone();
    let pending = tokio::spawn(async move {
        spaces::create_folder(&pool, "alice", team.id, None, "cancelled".into()).await
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
    spaces::create_folder(&e.pool, "alice", team.id, None, "after-cancel".into())
        .await
        .unwrap();
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
#[ignore = "needs Postgres: make test-integration"]
async fn blueprint_http_hierarchy_isolation_preflight_and_safe_errors() {
    use control_plane::api::{AppState, routes};
    use tower::ServiceExt;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let auth = std::sync::Arc::new(server.auth().await);
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let app = routes(AppState {
        agent_catalog: Default::default(),
        onboarding: Default::default(),
        lifecycle: Default::default(),
        auth: auth.clone(),
        pool: e.pool.clone(),
        directory: Some(directory.clone()),
        content: None,
        processing: None,
    });
    let token = server.token("root");
    let mut value = serde_json::json!({"users":[{"username":"alice","password":"private-password"},{"username":"bob","password":"private-password"}],"organizations":[{"ref":"a","name":"A","roles":{"alice":["owner","member","organization_admin"]}},{"ref":"b","name":"B","roles":{"bob":["owner","member","organization_admin"]}}],"teams":[{"ref":"at","name":"Team","organization":"a","roles":{"alice":["owner","member"]}},{"ref":"bt","name":"Team","organization":"b","roles":{"bob":["owner","analyst"]}}],"projects":[{"ref":"ap","name":"Project","team":"at","roles":{"alice":["owner","editor"]}},{"ref":"bp","name":"Project","team":"bt","roles":{"bob":["owner"]}}]});
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
    value["teams"][1]["roles"]["bob"] = serde_json::json!(["owner"]);
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
    value["teams"][1]["roles"]["bob"] = serde_json::json!(["owner", "analyst"]);
    // Owner exists only on organizations; a team owner is rejected before identities.
    value["teams"][0]["roles"]["alice"] =
        serde_json::json!(["owner", "member", "organization_admin"]);
    let (s, b) = http_import(
        &app,
        &token,
        &fixture_zip(&serde_json::to_vec(&value).unwrap()),
    )
    .await;
    assert_eq!(s, 422, "{b}");
    assert!(server.users.lock().await.is_empty());
    value["teams"][0]["roles"]["alice"] = serde_json::json!(["owner", "member"]);
    // A new organization needs a declared owner as well as an admin.
    value["organizations"][0]["roles"]["alice"] = serde_json::json!(["owner", "member"]);
    let (s, b) = http_import(
        &app,
        &token,
        &fixture_zip(&serde_json::to_vec(&value).unwrap()),
    )
    .await;
    assert_eq!(s, 422, "{b}");
    assert!(server.users.lock().await.is_empty());
    value["organizations"][0]["roles"]["alice"] =
        serde_json::json!(["owner", "member", "organization_admin"]);
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
        let org = named_space(&e.pool, None, name).await.unwrap().unwrap();
        let team = named_space(&e.pool, Some(org.id), "Team")
            .await
            .unwrap()
            .unwrap();
        let project = named_space(&e.pool, Some(team.id), "Project")
            .await
            .unwrap()
            .unwrap();
        assert_eq!(project.path, vec![org.id, team.id, project.id]);
        for space in [org.id, team.id, project.id] {
            assert!(
                control_plane::authorization::authorize(
                    &e.pool,
                    subject,
                    space,
                    Permission::Manage
                )
                .await
                .is_ok()
            );
            assert!(
                control_plane::authorization::authorize(&e.pool, other, space, Permission::Read)
                    .await
                    .is_err()
            );
            assert!(
                control_plane::authorization::authorize(&e.pool, other, space, Permission::Manage)
                    .await
                    .is_err()
            );
        }
        ids.push(project.id);
    }
    assert_ne!(ids[0], ids[1]);
    // Internal SQL failures expose a phase and counters, never database diagnostics.
    sqlx::raw_sql("CREATE FUNCTION fail_import_fixture() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.name = 'Internal failure' THEN RAISE EXCEPTION 'private-password'; END IF; RETURN NEW; END $$; CREATE TRIGGER fail_import_fixture BEFORE INSERT ON space FOR EACH ROW EXECUTE FUNCTION fail_import_fixture();").execute(&e.pool).await.unwrap();
    let failing=fixture_zip(br#"{"users":[{"username":"failure-owner","password":"private-password"}],"organizations":[{"ref":"bad","name":"Internal failure","roles":{"failure-owner":["owner","organization_admin"]}}],"teams":[],"projects":[]}"#);
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
    const ROOT: &str = "11111111-1111-4111-8111-111111111111";
    const PN: &str = "22222222-2222-4222-8222-222222222222";
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let state = AppState {
        agent_catalog: Default::default(),
        auth: Arc::new(server.auth().await),
        pool: e.pool.clone(),
        directory: None,
        content: None,
        processing: None,
        lifecycle: Default::default(),
        onboarding: Onboarding {
            user_directory: control_plane::users::DirectoryKind::Local,
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
        (
            "POST",
            "/bootstrap/platform-admin",
            json!({"token":"wrong-but-long-enough"}),
            403,
        ),
        ("POST", "/gcu", json!({"version":"v1"}), 403),
        (
            "PATCH",
            "/users/me/preferences",
            json!({"language":"fr"}),
            403,
        ),
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
                .oneshot(request(method, path, Some(server.token(ROOT)), body))
                .await
                .unwrap()
                .status(),
            expected,
            "{path}"
        );
    }
    // Merely opening Weaver with a valid foreign SSO session must remain read-only,
    // including the local-directory configuration used with a generic OIDC provider.
    for path in ["/me/onboarding", "/users/me/preferences"] {
        assert_eq!(
            app.clone()
                .oneshot(request("GET", path, Some(server.token(PN)), Value::Null))
                .await
                .unwrap()
                .status(),
            200
        );
    }
    assert_eq!(sqlx::query_scalar::<_, i64>("select (select count(*) from user_identity) + (select count(*) from users_preferences) + (select count(*) from terms_acceptance) + (select count(*) from platform_role_grant)").fetch_one(&e.pool).await.unwrap(), 0);
    assert!(!onboarding::bootstrap_completed(&e.pool).await.unwrap());
    assert!(
        onboarding::acceptance(&e.pool, ROOT)
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
                "/bootstrap/platform-admin",
                Some(server.token(ROOT)),
                secret.clone()
            ))
            .await
            .unwrap()
            .status(),
        200
    );
    assert_eq!(
        app.clone()
            .oneshot(request("GET", "/me", Some(server.token(ROOT)), Value::Null))
            .await
            .unwrap()
            .status(),
        403
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from user_identity")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        1
    );
    for path in ["/me/onboarding", "/users/me/preferences"] {
        assert_eq!(
            app.clone()
                .oneshot(request("GET", path, Some(server.token(PN)), Value::Null))
                .await
                .unwrap()
                .status(),
            200
        );
    }
    assert_eq!(
        app.clone()
            .oneshot(request("GET", "/me", Some(server.token(PN)), Value::Null))
            .await
            .unwrap()
            .status(),
        403
    );
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from user_identity where id::text = $1")
            .bind(PN)
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        0
    );
    assert_eq!(
        app.clone()
            .oneshot(request(
                "POST",
                "/gcu",
                Some(server.token(ROOT)),
                json!({"version":"old"})
            ))
            .await
            .unwrap()
            .status(),
        409
    );
    assert_eq!(
        app.clone()
            .oneshot(request(
                "POST",
                "/gcu",
                Some(server.token(ROOT)),
                json!({"version":"v1"})
            ))
            .await
            .unwrap()
            .status(),
        204
    );
    let first = onboarding::acceptance(&e.pool, ROOT)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(
        app.clone()
            .oneshot(request(
                "POST",
                "/gcu",
                Some(server.token(ROOT)),
                json!({"version":"v1"})
            ))
            .await
            .unwrap()
            .status(),
        204
    );
    assert_eq!(
        onboarding::acceptance(&e.pool, ROOT)
            .await
            .unwrap()
            .unwrap()
            .accepted_at,
        first.accepted_at
    );
    assert_eq!(
        app.clone()
            .oneshot(request(
                "POST",
                "/bootstrap/platform-admin",
                Some(server.token(ROOT)),
                json!({"token":"wrong-but-long-enough"})
            ))
            .await
            .unwrap()
            .status(),
        403
    );
    assert!(onboarding::bootstrap_completed(&e.pool).await.unwrap());
    assert_eq!(
        app.clone()
            .oneshot(request(
                "POST",
                "/bootstrap/platform-admin",
                Some(server.token(ROOT)),
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
            .oneshot(request("GET", "/me", Some(server.token(ROOT)), Value::Null))
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
                Some(server.token(ROOT)),
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
                Some(server.token(ROOT)),
                json!({"version":"v2"})
            ))
            .await
            .unwrap()
            .status(),
        204
    );
    assert_eq!(
        upgraded
            .oneshot(request("GET", "/me", Some(server.token(ROOT)), Value::Null))
            .await
            .unwrap()
            .status(),
        200
    );
    let visitor = app
        .clone()
        .oneshot(request(
            "GET",
            "/me/onboarding",
            Some(server.token(PN)),
            Value::Null,
        ))
        .await
        .unwrap();
    let status: Value =
        serde_json::from_slice(&to_bytes(visitor.into_body(), 65536).await.unwrap()).unwrap();
    assert_eq!(status["admitted"], false);
    assert_eq!(
        app.clone()
            .oneshot(request(
                "POST",
                "/gcu",
                Some(server.token(PN)),
                json!({"version":"v1"})
            ))
            .await
            .unwrap()
            .status(),
        403
    );
    assert!(onboarding::acceptance(&e.pool, PN).await.unwrap().is_none());

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
        403
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn admission_follows_active_grants_not_personal_space_or_old_consent() {
    use control_plane::authorization::is_admitted;
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    assert!(!is_admitted(&e.pool, "bob").await.unwrap());
    control_plane::onboarding::accept(&e.pool, Some("v1"), "bob", "v1")
        .await
        .unwrap();
    assert!(!is_admitted(&e.pool, "bob").await.unwrap());
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Member, "bob").await;
    delete_tuple(&e, "bob", "member", &format!("space:{}", org.id)).await;
    assert!(is_admitted(&e.pool, "bob").await.unwrap());
    spaces::create_personal_space(&e.pool, "bob", org.id)
        .await
        .unwrap();
    delete_tuple(&e, "bob", "member", &format!("space:{}", team.id)).await;
    assert!(!is_admitted(&e.pool, "bob").await.unwrap());
    grant(&e, org.id, Role::Owner, "bob").await;
    assert!(is_admitted(&e.pool, "bob").await.unwrap());
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.accept(&e.pool, "root", org.id).await.unwrap();
    assert!(!is_admitted(&e.pool, "bob").await.unwrap());
    assert!(is_admitted(&e.pool, "root").await.unwrap());
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn local_admission_requires_explicit_registration_and_a_role() {
    use control_plane::{api, onboarding, users};
    use serde_json::{Value, json};
    use std::sync::Arc;
    const ROOT: &str = "11111111-1111-4111-8111-111111111111";
    const VISITOR: &str = "22222222-2222-4222-8222-222222222222";
    let e = env().await;
    bootstrap::grant_root(&e.pool, ROOT).await.unwrap();
    onboarding::accept(&e.pool, Some("v1"), ROOT, "v1")
        .await
        .unwrap();
    let org = support::member_organization(&e.pool, "Local", ROOT)
        .await
        .unwrap();
    let identity = support::IdentityServer::start().await;
    let app = api::routes(api::AppState {
        agent_catalog: Default::default(),
        auth: Arc::new(identity.auth().await),
        pool: e.pool.clone(),
        directory: None,
        content: None,
        processing: None,
        lifecycle: Default::default(),
        onboarding: onboarding::Onboarding {
            user_directory: users::DirectoryKind::Local,
            gcu_version: Some("v1".into()),
            ..Default::default()
        },
    });
    let request = |actor, method, path, body| {
        support::request(&app, &identity, Some(actor), method, path, body)
    };
    let role_path = format!("/spaces/{}/roles/member/{VISITOR}", org.id);
    for (method, path, body, status) in [
        ("GET", "/me/onboarding", Value::Null, 200),
        ("GET", "/users/me/preferences", Value::Null, 200),
        ("GET", "/me", Value::Null, 403),
        ("POST", "/gcu", json!({"version":"v1"}), 403),
        (
            "PATCH",
            "/users/me/preferences",
            json!({"language":"fr"}),
            403,
        ),
    ] {
        assert_eq!(request(VISITOR, method, path, body).await.0, status);
    }
    assert!(
        !users::Directory::Local(&e.pool)
            .exists(VISITOR)
            .await
            .unwrap()
    );
    assert!(
        onboarding::acceptance(&e.pool, VISITOR)
            .await
            .unwrap()
            .is_none()
    );
    assert_eq!(request(ROOT, "PUT", &role_path, Value::Null).await.0, 422);

    // Exercise the real operator command, using only this test's disposable database.
    let pg = e.pool.connect_options();
    let config = json!({
        "app":{"base_url":"/control-plane/v1","port":8222},
        "security":{"user_directory":"local","user":{"realm_url":identity.realm,"client_id":"app"}},
        "storage":{"postgres":{"host":pg.get_host(),"port":pg.get_port(),"username":"fred_cp","database":pg.get_database()}},
        "scheduler":{}
    });
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("configuration.json");
    std::fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
    for (id, username, success) in [
        (VISITOR, VISITOR, true),
        (VISITOR, VISITOR, true),
        (VISITOR, "another-name", false),
        (VISITOR, "   ", false),
        ("not-a-uuid", VISITOR, false),
    ] {
        let output = tokio::process::Command::new(env!("CARGO_BIN_EXE_control-plane"))
            .args(["register-local-user", id, username])
            .env("CONFIG_FILE", &path)
            .env("ENV_FILE", "/nonexistent")
            .env("FRED_POSTGRES_PASSWORD", "it")
            .kill_on_drop(true)
            .output()
            .await
            .unwrap();
        assert_eq!(
            output.status.success(),
            success,
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
    }
    let local = users::Directory::Local(&e.pool);
    assert_eq!(
        local.find_username(VISITOR).await.unwrap().unwrap().id,
        VISITOR
    );
    assert!(
        !control_plane::authorization::is_admitted(&e.pool, VISITOR)
            .await
            .unwrap()
    );
    assert_eq!(
        request(VISITOR, "POST", "/gcu", json!({"version":"v1"}))
            .await
            .0,
        403
    );

    // Registration makes the identity eligible; only an authorized grant admits it.
    assert_eq!(
        request(VISITOR, "PUT", &role_path, Value::Null).await.0,
        403
    );
    assert_eq!(request(ROOT, "PUT", &role_path, Value::Null).await.0, 204);
    assert_eq!(
        request(VISITOR, "GET", "/me/onboarding", Value::Null)
            .await
            .1["admitted"],
        true
    );
    assert_eq!(request(VISITOR, "GET", "/me", Value::Null).await.0, 403);
    assert_eq!(
        request(VISITOR, "POST", "/gcu", json!({"version":"v1"}))
            .await
            .0,
        204
    );
    assert_eq!(request(VISITOR, "GET", "/me", Value::Null).await.0, 200);

    // Old consent and a retained profile do not survive removal of the last grant.
    assert_eq!(
        request(ROOT, "DELETE", &role_path, Value::Null).await.0,
        204
    );
    assert_eq!(
        request(VISITOR, "GET", "/me/onboarding", Value::Null)
            .await
            .1["admitted"],
        false
    );
    for (method, path, body) in [
        ("GET", "/me", Value::Null),
        ("POST", "/gcu", json!({"version":"v1"})),
        ("PATCH", "/users/me/preferences", json!({"language":"fr"})),
    ] {
        assert_eq!(
            request(VISITOR, method, path, body).await,
            (
                403,
                json!({"code":"admission_required","detail":"user_not_admitted"})
            )
        );
    }
}

/// TSN > BID > project P, all administered by alice, who is a member of TSN and BID.
async fn tree(e: &Env) -> (Space, Space, Space) {
    let (org, team) = org_and_team(e).await;
    let project = spaces::create_space(
        &e.pool,
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
#[ignore = "needs Postgres: make test-integration"]
async fn roles_stay_on_their_space() {
    use control_plane::roles::SpacePermission as P;
    let e = env().await;
    bootstrap::grant_root(&e.pool, "roles-fixture-root")
        .await
        .unwrap();
    let (org, team, project) = tree(&e).await;
    for (user, role) in [
        ("bob", Role::Editor),
        ("ana", Role::Analyst),
        ("claire", Role::Owner),
        ("max", Role::Member),
    ] {
        grant(&e, org.id, role, user).await;
        for space in [team.id, project.id] {
            for permission in [
                P::Read,
                P::Write,
                P::Manage,
                P::RunEvaluations,
                P::ManageEvaluationCorpus,
                P::ReadConversationsForEvaluation,
                P::ReadUsage,
            ] {
                assert!(
                    control_plane::authorization::authorize(&e.pool, user, space, permission)
                        .await
                        .is_err()
                );
            }
        }
        let memberships = spaces::memberships(&e.pool, user).await.unwrap();
        assert_eq!(memberships.len(), 1);
        assert_eq!(memberships[0].space.id, org.id);

        // Parent content membership is structural; the business role stays local.
        grant(&e, org.id, Role::Member, user).await;
        grant(&e, team.id, role, user).await;
        for permission in [
            P::Read,
            P::Write,
            P::Manage,
            P::RunEvaluations,
            P::ManageEvaluationCorpus,
            P::ReadConversationsForEvaluation,
            P::ReadUsage,
        ] {
            assert!(
                control_plane::authorization::authorize(&e.pool, user, project.id, permission)
                    .await
                    .is_err()
            );
        }
        grant(&e, team.id, Role::Member, user).await;
        grant(&e, project.id, role, user).await;
        for (permission, allowed) in [
            (P::Read, role != Role::Owner),
            (P::Write, role == Role::Editor),
            (P::Manage, role == Role::Owner),
            (
                P::RunEvaluations,
                matches!(role, Role::Analyst | Role::Owner),
            ),
            (
                P::ManageEvaluationCorpus,
                matches!(role, Role::Analyst | Role::Owner),
            ),
            (P::ReadConversationsForEvaluation, role == Role::Analyst),
            (P::ReadUsage, matches!(role, Role::Analyst | Role::Owner)),
        ] {
            assert_eq!(
                control_plane::authorization::authorize(&e.pool, user, project.id, permission)
                    .await
                    .is_ok(),
                allowed
            );
        }
    }

    grant(&e, org.id, Role::Member, "pat").await;
    // A personal space inherits nothing, and its organization still manages it.
    grant(&e, org.id, Role::Owner, "pat").await;
    let personal = spaces::create_personal_space(&e.pool, "pat", org.id)
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
        control_plane::authorization::authorize(&e.pool, "bob", personal.id, Permission::Write)
            .await
            .is_err()
    );
    let again = spaces::create_personal_space(&e.pool, "pat", org.id).await;
    assert_eq!(again.unwrap().0.id, personal.id);
    spaces::revoke(&e.pool, "alice", personal.id, Role::Editor, "pat")
        .await
        .unwrap();
}

// Proves: I4
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn child_roles_require_direct_parent_content() {
    let e = env().await;
    let (org, team, project) = tree(&e).await;
    grant(&e, org.id, Role::Editor, "bob").await;
    assert!(!reads(&e, "bob", team.id).await);
    let refused = spaces::grant(
        &e.pool,
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
    let blocked = spaces::revoke(&e.pool, "alice", org.id, Role::Editor, "bob").await;
    assert!(matches!(blocked, Err(AppError::Conflict(_))));
    grant(&e, org.id, Role::Member, "bob").await;
    spaces::revoke(&e.pool, "alice", org.id, Role::Editor, "bob")
        .await
        .unwrap();
    assert!(reads(&e, "bob", project.id).await);
    assert!(
        control_plane::authorization::authorize(&e.pool, "bob", project.id, Permission::Write)
            .await
            .is_err()
    );
}

// Proves: I20
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn memberships_list_direct_spaces_with_their_paths() {
    let e = env().await;
    let (org, team, project) = tree(&e).await;
    grant(&e, org.id, Role::Analyst, "ana").await;
    grant(&e, org.id, Role::Owner, "ana").await;
    let organization_only = spaces::memberships(&e.pool, "ana").await.unwrap();
    assert_eq!(organization_only.len(), 1);
    assert_eq!(organization_only[0].space.id, org.id);
    assert!(!organization_only.iter().any(|m| m.space.id == team.id));
    for space in [team.id, project.id] {
        grant(&e, space, Role::Analyst, "ana").await;
        grant(&e, space, Role::Owner, "ana").await;
    }
    let personal = spaces::create_personal_space(&e.pool, "ana", org.id)
        .await
        .unwrap()
        .0;
    let listed: std::collections::BTreeMap<Uuid, spaces::Membership> =
        spaces::memberships(&e.pool, "ana")
            .await
            .unwrap()
            .into_iter()
            .map(|m| (m.space.id, m))
            .collect();
    assert_eq!(listed.len(), 4);
    let expect = |id: Uuid, path: Vec<Uuid>, roles: Vec<Role>| {
        let m = &listed[&id];
        assert_eq!(m.space.path, path);
        assert_eq!(
            m.space.parent_id,
            path.len().checked_sub(2).map(|i| path[i])
        );
        assert_eq!(m.roles, roles);
    };
    expect(org.id, vec![org.id], vec![Role::Owner, Role::Analyst]);
    expect(
        team.id,
        vec![org.id, team.id],
        vec![Role::Owner, Role::Analyst],
    );
    expect(
        project.id,
        vec![org.id, team.id, project.id],
        vec![Role::Owner, Role::Analyst],
    );
    expect(
        personal.id,
        vec![personal.id],
        vec![Role::Member, Role::Editor],
    );

    // Each membership reports exactly its direct roles.
    let alice = spaces::memberships(&e.pool, "alice").await.unwrap();
    let on_team = alice.iter().find(|m| m.space.id == team.id).unwrap();
    assert_eq!(on_team.roles, vec![Role::Member, Role::Owner]);
}

// Proves: I7
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn scope_follows_ancestors_and_levels_only_narrow_it() {
    use SpaceKind::*;
    let e = env().await;
    let (org, team, project) = tree(&e).await;
    for space in [org.id, team.id, project.id] {
        grant(&e, space, Role::Member, "bob").await;
    }
    let scope = |space: Uuid, levels: Option<Vec<SpaceKind>>| {
        let pool = e.pool.clone();
        async move { spaces::scope(&pool, "bob", space, levels.as_deref()).await }
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
    grant(&e, org.id, Role::Owner, "bob").await;
    let personal = spaces::create_personal_space(&e.pool, "bob", org.id)
        .await
        .unwrap()
        .0;
    assert_eq!(scope(personal.id, None).await.unwrap(), vec![personal.id]);
    assert!(
        scope(personal.id, Some(vec![Team]))
            .await
            .unwrap()
            .is_empty()
    );
    assert_eq!(
        scope(personal.id, Some(vec![Personal])).await.unwrap(),
        vec![personal.id]
    );
    assert!(
        scope(project.id, Some(vec![Personal]))
            .await
            .unwrap()
            .is_empty()
    );
    assert!(
        scope(personal.id, Some(vec![Organization]))
            .await
            .unwrap()
            .is_empty()
    );
    let denied = spaces::scope(&e.pool, "eve", project.id, None).await;
    assert!(matches!(denied, Err(AppError::NotFound)));
}

// Proves: I1
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn space_and_folder_names_are_unique_in_canonical_form() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "writer").await;
    grant(&e, team.id, Role::Editor, "writer").await;
    // Surrounding whitespace and Unicode composition do not make a different name.
    for name in [" TSN", "TSN\u{a0}"] {
        let refused = crate::support::member_organization(&e.pool, name, "bob").await;
        assert_eq!(refused.unwrap_err().0, 409, "{name:?}");
    }
    let create_team = |name: &str| {
        spaces::create_space(
            &e.pool,
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
        "writer",
        team.id,
        None,
        " E\u{301}te\u{301}\t".into(),
    )
    .await
    .unwrap();
    assert_eq!(folder.name, "\u{c9}t\u{e9}");
    assert!(matches!(
        spaces::create_folder(&e.pool, "writer", team.id, None, "\u{c9}t\u{e9}".into()).await,
        Err(AppError::Conflict(_))
    ));
}

// Proves: I8, I14, I21
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn organization_admins_name_owners_and_read_nothing() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let server = support::IdentityServer::start().await;
    server
        .users
        .lock()
        .await
        .insert("olga".into(), "olga".into());
    let directory = server.directory();
    let (org, team) = org_and_team(&e).await;
    // Only a platform admin names organization admins, and only on organizations.
    let by_admin = spaces::grant(
        &e.pool,
        &e.subjects(),
        "alice",
        org.id,
        Role::OrganizationAdmin,
        "olga",
    )
    .await;
    assert!(matches!(by_admin, Err(AppError::Forbidden)));
    spaces::grant(
        &e.pool,
        &control_plane::users::Directory::Keycloak(Some(&directory)),
        "root",
        org.id,
        Role::OrganizationAdmin,
        "olga",
    )
    .await
    .unwrap();
    let on_team = spaces::grant(
        &e.pool,
        &e.subjects(),
        "root",
        team.id,
        Role::OrganizationAdmin,
        "olga",
    )
    .await;
    assert!(matches!(on_team, Err(AppError::Conflict(_))));

    // The admin names organization owners; neither role grants authority on the team.
    spaces::grant(&e.pool, &e.subjects(), "olga", org.id, Role::Owner, "bob")
        .await
        .unwrap();
    assert!(
        control_plane::authorization::authorize(&e.pool, "bob", team.id, Permission::Manage)
            .await
            .is_err()
    );
    assert!(
        control_plane::authorization::authorize(&e.pool, "bob", org.id, Permission::Manage)
            .await
            .is_ok()
    );
    assert!(!reads(&e, "bob", org.id).await);
    assert!(matches!(
        spaces::grant(
            &e.pool,
            &e.subjects(),
            "bob",
            team.id,
            Role::Member,
            "carol"
        )
        .await,
        Err(AppError::Forbidden)
    ));
    for space in [org.id, team.id] {
        assert!(!reads(&e, "olga", space).await);
        assert!(
            control_plane::authorization::authorize(&e.pool, "olga", space, Permission::Manage)
                .await
                .is_err()
        );
    }
    let member = spaces::grant(
        &e.pool,
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
        "olga",
        SpaceKind::Team,
        org.id,
        "By admin".into(),
        "alice",
    )
    .await;
    assert!(matches!(created, Err(AppError::Forbidden)));

    // An organization keeps an owner.
    spaces::revoke(
        &e.pool,
        "root",
        org.id,
        Role::OrganizationAdmin,
        "alice-owner",
    )
    .await
    .unwrap();
    let last = spaces::revoke(&e.pool, "root", org.id, Role::OrganizationAdmin, "olga").await;
    assert!(matches!(last, Err(AppError::Conflict(_))));
    assert_eq!(
        control_plane::authorization::space_holders(&e.pool, org.id, Role::OrganizationAdmin)
            .await
            .unwrap(),
        vec!["olga".to_string()]
    );
}

async fn content_app(e: &Env, identity: &support::IdentityServer) -> axum::Router {
    control_plane::api::router(
        control_plane::api::AppState {
            agent_catalog: Default::default(),
            auth: std::sync::Arc::new(identity.auth().await),
            pool: e.pool.clone(),
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
#[ignore = "needs Postgres: make test-integration"]
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
    let error = worker::run(e.pool.clone(), config, std::future::pending())
        .await
        .unwrap_err();
    assert_eq!(worker::stage(&error), "temporal_connect");
    assert!(!format!("{error:#}").contains("127.0.0.1"), "{error:#}");
    assert_eq!(worker::stage(&anyhow::anyhow!("other")), "unknown");
}

// Proves: I23
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn business_routes_share_one_authorization_answer() {
    use serde_json::{Value, json};
    use tower::ServiceExt;
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "writer").await;
    grant(&e, team.id, Role::Editor, "writer").await;
    grant(&e, org.id, Role::Member, "bystander").await;
    crate::support::member_organization(&e.pool, "Other", "carol")
        .await
        .unwrap();
    let folder = spaces::create_folder(&e.pool, "writer", team.id, None, "kept".into())
        .await
        .unwrap();
    let retired = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Team,
        org.id,
        "Retired".into(),
        "alice",
    )
    .await
    .unwrap();
    grant(&e, retired.id, Role::Editor, "writer").await;
    let retired_folder = spaces::create_folder(&e.pool, "writer", retired.id, None, "old".into())
        .await
        .unwrap();
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    let retired_org =
        crate::support::member_organization(&e.pool, "Retired personal organization", "writer")
            .await
            .unwrap();
    let (retired_personal, _) = spaces::create_personal_space(&e.pool, "writer", retired_org.id)
        .await
        .unwrap();
    for id in [retired.id, retired_org.id] {
        lifecycle.accept(&e.pool, "root", id).await.unwrap();
    }

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
    // Organization-only reads and mutations reject kind before permission or retirement.
    for user in ["alice", "bystander", "carol"] {
        for id in [team.id, retired.id] {
            let (status, body) = call(
                user,
                "GET",
                format!("/organizations/{id}/models"),
                Value::Null,
            )
            .await;
            assert_eq!(
                status, 404,
                "organization kind before access: {user}: {body}"
            );
            let (status, body) = call(
                user,
                "PUT",
                format!("/organizations/{id}/capabilities/pod/offer/default-on"),
                json!({"default_on": true}),
            )
            .await;
            assert_eq!(status, 404, "organization kind under lock: {user}: {body}");
        }
    }
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
            "retired before permission",
            "bystander",
            retired.id,
            None,
            409,
        ),
        ("context before retirement", "carol", retired.id, None, 404),
        (
            "personal retirement before fixed roles",
            "writer",
            retired_personal.id,
            None,
            409,
        ),
        (
            "personal context before fixed roles",
            "carol",
            retired_personal.id,
            None,
            404,
        ),
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
        for method in ["PUT", "DELETE"] {
            let answer = call(
                user,
                method,
                format!("/spaces/{space}/roles/member/bystander"),
                Value::Null,
            )
            .await;
            answers.push((method, answer));
        }
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
#[ignore = "needs Postgres: make test-integration"]
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
#[ignore = "needs Postgres: make test-integration"]
async fn content_http_waiters_recheck_existence_after_deletion() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "alice").await;
    let identity = support::IdentityServer::start().await;
    let app = content_app(&e, &identity).await;
    for method in ["PATCH", "DELETE", "POST"] {
        let folder = spaces::create_folder(&e.pool, "alice", org.id, None, "folder".into())
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
#[ignore = "needs Postgres: make test-integration"]
async fn organization_admin_grants_require_directory_identity_and_deleted_admins_can_be_revoked() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, _) = org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let app = content_app(&e, &identity).await;
    let token = identity.token("root");
    let before =
        control_plane::authorization::space_holders(&e.pool, org.id, Role::OrganizationAdmin)
            .await
            .unwrap();
    for (subject, expected) in [("missing", 422), ("unavailable", 500)] {
        assert_eq!(
            content_request(
                app.clone(),
                &token,
                "PUT",
                &format!("/spaces/{}/roles/organization_admin/{subject}", org.id),
                ""
            )
            .await,
            expected
        );
        assert_eq!(
            control_plane::authorization::space_holders(&e.pool, org.id, Role::OrganizationAdmin)
                .await
                .unwrap(),
            before
        );
    }
    assert!(matches!(
        spaces::grant(
            &e.pool,
            &control_plane::users::Directory::Keycloak(None),
            "root",
            org.id,
            Role::OrganizationAdmin,
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
    let path = format!("/spaces/{}/roles/organization_admin/olga", org.id);
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
            &format!("/spaces/{}/roles/organization_admin/alice-owner", org.id),
            ""
        )
        .await,
        409
    );
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
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

// Proves: I21
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn import_rechecks_admin_identity_before_publishing_spaces() {
    use std::{sync::Arc, time::Duration};
    let e = env().await;
    let server = support::IdentityServer::start().await;
    server
        .users
        .lock()
        .await
        .insert("alice-sub".into(), "alice".into());
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let directory = server.directory();
    let gate = Arc::new(support::Gate::default());
    server.control.lock().await.create_gate = Some(gate.clone());
    let bundle = parse_blueprint(br#"{"users":[{"username":"alice"},{"username":"bob","password":"fixture-password"}],"organizations":[{"ref":"org","name":"Race","roles":{"alice":["organization_admin","owner"]}}],"teams":[],"projects":[]}"#).unwrap();
    let pool = e.pool.clone();

    let pending = tokio::spawn(async move {
        control_plane::provisioning::Importer {
            pool: &pool,
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
    assert!(
        control_plane::authorization::roles_of(&e.pool, "alice-sub")
            .await
            .unwrap()
            .is_empty()
    );
}

// Proves: I21
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn import_checks_distinct_admins_once_with_bounded_concurrency() {
    let e = env().await;
    let server = support::IdentityServer::start().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let mut roles = serde_json::Map::new();
    let mut users = Vec::new();
    for i in 0..12 {
        let name = format!("owner{i}");
        server.users.lock().await.insert(name.clone(), name.clone());
        users.push(serde_json::json!({"username":name}));
        roles.insert(name, serde_json::json!(["organization_admin", "owner"]));
    }
    server.control.lock().await.subject_delay = true;
    let bundle = parse_blueprint(&serde_json::to_vec(&serde_json::json!({
        "users":users,"organizations":[{"ref":"a","name":"A","roles":roles}],"teams":[],"projects":[]
    })).unwrap()).unwrap();
    let directory = server.directory();
    control_plane::provisioning::Importer {
        pool: &e.pool,
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
#[ignore = "needs Postgres: make test-integration"]
async fn a_person_may_hold_roles_in_several_organizations() {
    let e = env().await;
    let a = crate::support::member_organization(&e.pool, "A", "alice")
        .await
        .unwrap();
    let b = crate::support::member_organization(&e.pool, "B", "carol")
        .await
        .unwrap();
    let subjects = e.subjects();
    let (first, second) = tokio::join!(
        spaces::grant(&e.pool, &subjects, "alice", a.id, Role::Owner, "bob"),
        spaces::grant(&e.pool, &subjects, "carol", b.id, Role::Member, "bob"),
    );
    first.unwrap();
    second.unwrap();
    for organization in [a.id, b.id] {
        assert!(
            control_plane::authorization::in_organization(&e.pool, "bob", organization)
                .await
                .unwrap()
        );
    }
    assert!(
        !control_plane::authorization::in_organization(&e.pool, "unattached", a.id)
            .await
            .unwrap()
    );
    // Each organization answers from the roles held there: owner of A reads nothing,
    // member of B reads B.
    assert!(!reads(&e, "bob", a.id).await);
    assert!(reads(&e, "bob", b.id).await);
    let listed: Vec<_> = spaces::memberships(&e.pool, "bob")
        .await
        .unwrap()
        .into_iter()
        .map(|m| (m.space.id, m.roles))
        .collect();
    assert!(listed.contains(&(a.id, vec![Role::Owner])));
    assert!(listed.contains(&(b.id, vec![Role::Member])));
    // A third organization can name the same person.
    crate::support::member_organization(&e.pool, "Third", "bob")
        .await
        .unwrap();
}

// Proves: I23, I8
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn organization_context_follows_direct_grants() {
    let e = env().await;
    let (a, _, project) = tree(&e).await;
    let b = crate::support::member_organization(&e.pool, "B", "carol")
        .await
        .unwrap();
    grant(&e, a.id, Role::Owner, "bob").await;
    assert!(
        control_plane::authorization::in_organization(&e.pool, "bob", a.id)
            .await
            .unwrap()
    );
    assert!(
        !control_plane::authorization::in_organization(&e.pool, "bob", b.id)
            .await
            .unwrap()
    );
    assert!(!reads(&e, "bob", a.id).await);
    // Context resolution agrees with direct SQL grants; it does not repair missing parent roles.
    control_plane::authorization::write_role(
        &mut e.pool.acquire().await.unwrap(),
        "orphan",
        Role::Editor,
        project.id,
        true,
    )
    .await
    .unwrap();
    assert!(
        control_plane::authorization::in_organization(&e.pool, "orphan", a.id)
            .await
            .unwrap()
    );
    let memberships = spaces::memberships(&e.pool, "orphan").await.unwrap();
    assert_eq!(memberships.len(), 1);
    assert_eq!(memberships[0].space.id, project.id);
    assert_eq!(memberships[0].space.path, project.path);
    assert_eq!(memberships[0].space.organization, a.id);
    assert_eq!(
        control_plane::authorization::roles_of(&e.pool, "orphan")
            .await
            .unwrap(),
        vec![(project.id, Role::Editor)]
    );
    // A second organization adds its own context without changing the first.
    spaces::grant(&e.pool, &e.subjects(), "carol", b.id, Role::Member, "bob")
        .await
        .unwrap();
    assert_eq!(spaces::memberships(&e.pool, "bob").await.unwrap().len(), 2);
    assert_eq!(
        spaces::scope(&e.pool, "bob", b.id, None).await.unwrap(),
        vec![b.id]
    );
    assert!(matches!(
        spaces::authorized_mutation(&e.pool, "bob", b.id, Permission::Write).await,
        Err(AppError::Forbidden)
    ));
    spaces::revoke(&e.pool, "carol", b.id, Role::Member, "bob")
        .await
        .unwrap();
    assert!(
        !control_plane::authorization::in_organization(&e.pool, "bob", b.id)
            .await
            .unwrap()
    );
    assert!(
        control_plane::authorization::in_organization(&e.pool, "bob", a.id)
            .await
            .unwrap()
    );
}

// Proves: I23
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn import_accepts_one_person_in_several_organizations() {
    use control_plane::provisioning::Importer;
    let e = env().await;
    let server = support::IdentityServer::start().await;
    let directory = server.directory();
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let value = serde_json::json!({"users":[{"username":"bob","password":"private-password"}],"organizations":[{"ref":"a","name":"A","roles":{"bob":["owner","organization_admin","member"]}},{"ref":"b","name":"B","roles":{"bob":["owner","organization_admin","member"]}}],"teams":[],"projects":[]});
    let bundle = parse_blueprint(&serde_json::to_vec(&value).unwrap()).unwrap();
    Importer {
        pool: &e.pool,
        directory: &directory,
        operator: "root",
    }
    .run(&bundle)
    .await
    .unwrap();
    let bob = directory.find_username("bob").await.unwrap().unwrap();
    for name in ["A", "B"] {
        let organization = named_space(&e.pool, None, name).await.unwrap().unwrap();
        assert!(
            control_plane::authorization::in_organization(&e.pool, &bob.id, organization.id)
                .await
                .unwrap()
        );
        assert!(reads(&e, &bob.id, organization.id).await);
    }
}

// Proves: I23
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn business_http_checks_each_organization_while_platform_metadata_stays_available() {
    use serde_json::json;
    use tower::ServiceExt;
    let e = env().await;
    let a = crate::support::member_organization(&e.pool, "A", "alice")
        .await
        .unwrap();
    let b = crate::support::member_organization(&e.pool, "B", "carol")
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
    // Outside B, its space does not exist for Bob.
    assert_eq!(
        content_request(
            app.clone(),
            &token,
            "GET",
            &format!("/spaces/{}/entries", b.id),
            ""
        )
        .await,
        404
    );
    // A role in B adds B's context; each probe answers from the roles held there.
    spaces::grant(&e.pool, &e.subjects(), "carol", b.id, Role::Editor, "bob")
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
            200,
            "{path}"
        );
    }
    assert_eq!(
        content_request(app.clone(), &token, "GET", "/me/spaces", "").await,
        200
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

// Proves: I23
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn import_and_a_waiting_grant_both_commit_across_organizations() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let a = crate::support::member_organization(&e.pool, "A", "alice")
        .await
        .unwrap();
    let server = support::IdentityServer::start().await;
    server.users.lock().await.insert("bob".into(), "bob".into());
    let gate = std::sync::Arc::new(support::Gate::default());
    server.control.lock().await.create_gate = Some(gate.clone());
    let directory = server.directory();
    let bundle = parse_blueprint(br#"{"users":[{"username":"carol","password":"private-password"},{"username":"bob"}],"organizations":[{"ref":"b","name":"B","roles":{"carol":["organization_admin","owner"],"bob":["member"]}}],"teams":[],"projects":[]}"#).unwrap();
    let pool = e.pool.clone();
    let import = tokio::spawn(async move {
        control_plane::provisioning::Importer {
            pool: &pool,
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
    let (pool, open) = (e.pool.clone(), e.open_directory());
    let grant = tokio::spawn(async move {
        spaces::grant(
            &pool,
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
    import.await.unwrap().unwrap();
    let b = named_space(&e.pool, None, "B").await.unwrap().unwrap();
    for organization in [a.id, b.id] {
        assert!(
            control_plane::authorization::in_organization(&e.pool, "bob", organization)
                .await
                .unwrap()
        );
    }
}

// Proves: I4, I6, I20, I23
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn personal_open_requires_business_role_and_never_repairs_revocation() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, _) = org_and_team(&e).await;
    spaces::grant(
        &e.pool,
        &e.subjects(),
        "root",
        org.id,
        Role::OrganizationAdmin,
        "admin",
    )
    .await
    .unwrap();
    assert!(matches!(
        spaces::create_personal_space(&e.pool, "admin", org.id).await,
        Err(AppError::Forbidden)
    ));
    assert!(matches!(
        spaces::create_personal_space(&e.pool, "root", org.id).await,
        Err(AppError::NotFound)
    ));
    grant(&e, org.id, Role::Owner, "priya").await;
    let (a, b) = tokio::join!(
        spaces::create_personal_space(&e.pool, "priya", org.id),
        spaces::create_personal_space(&e.pool, "priya", org.id)
    );
    let ((personal, created_a), (other, created_b)) = (a.unwrap(), b.unwrap());
    assert_eq!(personal.id, other.id);
    assert_ne!(created_a, created_b);
    assert_eq!(personal.kind, SpaceKind::Personal);
    assert_eq!(personal.organization, org.id);
    assert_eq!(personal.parent_id, None);
    assert_eq!(personal.personal_owner.as_deref(), Some("priya"));
    assert!(matches!(
        spaces::create_space(
            &e.pool,
            "alice",
            SpaceKind::Personal,
            org.id,
            "invalid".into(),
            "alice"
        )
        .await,
        Err(AppError::BadRequest(_))
    ));
    assert_eq!(personal.path, vec![personal.id]);
    assert!(!reads(&e, "alice", personal.id).await);
    spaces::revoke(&e.pool, "alice", personal.id, Role::Editor, "priya")
        .await
        .unwrap();

    let (again, created) = spaces::create_personal_space(&e.pool, "priya", org.id)
        .await
        .unwrap();
    assert!(!created);
    assert_eq!(again.id, personal.id);

    assert!(
        control_plane::authorization::authorize(&e.pool, "priya", personal.id, Permission::Write)
            .await
            .is_err()
    );
    spaces::revoke(&e.pool, "alice", personal.id, Role::Member, "priya")
        .await
        .unwrap();
    assert!(matches!(
        spaces::create_personal_space(&e.pool, "priya", org.id).await,
        Err(AppError::Forbidden)
    ));

    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space where personal_owner = 'priya'")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        1
    );
    for (user, role) in [
        ("member", Role::Member),
        ("editor", Role::Editor),
        ("analyst", Role::Analyst),
    ] {
        grant(&e, org.id, role, user).await;
        let (personal, created) = spaces::create_personal_space(&e.pool, user, org.id)
            .await
            .unwrap();
        assert!(created && reads(&e, user, personal.id).await);
        assert!(!reads(&e, "alice", personal.id).await);
        assert!(
            spaces::memberships(&e.pool, user)
                .await
                .unwrap()
                .iter()
                .any(|m| m.space.id == personal.id)
        );
    }
    for user in ["governor", "admin", "root"] {
        grant(&e, org.id, Role::Owner, user).await;
        let (own, created) = spaces::create_personal_space(&e.pool, user, org.id)
            .await
            .unwrap();
        assert!(created && reads(&e, user, own.id).await);
        assert!(!reads(&e, "alice", own.id).await);
        assert!(!reads(&e, user, org.id).await);
        let (again, created) = spaces::create_personal_space(&e.pool, user, org.id)
            .await
            .unwrap();
        assert!(!created);
        assert_eq!(again.id, own.id);
    }
    let foreign = crate::support::member_organization(&e.pool, "Other", "carol")
        .await
        .unwrap();
    let (private, _) = spaces::create_personal_space(&e.pool, "carol", foreign.id)
        .await
        .unwrap();
    assert_ne!(private.id, personal.id);
    assert_eq!(private.path, vec![private.id]);
    assert_eq!(private.organization, foreign.id);
    assert!(matches!(
        spaces::create_personal_space(&e.pool, "priya", foreign.id).await,
        Err(AppError::NotFound)
    ));
    let listed = spaces::memberships(&e.pool, "carol").await.unwrap();
    assert!(listed.iter().all(|m| m.space.organization == foreign.id));
    assert!(listed.iter().all(|m| m.space.id != personal.id));
}

#[path = "support/resource_browsing.rs"]
mod resource_browsing;

#[path = "support/space_deletion.rs"]
mod space_deletion;

#[path = "support/agent_enablement.rs"]
mod agent_enablement;

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
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
        "security":{"user":{"realm_url":identity.realm,"client_id":"app"}},
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
            405,
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
    let response = http
        .delete(format!("{base}/documents/{}", doc.id))
        .bearer_auth(&token)
        .send()
        .await
        .unwrap();
    assert_eq!(response.status(), 202);
    let receipt: serde_json::Value = response.json().await.unwrap();
    assert_eq!(receipt["target_id"], doc.id.to_string());
    assert_eq!(receipt["target_kind"], "document");
    assert_eq!(receipt["status"], "queued");
    let deletion_id: Option<Uuid> =
        sqlx::query_scalar("select deletion_id from document where id = $1")
            .bind(doc.id)
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(
        deletion_id,
        Some(Uuid::parse_str(receipt["id"].as_str().unwrap()).unwrap())
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

// Proves: I1
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn personal_space_identity_is_constrained_and_immutable() {
    let e = env().await;
    let mut conn = e.pool.acquire().await.unwrap();
    let org = Uuid::new_v4();
    let active = Uuid::new_v4();
    sqlx::query(
        "insert into space (id,kind,name,organization_id) values ($1,'organization',$2,$1)",
    )
    .bind(org)
    .bind(format!("Org {org}"))
    .execute(&mut *conn)
    .await
    .unwrap();
    sqlx::query("insert into space (id,kind,name,personal_owner,organization_id) values ($1,'personal','Personal','alice',$2)")
        .bind(active).bind(org).execute(&mut *conn).await.unwrap();
    for (kind, owner, parent) in [
        ("team", Some("bob"), None),
        ("personal", None, None),
        ("personal", Some("bob"), Some(org)),
    ] {
        let result = sqlx::query("insert into space (id,kind,name,personal_owner,organization_id,parent_id) values ($1,$2::text::space_kind,'Invalid',$3,$4,$5)")
            .bind(Uuid::new_v4()).bind(kind).bind(owner).bind(org).bind(parent)
            .execute(&mut *conn).await;
        assert_eq!(
            result
                .unwrap_err()
                .as_database_error()
                .unwrap()
                .constraint(),
            Some("space_personal_identity")
        );
    }
    let result = sqlx::query("update space set kind='team', personal_owner=null where id=$1")
        .bind(active)
        .execute(&mut *conn)
        .await;
    assert!(
        result
            .unwrap_err()
            .to_string()
            .contains("placement is immutable")
    );
}

#[path = "support/usage.rs"]
mod usage;

#[path = "support/agent_instances.rs"]
mod agent_instances;

#[path = "support/user_preferences.rs"]
mod user_preferences;

// Proves: I6, I20, I23
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn personal_access_survives_owner_revocation_while_membership_remains() {
    let e = env().await;
    let (org, team, project) = tree(&e).await;
    for scope in [team.id, project.id] {
        let user = if scope == team.id {
            "team-owner"
        } else {
            "project-owner"
        };
        grant(&e, org.id, Role::Member, user).await;
        if scope == project.id {
            grant(&e, team.id, Role::Member, user).await;
        }
        grant(&e, scope, Role::Owner, user).await;
        let (personal, _) = spaces::create_personal_space(&e.pool, user, org.id)
            .await
            .unwrap();
        control_plane::authorization::authorize(&e.pool, user, personal.id, Permission::Read)
            .await
            .unwrap();
        spaces::revoke(&e.pool, "alice", scope, Role::Owner, user)
            .await
            .unwrap();
        control_plane::authorization::authorize(&e.pool, user, personal.id, Permission::Read)
            .await
            .unwrap();
        assert!(
            spaces::memberships(&e.pool, user)
                .await
                .unwrap()
                .iter()
                .any(|m| m.space.id == personal.id)
        );
        grant(&e, scope, Role::Owner, user).await;
        let (again, created) = spaces::create_personal_space(&e.pool, user, org.id)
            .await
            .unwrap();
        assert!(!created);
        assert_eq!(again.id, personal.id);
    }
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn decisions_delegate_person_and_return_exact_readable_corpus() {
    use axum::{
        body::{Body, to_bytes},
        http::Request,
    };
    use control_plane::{
        api::{AppState, routes},
        auth::Authenticator,
        config::Configuration,
        onboarding::Onboarding,
    };
    use serde_json::{Value, json};
    use tower::ServiceExt;
    let e = env().await;
    let (org, team, project) = tree(&e).await;
    // Represent a project-only reader without adding an invitation feature.
    control_plane::authorization::write_role(
        &mut e.pool.acquire().await.unwrap(),
        "visitor",
        Role::Member,
        project.id,
        true,
    )
    .await
    .unwrap();
    control_plane::authorization::write_role(
        &mut e.pool.acquire().await.unwrap(),
        "visitor",
        Role::Owner,
        org.id,
        true,
    )
    .await
    .unwrap();
    let (personal, _) = spaces::create_personal_space(&e.pool, "visitor", org.id)
        .await
        .unwrap();
    let identity = support::IdentityServer::start().await;
    let mut config: Configuration =
        serde_yaml_ng::from_str(include_str!("../config/configuration.yaml")).unwrap();
    config.security.user.realm_url = identity.realm.clone();
    config.security.m2m = None;
    config.security.delegation.accept_delegated_calls = true;
    config.security.delegation.service_accounts_only = true;
    let auth = Authenticator::start(config.security().unwrap())
        .await
        .unwrap();
    control_plane::onboarding::accept(&e.pool, Some("v1"), "visitor", "v1")
        .await
        .unwrap();
    control_plane::authorization::write_platform(
        &mut e.pool.acquire().await.unwrap(),
        "service-account-kf",
        control_plane::roles::PlatformRole::PlatformAdmin,
        true,
    )
    .await
    .unwrap();
    let app = routes(AppState {
        pool: e.pool.clone(),
        auth: std::sync::Arc::new(auth),
        onboarding: Onboarding {
            gcu_version: Some("v1".into()),
            ..Default::default()
        },
        agent_catalog: Default::default(),
        lifecycle: Default::default(),
        directory: None,
        content: None,
        processing: None,
    });
    let now = chrono::Utc::now().timestamp();
    let workload=identity.sign(json!({"sub":"service-account-kf","preferred_username":"service-account-kf","azp":"kf","client_id":"kf","iss":identity.realm,"aud":"fred-delegation","iat":now,"exp":now+300,"resource_access":{"fred-delegation":{"roles":["delegation_caller"]}}}));
    let assertion = format!("person=visitor&run=run-1&agent={}", Uuid::new_v4());
    async fn call(app: &axum::Router, token: &str, path: &str, body: Value) -> (u16, Value) {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri(path)
                    .header("authorization", format!("Bearer {token}"))
                    .header("content-type", "application/json")
                    .body(Body::from(body.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        let status = response.status().as_u16();
        if status == 200 {
            assert_eq!(response.headers()["cache-control"], "no-store");
        }
        let body =
            serde_json::from_slice(&to_bytes(response.into_body(), 65536).await.unwrap()).unwrap();
        (status, body)
    }
    let scope = format!("/authorize/scope?{assertion}");
    assert_eq!(
        call(&app, &workload, &scope, json!({"space_id":personal.id})).await,
        (
            200,
            json!({"space_id":personal.id,"space_ids":[personal.id]})
        )
    );

    assert_eq!(
        call(&app, &workload, &scope, json!({"space_id":project.id})).await,
        (200, json!({"space_id":project.id,"space_ids":[project.id]}))
    );
    assert_eq!(
        call(
            &app,
            &workload,
            &scope,
            json!({"space_id":project.id,"levels":[]})
        )
        .await,
        (200, json!({"space_id":project.id,"space_ids":[]}))
    );
    assert_eq!(
        call(
            &app,
            &workload,
            &scope,
            json!({"space_id":project.id,"levels":["organization","team"]})
        )
        .await
        .1["space_ids"],
        json!([])
    );
    assert_eq!(
        call(&app, &workload, &scope, json!({"space_id":team.id}))
            .await
            .0,
        403
    );
    assert_eq!(
        call(&app, &workload, &scope, json!({"space_id":Uuid::new_v4()}))
            .await
            .0,
        404
    );
    assert_eq!(
        call(
            &app,
            &workload,
            &format!("/authorize/platform?{assertion}"),
            json!({"permission":"manage_platform"})
        )
        .await,
        (200, json!({"allowed":false}))
    );
    assert_eq!(
        call(
            &app,
            &workload,
            &format!("/authorize/space?{assertion}"),
            json!({"space_id":org.id,"permission":"read"})
        )
        .await,
        (200, json!({"allowed":false}))
    );
    for query in [
        "person=visitor".to_string(),
        format!("{assertion}&person=visitor"),
        format!("{assertion}&unknown=x"),
    ] {
        assert_eq!(
            call(
                &app,
                &workload,
                &format!("/authorize/scope?{query}"),
                json!({"space_id":project.id})
            )
            .await
            .0,
            422
        );
    }
    for body in [
        json!({"space_id":project.id,"user_id":"someone"}),
        json!({"space_id":project.id,"levels":["personal"]}),
    ] {
        assert_eq!(call(&app, &workload, &scope, body).await.0, 422);
    }
    assert_eq!(
        call(
            &app,
            &identity.token("visitor"),
            &scope,
            json!({"space_id":project.id})
        )
        .await
        .0,
        403
    );
    assert_eq!(
        call(
            &app,
            &workload,
            "/authorize/scope",
            json!({"space_id":project.id})
        )
        .await
        .0,
        403
    );
    assert_eq!(
        call(
            &app,
            &workload,
            &scope.replace("person=visitor", "person=unadmitted"),
            json!({"space_id":project.id})
        )
        .await
        .0,
        403
    );
}

// Proves: I27
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn role_grants_require_a_valid_known_subject() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let directory = identity.directory();
    let directory = control_plane::users::Directory::Keycloak(Some(&directory));
    for subject in ["", "user:alice", "*", "unknown"] {
        assert!(matches!(
            spaces::grant(&e.pool, &directory, "alice", org.id, Role::Member, subject).await,
            Err(AppError::Unprocessable(_))
        ));
        assert!(
            control_plane::authorization::direct_roles_on(&e.pool, subject, org.id)
                .await
                .unwrap()
                .is_empty()
        );
    }
    identity
        .users
        .lock()
        .await
        .insert("known".into(), "known".into());
    spaces::grant(&e.pool, &directory, "alice", org.id, Role::Member, "known")
        .await
        .unwrap();
    assert!(
        control_plane::authorization::authorize(&e.pool, "known", org.id, Permission::Read)
            .await
            .is_ok()
    );
}

#[path = "support/prompts.rs"]
mod prompts;

// The Nova path: owner-only team governance never implies content access.
#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn owner_only_team_membership_governance() {
    let e = env().await;
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    spaces::revoke(&e.pool, "alice", team.id, Role::Member, "alice")
        .await
        .unwrap();
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Member, "bob").await;
    // A parent owner without a content role is not eligible for a child role.
    grant(&e, org.id, Role::Owner, "governor").await;
    let other = crate::support::member_organization(&e.pool, "Other", "outsider")
        .await
        .unwrap();
    let directory = control_plane::users::Directory::Local(&e.pool);
    let roster =
        control_plane::space_members::list(&e.pool, &directory, "alice", team.id, None, false)
            .await
            .unwrap();
    assert_eq!(roster.items.len(), 2);
    assert_eq!(
        roster
            .items
            .iter()
            .find(|m| m.user.id == "alice")
            .unwrap()
            .roles,
        [Role::Owner]
    );
    assert!(!reads(&e, "alice", team.id).await);
    for caller in ["bob", "governor", "outsider", "root"] {
        for candidates in [false, true] {
            assert!(
                control_plane::space_members::list(
                    &e.pool, &directory, caller, team.id, None, candidates
                )
                .await
                .is_err()
            );
        }
    }
    let eligible =
        control_plane::space_members::list(&e.pool, &directory, "alice", team.id, None, true)
            .await
            .unwrap();
    assert_eq!(
        eligible
            .items
            .iter()
            .map(|m| m.user.id.as_str())
            .collect::<Vec<_>>(),
        ["alice", "bob"]
    );
    assert!(
        spaces::grant(
            &e.pool,
            &e.subjects(),
            "alice",
            team.id,
            Role::Editor,
            "outsider"
        )
        .await
        .is_err()
    );
    spaces::grant(
        &e.pool,
        &e.subjects(),
        "alice",
        team.id,
        Role::Editor,
        "bob",
    )
    .await
    .unwrap();
    assert!(!reads(&e, "alice", team.id).await);
    assert!(
        spaces::revoke(&e.pool, "alice", team.id, Role::Owner, "alice")
            .await
            .is_err()
    );
    spaces::grant(&e.pool, &e.subjects(), "alice", team.id, Role::Owner, "bob")
        .await
        .unwrap();
    spaces::revoke(&e.pool, "alice", team.id, Role::Owner, "alice")
        .await
        .unwrap();
    assert!(
        control_plane::space_members::list(&e.pool, &directory, "alice", team.id, None, false)
            .await
            .is_err()
    );
    assert!(
        spaces::grant(
            &e.pool,
            &e.subjects(),
            "alice",
            team.id,
            Role::Member,
            "alice"
        )
        .await
        .is_err()
    );
    assert!(!reads(&e, "bob", other.id).await);
    sqlx::query("insert into space_role_grant(space_id,subject,role) select $1, 'candidate-' || lpad(n::text,3,'0'), 'member' from generate_series(1,51) n")
        .bind(org.id).execute(&e.pool).await.unwrap();
    let first = control_plane::space_members::list(&e.pool, &directory, "bob", team.id, None, true)
        .await
        .unwrap();
    assert_eq!(first.items.len(), 50);
    let second = control_plane::space_members::list(
        &e.pool,
        &directory,
        "bob",
        team.id,
        first.next_cursor.as_deref(),
        true,
    )
    .await
    .unwrap();
    assert_eq!(second.items.len(), 3);
    assert!(second.next_cursor.is_none());
    assert!(
        first
            .items
            .iter()
            .all(|a| second.items.iter().all(|b| a.user.id != b.user.id))
    );
}

#[path = "support/embedded_conversations.rs"]
mod embedded_conversations;
