// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Read platform grants from the Control Plane schema; mutations remain its responsibility.
use serde::{Deserialize, Serialize};

#[derive(
    Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, utoipa::ToSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum PlatformRole {
    PlatformAdmin,
    PlatformObserver,
    FeatureManager,
    PromptEditor,
}
impl PlatformRole {
    pub const ALL: [Self; 4] = [
        Self::PlatformAdmin,
        Self::PlatformObserver,
        Self::FeatureManager,
        Self::PromptEditor,
    ];
    pub fn relation(self) -> &'static str {
        match self {
            Self::PlatformAdmin => "platform_admin",
            Self::PlatformObserver => "platform_observer",
            Self::FeatureManager => "feature_manager",
            Self::PromptEditor => "prompt_editor",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "platform_admin" => Some(Self::PlatformAdmin),
            "platform_observer" => Some(Self::PlatformObserver),
            "feature_manager" => Some(Self::FeatureManager),
            "prompt_editor" => Some(Self::PromptEditor),
            _ => None,
        }
    }
}

pub async fn platform_roles<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
) -> sqlx::Result<Vec<PlatformRole>> {
    let roles: Vec<String> =
        sqlx::query_scalar("select role from platform_role_grant where subject=$1")
            .bind(subject)
            .fetch_all(ex)
            .await?;
    Ok(roles
        .iter()
        .filter_map(|r| PlatformRole::parse(r))
        .collect())
}

/// Evaluate the current database grant, never an asserted role from the browser.
pub async fn is_platform_admin<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    subject: &str,
) -> sqlx::Result<bool> {
    Ok(platform_roles(ex, subject)
        .await?
        .contains(&PlatformRole::PlatformAdmin))
}
