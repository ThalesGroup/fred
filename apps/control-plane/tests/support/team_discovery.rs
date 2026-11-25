// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use control_plane::team_discovery::{self, TeamDirectoryQuery, TeamJoiningMode, TeamVisibility};

async fn discovery_prompt(e: &Env, space: Uuid, name: &str, discoverable: bool) -> Uuid {
    let id = Uuid::new_v4();
    sqlx::query("insert into prompt(prompt_id,space_id,logical_name,display_name,description,text,created_by,discoverable)
        values($1,$2,$1::text,$3,'Public purpose','hidden-instruction-marker','alice',$4)")
        .bind(id).bind(space).bind(name).bind(discoverable).execute(&e.pool).await.unwrap();
    id
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn unchanged_agent_discovery_setting_keeps_the_explicit_failed_preparation_retry() {
    use control_plane::api::{AppState, routes};
    use serde_json::json;
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let agent = Uuid::new_v4();
    let file = Uuid::new_v4();
    let failed = Uuid::new_v4();
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,logical_name,display_name,tuning,created_by)
        values($1,$2,$1,'native','assistant',$1::text,'Presentation assistant',$3,'alice')")
        .bind(agent).bind(team.id).bind(json!({
            "role":"Assistant", "selected_capability_ids":["ppt_builder"],
            "capability_config":{"ppt_builder":{"config":{}}}
        })).execute(&e.pool).await.unwrap();
    authorization::set_agent_default_on(&mut e.pool.acquire().await.unwrap(), org.id, agent, true)
        .await
        .unwrap();
    // Seed the already accepted original and failed durable job; this HTTP test
    // needs no object store, worker, or external capability validation call.
    sqlx::query("insert into document_storage(namespace,endpoint,bucket,prefix) values($1,'http://unused','fixture','fixture') on conflict(singleton) do nothing")
        .bind(Uuid::new_v4()).execute(&e.pool).await.unwrap();
    sqlx::query("insert into powerpoint_file(id,request_key,actor,organization_id,space_id,agent_instance_id,live_space_id,live_agent_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,cleanup_due_at,runtime_id)
        values($1,$1,'alice',$2,$3,$4,$3,$4,$3,'template.pptx','application/octet-stream',3,repeat('a',64),$1::text,'pending',clock_timestamp()+interval '5 minutes',clock_timestamp(),'native')")
        .bind(file).bind(org.id).bind(team.id).bind(agent).execute(&e.pool).await.unwrap();
    sqlx::query("update powerpoint_file set status='stored',published_at=clock_timestamp(),upload_ready=true where id=$1")
        .bind(file).execute(&e.pool).await.unwrap();
    sqlx::query("insert into capability_preparation(id,file_id,runtime_id,capability_id,space_id,agent_instance_id,configuration_revision,config,state,error,workflow_id,task_queue)
        values($1,$2,'native','ppt_builder',$3,$4,1,'{}','failed','Analysis failed',$1::text,'fixture')")
        .bind(failed).bind(file).bind(team.id).bind(agent).execute(&e.pool).await.unwrap();
    sqlx::query("update agent_instance set preparation_id=$2,preparation_state='failed',preparation_error='Analysis failed' where agent_instance_id=$1")
        .bind(agent).bind(failed).execute(&e.pool).await.unwrap();
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
    let path = format!("/spaces/{}/agent-instances/{agent}", team.id);
    let changed = support::request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &path,
        json!({"discoverable":true}),
    )
    .await;
    assert_eq!(changed.0, 200, "{changed:?}");
    assert_eq!(changed.1["discoverable"], true);
    assert_eq!(changed.1["configuration_revision"], 1);
    assert_eq!(changed.1["preparation_state"], "failed");
    let unchanged = support::request(
        &app,
        &identity,
        Some("alice"),
        "PATCH",
        &path,
        json!({"discoverable":true}),
    )
    .await;
    assert_eq!(unchanged.0, 200, "{unchanged:?}");
    assert_eq!(unchanged.1["configuration_revision"], 1);
    assert_eq!(unchanged.1["preparation_state"], "pending");
    let jobs: Vec<(Uuid, String)> =
        sqlx::query_as("select id,state from capability_preparation where agent_instance_id=$1")
            .bind(agent)
            .fetch_all(&e.pool)
            .await
            .unwrap();
    assert_eq!(jobs.len(), 2);
    assert!(
        jobs.iter()
            .any(|(id, state)| *id == failed && state == "obsolete")
    );
    assert!(
        jobs.iter()
            .any(|(id, state)| *id != failed && state == "pending")
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn resource_discovery_discloses_only_opted_in_metadata_with_current_space_boundaries() {
    use control_plane::team_discovery::ResourceDirectoryQuery;
    let e = env().await;
    // Root bootstrap happens once, before the fixture organization would complete it.
    bootstrap::grant_root(&e.pool, "root").await.unwrap();
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "bob").await;
    authorization::write_role(
        &mut e.pool.acquire().await.unwrap(),
        "admin",
        Role::OrganizationAdmin,
        org.id,
        true,
    )
    .await
    .unwrap();
    support::member_organization(&e.pool, "Foreign", "outsider")
        .await
        .unwrap();
    let prompt = discovery_prompt(&e, team.id, "Visible prompt", true).await;
    discovery_prompt(&e, team.id, "Unlisted prompt", false).await;
    let skill = Uuid::new_v4();
    sqlx::query("insert into skill(skill_id,space_id,name,summary,files,revision,created_by,updated_by,discoverable)
        values($1,$2,'visible-skill','{\"name\":\"visible-skill\",\"description\":\"Public purpose\",\"argument_hint\":\"hidden-hint-marker\"}',
        '{\"SKILL.md\":\"hidden-file-marker\"}',repeat('a',64),'alice','alice',true)")
        .bind(skill).bind(team.id).execute(&e.pool).await.unwrap();
    let agent = Uuid::new_v4();
    sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,logical_name,display_name,description,tuning,created_by,discoverable)
        values($1,$2,$1,'native','assistant',$1::text,'Visible agent','Public purpose','{\"role\":\"hidden-config-marker\"}','alice',true)")
        .bind(agent).bind(team.id).execute(&e.pool).await.unwrap();
    let query = ResourceDirectoryQuery::default();
    assert_eq!(
        team_discovery::resources(&e.pool, "bob", org.id, &query)
            .await
            .unwrap()
            .total,
        0
    );
    open(&e, team.id).await;
    for caller in ["bob", "admin"] {
        let page = team_discovery::resources(&e.pool, caller, org.id, &query)
            .await
            .unwrap();
        assert_eq!(page.total, 3);
        assert!(page.items.iter().all(|item| !item.can_read));
        let value = serde_json::to_value(&page.items).unwrap();
        let keys: std::collections::BTreeSet<_> = value[0]
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect();
        assert_eq!(
            keys,
            [
                "resource_id",
                "kind",
                "display_name",
                "description",
                "space_id",
                "space_name",
                "space_kind",
                "can_read"
            ]
            .into_iter()
            .collect()
        );
        assert!(!value.to_string().contains("hidden-"));
        assert!(
            authorization::authorize(&e.pool, caller, team.id, Permission::Read)
                .await
                .is_err()
        );
    }
    for marker in [
        "hidden-instruction-marker",
        "hidden-file-marker",
        "hidden-hint-marker",
        "hidden-config-marker",
    ] {
        let query = ResourceDirectoryQuery {
            search: Some(marker.into()),
            ..Default::default()
        };
        assert_eq!(
            team_discovery::resources(&e.pool, "bob", org.id, &query)
                .await
                .unwrap()
                .total,
            0
        );
    }
    for caller in ["outsider", "root"] {
        assert!(
            team_discovery::resources(&e.pool, caller, org.id, &query)
                .await
                .is_err()
        );
    }
    grant(&e, team.id, Role::Member, "bob").await;
    let page = team_discovery::resources(&e.pool, "bob", org.id, &query)
        .await
        .unwrap();
    assert!(
        page.items
            .iter()
            .find(|item| item.resource_id == prompt)
            .unwrap()
            .can_read
    );
    // Template policy remains necessary to open full agent configuration.
    assert!(
        !page
            .items
            .iter()
            .find(|item| item.resource_id == agent)
            .unwrap()
            .can_read
    );
    authorization::set_agent_default_on(&mut e.pool.acquire().await.unwrap(), org.id, agent, true)
        .await
        .unwrap();
    assert!(
        team_discovery::resources(&e.pool, "bob", org.id, &query)
            .await
            .unwrap()
            .items
            .iter()
            .all(|item| item.can_read)
    );
    let project = spaces::create_space(
        &e.pool,
        "alice",
        SpaceKind::Project,
        team.id,
        "Project origin".into(),
        "alice",
    )
    .await
    .unwrap();
    discovery_prompt(&e, project.id, "Project prompt", true).await;
    // A hidden project keeps its resources out of the catalog, even under a visible team.
    assert_eq!(
        team_discovery::resources(&e.pool, "admin", org.id, &query)
            .await
            .unwrap()
            .total,
        3
    );
    open(&e, project.id).await;
    assert_eq!(
        team_discovery::resources(&e.pool, "admin", org.id, &query)
            .await
            .unwrap()
            .total,
        4
    );
    spaces::update_space_parameters(
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
    assert_eq!(
        team_discovery::resources(&e.pool, "admin", org.id, &query)
            .await
            .unwrap()
            .total,
        0
    );
    authorization::write_role(
        &mut e.pool.acquire().await.unwrap(),
        "child-only",
        Role::Member,
        project.id,
        true,
    )
    .await
    .unwrap();
    let child = team_discovery::resources(&e.pool, "child-only", org.id, &query)
        .await
        .unwrap();
    assert_eq!(child.total, 1);
    assert_eq!(child.items[0].space_name, "Project origin");
    assert!(!serde_json::to_string(&child).unwrap().contains(&team.name));
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    let private = discovery_prompt(&e, personal.id, "Personal prompt", false).await;
    assert!(
        sqlx::query("update prompt set discoverable=true where prompt_id=$1")
            .bind(private)
            .execute(&e.pool)
            .await
            .is_err()
    );
    assert!(
        team_discovery::resources(&e.pool, "alice", org.id, &query)
            .await
            .unwrap()
            .items
            .iter()
            .all(|item| item.space_id != personal.id)
    );
    // Losing the last active collective role closes the organization audience.
    authorization::write_role(
        &mut e.pool.acquire().await.unwrap(),
        "child-only",
        Role::Member,
        project.id,
        false,
    )
    .await
    .unwrap();
    assert!(
        team_discovery::resources(&e.pool, "child-only", org.id, &query)
            .await
            .is_err()
    );
    let mut lifecycle = control_plane::lifecycle::Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle
        .accept(&e.pool, "root", team.id, false)
        .await
        .unwrap();
    assert_eq!(
        team_discovery::resources(&e.pool, "bob", org.id, &query)
            .await
            .unwrap()
            .total,
        0
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn resource_search_paginates_the_filtered_sql_metadata_set() {
    use control_plane::team_discovery::{DiscoverableResourceKind, ResourceDirectoryQuery};
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Member, "bob").await;
    open(&e, team.id).await;
    for index in 0..23 {
        discovery_prompt(&e, team.id, &format!("Visible {index:02}"), true).await;
    }
    discovery_prompt(&e, team.id, "Other", true).await;
    let mut query = ResourceDirectoryQuery {
        search: Some("VISIBLE purpose".into()),
        page: None,
        kind: Some(DiscoverableResourceKind::Prompt),
    };
    let first = team_discovery::resources(&e.pool, "bob", org.id, &query)
        .await
        .unwrap();
    query.page = Some(1);
    let second = team_discovery::resources(&e.pool, "bob", org.id, &query)
        .await
        .unwrap();
    assert_eq!(
        (
            first.total,
            first.items.len(),
            second.total,
            second.items.len()
        ),
        (23, 20, 23, 3)
    );
    assert!(
        first
            .items
            .iter()
            .all(|a| second.items.iter().all(|b| a.resource_id != b.resource_id))
    );
    query.page = Some(9);
    let empty = team_discovery::resources(&e.pool, "bob", org.id, &query)
        .await
        .unwrap();
    assert_eq!(empty.total, 23);
    assert!(empty.items.is_empty());
    query.page = None;
    query.kind = Some(DiscoverableResourceKind::Skill);
    assert_eq!(
        team_discovery::resources(&e.pool, "bob", org.id, &query)
            .await
            .unwrap()
            .total,
        0
    );
    query.kind = None;
    query.search = Some("%".into());
    assert_eq!(
        team_discovery::resources(&e.pool, "bob", org.id, &query)
            .await
            .unwrap()
            .total,
        0
    );
    query.search = Some("x".repeat(181));
    assert!(
        team_discovery::resources(&e.pool, "bob", org.id, &query)
            .await
            .is_err()
    );
}

async fn open(e: &Env, team: Uuid) {
    spaces::update_space_parameters(
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
    // A hidden project is disclosed to its direct role holders only.
    assert!(
        team_discovery::metadata(&e.pool, "alice", project.id)
            .await
            .unwrap()
            .is_member
    );
    assert!(
        team_discovery::metadata(&e.pool, "bob", project.id)
            .await
            .is_err()
    );
    open(&e, team.id).await;
    let visible = team_discovery::metadata(&e.pool, "bob", team.id)
        .await
        .unwrap();
    assert!(visible.can_join);
    assert!(!visible.is_member);
    // Alice's owner and member roles count once; names are resolved by the route.
    assert_eq!((visible.member_count, visible.owner_count), (1, 1));
    assert!(visible.owners.is_empty() && visible.owner_subjects == ["alice"]);
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
    identity
        .users
        .lock()
        .await
        .insert("alice".into(), "Alice Martin".into());
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
            "can_join",
            "member_count",
            "owner_count",
            "owners"
        ]
        .into_iter()
        .collect()
    );
    assert_eq!(
        payload["owners"],
        json!([{"id": "alice", "display_name": "Alice Martin"}])
    );
    assert_eq!(payload["member_count"], 1);
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
    spaces::update_space_parameters(
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
        spaces::update_space_parameters(
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
    spaces::update_space_parameters(
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
        let resources = team_discovery::resources(
            &e.pool,
            "bob",
            org.id,
            &team_discovery::ResourceDirectoryQuery::default(),
        )
        .await;
        if retire_org {
            assert!(catalogue.is_err());
            assert!(resources.is_err());
        } else {
            assert!(catalogue.unwrap().items.is_empty());
            assert!(resources.unwrap().items.is_empty());
        }
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn project_parameters_and_enrollment_follow_the_parent_team_audience() {
    use control_plane::api::{AppState, routes};
    use serde_json::{Value, json};
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    open(&e, team.id).await;
    for user in ["bob", "carol", "dave"] {
        grant(&e, org.id, Role::Member, user).await;
    }
    grant(&e, team.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Member, "carol").await;
    let create = |name: &str| {
        spaces::create_space(
            &e.pool,
            "alice",
            SpaceKind::Project,
            team.id,
            name.into(),
            "carol",
        )
    };
    let hidden = create("Hidden project").await.unwrap();
    let shared = create("Shared project").await.unwrap();
    // The team owner holds no project role, so it cannot change project parameters.
    assert!(matches!(
        spaces::update_space_parameters(
            &e.pool,
            "alice",
            shared.id,
            Some("Renamed"),
            None,
            None,
            None
        )
        .await,
        Err(AppError::Forbidden)
    ));
    let updated = spaces::update_space_parameters(
        &e.pool,
        "carol",
        shared.id,
        Some("Shared tender"),
        Some("A project description long enough"),
        Some(TeamVisibility::Visible),
        Some(TeamJoiningMode::Open),
    )
    .await
    .unwrap();
    assert_eq!(updated.name, "Shared tender");
    assert!(
        spaces::update_space_parameters(
            &e.pool,
            "carol",
            hidden.id,
            Some("Shared tender"),
            None,
            None,
            None
        )
        .await
        .is_err(),
        "sibling project names stay unique"
    );
    // Avatar and conversation retention accept a project placement.
    sqlx::query("insert into avatar(id,space_id,object_key,size,status,expires_at) values(gen_random_uuid(),$1,'avatars/project',1,'pending',now()+interval '1 hour')")
        .bind(shared.id).execute(&e.pool).await.unwrap();
    sqlx::query("update space set conversation_retention_seconds=0 where id=$1")
        .bind(shared.id)
        .execute(&e.pool)
        .await
        .unwrap();

    let ids = |cards: Vec<team_discovery::DiscoverableTeam>| {
        cards
            .into_iter()
            .map(|c| (c.id, c.is_member, c.can_join))
            .collect::<Vec<_>>()
    };
    assert_eq!(
        ids(team_discovery::projects(&e.pool, "carol", team.id)
            .await
            .unwrap()),
        [(hidden.id, true, false), (shared.id, true, false)]
    );
    assert_eq!(
        ids(team_discovery::projects(&e.pool, "bob", team.id)
            .await
            .unwrap()),
        [(shared.id, false, true)]
    );
    // Without any role on the team, neither its projects nor their cards exist.
    assert!(matches!(
        team_discovery::projects(&e.pool, "dave", team.id).await,
        Err(AppError::NotFound)
    ));
    // A team owner without a content role lists the projects but cannot join them.
    grant(&e, org.id, Role::Member, "erin").await;
    grant(&e, team.id, Role::Owner, "erin").await;
    assert_eq!(
        ids(team_discovery::projects(&e.pool, "erin", team.id)
            .await
            .unwrap()),
        [(shared.id, false, false)]
    );
    assert!(matches!(
        team_discovery::join(&e.pool, "erin", shared.id).await,
        Err(AppError::NotFound)
    ));
    assert!(matches!(
        team_discovery::projects(&e.pool, "carol", shared.id).await,
        Err(AppError::NotFound)
    ));
    assert!(
        team_discovery::metadata(&e.pool, "dave", shared.id)
            .await
            .is_err()
    );
    assert!(
        team_discovery::metadata(&e.pool, "bob", hidden.id)
            .await
            .is_err()
    );
    assert!(
        team_discovery::metadata(&e.pool, "bob", shared.id)
            .await
            .unwrap()
            .can_join
    );
    assert!(
        team_discovery::list(&e.pool, "bob", org.id, &TeamDirectoryQuery::default())
            .await
            .unwrap()
            .items
            .iter()
            .all(|card| card.id == team.id)
    );

    // Enrollment requires the parent team's content role and grants only Member.
    assert!(matches!(
        team_discovery::join(&e.pool, "dave", shared.id).await,
        Err(AppError::NotFound)
    ));
    assert!(
        team_discovery::join(&e.pool, "bob", hidden.id)
            .await
            .is_err()
    );
    team_discovery::join(&e.pool, "bob", shared.id)
        .await
        .unwrap();
    assert!(reads(&e, "bob", shared.id).await);
    assert!(!reads(&e, "bob", hidden.id).await);
    spaces::update_space_parameters(
        &e.pool,
        "carol",
        shared.id,
        None,
        None,
        None,
        Some(TeamJoiningMode::InviteOnly),
    )
    .await
    .unwrap();
    grant(&e, team.id, Role::Member, "dave").await;
    assert!(matches!(
        team_discovery::join(&e.pool, "dave", shared.id).await,
        Err(AppError::Forbidden)
    ));

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
    let listing = format!("/spaces/{}/projects", team.id);
    let (status, payload) =
        support::request(&app, &identity, Some("bob"), "GET", &listing, Value::Null).await;
    assert_eq!(status, 200, "{payload:?}");
    assert_eq!(payload.as_array().unwrap().len(), 1);
    let patch = format!("/spaces/{}", shared.id);
    for (caller, expected) in [("alice", 403), ("carol", 200)] {
        assert_eq!(
            support::request(
                &app,
                &identity,
                Some(caller),
                "PATCH",
                &patch,
                json!({"visibility":"hidden"})
            )
            .await
            .0,
            expected
        );
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn team_owner_creates_a_configured_project_with_its_initial_members() {
    use control_plane::api::{AppState, routes};
    use serde_json::json;
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    for user in ["bob", "carol", "dave"] {
        grant(&e, org.id, Role::Member, user).await;
    }
    grant(&e, team.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Editor, "carol").await;
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
    let body = |name: &str, members: serde_json::Value| {
        json!({"kind":"project","parent_id":team.id,"name":name,
            "description":"  A tender answered by a small group  ",
            "visibility":"visible","joining_mode":"open",
            "conversation_retention_seconds":3600,"members":members})
    };
    let create = |caller: &'static str, payload: serde_json::Value| {
        let app = app.clone();
        let identity = &identity;
        async move { support::request(&app, identity, Some(caller), "POST", "/spaces", payload).await }
    };
    let both =
        json!([{"user":"bob","roles":["owner","member"]},{"user":"carol","roles":["editor"]}]);
    // Only the team's direct owner creates; a team member is refused.
    assert_eq!(create("bob", body("Tender", both.clone())).await.0, 403);
    // At least one owner, a description, and team content roles for every member.
    assert_eq!(
        create(
            "alice",
            body("Tender", json!([{"user":"carol","roles":["editor"]}]))
        )
        .await
        .0,
        422
    );
    let mut undescribed = body("Tender", both.clone());
    undescribed.as_object_mut().unwrap().remove("description");
    assert_eq!(create("alice", undescribed.clone()).await.0, 422);
    undescribed["description"] = json!("Too short");
    assert_eq!(create("alice", undescribed).await.0, 422);
    assert_eq!(
        create(
            "alice",
            body("Tender", json!([{"user":"dave","roles":["owner"]}]))
        )
        .await
        .0,
        409
    );
    assert!(
        control_plane::authorization::roles_of(&e.pool, "dave")
            .await
            .unwrap()
            .iter()
            .all(|(id, _)| *id == org.id),
        "refused creations leave no role"
    );

    let (status, created) = create("alice", body("Tender", both.clone())).await;
    assert_eq!(status, 201, "{created:?}");
    let id: Uuid = created["id"].as_str().unwrap().parse().unwrap();
    let row: (Option<String>, TeamVisibility, TeamJoiningMode, Option<i64>) = sqlx::query_as(
        "select description, visibility, joining_mode, conversation_retention_seconds from space where id=$1",
    )
    .bind(id)
    .fetch_one(&e.pool)
    .await
    .unwrap();
    assert_eq!(
        row,
        (
            Some("A tender answered by a small group".into()),
            TeamVisibility::Visible,
            TeamJoiningMode::Open,
            Some(3600)
        )
    );
    let roles_on = |user: &'static str| {
        let pool = e.pool.clone();
        async move {
            let mut roles: Vec<Role> = control_plane::authorization::roles_of(&pool, user)
                .await
                .unwrap()
                .into_iter()
                .filter(|(space, _)| *space == id)
                .map(|(_, role)| role)
                .collect();
            roles.sort();
            roles
        }
    };
    assert_eq!(roles_on("bob").await, [Role::Member, Role::Owner]);
    assert_eq!(roles_on("carol").await, [Role::Editor]);
    assert!(
        roles_on("alice").await.is_empty(),
        "the creator gets nothing unless listed"
    );
    // Sibling names stay unique.
    assert_eq!(create("alice", body("Tender", both)).await.0, 409);
}
