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
    if template.supports_managed_mcp && template.supports_capabilities {
        template.available_capabilities.extend_from_slice(offers);
    }
}

/// Resolve in the admission snapshot. Caller has checked the same selection's
/// organization/local policy. Network discovery never occurs in this transaction.
pub(crate) async fn bindings(
    conn: &mut PgConnection,
    selected: &[String],
) -> AppResult<Vec<McpBinding>> {
    let mut result = Vec::new();
    for id in selected.iter().filter(|id| id.starts_with("managed-mcp:")) {
        let key = id
            .strip_prefix("managed-mcp:")
            .and_then(|id| Uuid::parse_str(id).ok())
            .ok_or_else(|| crate::agents::enablement::not_enabled(id))?;
        let connection = get(&mut *conn, key).await?;
        if !connection.available() {
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
