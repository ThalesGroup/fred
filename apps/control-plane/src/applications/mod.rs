// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! SQL-managed destinations. Offers own presentation and availability; the
//! existing capability policy owns business authorization. No runtime is created.
mod http;
mod proxy;

pub(crate) use http::routes;
pub(crate) use proxy::routes as proxy_routes;

use crate::{
    agents::enablement,
    authorization,
    domain::{Space, SpaceKind},
    error::{AppError, AppResult},
    roles::SpacePermission,
};
use axum::http::StatusCode;
use serde::{Deserialize, Serialize};
use sqlx::{PgConnection, types::Json};
use std::collections::BTreeMap;
use utoipa::ToSchema;
use uuid::Uuid;

pub const SOURCE_ID: &str = "$applications";

#[derive(Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ApplicationMetadata {
    pub display_name: String,
    pub description: String,
    pub icon: String,
    #[serde(default)]
    pub display_name_by_lang: BTreeMap<String, String>,
    #[serde(default)]
    pub description_by_lang: BTreeMap<String, String>,
    #[serde(default = "default_version")]
    pub version: String,
}
fn default_version() -> String {
    "1.0.0".into()
}

#[derive(Serialize, ToSchema)]
pub struct Application {
    pub id: Uuid,
    pub logical_name: String,
    pub ui_base_url: String,
    pub api_base_url: Option<String>,
    pub entry_permission: SpacePermission,
    pub revision: i64,
    pub enabled: bool,
    pub source_id: String,
    pub capability_id: String,
    #[serde(flatten)]
    pub metadata: ApplicationMetadata,
}

#[derive(sqlx::FromRow)]
struct StoredApplication {
    id: Uuid,
    logical_name: String,
    ui_base_url: String,
    api_base_url: Option<String>,
    entry_permission: String,
    revision: i64,
    advertised: bool,
    descriptor: Json<serde_json::Value>,
}

const SELECT: &str = "select a.id,a.logical_name,a.ui_base_url,a.api_base_url,a.entry_permission,a.revision,o.advertised,o.descriptor from application a join capability_offer o on o.application_id=a.id";

impl TryFrom<StoredApplication> for Application {
    type Error = AppError;
    fn try_from(row: StoredApplication) -> AppResult<Self> {
        let d = row.descriptor.0;
        Ok(Self {
            id: row.id,
            logical_name: row.logical_name,
            ui_base_url: row.ui_base_url,
            api_base_url: row.api_base_url,
            entry_permission: serde_json::from_value(serde_json::Value::String(
                row.entry_permission,
            ))
            .map_err(anyhow::Error::from)?,
            revision: row.revision,
            enabled: row.advertised,
            source_id: SOURCE_ID.into(),
            capability_id: format!("application:{}", row.id),
            metadata: ApplicationMetadata {
                display_name: d["name"].as_str().unwrap_or_default().into(),
                description: d["description"].as_str().unwrap_or_default().into(),
                icon: d["icon"].as_str().unwrap_or_default().into(),
                version: d["version"].as_str().unwrap_or_default().into(),
                display_name_by_lang: serde_json::from_value(d["name_by_lang"].clone())
                    .map_err(anyhow::Error::from)?,
                description_by_lang: serde_json::from_value(d["description_by_lang"].clone())
                    .map_err(anyhow::Error::from)?,
            },
        })
    }
}

async fn all(conn: &mut PgConnection) -> AppResult<Vec<Application>> {
    sqlx::query_as::<_, StoredApplication>(sqlx::AssertSqlSafe(format!(
        "{SELECT} order by a.logical_name"
    )))
    .fetch_all(conn)
    .await?
    .into_iter()
    .map(Application::try_from)
    .collect()
}
async fn by_name(conn: &mut PgConnection, name: &str) -> AppResult<Application> {
    sqlx::query_as::<_, StoredApplication>(sqlx::AssertSqlSafe(format!(
        "{SELECT} where a.logical_name=$1"
    )))
    .bind(name)
    .fetch_one(conn)
    .await?
    .try_into()
}

/// One admission snapshot. No SQL transaction survives the upstream request.
async fn authorize(
    conn: &mut PgConnection,
    uid: &str,
    space_id: Uuid,
    app: &Application,
) -> AppResult<Space> {
    let space = authorization::authorize(&mut *conn, uid, space_id, app.entry_permission).await?;
    if space.kind == SpaceKind::Personal {
        return Err(AppError::Forbidden);
    }
    let policy = enablement::Policy::load_for_space(&mut *conn, &space).await?;
    if !app.enabled || !enablement::usable(&policy, &space, SOURCE_ID, &app.capability_id) {
        return Err(AppError::problem(
            StatusCode::FORBIDDEN,
            "application_unavailable",
            "This application is not available in this space.",
        ));
    }
    Ok(space)
}

fn descriptor(id: Uuid, m: &ApplicationMetadata) -> serde_json::Value {
    serde_json::json!({"id":format!("application:{id}"),"version":m.version,"name":m.display_name,
        "description":m.description,"icon":m.icon,"kind":"application",
        "name_by_lang":m.display_name_by_lang,"description_by_lang":m.description_by_lang,
        "execution_models":[]})
}
