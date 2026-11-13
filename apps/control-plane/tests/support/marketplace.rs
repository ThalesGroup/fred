// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use axum::Router;
use control_plane::api::{AppState, routes};
use serde_json::{Value, json};
use std::sync::Arc;
use support::{IdentityServer, request, request_with_headers};

async fn app(e: &Env, identity: &IdentityServer) -> Router {
    routes(AppState {
        history: None,
        pool: e.pool.clone(),
        agent_catalog: Default::default(),
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: control_plane::onboarding::Onboarding {
            gcu_version: None,
            ..Default::default()
        },
        lifecycle: Default::default(),
    })
}

async fn post(
    app: &Router,
    identity: &IdentityServer,
    actor: &str,
    route: &str,
    key: Uuid,
    body: Value,
) -> (u16, Value) {
    request_with_headers(
        app,
        identity,
        Some(actor),
        "POST",
        route,
        body,
        &[("Idempotency-Key", key.to_string())],
    )
    .await
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn marketplace_space_rights_snapshots_and_installation_retries() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "alice").await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Editor, "bob").await;
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
    grant(&e, org.id, Role::Member, "reader").await;
    grant(&e, team.id, Role::Member, "reader").await;
    grant(&e, project.id, Role::Member, "reader").await;
    sqlx::query("delete from space_role_grant where subject='reader' and space_id=any($1)")
        .bind(vec![org.id, team.id])
        .execute(&e.pool)
        .await
        .unwrap();
    let (personal, _) = spaces::create_personal_space(&e.pool, "bob", org.id)
        .await
        .unwrap();
    sqlx::query("insert into space_role_grant(space_id,subject,role) values($1,'technical','organization_admin')")
        .bind(org.id).execute(&e.pool).await.unwrap();
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    let root = format!("/spaces/{}/marketplace", org.id);
    let proposals = format!("{root}/proposals");
    for kind in ["prompt", "skill"] {
        let (resource, revision, source_route) = if kind == "prompt" {
            let route = format!("/spaces/{}/prompts", personal.id);
            let (status, p) = request(
                &app,
                &identity,
                Some("bob"),
                "POST",
                &route,
                json!({"logical_name":"shared","display_name":"Shared","text":"Original"}),
            )
            .await;
            assert_eq!(status, 201, "{p}");
            (
                p["prompt_id"].clone(),
                p["updated_at"].clone(),
                format!("{route}/{}", p["prompt_id"].as_str().unwrap()),
            )
        } else {
            let route = format!("/spaces/{}/skills", personal.id);
            let files = json!({"SKILL.md":"---\nname: shared\ndescription: Shared\nlicense: MIT\n---\nOriginal","LICENSE.txt":"Keep this notice"});
            assert_eq!(
                request(
                    &app,
                    &identity,
                    Some("bob"),
                    "POST",
                    &route,
                    json!({"name":"shared","files":files})
                )
                .await
                .0,
                204
            );
            let (_, rows) = request(&app, &identity, Some("bob"), "GET", &route, Value::Null).await;
            let id = rows[0]["skill_id"].clone();
            (
                id.clone(),
                rows[0]["revision"].clone(),
                format!("{route}/{}", id.as_str().unwrap()),
            )
        };
        let body = json!({"source_space_id":personal.id,"source_resource_id":resource,"kind":kind,"expected_revision":revision});
        let key = Uuid::new_v4();
        // Force both requests past their absent-key read before either inserts its proposal.
        let mut gate = e.pool.begin().await.unwrap();
        sqlx::query("lock table marketplace_proposal in share mode")
            .execute(&mut *gate)
            .await
            .unwrap();
        let submissions = async {
            tokio::join!(
                post(&app, &identity, "bob", &proposals, key, body.clone()),
                post(&app, &identity, "bob", &proposals, key, body.clone())
            )
        };
        tokio::pin!(submissions);
        tokio::select! {
            result = &mut submissions => panic!("submissions bypassed the insert gate: {result:?}"),
            () = wait_for_relation_waiters(&e.pool, "marketplace_proposal", 2) => {}
        }
        gate.rollback().await.unwrap();
        let (left, right) = submissions.await;
        assert_eq!(left.0, 200, "{}", left.1);
        assert_eq!(right.0, 200, "{}", right.1);
        assert_eq!(left.1, right.1);
        let entries: i64 = sqlx::query_scalar(
            "select count(*) from marketplace_entry where marketplace_space_id=$1 and kind=$2",
        )
        .bind(org.id)
        .bind(kind)
        .fetch_one(&e.pool)
        .await
        .unwrap();
        assert_eq!(
            entries, 1,
            "the losing submission must roll back its speculative entry"
        );
        let p = left.1;
        let path = format!("{proposals}/{}", p["proposal_id"].as_str().unwrap());
        let entry = format!("{root}/entries/{}", p["entry_id"].as_str().unwrap());
        // A source editor can propose; their role cannot decide for the catalogue.
        for actor in ["bob", "reader", "technical"] {
            let (status, _) = request(
                &app,
                &identity,
                Some(actor),
                "PUT",
                &format!("{path}/decision"),
                json!({"approve":true,"expected_publication_version":0}),
            )
            .await;
            assert!(matches!(status, 403 | 404), "{actor}: {status}");
        }
        for actor in ["reader", "technical"] {
            assert_eq!(
                request(&app, &identity, Some(actor), "GET", &path, Value::Null)
                    .await
                    .0,
                404
            );
        }
        let (_, queue) = request(
            &app,
            &identity,
            Some("reader"),
            "GET",
            &proposals,
            Value::Null,
        )
        .await;
        assert_eq!(queue["items"], json!([]));
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "GET",
                &source_route,
                Value::Null
            )
            .await
            .0,
            403
        );
        let (status, examined) =
            request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await;
        assert_eq!(status, 200);
        assert_eq!(examined["package"], p["package"]);
        let mut different = body.clone();
        different["source_resource_id"] = json!(Uuid::new_v4());
        assert_eq!(
            post(&app, &identity, "bob", &proposals, key, different)
                .await
                .1["code"],
            "idempotency_conflict"
        );
        assert_eq!(
            request(&app, &identity, Some("reader"), "GET", &entry, Value::Null)
                .await
                .0,
            404
        );
        let decision = json!({"approve":true,"expected_publication_version":0});
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &format!("{path}/decision"),
                decision.clone()
            )
            .await
            .0,
            200
        );
        // Project participation reads the publication, without organization library rights.
        assert_eq!(
            request(
                &app,
                &identity,
                Some("reader"),
                "GET",
                &format!("/spaces/{}/prompts", org.id),
                Value::Null
            )
            .await
            .0,
            403
        );
        let (status, published) =
            request(&app, &identity, Some("reader"), "GET", &entry, Value::Null).await;
        assert_eq!(status, 200, "{published}");
        assert_eq!(published["package"], p["package"]);
        assert!(published.get("proposing_space_id").is_none());
        // Source mutation never touches the snapshot. Capture a successor, then refuse it.
        if kind == "prompt" {
            assert_eq!(
                request(
                    &app,
                    &identity,
                    Some("bob"),
                    "PATCH",
                    &source_route,
                    json!({"text":"Changed"})
                )
                .await
                .0,
                200
            );
        } else {
            let (_, current) = request(
                &app,
                &identity,
                Some("bob"),
                "GET",
                &source_route,
                Value::Null,
            )
            .await;
            let mut changed = current.clone();
            changed["files"]["LICENSE.txt"] = json!("Changed notice");
            assert_eq!(
                request(&app, &identity, Some("bob"), "PUT", &source_route, changed)
                    .await
                    .0,
                204
            );
        }
        let (_, current) = request(
            &app,
            &identity,
            Some("bob"),
            "GET",
            &source_route,
            Value::Null,
        )
        .await;
        let mut successor = body.clone();
        successor["entry_id"] = p["entry_id"].clone();
        successor["expected_revision"] = current[if kind == "prompt" {
            "updated_at"
        } else {
            "expected_revision"
        }]
        .clone();
        let (status, next) = post(
            &app,
            &identity,
            "bob",
            &proposals,
            Uuid::new_v4(),
            successor,
        )
        .await;
        assert_eq!(status, 200, "{next}");
        let refusal = format!(
            "{proposals}/{}/decision",
            next["proposal_id"].as_str().unwrap()
        );
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &refusal,
                json!({"approve":false,"reason":"Revise","expected_publication_version":1})
            )
            .await
            .0,
            200
        );
        let (_, still) = request(&app, &identity, Some("reader"), "GET", &entry, Value::Null).await;
        assert_eq!(still["package"], p["package"]);
        let options = if kind == "prompt" {
            json!({"kind":"prompt","logical_name":"shared"})
        } else {
            json!({"kind":"skill"})
        };
        let install_body = json!({"proposal_id":p["proposal_id"],"destination_space_id":team.id,"options":options});
        let install_route = format!("{entry}/installations");
        let install_key = Uuid::new_v4();
        let (a, b) = tokio::join!(
            post(
                &app,
                &identity,
                "bob",
                &install_route,
                install_key,
                install_body.clone()
            ),
            post(
                &app,
                &identity,
                "bob",
                &install_route,
                install_key,
                install_body.clone()
            )
        );
        assert_eq!(a.0, 200, "{}", a.1);
        assert_eq!(a, b);
        let receipt = a.1;
        assert_eq!(
            post(
                &app,
                &identity,
                "bob",
                &install_route,
                Uuid::new_v4(),
                install_body.clone()
            )
            .await
            .0,
            409
        );
        assert_eq!(
            request(
                &app,
                &identity,
                Some("bob"),
                "DELETE",
                &source_route,
                Value::Null
            )
            .await
            .0,
            204
        );
        assert_eq!(
            post(&app, &identity, "bob", &proposals, key, body.clone())
                .await
                .1["package"],
            p["package"]
        );
        assert_eq!(
            request(&app, &identity, Some("reader"), "GET", &entry, Value::Null)
                .await
                .0,
            200
        );
        // Republication is another snapshot; an installed copy can be its source.
        let local = format!(
            "/spaces/{}/{}/{}",
            team.id,
            if kind == "prompt" {
                "prompts"
            } else {
                "skills"
            },
            receipt["resource_id"].as_str().unwrap()
        );
        let (_, copied) = request(&app, &identity, Some("bob"), "GET", &local, Value::Null).await;
        let next_body = json!({"entry_id":p["entry_id"],"source_space_id":team.id,"source_resource_id":receipt["resource_id"],"kind":kind,
            "expected_revision":copied[if kind=="prompt" {"updated_at"} else {"expected_revision"}]});
        let (status, republication) = post(
            &app,
            &identity,
            "bob",
            &proposals,
            Uuid::new_v4(),
            next_body,
        )
        .await;
        assert_eq!(status, 200, "{republication}");
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &format!(
                    "{proposals}/{}/decision",
                    republication["proposal_id"].as_str().unwrap()
                ),
                json!({"approve":true,"expected_publication_version":1})
            )
            .await
            .0,
            200
        );
        assert_eq!(
            request(&app, &identity, Some("bob"), "GET", &local, Value::Null)
                .await
                .1,
            copied
        );
        let withdrawal = format!("{entry}/withdrawal");
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &withdrawal,
                json!({"expected_publication_version":2})
            )
            .await
            .0,
            204
        );
        assert_eq!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &format!("{path}/decision"),
                decision
            )
            .await
            .0,
            200
        );
        assert_eq!(
            request(&app, &identity, Some("reader"), "GET", &entry, Value::Null)
                .await
                .0,
            404
        );
        assert_eq!(
            post(
                &app,
                &identity,
                "bob",
                &install_route,
                install_key,
                install_body.clone()
            )
            .await
            .1,
            receipt
        );
        let local = format!(
            "/spaces/{}/{}/{}",
            team.id,
            if kind == "prompt" {
                "prompts"
            } else {
                "skills"
            },
            receipt["resource_id"].as_str().unwrap()
        );
        let (_, copied) = request(&app, &identity, Some("bob"), "GET", &local, Value::Null).await;
        if kind == "prompt" {
            assert_eq!(copied["text"], "Original");
        } else {
            assert_eq!(copied["files"]["LICENSE.txt"], "Keep this notice");
        }
        assert_eq!(
            request(&app, &identity, Some("bob"), "DELETE", &local, Value::Null)
                .await
                .0,
            204
        );
        let (_, replayed) = post(
            &app,
            &identity,
            "bob",
            &install_route,
            install_key,
            install_body,
        )
        .await;
        assert_eq!(replayed["resource_id"], receipt["resource_id"]);
        assert_eq!(replayed["resource_exists"], false);
    }
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn marketplace_revocation_and_competing_decisions_use_current_space_rights() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "alice").await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Editor, "bob").await;
    let (personal, _) = spaces::create_personal_space(&e.pool, "bob", org.id)
        .await
        .unwrap();
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    let (_, prompt) = request(
        &app,
        &identity,
        Some("bob"),
        "POST",
        &format!("/spaces/{}/prompts", personal.id),
        json!({"logical_name":"sample","display_name":"Sample","text":"Original"}),
    )
    .await;
    let root = format!("/spaces/{}/marketplace", org.id);
    let proposals = format!("{root}/proposals");
    let body = json!({"source_space_id":personal.id,"source_resource_id":prompt["prompt_id"],"expected_revision":prompt["updated_at"],"kind":"prompt"});
    let (status, first) = post(
        &app,
        &identity,
        "bob",
        &proposals,
        Uuid::new_v4(),
        body.clone(),
    )
    .await;
    assert_eq!(status, 200, "{first}");
    let mut next = body.clone();
    next["entry_id"] = first["entry_id"].clone();
    let (status, second) = post(&app, &identity, "bob", &proposals, Uuid::new_v4(), next).await;
    assert_eq!(status, 200, "{second}");
    let first_path = format!("{proposals}/{}", first["proposal_id"].as_str().unwrap());
    let second_path = format!("{proposals}/{}", second["proposal_id"].as_str().unwrap());
    let d1 = format!("{first_path}/decision");
    let d2 = format!("{second_path}/decision");
    let mut gate = e.pool.begin().await.unwrap();
    sqlx::query("select entry_id from marketplace_entry where entry_id=$1 for update")
        .bind(Uuid::parse_str(first["entry_id"].as_str().unwrap()).unwrap())
        .execute(&mut *gate)
        .await
        .unwrap();
    let decisions = async {
        tokio::join!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &d1,
                json!({"approve":true,"expected_publication_version":0})
            ),
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &d2,
                json!({"approve":true,"expected_publication_version":0})
            )
        )
    };
    tokio::pin!(decisions);
    tokio::select! {
        result = &mut decisions => panic!("decisions bypassed the entry guard: {result:?}"),
        () = wait_for_content_waiters(&e.pool, "^select e.entry_id from marketplace_entry") => {}
    }
    gate.rollback().await.unwrap();
    let (a, b) = decisions.await;
    assert!(matches!((a.0, b.0), (200, 409) | (409, 200)), "{a:?} {b:?}");
    let version: i64 =
        sqlx::query_scalar("select publication_version from marketplace_entry where entry_id=$1")
            .bind(Uuid::parse_str(first["entry_id"].as_str().unwrap()).unwrap())
            .fetch_one(&e.pool)
            .await
            .unwrap();
    assert_eq!(version, 1, "exactly one proposal publishes");
    spaces::revoke(&e.pool, "alice", personal.id, Role::Editor, "bob")
        .await
        .unwrap();
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "GET",
            &first_path,
            Value::Null
        )
        .await
        .0,
        404
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &first_path,
            Value::Null
        )
        .await
        .0,
        200
    );
    // Removing the proposing space keeps both proposals and the approved catalogue copy.
    sqlx::query("delete from space where id=$1")
        .bind(personal.id)
        .execute(&e.pool)
        .await
        .unwrap();
    let entry = format!("{root}/entries/{}", first["entry_id"].as_str().unwrap());
    assert_eq!(
        request(&app, &identity, Some("bob"), "GET", &entry, Value::Null)
            .await
            .0,
        200
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &first_path,
            Value::Null
        )
        .await
        .0,
        200
    );
    let other = support::member_organization(&e.pool, "Other", "carol").await;
    assert!(other.is_ok());
    assert_eq!(
        request(&app, &identity, Some("carol"), "GET", &entry, Value::Null)
            .await
            .0,
        404
    );
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn marketplace_native_ralph_uses_local_owner_and_independent_installation() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    grant(&e, org.id, Role::Editor, "alice").await;
    grant(&e, org.id, Role::Member, "bob").await;
    grant(&e, team.id, Role::Editor, "bob").await;
    grant(&e, org.id, Role::Member, "reader").await;
    let (personal, _) = spaces::create_personal_space(&e.pool, "bob", org.id)
        .await
        .unwrap();
    let identity = IdentityServer::start().await;
    // No HTTP pod is configured: creation and marketplace use the native owner.
    let app = app(&e, &identity).await;
    let template = control_plane::agents::template_id(
        org.id,
        fred_rust_agent::DEFINITION.provider,
        fred_rust_agent::AGENT_ID,
    );
    control_plane::authorization::set_agent_default_on(
        &mut e.pool.acquire().await.unwrap(),
        org.id,
        template,
        true,
    )
    .await
    .unwrap();
    let collection = format!("/spaces/{}/agent-instances", personal.id);
    let (status,source)=request(&app,&identity,Some("bob"),"POST",&collection,json!({
        "template_id":template,"logical_name":"source-ralph","display_name":"Local Ralph",
        "role":"Original role","usage_statement":"Original usage","description":"Original description"
    })).await;
    assert_eq!(status, 201, "{source}");
    let source_id: Uuid = source["agent_instance_id"]
        .as_str()
        .unwrap()
        .parse()
        .unwrap();
    let record = control_plane::agent_instances::get_for_space(&e.pool, personal.id, source_id)
        .await
        .unwrap()
        .unwrap();
    let submissions = format!("/spaces/{}/marketplace/proposals", org.id);
    let body = json!({"source_space_id":personal.id,"source_resource_id":source_id,"kind":"agent","expected_revision":record.configuration_revision.to_string()});
    assert_eq!(
        post(
            &app,
            &identity,
            "reader",
            &submissions,
            Uuid::new_v4(),
            body.clone()
        )
        .await
        .0,
        403
    );
    // Native configuration has no custom fields: unknown saved references fail closed.
    sqlx::query("update agent_instance set tuning=jsonb_set(tuning,'{values}',$2) where agent_instance_id=$1")
        .bind(source_id).bind(json!({"source_id":"private-reference"})).execute(&e.pool).await.unwrap();
    assert_eq!(
        post(
            &app,
            &identity,
            "bob",
            &submissions,
            Uuid::new_v4(),
            body.clone()
        )
        .await
        .0,
        422
    );
    sqlx::query("update agent_instance set tuning=$2 where agent_instance_id=$1")
        .bind(source_id)
        .bind(record.tuning.0)
        .execute(&e.pool)
        .await
        .unwrap();
    let key = Uuid::new_v4();
    let (status, proposal) = post(&app, &identity, "bob", &submissions, key, body.clone()).await;
    assert_eq!(status, 200, "{proposal}");
    let package = &proposal["package"]["content"];
    assert_eq!(package["runtime_id"], fred_rust_agent::DEFINITION.provider);
    assert_eq!(package["template_agent_id"], fred_rust_agent::AGENT_ID);
    assert_eq!(package["tuning_field_values"], json!({}));
    assert_eq!(package["capabilities"], json!({}));
    let path = format!(
        "{submissions}/{}",
        proposal["proposal_id"].as_str().unwrap()
    );
    let source_path = format!("{collection}/{source_id}");
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &source_path,
            Value::Null
        )
        .await
        .0,
        403
    );
    assert_eq!(
        request(&app, &identity, Some("alice"), "GET", &path, Value::Null)
            .await
            .0,
        200
    );
    assert_eq!(
        request(&app, &identity, Some("reader"), "GET", &path, Value::Null)
            .await
            .0,
        404
    );
    let decision = json!({"approve":true,"expected_publication_version":0});
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "PUT",
            &format!("{path}/decision"),
            decision.clone()
        )
        .await
        .0,
        403
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &format!("{path}/decision"),
            decision
        )
        .await
        .0,
        200
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "PATCH",
            &source_path,
            json!({"role":"Changed"})
        )
        .await
        .0,
        200
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("bob"),
            "DELETE",
            &source_path,
            Value::Null
        )
        .await
        .0,
        204
    );
    assert_eq!(
        post(&app, &identity, "bob", &submissions, key, body)
            .await
            .1["package"],
        proposal["package"]
    );
    let entry = format!(
        "/spaces/{}/marketplace/entries/{}",
        org.id,
        proposal["entry_id"].as_str().unwrap()
    );
    assert_eq!(
        request(&app, &identity, Some("reader"), "GET", &entry, Value::Null)
            .await
            .0,
        200
    );
    let route = format!("{entry}/installations");
    let install = json!({"proposal_id":proposal["proposal_id"],"destination_space_id":team.id,"options":{"kind":"agent","logical_name":"installed-ralph","display_name":"Installed Ralph"}});
    assert_eq!(
        post(
            &app,
            &identity,
            "reader",
            &route,
            Uuid::new_v4(),
            install.clone()
        )
        .await
        .0,
        403
    );
    control_plane::authorization::set_agent_default_on(
        &mut e.pool.acquire().await.unwrap(),
        org.id,
        template,
        false,
    )
    .await
    .unwrap();
    assert_eq!(
        post(
            &app,
            &identity,
            "bob",
            &route,
            Uuid::new_v4(),
            install.clone()
        )
        .await
        .0,
        404
    );
    control_plane::authorization::set_agent_default_on(
        &mut e.pool.acquire().await.unwrap(),
        org.id,
        template,
        true,
    )
    .await
    .unwrap();
    let install_key = Uuid::new_v4();
    let (status, receipt) =
        post(&app, &identity, "bob", &route, install_key, install.clone()).await;
    assert_eq!(status, 200, "{receipt}");
    assert_ne!(receipt["resource_id"], json!(source_id));
    let local = format!(
        "/spaces/{}/agent-instances/{}",
        team.id,
        receipt["resource_id"].as_str().unwrap()
    );
    let (status, installed) =
        request(&app, &identity, Some("bob"), "GET", &local, Value::Null).await;
    assert_eq!(status, 200, "{installed}");
    assert_eq!(installed["role"], "Original role");
    assert_eq!(installed["usage_statement"], "Original usage");
    assert_eq!(installed["description"], "Original description");
    assert_eq!(installed["template_id"], json!(template));
    assert_eq!(
        post(&app, &identity, "bob", &route, install_key, install)
            .await
            .1,
        receipt
    );
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "PUT",
            &format!("{entry}/withdrawal"),
            json!({"expected_publication_version":1})
        )
        .await
        .0,
        204
    );
    assert_eq!(
        request(&app, &identity, Some("bob"), "GET", &local, Value::Null)
            .await
            .1,
        installed
    );
}

async fn wait_for_relation_waiters(pool: &PgPool, relation: &str, count: i64) {
    tokio::time::timeout(Duration::from_secs(3), async {
        loop {
            let waiting: i64 = sqlx::query_scalar("select count(*) from pg_locks where database=(select oid from pg_database where datname=current_database()) and relation=$1::text::regclass and not granted")
                .bind(relation).fetch_one(pool).await.unwrap();
            if waiting >= count { break; }
            tokio::task::yield_now().await;
        }
    }).await.expect("both submissions must reach the insert gate");
}

async fn wait_for_content_waiters(pool: &PgPool, pattern: &str) {
    tokio::time::timeout(Duration::from_secs(3), async {
        loop {
            let waiting: i64 = sqlx::query_scalar("select count(*) from pg_stat_activity where datname=current_database() and wait_event_type='Lock' and query ~ $1")
                .bind(pattern).fetch_one(pool).await.unwrap();
            if waiting == 2 { break; }
            tokio::task::yield_now().await;
        }
    }).await.expect("both content requests must reach their row guards");
}

#[tokio::test]
#[ignore = "needs disposable Postgres: make test-integration"]
async fn concurrent_put_skill_accepts_only_one_expected_revision() {
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    grant(&e, team.id, Role::Editor, "alice").await;
    let identity = IdentityServer::start().await;
    let app = app(&e, &identity).await;
    let root = format!("/spaces/{}/skills", team.id);
    let files = |text: &str| json!({"SKILL.md":format!("---\nname: sample\ndescription: Sample\nlicense: MIT\n---\n{text}")});
    assert_eq!(
        request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            &root,
            json!({"name":"sample","files":files("Original")})
        )
        .await
        .0,
        204
    );
    let (_, rows) = request(&app, &identity, Some("alice"), "GET", &root, Value::Null).await;
    let path = format!("{root}/{}", rows[0]["skill_id"].as_str().unwrap());
    let revision = &rows[0]["revision"];
    let mut gate = e.pool.begin().await.unwrap();
    sqlx::query("select skill_id from skill where space_id=$1 for update")
        .bind(team.id)
        .execute(&mut *gate)
        .await
        .unwrap();
    let replacements = async {
        tokio::join!(
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &path,
                json!({"expected_revision":revision,"files":files("Left")})
            ),
            request(
                &app,
                &identity,
                Some("alice"),
                "PUT",
                &path,
                json!({"expected_revision":revision,"files":files("Right")})
            )
        )
    };
    tokio::pin!(replacements);
    tokio::select! {
        result = &mut replacements => panic!("replacements bypassed the row guard: {result:?}"),
        () = wait_for_content_waiters(&e.pool, "^(select revision from skill|select id from space|insert into skill)") => {}
    }
    gate.rollback().await.unwrap();
    let (a, b) = replacements.await;
    assert!(matches!((a.0, b.0), (204, 409) | (409, 204)), "{a:?} {b:?}");
    let (_, saved) = request(&app, &identity, Some("alice"), "GET", &path, Value::Null).await;
    assert_eq!(
        saved["files"],
        files(if a.0 == 204 { "Left" } else { "Right" })
    );
}
