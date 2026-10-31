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

//! Platform-role administration by platform admins. Bootstrap and role writes share one
//! lock so a revoked admin cannot complete a previously authorized mutation.

use crate::{
    authorization::{self, Authorization},
    bootstrap,
    error::{AppError, AppResult},
    keycloak::Directory,
    roles::PlatformRole,
};
use serde::Serialize;
use sqlx::PgPool;

pub(crate) async fn require_admin(authorization: &Authorization, caller: &str) -> AppResult<()> {
    if !authorization.is_platform_admin(caller).await? {
        return Err(AppError::Forbidden);
    }
    Ok(())
}

#[derive(Serialize, utoipa::ToSchema)]
pub struct Grant {
    pub user_id: String,
    pub role: PlatformRole,
}

pub async fn list(authorization: &Authorization, caller: &str) -> AppResult<Vec<Grant>> {
    require_admin(authorization, caller).await?;
    Ok(authorization
        .platform_grants()
        .await?
        .into_iter()
        .map(|(user_id, role)| Grant { user_id, role })
        .collect())
}

pub async fn grant(
    pool: &PgPool,
    directory: Option<&Directory>,
    caller: &str,
    target: &str,
    role: PlatformRole,
) -> AppResult<()> {
    let mut tx = bootstrap::locked(pool).await?;
    require_admin_locked(&mut tx, caller).await?;
    let directory = directory
        .ok_or_else(|| AppError::Unavailable("Keycloak directory is not configured".into()))?;
    if !directory.exists(target).await? {
        return Err(AppError::NotFound);
    }
    authorization::write_platform(&mut tx, target, role, true).await?;
    crate::logging::audit_relation(Some(caller), target, role.relation(), "platform:root", true);
    tx.commit().await?;

    Ok(())
}

pub async fn revoke(
    pool: &PgPool,
    caller: &str,
    target: &str,
    role: PlatformRole,
) -> AppResult<()> {
    let mut tx = bootstrap::locked(pool).await?;
    require_admin_locked(&mut tx, caller).await?;
    let grants = authorization::platform_grants(&mut *tx).await?;
    if !grants.contains(&(target.to_owned(), role)) {
        return Err(AppError::NotFound);
    }
    if role == PlatformRole::PlatformAdmin
        && !grants
            .iter()
            .any(|(user, r)| *r == PlatformRole::PlatformAdmin && user != target)
    {
        return Err(AppError::Conflict(
            "the platform must retain an admin".into(),
        ));
    }
    authorization::write_platform(&mut tx, target, role, false).await?;
    crate::logging::audit_relation(
        Some(caller),
        target,
        role.relation(),
        "platform:root",
        false,
    );
    tx.commit().await?;

    Ok(())
}

pub(crate) async fn require_admin_locked(
    conn: &mut sqlx::PgConnection,
    caller: &str,
) -> AppResult<()> {
    if authorization::platform_roles(conn, caller)
        .await?
        .contains(&PlatformRole::PlatformAdmin)
    {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}
