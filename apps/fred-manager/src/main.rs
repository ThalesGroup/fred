//! fred-manager: ownership of spaces, folders and documents, their authorization,
//! and submission of ingestion work to the Python workers.

mod api;
mod auth;
mod bootstrap;
mod config;
mod db;
mod domain;
mod error;
mod fga;
mod ingestion;

use anyhow::{Context, Result, bail};
use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

use crate::{
    config::Configuration as Config,
    domain::{Role, Space, SpaceKind},
    fga::{Fga, Tuple},
};

const USAGE: &str = "usage: fred-manager [serve | create-org <name> <admin-user>]";

#[tokio::main]
async fn main() -> Result<()> {
    // Same rule as fred-pod: ENV_FILE, default ./config/.env, never overriding the process.
    let env_file = std::env::var("ENV_FILE").unwrap_or_else(|_| "./config/.env".into());
    let env_loaded = dotenvy::from_path(&env_file).is_ok();
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();
    if env_loaded {
        tracing::info!(env_file, "Environment configuration loaded");
    } else {
        tracing::warn!(
            env_file,
            "Environment file unavailable; using process environment"
        );
    }
    let args: Vec<String> = std::env::args().skip(1).collect();
    let (config_file, config) = Config::load()?;
    tracing::info!(config_file, "Configuration loaded");
    match args
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>()
        .as_slice()
    {
        [] | ["serve"] => serve(config).await,
        ["create-org", name, admin] => create_org(config, name, admin).await,
        _ => bail!(USAGE),
    }
}

async fn pool(config: &Config) -> Result<sqlx::PgPool> {
    let pool = PgPoolOptions::new()
        .max_connections(10)
        .connect_with(config.postgres()?)
        .await
        .context("postgres unreachable")?;
    sqlx::migrate!().run(&pool).await?;
    Ok(pool)
}

async fn fga(config: &Config) -> Result<Fga> {
    let rebac = &config.security.rebac;
    Fga::connect(
        &rebac.api_url,
        &rebac.store_name,
        rebac.create_store_if_needed,
        rebac.sync_schema_on_init,
        config.fga_token(),
        config.fga_timeout(),
    )
    .await
}

async fn serve(config: Config) -> Result<()> {
    let state = api::AppState {
        auth: std::sync::Arc::new(auth::Authenticator::start(config.security()?).await?),
        pool: pool(&config).await?,
        fga: fga(&config).await?,
        bootstrap_token_env_var: config.app.bootstrap_token_env_var.clone(),
        ingestion: ingestion::Ingestion::connect(
            &config.temporal_url(),
            &config.scheduler.temporal.namespace,
            &config.scheduler.temporal.task_queue,
        )
        .await?,
    };
    let addr = config.listen_addr();
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    tracing::info!(addr, "fred-manager listening");
    let app = api::router(
        state,
        &config.app.base_url,
        &config.security.authorized_origins,
    );
    axum::serve(listener, app).await?;
    Ok(())
}

/// Organizations are created by an operator, not through the API.
async fn create_org(config: Config, name: &str, admin: &str) -> Result<()> {
    let pool = pool(&config).await?;
    let fga = fga(&config).await?;
    let id = Uuid::new_v4();
    let org = Space {
        id,
        kind: SpaceKind::Organization,
        name: name.to_string(),
        parent_id: None,
        personal_owner: None,
        path: vec![id],
    };
    let tuples = [
        Tuple {
            user: admin,
            role: Role::Admin,
            space: id,
        },
        Tuple {
            user: admin,
            role: Role::Member,
            space: id,
        },
    ];
    api::persist_space_with(&pool, &fga, &org, &tuples)
        .await
        .map_err(|e| anyhow::anyhow!("{e}"))?;
    println!("{id}");
    Ok(())
}
