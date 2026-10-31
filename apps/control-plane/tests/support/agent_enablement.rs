// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use control_plane::{agents::template_id, authorization::set_agent_default_on};

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn defaults_are_isolated_and_revocable() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let other = support::member_organization(&e.pool, &e.authorization, "Other", "bob")
        .await
        .unwrap();
    let template = template_id(org.id, "runtime", "hello");
    assert!(
        !e.authorization
            .can_use_agent(template, &team)
            .await
            .unwrap()
    );
    let mut tx = e.pool.begin().await.unwrap();
    assert!(
        set_agent_default_on(&mut tx, org.id, template, true)
            .await
            .unwrap()
    );
    tx.commit().await.unwrap();
    assert!(
        e.authorization
            .can_use_agent(template, &team)
            .await
            .unwrap()
    );
    assert!(
        !e.authorization
            .agent_default_on(other.id, template)
            .await
            .unwrap()
    );
    let (personal, _) = spaces::create_personal_space(&e.pool, "alice", org.id)
        .await
        .unwrap();
    assert!(
        e.authorization
            .can_use_agent(template, &personal)
            .await
            .unwrap()
    );
    let mut tx = e.pool.begin().await.unwrap();
    assert!(
        set_agent_default_on(&mut tx, org.id, template, false)
            .await
            .unwrap()
    );
    tx.commit().await.unwrap();
    assert!(
        !e.authorization
            .can_use_agent(template, &team)
            .await
            .unwrap()
    );
    assert!(
        !e.authorization
            .can_use_agent(template, &personal)
            .await
            .unwrap()
    );
}
