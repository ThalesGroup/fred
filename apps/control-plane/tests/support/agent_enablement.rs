// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::*;
use control_plane::agents::template_id;
use serde_json::json;

async fn tuple(e: &Env, template: Uuid, subject: Uuid, relation: &str) {
    let response = reqwest::Client::new()
        .post(format!("{}/stores/{}/write", e.openfga, e.fga.store_id()))
        .json(&json!({"writes":{"tuple_keys":[{
            "user":format!("space:{subject}"), "relation":relation,
            "object":format!("agent_template:{template}")
        }], "on_duplicate":"ignore"}}))
        .send()
        .await
        .unwrap();
    assert!(
        response.status().is_success(),
        "{}",
        response.text().await.unwrap()
    );
}

#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn defaults_are_isolated_and_exceptions_remain_authoritative() {
    let e = env().await;
    let (o1, e1) = org_and_team(&e).await;
    let o2 = support::member_organization(&e.pool, &e.fga, "O2", "bob")
        .await
        .unwrap();
    let a1 = template_id(o1.id, "runtime", "hello");
    let a2 = template_id(o2.id, "runtime", "hello");
    assert_ne!(a1, a2);
    assert!(!e.fga.agent_default_on(o1.id, a1).await.unwrap());
    assert!(!e.fga.can_use_agent(a1, &e1).await.unwrap());
    let mut guard = e.fga.guard(&[Scope::Organization(o1.id)]).await.unwrap();
    e.fga
        .set_agent_default_on(&mut guard, o1.id, a1, true)
        .await
        .unwrap();
    assert!(e.fga.agent_default_on(o1.id, a1).await.unwrap());
    assert!(!e.fga.agent_default_on(o2.id, a2).await.unwrap());
    assert!(e.fga.can_use_agent(a1, &e1).await.unwrap());
    assert!(!e.fga.can_use_agent(a2, &e1).await.unwrap());

    spaces::grant(
        &e.pool,
        &e.fga,
        &e.subjects(),
        "alice",
        o1.id,
        Role::PersonalSpaceCreator,
        "alice",
    )
    .await
    .unwrap();
    let (personal, _) = spaces::create_personal_space(&e.pool, &e.fga, "alice", o1.id)
        .await
        .unwrap();
    assert!(e.fga.can_use_agent(a1, &personal).await.unwrap());
    tuple(&e, a1, o1.id, "personal_disabled").await;
    assert!(!e.fga.can_use_agent(a1, &personal).await.unwrap());
    tuple(&e, a1, personal.id, "enabled").await;
    assert!(e.fga.can_use_agent(a1, &personal).await.unwrap());
    tuple(&e, a1, e1.id, "enabled").await;
    // Capture a fresh guard after the normal personal-space mutations above.
    let mut guard = e.fga.guard(&[Scope::Organization(o1.id)]).await.unwrap();
    e.fga
        .set_agent_default_on(&mut guard, o1.id, a1, false)
        .await
        .unwrap();
    assert!(e.fga.can_use_agent(a1, &e1).await.unwrap());
    tuple(&e, a1, e1.id, "disabled").await;
    assert!(!e.fga.can_use_agent(a1, &e1).await.unwrap());
    // A class grant survives default-off, without granting an ordinary team.
    let other = template_id(o1.id, "runtime", "second");
    tuple(&e, other, o1.id, "organization").await;
    tuple(&e, other, o1.id, "personal_on").await;
    assert!(e.fga.can_use_agent(other, &personal).await.unwrap());
    assert!(!e.fga.can_use_agent(other, &e1).await.unwrap());
}

// Proves: I24
#[tokio::test]
#[ignore = "needs Postgres and OpenFGA: make test-integration"]
async fn organization_cleanup_drains_template_grants_across_pages() {
    use control_plane::lifecycle::{Lifecycle, Status, cleanup, store};
    let e = env().await;
    bootstrap::grant_root(&e.pool, &e.fga, "root")
        .await
        .unwrap();
    let (organization, _) = org_and_team(&e).await;
    let template = template_id(organization.id, "runtime", "hello");
    let mut guard = e
        .fga
        .guard(&[Scope::Organization(organization.id)])
        .await
        .unwrap();
    e.fga
        .set_agent_default_on(&mut guard, organization.id, template, true)
        .await
        .unwrap();
    // Orphan exception subjects must be cleaned with the template anchor too.
    for _ in 0..110 {
        tuple(&e, template, Uuid::new_v4(), "enabled").await;
    }
    let mut lifecycle = Lifecycle::default();
    lifecycle.config.enabled = true;
    lifecycle.catalog.space_policies.purge.default.retention =
        serde_yaml_ng::from_str("PT0S").unwrap();
    let receipt = lifecycle
        .accept(&e.pool, &e.fga, "root", organization.id)
        .await
        .unwrap();
    for _ in 0..100 {
        if store::status(&e.pool, &e.fga, "root", receipt.id)
            .await
            .unwrap()
            .status
            == Status::Completed
        {
            break;
        }
        cleanup::batch(&e.pool, &e.fga, receipt.id).await.unwrap();
    }
    assert_eq!(
        store::status(&e.pool, &e.fga, "root", receipt.id)
            .await
            .unwrap()
            .status,
        Status::Completed
    );
    let response: serde_json::Value = reqwest::Client::new()
        .post(format!("{}/stores/{}/read", e.openfga, e.fga.store_id()))
        .json(&json!({"tuple_key":{"object":format!("agent_template:{template}")},"consistency":"HIGHER_CONSISTENCY"}))
        .send().await.unwrap().json().await.unwrap();
    assert_eq!(response["tuples"], json!([]));
}
