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

use fred_manager::{api, auth, config::Configuration as Config, fga::Fga, logging, spaces};

const USAGE: &str = "usage: fred-manager [serve | worker | migrate | generate-openapi | generate-config-schema | create-org <name> <admin-user> | import-provisioning <bundle.zip> --token-file <path>]";

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
            serde_json::to_string_pretty(&fred_manager::processing::models::schema())?
        );
        return Ok(());
    }
    if args == ["generate-config-schema"] {
        println!(
            "{}",
            serde_json::to_string_pretty(&fred_manager::config::schema())?
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
    // Startup events wait for the configured format, as fred-pod buffers them.
    logging::init_role(
        &config.app.log_level,
        config.app.log_format,
        if args == ["worker"] {
            logging::ServiceRole::Worker
        } else {
            logging::ServiceRole::Api
        },
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
        ["worker"] => worker(config).await,
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
        false,
        config.fga_token(),
        config.fga_timeout(),
    )
    .await
}

async fn serve(config: Config) -> Result<()> {
    let pool = pool(&config).await?;
    let fga = if config.security.rebac.sync_schema_on_init {
        fga(&config).await?.initialize(&pool).await?
    } else {
        fga(&config).await?.load(&pool).await?
    };
    let content = if let Some(content) = config.storage.content.clone() {
        let access =
            std::env::var(&content.access_key_env_var).context("missing content access key")?;
        let secret =
            std::env::var(&content.secret_key_env_var).context("missing content secret key")?;
        Some(
            fred_manager::documents::Storage::start(
                &pool,
                &fga,
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
    let cleanup = content.clone().map(|storage| {
        tokio::spawn(async move {
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
        })
    });
    let processing = match (&config.scheduler.processing, &content) {
        (Some(settings), Some(originals)) => Some(
            fred_manager::processing::Processing::configured(
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
        processing,
        content,
        directory: fred_manager::keycloak::Directory::configured(config.security.m2m.as_ref())?,
        auth: std::sync::Arc::new(auth::Authenticator::start(config.security()?).await?),
        pool,
        fga,
        onboarding: (&config).into(),
        lifecycle: fred_manager::lifecycle::Lifecycle {
            config: config.scheduler.lifecycle.clone(),
            catalog: fred_manager::lifecycle::policy::Catalog::load(
                config.policies.purge_catalog_path.as_deref(),
            )?,
        },
    };
    let addr = config.listen_addr();
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    tracing::info!(addr, "fred-manager listening");
    let app = api::router(
        state,
        &config.app.base_url,
        &config.security.authorized_origins,
    );
    let result = axum::serve(listener, app).await;
    if let Some(cleanup) = cleanup {
        cleanup.abort();
    }
    result?;
    Ok(())
}

/// Operator creation retains the historical combined owner/admin/member assignment.
async fn create_org(config: Config, name: &str, admin: &str) -> Result<()> {
    let directory = fred_manager::keycloak::Directory::configured(config.security.m2m.as_ref())?
        .context("organization creation requires configured Keycloak service credentials")?;
    let auth = auth::Authenticator::start(config.security()?).await?;
    anyhow::ensure!(
        auth.directory_subjects_match(directory.realm()),
        "organization creation requires Keycloak subject mapping in the directory realm"
    );
    anyhow::ensure!(
        directory.exists(admin).await?,
        "organization owner does not exist in Keycloak"
    );
    let pool = pool(&config).await?;
    let fga = fga(&config).await?.load(&pool).await?;
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
        fred_manager::onboarding::require_accepted(
            &pool,
            config.app.gcu_version.as_deref(),
            &caller.uid,
        )
        .await?;
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
        .load(&pool)
        .await?;
        anyhow::ensure!(
            fga.is_platform_owner(&caller.uid).await?,
            "import requires platform owner"
        );
        use tokio::io::AsyncReadExt;
        let file = tokio::fs::File::open(bundle_file)
            .await
            .map_err(|_| anyhow::anyhow!("cannot read provisioning bundle"))?;
        let mut bytes = Vec::new();
        file.take(fred_manager::blueprint::MAX_ARCHIVE as u64 + 1)
            .read_to_end(&mut bytes)
            .await
            .map_err(|_| anyhow::anyhow!("cannot read provisioning bundle"))?;
        let bundle = tokio::task::spawn_blocking(move || Bundle::parse(&bytes)).await??;
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
        | "user_not_accept_gcu"
        | "import requires platform owner"
        | "import requires configured Keycloak service credentials"
        | "import requires enabled Keycloak subject authentication in the directory realm"
        | "import database unavailable"
        | "initialize the compatible fred-manager schema with serve before import"
        | "initialize fred-manager with serve before import"
        | "initialize the compatible fred-manager model with serve before import"
        | "not_yet_supported"
        | "invalid provisioning ZIP or declaration"
        | "provisioning bundle exceeds size limit" => message.as_str(),
        _ => "configuration or dependency validation failed",
    };
    anyhow::anyhow!(
        "provisioning initialization/validation failed: {reason}; {}; no provisioning writes; correct the cause and replay",
        fred_manager::provisioning::Report::default()
    )
}

async fn worker(config: Config) -> Result<()> {
    let pool = PgPoolOptions::new()
        .max_connections(10)
        .connect_with(
            config
                .postgres()?
                .options([("lock_timeout", "5000"), ("statement_timeout", "45000")]),
        )
        .await
        .context("worker postgres unavailable")?;
    fred_manager::db::require_initialized(&pool).await?;
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
    .load(&pool)
    .await?;
    fred_manager::lifecycle::policy::Catalog::load(config.policies.purge_catalog_path.as_deref())?;
    let listen = config.listen_addr();
    let mut dispatch = tokio::spawn({
        let pool = pool.clone();
        async move {
            if let Some(settings) = config.scheduler.processing {
                fred_manager::processing::dispatch::run(pool, settings).await;
            } else {
                std::future::pending::<()>().await;
            }
        }
    });
    let listener = tokio::net::TcpListener::bind(&listen).await?;
    let mut health = tokio::spawn(async move {
        axum::serve(
            listener,
            axum::Router::new().route("/healthz", axum::routing::get(|| async { "ok" })),
        )
        .await
    });
    let result = loop {
        let lifecycle = tokio::select! {
            result = fred_manager::lifecycle::worker::run(pool.clone(), fga.clone(), config.scheduler.lifecycle.clone()) => result,
            _ = &mut dispatch => break Err(anyhow::anyhow!("processing dispatcher stopped")),
            _ = &mut health => break Err(anyhow::anyhow!("worker health listener stopped")),
        };
        match lifecycle {
            Ok(()) => break Ok(()),
            Err(_) => tracing::warn!(
                error_code = "lifecycle_retry",
                "Lifecycle worker will reconnect"
            ),
        }
        tokio::select! {
            _ = tokio::time::sleep(std::time::Duration::from_secs(5)) => {},
            _ = worker_shutdown() => break Ok(()),
            _ = &mut dispatch => break Err(anyhow::anyhow!("processing dispatcher stopped")),
            _ = &mut health => break Err(anyhow::anyhow!("worker health listener stopped")),
        }
    };
    health.abort();
    dispatch.abort();
    result
}

async fn worker_shutdown() {
    let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        .expect("signal handler");
    tokio::select! {_=tokio::signal::ctrl_c()=>{},_=term.recv()=>{}}
}
