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
    bootstrap,
    error::{AppError, AppResult},
    fga::{Fga, Scope},
    keycloak::Directory,
    roles::PlatformRole,
};
use serde::Serialize;
use sqlx::PgPool;

pub(crate) async fn require_admin(fga: &Fga, caller: &str) -> AppResult<()> {
    if !fga.is_platform_admin(caller).await? {
        return Err(AppError::Forbidden);
    }
    Ok(())
}

#[derive(Serialize, utoipa::ToSchema)]
pub struct Grant {
    pub user_id: String,
    pub role: PlatformRole,
}

pub async fn list(fga: &Fga, caller: &str) -> AppResult<Vec<Grant>> {
    require_admin(fga, caller).await?;
    Ok(fga
        .platform_grants()
        .await?
        .into_iter()
        .map(|(user_id, role)| Grant { user_id, role })
        .collect())
}

pub async fn grant(
    pool: &PgPool,
    fga: &Fga,
    directory: Option<&Directory>,
    caller: &str,
    target: &str,
    role: PlatformRole,
) -> AppResult<()> {
    let tx = bootstrap::locked(pool).await?;
    let mut guard = fga.guard(&[Scope::Platform]).await?;
    require_admin(fga, caller).await?;
    let directory = directory
        .ok_or_else(|| AppError::Unavailable("Keycloak directory is not configured".into()))?;
    if !directory.exists(target).await? {
        return Err(AppError::NotFound);
    }
    fga.write_platform(&mut guard, target, role, true).await?;
    crate::logging::audit_relation(Some(caller), target, role.relation(), "platform:root", true);
    tx.commit().await?;

    Ok(())
}

pub async fn revoke(
    pool: &PgPool,
    fga: &Fga,
    caller: &str,
    target: &str,
    role: PlatformRole,
) -> AppResult<()> {
    let tx = bootstrap::locked(pool).await?;
    let mut guard = fga.guard(&[Scope::Platform]).await?;
    require_admin(fga, caller).await?;
    let grants = fga.platform_grants().await?;
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
    fga.write_platform(&mut guard, target, role, false).await?;
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
