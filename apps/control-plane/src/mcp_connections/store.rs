// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{Connection, McpBinding, SOURCE_ID};
use crate::{
    agents::AgentTemplateSummary,
    error::{AppError, AppResult},
};
use serde_json::Value;
use sqlx::{PgConnection, types::Json};
use std::collections::BTreeMap;
use uuid::Uuid;

pub(super) async fn get<'e>(ex: impl sqlx::PgExecutor<'e>, id: Uuid) -> AppResult<Connection> {
    sqlx::query_as("select * from mcp_connection where id=$1")
        .bind(id)
        .fetch_optional(ex)
        .await?
        .ok_or(AppError::NotFound)
}

pub(super) async fn list<'e>(ex: impl sqlx::PgExecutor<'e>) -> AppResult<Vec<Connection>> {
    Ok(
        sqlx::query_as("select * from mcp_connection order by logical_name")
            .fetch_all(ex)
            .await?,
    )
}

pub(super) async fn update_offer(conn: &mut PgConnection, value: &Connection) -> AppResult<()> {
    sqlx::query("insert into capability_offer(source_id,capability_id,version,descriptor,advertised,connection_id)
        values($1,$2,'1',$3,$4,$5) on conflict(source_id,capability_id) do update set
        descriptor=excluded.descriptor, advertised=excluded.advertised")
        .bind(SOURCE_ID).bind(value.capability_id()).bind(value.descriptor())
        .bind(value.available()).bind(value.id).execute(conn).await?;
    Ok(())
}

/// Read the offer projection maintained in the same transaction as each connection
/// mutation. Template pickers never need observed/published tool contracts.
pub(crate) async fn available_offers<'e>(
    ex: impl sqlx::PgExecutor<'e>,
) -> AppResult<Vec<BTreeMap<String, Value>>> {
    let rows: Vec<Json<BTreeMap<String, Value>>> = sqlx::query_scalar(
        "select descriptor from capability_offer where source_id=$1 and advertised order by capability_id")
        .bind(SOURCE_ID).fetch_all(ex).await?;
    Ok(rows.into_iter().map(|row| row.0).collect())
}

/// One request can share this lightweight projection across all its templates.
/// Final admission still checks the selected connections in its SQL snapshot.
pub(crate) fn extend_template(
    template: &mut AgentTemplateSummary,
    offers: &[BTreeMap<String, Value>],
) {
    let contributions: Vec<_> = template
        .available_capabilities
        .iter()
        .filter(|entry| entry.get("mcp_service").is_some_and(|v| !v.is_null()))
        .cloned()
        .collect();
    template
        .available_capabilities
        .retain(|entry| !entry.get("mcp_service").is_some_and(|v| !v.is_null()));
    if !template.supports_managed_mcp {
        return;
    }
    for offer in offers {
        let mut offer = offer.clone();
        if let Some(service) = offer.get("mcp_service").filter(|v| !v.is_null()) {
            let Some(owner) = contributions
                .iter()
                .find(|entry| entry.get("mcp_service") == Some(service))
            else {
                continue;
            };
            let Some(owner_id) = owner.get("id").and_then(Value::as_str) else {
                continue;
            };
            let Some(id) = offer.get("id").and_then(Value::as_str).map(str::to_owned) else {
                continue;
            };
            if !template.supports_capabilities
                && !template
                    .default_capability_ids
                    .iter()
                    .any(|id| id == owner_id)
            {
                continue;
            }
            for default in &mut template.default_capability_ids {
                if default == owner_id {
                    *default = id.clone();
                }
            }
            offer.insert(
                "capability_owner".into(),
                Value::String(owner_id.to_owned()),
            );
            for key in ["config_fields", "version", "execution_models"] {
                if let Some(value) = owner.get(key) {
                    offer.insert(key.into(), value.clone());
                }
            }
        }
        if !template.supports_capabilities && !offer.contains_key("capability_owner") {
            continue;
        }
        template.available_capabilities.push(offer);
    }
}

pub(crate) fn capability_owner<'a>(template: &'a AgentTemplateSummary, id: &'a str) -> &'a str {
    template
        .available_capabilities
        .iter()
        .find(|entry| entry.get("id").and_then(Value::as_str) == Some(id))
        .and_then(|entry| entry.get("capability_owner"))
        .and_then(Value::as_str)
        .unwrap_or(id)
}

/// Resolve in the admission snapshot. Caller has checked the same selection's
/// organization/local policy. Network discovery never occurs in this transaction.
pub(crate) async fn bindings(
    conn: &mut PgConnection,
    selected: &[String],
    knowledge_flow_url: Option<&str>,
) -> AppResult<Vec<McpBinding>> {
    let mut result = Vec::new();
    for id in selected.iter().filter(|id| id.starts_with("managed-mcp:")) {
        let key = id
            .strip_prefix("managed-mcp:")
            .and_then(|id| Uuid::parse_str(id).ok())
            .ok_or_else(|| crate::agents::enablement::not_enabled(id))?;
        let connection = get(&mut *conn, key).await?;
        if !connection.available()
            || connection
                .configuration
                .trusted_destination(knowledge_flow_url)
                .is_err()
        {
            return Err(crate::agents::enablement::not_enabled(id));
        }
        result.push(McpBinding {
            connection_id: key,
            capability_id: id.clone(),
            revision: connection.revision,
            display_name: connection.display_name,
            configuration: connection.configuration.0,
            tools: connection.published_tools.0,
        });
    }
    Ok(result)
}
