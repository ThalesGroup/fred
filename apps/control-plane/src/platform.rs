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
    authorization, bootstrap,
    error::{AppError, AppResult},
    keycloak::Directory,
    roles::PlatformPermission,
    roles::PlatformRole,
};
use serde::Serialize;
use sqlx::PgPool;

#[derive(Serialize, utoipa::ToSchema)]
pub struct Grant {
    pub user_id: String,
    pub role: PlatformRole,
}

pub async fn list(pool: &PgPool, caller: &str) -> AppResult<Vec<Grant>> {
    authorization::require_platform(pool, caller, PlatformPermission::ManagePlatform).await?;
    Ok(crate::authorization::platform_grants(pool)
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
    // Authorize discovery without retaining a SQL connection across the directory call.
    authorization::require_platform(pool, caller, PlatformPermission::ManagePlatform).await?;
    let directory = directory
        .ok_or_else(|| AppError::Unavailable("Keycloak directory is not configured".into()))?;
    if !directory.exists(target).await? {
        return Err(AppError::NotFound);
    }
    let mut tx = bootstrap::locked(pool).await?;
    authorization::require_platform(&mut *tx, caller, PlatformPermission::ManagePlatform).await?;
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
    authorization::require_platform(&mut *tx, caller, PlatformPermission::ManagePlatform).await?;
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
