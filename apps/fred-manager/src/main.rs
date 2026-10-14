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

//! fred-manager CLI: serve, operator organization creation, authenticated provisioning.

use anyhow::{Context, Result};
use sqlx::postgres::PgPoolOptions;

use fred_manager::{
    api, auth, config::Configuration as Config, fga::Fga, ingestion, logging, spaces,
};

const USAGE: &str = "usage: fred-manager [serve | create-org <name> <admin-user> | import-provisioning <bundle.json> --token-file <path>]";

#[tokio::main]
async fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args == ["--help"] || args == ["-h"] {
        println!(
            "{USAGE}\nImport requires an operator bearer file and an initialized schema/model. Replay is additive."
        );
        return Ok(());
    }
    // Same rule as fred-pod: ENV_FILE, default ./config/.env, never overriding the process.
    let env_file = std::env::var("ENV_FILE").unwrap_or_else(|_| "./config/.env".into());
    let env_loaded = dotenvy::from_path(&env_file).is_ok();
    let (config_file, config) = Config::load().map_err(|error| {
        if args.first().is_some_and(|a| a == "import-provisioning") {
            import_setup_error(error)
        } else {
            error
        }
    })?;
    // Startup events wait for the configured format, as fred-pod buffers them.
    logging::init(&config.app.log_level, config.app.log_format).map_err(|error| {
        if args.first().is_some_and(|a| a == "import-provisioning") {
            import_setup_error(error)
        } else {
            error
        }
    })?;
    if env_loaded {
        tracing::info!(env_file, "Environment configuration loaded");
    } else {
        tracing::warn!(
            env_file,
            "Environment file unavailable; using process environment"
        );
    }
    tracing::info!(config_file, "Configuration loaded");
    let outcome = match args
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>()
        .as_slice()
    {
        [] | ["serve"] => serve(config).await,
        ["create-org", name, admin] => create_org(config, name, admin).await,
        ["import-provisioning", bundle, "--token-file", token] => {
            import(config, bundle, token).await
        }
        _ => Err(anyhow::anyhow!(USAGE)),
    };
    // Once logging runs, a fatal error is one more structured event, not stray stderr.
    if let Err(error) = outcome {
        tracing::error!(error = format!("{error:#}"), "fred-manager stopped");
        std::process::exit(1);
    }
    Ok(())
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
        directory: fred_manager::keycloak::Directory::configured(config.security.m2m.as_ref())?,
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
    let org = spaces::create_organization(&pool, &fga, name, admin)
        .await
        .map_err(|e| anyhow::anyhow!("{e}"))?;
    println!("{}", org.id);
    Ok(())
}

/// Authentication precedes all initialization. SQL/model verification is read-only;
/// neither the API server nor Temporal participates in a provisioning command.
async fn import(config: Config, bundle_file: &str, token_file: &str) -> Result<()> {
    use fred_manager::{
        db,
        keycloak::Directory,
        provisioning::{Bundle, Importer},
    };
    let prepared = async {
        let bearer = tokio::fs::read_to_string(token_file)
            .await
            .map_err(|_| anyhow::anyhow!("cannot read operator token file"))?;
        let auth = auth::Authenticator::start(config.security()?).await?;
        let directory = Directory::configured(config.security.m2m.as_ref())?
            .context("import requires configured Keycloak service credentials")?;
        anyhow::ensure!(
            auth.directory_subjects_match(directory.realm()),
            "import requires enabled Keycloak subject authentication in the directory realm"
        );
        let caller = auth
            .authenticate(Some(bearer.trim()))
            .await
            .map_err(|_| anyhow::anyhow!("invalid or expired operator bearer"))?;
        let rebac = &config.security.rebac;
        let fga = Fga::connect(
            &rebac.api_url,
            &rebac.store_name,
            false,
            false,
            config.fga_token(),
            config.fga_timeout(),
        )
        .await?
        .require_compatible_model()
        .await?;
        anyhow::ensure!(
            fga.is_platform_admin(&caller.uid).await?,
            "import requires platform admin"
        );
        let pool = PgPoolOptions::new()
            .max_connections(2)
            .connect_with(config.postgres()?)
            .await
            .map_err(|_| anyhow::anyhow!("import database unavailable"))?;
        db::require_initialized(&pool).await.map_err(|_| {
            anyhow::anyhow!(
                "initialize the compatible fred-manager schema with serve before import"
            )
        })?;
        let bytes = tokio::fs::read(bundle_file)
            .await
            .map_err(|_| anyhow::anyhow!("cannot read provisioning bundle"))?;
        let bundle = Bundle::parse(&bytes)?;
        Ok::<_, anyhow::Error>((pool, fga, directory, auth, bearer, bundle))
    }
    .await;
    let (pool, fga, directory, auth, bearer, bundle) = prepared.map_err(import_setup_error)?;
    let report = Importer {
        pool: &pool,
        fga: &fga,
        directory: &directory,
        auth: &auth,
        bearer: bearer.trim(),
    }
    .run(&bundle)
    .await?;
    println!("{}", serde_json::to_string(&report)?);
    Ok(())
}

/// A setup failure has no provisioning effects. Keep dependency/configuration payloads
/// out of the error chain while retaining actionable, known-static validation reasons.
fn import_setup_error(error: anyhow::Error) -> anyhow::Error {
    let message = error.to_string();
    let reason = match message.as_str() {
        "cannot read operator token file"
        | "cannot read provisioning bundle"
        | "invalid or expired operator bearer"
        | "import requires platform admin"
        | "import requires configured Keycloak service credentials"
        | "import requires enabled Keycloak subject authentication in the directory realm"
        | "import database unavailable"
        | "initialize the compatible fred-manager schema with serve before import"
        | "initialize fred-manager with serve before import"
        | "initialize the compatible fred-manager model with serve before import"
        | "invalid provisioning JSON or unknown field"
        | "organization name must be nonempty"
        | "organization admins must be nonempty"
        | "username must be nonempty"
        | "duplicate username"
        | "team name must be nonempty"
        | "unknown or non-assignable team role"
        | "unknown or non-assignable platform role"
        | "organization admin must name a bundle user" => message.as_str(),
        _ => "configuration or dependency validation failed",
    };
    anyhow::anyhow!(
        "provisioning initialization/validation failed: {reason}; {}; no provisioning writes; correct the cause and replay",
        fred_manager::provisioning::Report::default()
    )
}
