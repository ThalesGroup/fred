// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use control_plane::{
    agents::PlatformConfig,
    api::{AppState, routes},
    knowledge_bases::{Config, CredentialBinding},
    processing::config::WorkerIdentity,
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, sync::Arc};

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn knowledge_base_publication_requires_exact_worker_and_reuses_offer_policy() {
    let e = env().await;
    let (org, team) = org_and_team(&e).await;
    let identity = support::IdentityServer::start().await;
    let worker = |client: &str| WorkerIdentity {
        issuer: identity.realm.clone(),
        audience: "app".into(),
        client_id: client.into(),
    };
    let config = PlatformConfig {
        knowledge_bases: Config {
            workers: BTreeMap::from([
                ("webdav".into(), worker("webdav-worker")),
                ("other".into(), worker("other-worker")),
            ]),
            credentials: vec![CredentialBinding {
                runtime_id: "webdav".into(),
                space_id: team.id,
                credential_binding: "team-source".into(),
            }],
        },
        ..Default::default()
    };
    // A collector is not required to expose an HTTP agent catalog.
    config.validate().unwrap();
    let app = routes(AppState {
        history: None,
        pool: e.pool.clone(),
        agent_catalog: config,
        auth: Arc::new(identity.auth().await),
        directory: Some(identity.directory()),
        content: None,
        processing: None,
        onboarding: Default::default(),
        lifecycle: Default::default(),
    });
    let token = |client: &str| {
        let now = chrono::Utc::now().timestamp();
        identity.sign(json!({"sub":format!("service-{client}"),"preferred_username":format!("service-account-{client}"),"azp":client,"client_id":client,"iss":identity.realm,"aud":"app","iat":now,"exp":now+300}))
    };
    let declaration = json!({"runtime_id":"webdav","definitions":[{"id":"fred.webdav.folder","version":"1","name":"WebDAV","description":"A folder mirror","icon":"folder","config_schema":{"fields":[]}}]});
    let path = "/knowledge-base-definitions/publish";
    let call = |client: &str, body: Value| {
        let auth = format!("Bearer {}", token(client));
        let app = app.clone();
        let identity = &identity;
        async move {
            support::request_with_headers(
                &app,
                identity,
                None,
                "POST",
                path,
                body,
                &[("authorization", auth)],
            )
            .await
        }
    };
    assert_eq!(call("other-worker", declaration.clone()).await.0, 403);
    assert_eq!(
        support::request(
            &app,
            &identity,
            Some("alice"),
            "POST",
            path,
            declaration.clone()
        )
        .await
        .0,
        403
    );
    assert_eq!(call("webdav-worker", declaration.clone()).await.0, 204);
    let (status, inventory) = support::request(
        &app,
        &identity,
        Some("alice"),
        "GET",
        &format!("/organizations/{}/capabilities", org.id),
        json!(null),
    )
    .await;
    assert_eq!(status, 200, "{inventory}");
    let source = inventory
        .as_array()
        .unwrap()
        .iter()
        .find(|source| source["source_id"] == "webdav")
        .unwrap();
    assert_eq!(
        source["capabilities"][0]["descriptor"]["kind"],
        "knowledge_base"
    );
    let mut stolen = declaration.clone();
    stolen["runtime_id"] = json!("other");
    assert_eq!(call("other-worker", stolen).await.0, 409);
    let list = format!("/spaces/{}/knowledge-base-definitions", team.id);
    assert_eq!(
        support::request(&app, &identity, Some("alice"), "GET", &list, json!(null))
            .await
            .1,
        json!([])
    );
    sqlx::query("insert into organization_capability(organization_id,source_id,capability_id,enabled_by) values($1,'webdav','knowledge-base:fred.webdav.folder','alice')").bind(org.id).execute(&e.pool).await.unwrap();
    let (status, available) =
        support::request(&app, &identity, Some("alice"), "GET", &list, json!(null)).await;
    assert_eq!(status, 200, "{available}");
    assert_eq!(available[0]["credential_bindings"], json!(["team-source"]));
    let org_list = format!("/spaces/{}/knowledge-base-definitions", org.id);
    assert_eq!(
        support::request(
            &app,
            &identity,
            Some("alice"),
            "GET",
            &org_list,
            json!(null)
        )
        .await
        .1[0]["credential_bindings"],
        json!([])
    );
    sqlx::query("insert into space_capability_policy(space_id,source_id,revision,restricted,updated_by) values($1,'webdav',1,true,'alice')").bind(team.id).execute(&e.pool).await.unwrap();
    assert_eq!(
        support::request(&app, &identity, Some("alice"), "GET", &list, json!(null))
            .await
            .1,
        json!([])
    );
    // Refreshing the agent catalog neither withdraws nor forges collector offers.
    control_plane::agents::catalog::replace(
        &mut e.pool.acquire().await.unwrap(),
        "webdav",
        &control_plane::agents::catalog::CatalogSnapshot {
            capabilities: vec![],
            template_capabilities: vec![],
        },
    )
    .await
    .unwrap();
    assert!(sqlx::query_scalar::<_,bool>("select advertised from capability_offer where source_id='webdav' and capability_id='knowledge-base:fred.webdav.folder'").fetch_one(&e.pool).await.unwrap());
}

#[tokio::test]
#[ignore = "needs Postgres: make test-integration"]
async fn knowledge_base_run_scope_is_immutable_and_one_active_per_instance() {
    let e = env().await;
    let (_, team) = org_and_team(&e).await;
    sqlx::query("insert into runtime_catalog(runtime_id,reachable) values('webdav',true)")
        .execute(&e.pool)
        .await
        .unwrap();
    sqlx::query("insert into capability_offer(source_id,capability_id,version,descriptor,advertised) values('webdav','knowledge-base:fred.webdav.folder','1','{}',true)").execute(&e.pool).await.unwrap();
    sqlx::query("insert into kb_definition(id,runtime_id,config_schema) values('fred.webdav.folder','webdav','{}')").execute(&e.pool).await.unwrap();
    let folder = Uuid::new_v4();
    let instance = Uuid::new_v4();
    let run = Uuid::new_v4();
    sqlx::query("insert into folder(id,space_id,name,path) values($1,$2,'Mirror',$3)")
        .bind(folder)
        .bind(team.id)
        .bind(format!("/{folder}/"))
        .execute(&e.pool)
        .await
        .unwrap();
    sqlx::query("insert into kb_instance(id,definition_id,space_id,folder_id,config,credential_refs,profile,created_by) values($1,'fred.webdav.folder',$2,$3,'{}','{}','medium','alice')").bind(instance).bind(team.id).bind(folder).execute(&e.pool).await.unwrap();
    let insert = "insert into kb_run(id,instance_id,runtime_id,definition_id,space_id,folder_id,config,credential_refs,profile,request_key,requested_by,workflow_id,task_queue) values($1,$2,'webdav','fred.webdav.folder',$3,$4,'{}','{}','medium',$5,'alice',$6,'queue')";
    sqlx::query(insert)
        .bind(run)
        .bind(instance)
        .bind(team.id)
        .bind(folder)
        .bind("first")
        .bind(run.to_string())
        .execute(&e.pool)
        .await
        .unwrap();
    let second = Uuid::new_v4();
    assert!(
        sqlx::query(insert)
            .bind(second)
            .bind(instance)
            .bind(team.id)
            .bind(folder)
            .bind("second")
            .bind(second.to_string())
            .execute(&e.pool)
            .await
            .is_err()
    );
    assert!(
        sqlx::query("update kb_run set config='{\"url\":\"changed\"}' where id=$1")
            .bind(run)
            .execute(&e.pool)
            .await
            .is_err()
    );
    sqlx::query("update kb_instance set paused=true where id=$1")
        .bind(instance)
        .execute(&e.pool)
        .await
        .unwrap();
    assert_eq!(
        sqlx::query_scalar::<_, String>("select state from kb_run where id=$1")
            .bind(run)
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        "pending"
    );
    sqlx::query("update kb_run set state='succeeded',completed_at=clock_timestamp(),result='{}' where id=$1").bind(run).execute(&e.pool).await.unwrap();
    assert!(
        sqlx::query("update kb_run set state='pending',completed_at=null where id=$1")
            .bind(run)
            .execute(&e.pool)
            .await
            .is_err()
    );
    assert!(db::folder(&e.pool, folder).await.is_ok());
}
