// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Browser acceptance of the real manager HTTP handlers and Keycloak login.
//! No control-plane route or prepared root role participates in this journey.
use control_plane::{api, auth::Authenticator, config::Configuration, keycloak::Directory};
use std::{path::PathBuf, sync::Arc, time::Duration};

#[allow(dead_code)]
#[path = "support/environment.rs"]
mod environment;
use environment::named_space;
#[path = "support/browser_resources.rs"]
mod browser_resources;
#[allow(dead_code)]
#[path = "support/content_bucket.rs"]
mod content_bucket;
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
    config.app.bootstrap_token_env_var = Some("CONTROL_PLANE_TEST_BOOTSTRAP_TOKEN".into());
    let auth = Arc::new(
        Authenticator::start(config.security().unwrap())
            .await
            .unwrap(),
    );
    let directory = Directory::new(&realm, "control-plane", "it-manager".into()).unwrap();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let manager_url = format!("http://{}", listener.local_addr().unwrap());
    let bucket = content_bucket::Bucket::start().await;
    let spool = tempfile::tempdir().unwrap();
    let mut storage_config = bucket.config.clone();
    storage_config.temp_dir = spool.path().to_str().unwrap().into();
    let content = control_plane::documents::Storage::start(
        &e.pool,
        &e.fga,
        config.app.gcu_version.clone(),
        storage_config,
        "fixture-access".into(),
        "fixture-secret".into(),
    )
    .await
    .unwrap();
    let app = api::router(
        api::AppState {
            agent_catalog: Default::default(),
            onboarding: (&config).into(),
            lifecycle: Default::default(),
            auth,
            pool: e.pool.clone(),
            fga: e.fga.clone(),
            directory: Some(directory.clone()),
            content: Some(content),
            processing: None,
        },
        "/control-plane/v1",
        &[],
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
        Duration::from_secs(480),
        tokio::process::Command::new("node")
            .arg("tests/provisioning-browser.mjs")
            .current_dir("../frontend")
            .env("CONTROL_PLANE_BROWSER_URL", &manager_url)
            .env("CONTROL_PLANE_BROWSER_REALM", &realm)
            .env("CONTROL_PLANE_BROWSER_PORT", port.to_string())
            .env("CONTROL_PLANE_BROWSER_BUNDLE", &bundle)
            .kill_on_drop(true)
            .output(),
    )
    .await
    .expect("browser test exceeded eight minutes")
    .unwrap();
    server.abort();
    if !output.status.success() {
        let uploads: Vec<(String, i64, Option<String>)> =
            sqlx::query_as("select status, size, error_code from document_upload")
                .fetch_all(&e.pool)
                .await
                .unwrap();
        eprintln!("Browser fixture upload states: {uploads:?}");
        let keys: Vec<String> = sqlx::query_scalar("select object_key from document_upload")
            .fetch_all(&e.pool)
            .await
            .unwrap();
        for key in keys {
            let object = bucket
                .client
                .head_object()
                .bucket("originals")
                .key(key)
                .send()
                .await;
            eprintln!(
                "Browser fixture stored object length: {:?}",
                object.ok().and_then(|o| o.content_length())
            );
        }
    }
    // Script output contains assertions only; no tokens or browser storage are emitted.
    assert!(
        output.status.success(),
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    println!("{}", String::from_utf8_lossy(&output.stdout));
    if std::env::var("CONTROL_PLANE_BROWSER_DOCUMENTS_ONLY").as_deref() == Ok("1") {
        assert_eq!(
            sqlx::query_scalar::<_, i64>("select count(*) from document")
                .fetch_one(&e.pool)
                .await
                .unwrap(),
            2
        );
        return;
    }
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
            .check(
                &sophia.id,
                control_plane::domain::Permission::Read,
                north.id
            )
            .await
            .unwrap()
    );
}
