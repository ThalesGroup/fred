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

//! control-plane CLI: serve, migrations, authenticated provisioning.

use anyhow::{Context, Result};
use futures::{FutureExt, StreamExt, future::LocalBoxFuture, stream::FuturesUnordered};
use sqlx::postgres::PgPoolOptions;

use control_plane::{
    api, auth, authorization::Authorization, config::Configuration as Config, logging,
};

const USAGE: &str = "usage: control-plane [serve | discover-agents | migrate | generate-openapi | generate-config-schema | processing-schema | import-provisioning <bundle.zip> --token-file <path>]";

#[tokio::main]
async fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args == ["--help"] || args == ["-h"] {
        println!(
            "{USAGE}\nImport requires an operator bearer file and an initialized schema/model. Replay is additive."
        );
        return Ok(());
    }
    // Contract generation never loads secrets or initializes service dependencies.
    if args == ["generate-openapi"] {
        println!("{}", serde_json::to_string_pretty(&api::openapi())?);
        return Ok(());
    }
    if args == ["processing-schema"] {
        println!(
            "{}",
            serde_json::to_string_pretty(&control_plane::processing::models::schema())?
        );
        return Ok(());
    }
    if args == ["generate-config-schema"] {
        println!(
            "{}",
            serde_json::to_string_pretty(&control_plane::config::schema())?
        );
        return Ok(());
    }
    // Helm's pre-install Job has only DATABASE_URL; release config and identities do not exist yet.
    if args == ["migrate"] {
        let url = std::env::var("DATABASE_URL").context("DATABASE_URL is required")?;
        let url = match url.strip_prefix("postgresql+asyncpg://") {
            Some(rest) => format!("postgresql://{rest}"),
            None => url,
        };
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .connect(&url)
            .await
            .map_err(|_| anyhow::anyhow!("migration database connection failed"))?;
        sqlx::migrate!()
            .run(&pool)
            .await
            .map_err(|_| anyhow::anyhow!("manager SQL migration failed"))?;
        println!("Manager SQL migrations completed");
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
    // Operator discovery prints only JSON and does not initialize SQL or HTTP.
    if args == ["discover-agents"] {
        let catalogs = control_plane::agents::discover(&config.platform).await?;
        println!("{}", serde_json::to_string_pretty(&catalogs)?);
        return Ok(());
    }
    // Startup events wait for the configured format, as fred-pod buffers them.
    logging::init_role(
        &config.app.log_level,
        config.app.log_format,
        logging::ServiceRole::Api,
    )
    .map_err(|error| {
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
        ["import-provisioning", bundle, "--token-file", token] => {
            import(config, bundle, token).await
        }
        _ => Err(anyhow::anyhow!(USAGE)),
    };
    // Once logging runs, a fatal error is one more structured event, not stray stderr.
    if let Err(error) = outcome {
        tracing::error!(error = format!("{error:#}"), "control-plane stopped");
        std::process::exit(1);
    }
    Ok(())
}

async fn pool(config: &Config) -> Result<sqlx::PgPool> {
    let pool = PgPoolOptions::new()
        .max_connections(10)
        .connect_with(
            config
                .postgres()?
                .options([("lock_timeout", "5000"), ("statement_timeout", "45000")]),
        )
        .await
        .context("postgres unreachable")?;
    control_plane::db::require_initialized(&pool).await.context(
        "database schema does not match this control-plane binary; apply pending migrations with the deployment Job or `control-plane migrate` before starting the API; if history or checksums differ, inspect them without rewriting applied migrations",
    )?;
    Ok(pool)
}

async fn serve(config: Config) -> Result<()> {
    let pool = pool(&config).await?;
    control_plane::model_catalog::configure_sources(&pool, &config.platform.model_sources).await?;
    let authorization = Authorization::new(pool.clone());
    let content = if let Some(content) = config.storage.content.clone() {
        let access =
            std::env::var(&content.access_key_env_var).context("missing content access key")?;
        let secret =
            std::env::var(&content.secret_key_env_var).context("missing content secret key")?;
        Some(
            control_plane::documents::Storage::start(
                &pool,
                &authorization,
                config
                    .app
                    .gcu_version
                    .clone()
                    .filter(|_| config.security.user.enabled),
                content,
                access,
                secret,
            )
            .await?,
        )
    } else {
        None
    };
    let processing = match (&config.scheduler.processing, &content) {
        (Some(settings), Some(originals)) => Some(
            control_plane::processing::Processing::configured(
                settings.clone(),
                originals.clone(),
                config.security()?,
            )
            .await?,
        ),
        (Some(_), None) => anyhow::bail!("processing requires original storage"),
        _ => None,
    };
    let state = api::AppState {
        agent_catalog: config.platform.clone(),
        processing,
        content: content.clone(),
        directory: if config.security.user_directory == control_plane::users::DirectoryKind::Local {
            None
        } else {
            control_plane::keycloak::Directory::configured(config.security.m2m.as_ref())?
        },
        auth: std::sync::Arc::new(auth::Authenticator::start(config.security()?).await?),
        pool: pool.clone(),
        authorization: authorization.clone(),
        onboarding: (&config).into(),
        lifecycle: control_plane::lifecycle::Lifecycle {
            config: config.scheduler.lifecycle.clone(),
            catalog: control_plane::lifecycle::policy::Catalog::load(
                config.policies.purge_catalog_path.as_deref(),
            )?,
        },
    };
    let addr = config.listen_addr();
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    tracing::info!(addr, "control-plane listening");
    let app = api::router(
        state,
        &config.app.base_url,
        &config.security.authorized_origins,
    );
    // One process owns HTTP and durable background work. A stopped task fails
    // the process; SQL requests and Temporal history survive its restart.
    let (stop, mut stopped) = tokio::sync::watch::channel(());
    let stopping = async move {
        let _ = stopped.changed().await;
    }
    .shared();
    // Temporal's workflow runner is a local future; poll it alongside the others.
    let mut tasks = FuturesUnordered::<LocalBoxFuture<'static, Result<()>>>::new();
    tasks.push(Box::pin({
        let stopping = stopping.clone();
        async move {
            axum::serve(listener, app)
                .with_graceful_shutdown(stopping)
                .await
                .context("HTTP server stopped")
        }
    }));
    if let Some(storage) = content {
        let stopping = stopping.clone();
        tasks.push(Box::pin(async move {
            let cleanup = async {
                let mut interval = tokio::time::interval(std::time::Duration::from_secs(
                    storage.config.limits.cleanup_interval_seconds,
                ));
                interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
                loop {
                    interval.tick().await;
                    if storage.cleanup_tick().await.is_err() {
                        tracing::warn!(
                            outcome = "retry",
                            "document cleanup interrupted; retrying on next interval"
                        );
                    }
                }
            };
            tokio::select! {
                _ = stopping => Ok(()),
                _ = cleanup => anyhow::bail!("document cleanup stopped"),
            }
        }));
    }
    if let Some(settings) = config.scheduler.processing {
        let pool = pool.clone();
        let stopping = stopping.clone();
        tasks.push(Box::pin(async move {
            tokio::select! {
                _ = stopping => Ok(()),
                _ = control_plane::processing::dispatch::run(pool, settings) => {
                    anyhow::bail!("processing dispatcher stopped")
                }
            }
        }));
    }
    tasks.push(Box::pin(async move {
        loop {
            match control_plane::lifecycle::worker::run(
                pool.clone(),
                config.scheduler.lifecycle.clone(),
                stopping.clone(),
            )
            .await
            {
                Ok(()) => return Ok(()),
                Err(error) => tracing::warn!(
                    error_code = "lifecycle_retry",
                    stage = control_plane::lifecycle::worker::stage(&error),
                    "Lifecycle worker will reconnect"
                ),
            }
            tokio::select! {
                _ = stopping.clone() => return Ok(()),
                _ = tokio::time::sleep(std::time::Duration::from_secs(5)) => {},
            }
        }
    }));
    let result = tokio::select! {
        _ = shutdown_signal() => Ok(()),
        task = tasks.next() => match task {
            Some(Err(error)) => Err(error),
            _ => Err(anyhow::anyhow!("manager task stopped unexpectedly")),
        },
    };
    let _ = stop.send(());
    let drain = async { while tasks.next().await.is_some() {} };
    if tokio::time::timeout(std::time::Duration::from_secs(25), drain)
        .await
        .is_err()
    {
        tracing::warn!("Manager shutdown deadline reached; cancelling remaining tasks");
    }
    result
}

/// Authentication precedes all initialization. SQL/model verification is read-only;
/// neither the API server nor Temporal participates in a provisioning command.
async fn import(config: Config, bundle_file: &str, token_file: &str) -> Result<()> {
    use control_plane::{
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
        let pool = PgPoolOptions::new()
            .max_connections(2)
            .connect_with(config.postgres()?)
            .await
            .map_err(|_| anyhow::anyhow!("import database unavailable"))?;
        db::require_initialized(&pool).await.map_err(|_| {
            anyhow::anyhow!(
                "initialize the compatible control-plane schema with migrate before import"
            )
        })?;
        control_plane::onboarding::require_accepted(
            &pool,
            config.app.gcu_version.as_deref(),
            &caller.uid,
        )
        .await?;
        let authorization = Authorization::new(pool.clone());
        anyhow::ensure!(
            authorization.is_platform_admin(&caller.uid).await?,
            "import requires platform admin"
        );
        use tokio::io::AsyncReadExt;
        let file = tokio::fs::File::open(bundle_file)
            .await
            .map_err(|_| anyhow::anyhow!("cannot read provisioning bundle"))?;
        let mut bytes = Vec::new();
        file.take(control_plane::blueprint::MAX_ARCHIVE as u64 + 1)
            .read_to_end(&mut bytes)
            .await
            .map_err(|_| anyhow::anyhow!("cannot read provisioning bundle"))?;
        let bundle = tokio::task::spawn_blocking(move || Bundle::parse(&bytes)).await??;
        Ok::<_, anyhow::Error>((pool, authorization, directory, caller.uid, bundle))
    }
    .await;
    let (pool, authorization, directory, operator, bundle) =
        prepared.map_err(import_setup_error)?;
    let report = Importer {
        pool: &pool,
        authorization: &authorization,
        directory: &directory,
        operator: &operator,
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
        | "user_not_accept_gcu"
        | "import requires platform admin"
        | "import requires configured Keycloak service credentials"
        | "import requires enabled Keycloak subject authentication in the directory realm"
        | "import database unavailable"
        | "initialize the compatible control-plane schema with migrate before import"
        | "initialize control-plane with serve before import"
        | "initialize the compatible control-plane model with serve before import"
        | "not_yet_supported"
        | "invalid provisioning ZIP or declaration"
        | "provisioning bundle exceeds size limit" => message.as_str(),
        _ => "configuration or dependency validation failed",
    };
    anyhow::anyhow!(
        "provisioning initialization/validation failed: {reason}; {}; no provisioning writes; correct the cause and replay",
        control_plane::provisioning::Report::default()
    )
}

async fn shutdown_signal() {
    let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        .expect("signal handler");
    tokio::select! {_=tokio::signal::ctrl_c()=>{},_=term.recv()=>{}}
}
