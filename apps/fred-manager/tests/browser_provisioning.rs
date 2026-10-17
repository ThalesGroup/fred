// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Browser acceptance of the real manager HTTP handlers and Keycloak login.
//! No control-plane route or prepared root role participates in this journey.
use fred_manager::{api, auth::Authenticator, config::Configuration, keycloak::Directory};
use std::{path::PathBuf, sync::Arc, time::Duration};

#[allow(dead_code)]
#[path = "support/environment.rs"]
mod environment;
use environment::named_space;
#[path = "support/browser_resources.rs"]
mod browser_resources;
#[path = "support/real_keycloak.rs"]
mod real_keycloak;

struct Workspace(PathBuf);
impl Drop for Workspace {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

// Proves: I1, I4, I8, I17, I18, I19
#[tokio::test]
#[ignore = "needs disposable services, frontend dependencies and Chromium: make test-browser"]
async fn provisioning_browser_journey() {
    let e = environment::env().await;
    let kc = real_keycloak::Keycloak::start().await;
    let realm = kc.configure().await;
    let mut config: Configuration =
        serde_yaml_ng::from_str(include_str!("../config/configuration.yaml")).unwrap();
    config.security.user.realm_url = realm.clone();
    config.security.m2m = None;
    config.app.bootstrap_token_env_var = Some("FRED_MANAGER_TEST_BOOTSTRAP_TOKEN".into());
    let auth = Arc::new(
        Authenticator::start(config.security().unwrap())
            .await
            .unwrap(),
    );
    let directory = Directory::new(&realm, "fred-manager", "it-manager".into()).unwrap();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let manager_url = format!("http://{}", listener.local_addr().unwrap());
    let app = axum::Router::new()
        .nest(
            "/fred-manager/v1",
            api::governance_router(api::AppState {
                onboarding: (&config).into(),
                lifecycle: Default::default(),
                auth,
                pool: e.pool.clone(),
                fga: e.fga.clone(),
                directory: Some(directory.clone()),
            }),
        )
        .merge(browser_resources::router(
            e.pool.clone(),
            e.fga.clone(),
            directory.clone(),
        ));
    let server = tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    let port = std::net::TcpListener::bind("127.0.0.1:0")
        .unwrap()
        .local_addr()
        .unwrap()
        .port();
    kc.allow_browser(&format!("http://127.0.0.1:{port}")).await;
    let workspace = Workspace(
        std::env::current_dir()
            .unwrap()
            .join("target")
            .join(format!("browser-{}", uuid::Uuid::new_v4())),
    );
    std::fs::create_dir_all(&workspace.0).unwrap();
    let bundle = workspace.0.join("demo.zip");
    assert!(
        tokio::process::Command::new("make")
            .arg("build-demo-bundle")
            .env("DEMO_BUNDLE_FILE", &bundle)
            .status()
            .await
            .unwrap()
            .success()
    );
    let output = tokio::time::timeout(
        Duration::from_secs(300),
        tokio::process::Command::new("node")
            .arg("tests/provisioning-browser.mjs")
            .current_dir("../frontend")
            .env("FRED_MANAGER_BROWSER_URL", &manager_url)
            .env("FRED_MANAGER_BROWSER_REALM", &realm)
            .env("FRED_MANAGER_BROWSER_PORT", port.to_string())
            .env("FRED_MANAGER_BROWSER_BUNDLE", &bundle)
            .kill_on_drop(true)
            .output(),
    )
    .await
    .expect("browser test exceeded five minutes")
    .unwrap();
    server.abort();
    // Script output contains assertions only; no tokens or browser storage are emitted.
    assert!(
        output.status.success(),
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    println!("{}", String::from_utf8_lossy(&output.stdout));
    let org = named_space(&e.pool, &e.fga, None, "Demo")
        .await
        .unwrap()
        .unwrap();
    let north = named_space(&e.pool, &e.fga, Some(org.id), "northbridge")
        .await
        .unwrap()
        .unwrap();
    let project = named_space(&e.pool, &e.fga, Some(north.id), "Browser project")
        .await
        .unwrap()
        .unwrap();
    assert_eq!(project.path, vec![org.id, north.id, project.id]);
    assert_eq!(
        sqlx::query_scalar::<_, i64>("select count(*) from space")
            .fetch_one(&e.pool)
            .await
            .unwrap(),
        6
    );
    let sophia = directory.find_username("sophia").await.unwrap().unwrap();
    assert!(
        !e.fga
            .check(&sophia.id, fred_manager::domain::Permission::Read, north.id)
            .await
            .unwrap()
    );
}
