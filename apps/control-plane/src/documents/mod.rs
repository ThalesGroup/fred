// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Original storage and upload recovery, with optional atomic processing intent.
mod cleanup;
pub mod config;
pub mod http;
pub mod models;
pub mod object_store;
mod reads;
mod upload;

use crate::{
    authorization::Authorization,
    domain::{Space, SpaceKind},
    error::{AppError, AppResult},
};
use anyhow::{Context, Result, ensure};
use axum::http::StatusCode;
use config::ContentConfig;
use object_store::ObjectStore;
use sqlx::{PgPool, Postgres, Transaction};
use std::{sync::Arc, time::Duration};
use tokio::sync::Semaphore;
use uuid::Uuid;

/// Drive mutations require a space writer; attachments require their live conversation's owner.
pub(crate) async fn authorized_mutation(
    pool: &PgPool,
    actor: &str,
    space_id: Uuid,
    session_id: Option<Uuid>,
) -> AppResult<Transaction<'static, Postgres>> {
    match session_id {
        Some(session) => crate::sessions::lock_owner(pool, actor, space_id, session).await,
        None => crate::spaces::authorized_write(pool, actor, space_id).await,
    }
}

pub struct Storage {
    pub(crate) pool: PgPool,
    pub(crate) authorization: Authorization,
    pub(crate) terms: Option<String>,
    pub config: ContentConfig,
    pub objects: ObjectStore,
    pub(crate) prefix: String,
    pub(crate) uploads: Arc<Semaphore>,
    pub(crate) downloads: Arc<Semaphore>,
    pub(crate) temp: tempfile::TempDir,
    _temp_lock: std::fs::File,
}

impl Storage {
    /// Initialize the namespace before serving; a fresh database never adopts old keys.
    pub async fn start(
        pool: &PgPool,
        authorization: &Authorization,
        terms: Option<String>,
        config: ContentConfig,
        access: String,
        secret: String,
    ) -> Result<Arc<Self>> {
        config.validate()?;
        let objects = ObjectStore::new(&config, access, secret)?;
        objects.validate_bucket().await?;
        sqlx::query("insert into document_storage(singleton,namespace,endpoint,bucket,prefix) values (true,$1,$2,$3,$4) on conflict do nothing")
            .bind(Uuid::new_v4()).bind(&config.endpoint).bind(&config.bucket).bind(&config.prefix).execute(pool).await?;
        let (namespace, endpoint, bucket, prefix): (Uuid, String, String, String) = sqlx::query_as(
            "select namespace,endpoint,bucket,prefix from document_storage where singleton",
        )
        .fetch_one(pool)
        .await?;
        ensure!(
            endpoint == config.endpoint && bucket == config.bucket && prefix == config.prefix,
            "content storage configuration does not match the database namespace"
        );
        let temp_root = std::path::Path::new(&config.temp_dir).join("private");
        let (temp, lock) = tokio::task::spawn_blocking(move || -> Result<_> {
            use std::os::unix::fs::PermissionsExt;
            std::fs::create_dir_all(&temp_root)?;
            ensure!(
                !std::fs::symlink_metadata(&temp_root)?
                    .file_type()
                    .is_symlink(),
                "content temp directory cannot be a symlink"
            );
            std::fs::set_permissions(&temp_root, std::fs::Permissions::from_mode(0o700))?;
            let setup = std::fs::OpenOptions::new()
                .create(true)
                .truncate(false)
                .read(true)
                .write(true)
                .open(std::path::Path::new(&temp_root).join("startup.lock"))?;
            setup.lock()?;
            for entry in std::fs::read_dir(&temp_root)? {
                let entry = entry?;
                if !entry.file_name().to_string_lossy().starts_with("replica-")
                    || !entry.file_type()?.is_dir()
                {
                    continue;
                }
                match std::fs::OpenOptions::new()
                    .read(true)
                    .write(true)
                    .open(entry.path().join("lease"))
                {
                    Ok(file) if file.try_lock().is_ok() => std::fs::remove_dir_all(entry.path())?,
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                        std::fs::remove_dir_all(entry.path())?
                    }
                    Err(error) => return Err(error.into()),
                    _ => {}
                }
            }
            let dir = tempfile::Builder::new()
                .prefix("replica-")
                .tempdir_in(&temp_root)?;
            let lock = std::fs::File::create(dir.path().join("lease"))?;
            lock.lock()?;
            Ok((dir, lock))
        })
        .await
        .context("content spool initialization failed")??;
        Ok(Arc::new(Self {
            pool: pool.clone(),
            authorization: authorization.clone(),
            terms,
            prefix: if prefix.is_empty() {
                prefix
            } else {
                format!("{prefix}/")
            },
            uploads: Arc::new(Semaphore::new(config.limits.uploads as usize)),
            downloads: Arc::new(Semaphore::new(config.limits.downloads as usize)),
            config,
            objects: objects.with_original_owner(namespace),
            temp,
            _temp_lock: lock,
        }))
    }

    pub(crate) fn quota(&self, space: &Space) -> AppResult<(Uuid, i64)> {
        Ok(match space.kind {
            SpaceKind::Personal => (space.id, self.config.limits.personal_bytes),
            SpaceKind::Organization => (space.id, self.config.limits.organization_bytes),
            SpaceKind::Team => (space.id, self.config.limits.team_bytes),
            SpaceKind::Project => (
                space.parent_id.ok_or_else(unavailable)?,
                self.config.limits.team_bytes,
            ),
        })
    }

    pub(crate) fn idle(&self) -> Duration {
        Duration::from_secs(self.config.limits.idle_seconds)
    }
    pub(crate) fn deadline(&self) -> Duration {
        Duration::from_secs(self.config.limits.transfer_seconds)
    }

    pub(crate) fn original_id(&self, key: &str) -> Option<Uuid> {
        let mut parts = key.strip_prefix(&self.prefix)?.split('/');
        let id = Uuid::parse_str(parts.next()?).ok()?;
        if parts.next()? != "input" || parts.next()?.is_empty() || parts.next().is_some() {
            return None;
        }
        Some(id)
    }
}

pub(crate) fn unavailable() -> AppError {
    AppError::problem(
        StatusCode::SERVICE_UNAVAILABLE,
        "storage_unavailable",
        "Document storage is temporarily unavailable",
    )
}
pub(crate) fn conflict(code: &'static str, detail: &'static str) -> AppError {
    AppError::problem(StatusCode::CONFLICT, code, detail)
}
pub(crate) fn invalid(detail: &'static str) -> AppError {
    AppError::problem(StatusCode::UNPROCESSABLE_ENTITY, "invalid_fields", detail)
}

pub(crate) fn dependency_error(error: AppError) -> AppError {
    match error {
        AppError::Internal(_) => unavailable(),
        other => other,
    }
}
