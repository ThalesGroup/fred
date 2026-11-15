// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use control_plane::team_discovery::{self, TeamDirectoryQuery, TeamJoiningMode, TeamVisibility};

async fn open(e: &Env, team: Uuid) {
    spaces::update_team_parameters(
        &e.pool,
        "alice",
        team,
        None,
        None,
        Some(TeamVisibility::Visible),
        Some(TeamJoiningMode::Open),
    )
    .await
    .unwrap();
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn discovery_scopes_metadata_and_avatars_without_content_rights() {
    use control_plane::api::{AppState, routes};
    use serde_json::{Value, json};
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "bob").await;
    let foreign = support::member_organization(&e.pool, "Foreign", "outsider")
        .await
        .unwrap();
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "Project".into(),
        "alice",
    )
    .await
    .unwrap();
    spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    let hidden = team_discovery::metadata(&e.pool, "alice", team.id)
        .await
        .unwrap();
    assert_eq!(hidden.visibility, TeamVisibility::Hidden);
    assert_eq!(hidden.joining_mode, TeamJoiningMode::InviteOnly);
    assert!(
        team_discovery::list(&e.pool, "bob", org.id, &TeamDirectoryQuery::default())
            .await
            .unwrap()
            .items
            .is_empty()
    );
    assert!(
        team_discovery::metadata(&e.pool, "bob", team.id)
            .await
            .is_err()
    );
    assert!(
        team_discovery::metadata(&e.pool, "alice", project.id)
            .await
            .is_err()
    );
    open(&e, team.id).await;
    let visible = team_discovery::metadata(&e.pool, "bob", team.id)
        .await
        .unwrap();
    assert!(visible.can_join);
    assert!(!visible.is_member);
    assert_eq!(
        team_discovery::list(&e.pool, "bob", org.id, &TeamDirectoryQuery::default())
            .await
            .unwrap()
            .total,
        1
    );
    assert!(
        team_discovery::list(&e.pool, "outsider", org.id, &TeamDirectoryQuery::default())
            .await
            .is_err()
    );
    assert!(
        team_discovery::list(&e.pool, "bob", foreign.id, &TeamDirectoryQuery::default())
            .await
            .is_err()
    );
    // Organization context from an isolated child role follows the canonical rule,
    // but discovery must not fabricate the parent content role needed to enroll.
    authorization::write_role(
        &mut e.pool.acquire().await.unwrap(),
        "child-only",
        Role::Owner,
        project.id,
        true,
    )
    .await
    .unwrap();
    assert!(
        !team_discovery::metadata(&e.pool, "child-only", team.id)
            .await
            .unwrap()
            .can_join
    );
    assert!(
        team_discovery::join(&e.pool, "child-only", team.id)
            .await
            .is_err()
    );
    for permission in [Permission::Read, Permission::Write, Permission::Manage] {
        assert!(
            authorization::authorize(&e.pool, "bob", team.id, permission)
                .await
                .is_err()
        );
    }
    let identity = support::IdentityServer::start().await;
    let app = routes(AppState {
        history: None,
        agent_catalog: Default::default(),
        pool: e.pool.clone(),
        auth: std::sync::Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    });
    let metadata = format!("/spaces/{}/discovery", team.id);
    let avatar = format!("/spaces/{}/avatar", team.id);
    let (status, payload) =
        support::request(&app, &identity, Some("bob"), "GET", &metadata, Value::Null).await;
    assert_eq!(status, 200);
    let keys: std::collections::BTreeSet<_> = payload
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(
        keys,
        [
            "id",
            "name",
            "description",
            "visibility",
            "joining_mode",
            "is_member",
            "can_join"
        ]
        .into_iter()
        .collect()
    );
    assert_eq!(
        support::request(&app, &identity, Some("bob"), "GET", &avatar, Value::Null)
            .await
            .0,
        204
    );
    for path in [&metadata, &avatar] {
        assert_eq!(
            support::request(&app, &identity, Some("outsider"), "GET", path, Value::Null)
                .await
                .0,
            404
        );
    }
    assert_eq!(
        support::request(
            &app,
            &identity,
            Some("bob"),
            "GET",
            &format!("/spaces/{}/members", team.id),
            Value::Null
        )
        .await
        .0,
        403
    );
    assert_eq!(
        support::request(
            &app,
            &identity,
            Some("bob"),
            "PATCH",
            &format!("/spaces/{}", team.id),
            json!({"visibility":"hidden"})
        )
        .await
        .0,
        403
    );
    spaces::update_team_parameters(
        &e.pool,
        "alice",
        team.id,
        None,
        None,
        Some(TeamVisibility::Hidden),
        None,
    )
    .await
    .unwrap();
    for path in [&metadata, &avatar] {
        assert_eq!(
            support::request(&app, &identity, Some("bob"), "GET", path, Value::Null)
                .await
                .0,
            404
        );
        assert!(matches!(
            support::request(&app, &identity, Some("alice"), "GET", path, Value::Null)
                .await
                .0,
            200 | 204
        ));
    }
    assert!(team_discovery::join(&e.pool, "bob", team.id).await.is_err());
    // Invitation remains usable while hidden/open, independently of discovery.
    let link = control_plane::team_join_links::create(&e.pool, "alice", team.id)
        .await
        .unwrap();
    control_plane::team_join_links::join(&e.pool, "bob", link.token, true)
        .await
        .unwrap();
    assert!(
        team_discovery::metadata(&e.pool, "bob", team.id)
            .await
            .unwrap()
            .is_member
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn discovery_search_and_pagination_filter_before_counting() {
    let e = env().await;
    let (org, _) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "bob").await;
    for index in 0..23 {
        let team = spaces::create_space(
            &e.pool,
            "alice",
            SpaceKind::Team,
            org.id,
            format!("Visible {index:02}"),
            "alice",
        )
        .await
        .unwrap();
        spaces::update_team_parameters(
            &e.pool,
            "alice",
            team.id,
            None,
            Some("Research on wind turbines."),
            Some(TeamVisibility::Visible),
            None,
        )
        .await
        .unwrap();
    }
    let first = team_discovery::list(
        &e.pool,
        "bob",
        org.id,
        &TeamDirectoryQuery {
            search: Some("VISIBLE turbines".into()),
            page: None,
        },
    )
    .await
    .unwrap();
    let second = team_discovery::list(
        &e.pool,
        "bob",
        org.id,
        &TeamDirectoryQuery {
            search: Some("VISIBLE turbines".into()),
            page: Some(1),
        },
    )
    .await
    .unwrap();
    assert_eq!(first.total, 23);
    assert_eq!(first.items.len(), 20);
    assert_eq!(second.items.len(), 3);
    assert!(
        first
            .items
            .iter()
            .all(|a| second.items.iter().all(|b| a.id != b.id))
    );
    let literal = team_discovery::list(
        &e.pool,
        "bob",
        org.id,
        &TeamDirectoryQuery {
            search: Some("%".into()),
            page: None,
        },
    )
    .await
    .unwrap();
    assert_eq!(literal.total, 0);
    assert!(
        team_discovery::list(
            &e.pool,
            "bob",
            org.id,
            &TeamDirectoryQuery {
                search: Some("x".repeat(181)),
                page: None
            }
        )
        .await
        .is_err()
    );
    assert!(
        sqlx::query("update space set visibility='visible' where id=$1")
            .bind(org.id)
            .execute(&e.pool)
            .await
            .is_err()
    );
    assert!(
        sqlx::query("update space set joining_mode='invalid' where id=$1")
            .bind(org.id)
            .execute(&e.pool)
            .await
            .is_err()
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn open_and_invited_joins_converge_without_promoting_existing_roles() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "bob").await;
    open(&e, team.id).await;
    let link = control_plane::team_join_links::create(&e.pool, "alice", team.id)
        .await
        .unwrap();
    let (one, two, invited) = tokio::join!(
        team_discovery::join(&e.pool, "bob", team.id),
        team_discovery::join(&e.pool, "bob", team.id),
        control_plane::team_join_links::join(&e.pool, "bob", link.token, true)
    );
    one.unwrap();
    two.unwrap();
    invited.unwrap();
    let roles: Vec<String> =
        sqlx::query_scalar("select role from space_role_grant where space_id=$1 and subject='bob'")
            .bind(team.id)
            .fetch_all(&e.pool)
            .await
            .unwrap();
    assert_eq!(roles, ["member"]);
    grant(&e, org.id, Role::Member, "owner-only").await;
    grant(&e, team.id, Role::Owner, "owner-only").await;
    team_discovery::join(&e.pool, "owner-only", team.id)
        .await
        .unwrap();
    assert!(!reads(&e, "owner-only", team.id).await);
    spaces::update_team_parameters(
        &e.pool,
        "alice",
        team.id,
        None,
        None,
        Some(TeamVisibility::Hidden),
        Some(TeamJoiningMode::InviteOnly),
    )
    .await
    .unwrap();
    assert!(reads(&e, "bob", team.id).await);
    assert!(team_discovery::join(&e.pool, "bob", team.id).await.is_err());
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn queued_join_rechecks_hiding_closure_and_eligibility_after_the_lock() {
    for change in ["hidden", "closed", "revoked"] {
        let e = env().await;
        let (org, team) = org_and_team(&e).await;
        grant(&e, org.id, Role::Member, "bob").await;
        open(&e, team.id).await;
        let mut held = hold_organization_lock(&e, org.id).await;
        let pool = e.pool.clone();
        let waiting =
            tokio::spawn(async move { team_discovery::join(&pool, "bob", team.id).await });
        tokio::time::timeout(Duration::from_secs(3), async {
            loop {
                let pending: bool = sqlx::query_scalar("select exists(select 1 from pg_locks where locktype='advisory' and not granted and database=(select oid from pg_database where datname=current_database()))").fetch_one(&e.pool).await.unwrap();
                if pending { break; }
                tokio::task::yield_now().await;
            }
        }).await.expect("join must wait on organization governance");
        match change {
            "hidden" => {
                sqlx::query("update space set visibility='hidden' where id=$1")
                    .bind(team.id)
                    .execute(&mut *held)
                    .await
                    .unwrap();
            }
            "closed" => {
                sqlx::query("update space set joining_mode='invite_only' where id=$1")
                    .bind(team.id)
                    .execute(&mut *held)
                    .await
                    .unwrap();
            }
            _ => {
                authorization::write_role(&mut held, "bob", Role::Member, org.id, false)
                    .await
                    .unwrap();
            }
        }
        held.commit().await.unwrap();
        assert!(waiting.await.unwrap().is_err(), "{change}");
        assert!(!reads(&e, "bob", team.id).await);
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn retired_teams_and_organizations_refuse_discovery_and_enrollment() {
    for retire_org in [false, true] {
        let e = env().await;
        bootstrap::grant_root(&e.pool, "root").await.unwrap();
        let (org, team) = org_and_team(&e).await;
        grant(&e, org.id, Role::Member, "bob").await;
        open(&e, team.id).await;
        let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
        lifecycle.config.enabled = true;
        lifecycle
            .accept(
                &e.pool,
                "root",
                if retire_org { org.id } else { team.id },
                false,
            )
            .await
            .unwrap();
        assert!(
            team_discovery::metadata(&e.pool, "bob", team.id)
                .await
                .is_err()
        );
        assert!(team_discovery::join(&e.pool, "bob", team.id).await.is_err());
        let catalogue =
            team_discovery::list(&e.pool, "bob", org.id, &TeamDirectoryQuery::default()).await;
        if retire_org {
            assert!(catalogue.is_err());
        } else {
            assert!(catalogue.unwrap().items.is_empty());
        }
    }
}
