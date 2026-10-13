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
    domain::{Document, Permission, Role, Space, SpaceKind},
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
    Env { pool, fga }
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

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn pagination_survives_deleting_the_cursor_row() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    let mut docs = Vec::new();
    for name in ["a", "b", "c"] {
        let d = Document {
            id: Uuid::new_v4(),
            space_id: org.id,
            folder_id: None,
            name: name.into(),
            mime: "text/plain".into(),
            size: 1,
            sha256: "x".into(),
            created_by: "alice".into(),
        };
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
