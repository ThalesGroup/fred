// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use axum::response::IntoResponse;
use std::{
    io::{Cursor, Write},
    sync::{Arc, LazyLock},
};
static EXPORTS: LazyLock<Arc<tokio::sync::Semaphore>> =
    LazyLock::new(|| Arc::new(tokio::sync::Semaphore::new(2)));

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(export_conversation_traces))
}
struct Archive {
    files: Vec<(String, Vec<u8>)>,
    bytes: usize,
}
impl Archive {
    fn add(&mut self, path: String, value: Value) -> AppResult<()> {
        let data = serde_json::to_vec(&value).map_err(|e| AppError::Internal(e.into()))?;
        if self.files.len() >= 4096 || self.bytes + data.len() > 64 * 1024 * 1024 {
            return Err(AppError::Unprocessable(
                "Trace export exceeds archive limits".into(),
            ));
        }
        self.bytes += data.len();
        self.files.push((path, data));
        Ok(())
    }
}
#[utoipa::path(post,path="/organizations/{organization_id}/conversation-traces/export",params(("organization_id"=Uuid,Path)),request_body=ExportConversationTracesRequest,responses((status=200,body=String,content_type="application/zip")))]
async fn export_conversation_traces(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(org): ApiPath<Uuid>,
    headers: HeaderMap,
    ApiJson(body): ApiJson<ExportConversationTracesRequest>,
) -> AppResult<axum::response::Response> {
    observer(&s, &user.uid, org).await?;
    if body.session_ids.is_empty() || body.session_ids.len() > 100 {
        return Err(AppError::Unprocessable(
            "Select 1 to 100 conversations".into(),
        ));
    }
    let permit = EXPORTS
        .clone()
        .try_acquire_owned()
        .map_err(|_| AppError::Unavailable("Trace exports busy".into()))?;
    let (archive, states) = tokio::time::timeout(
        std::time::Duration::from_secs(90),
        build(&s, &user.uid, org, &headers, body),
    )
    .await
    .map_err(|_| AppError::Unavailable("Trace export timeout".into()))??;
    let data = tokio::task::spawn_blocking(move || -> AppResult<Vec<u8>> {
        let _permit = permit;
        let mut zip = zip::ZipWriter::new(Cursor::new(Vec::new()));
        for (name, bytes) in archive.files {
            zip.start_file(
                name,
                zip::write::SimpleFileOptions::default()
                    .compression_method(zip::CompressionMethod::Deflated),
            )
            .map_err(|e| AppError::Internal(e.into()))?;
            zip.write_all(&bytes)
                .map_err(|e| AppError::Internal(e.into()))?;
        }
        Ok(zip
            .finish()
            .map_err(|e| AppError::Internal(e.into()))?
            .into_inner())
    })
    .await
    .map_err(|e| AppError::Internal(e.into()))??;
    observer(&s, &user.uid, org).await?;
    for (session, version) in states {
        authorized(&s, &user.uid, org, session).await?;
        if export_state(&s, session).await? != version {
            return Err(AppError::Conflict("trace_export_changed".into()));
        }
    }
    tracing::info!(organization_id=%org,actor=%user.uid,"conversation_trace.exported");
    Ok((
        [
            (header::CONTENT_TYPE, "application/zip"),
            (
                header::CONTENT_DISPOSITION,
                "attachment; filename=conversation-traces.zip",
            ),
            (header::CACHE_CONTROL, "no-store"),
        ],
        data,
    )
        .into_response())
}
async fn build(
    s: &AppState,
    actor: &str,
    org: Uuid,
    headers: &HeaderMap,
    body: ExportConversationTracesRequest,
) -> AppResult<(Archive, Vec<(Uuid, Value)>)> {
    let mut archive = Archive {
        files: vec![],
        bytes: 0,
    };
    let mut states = vec![];
    let mut summaries = vec![];
    let mut spans = vec![];
    let mut turn_count = 0;
    for raw in body
        .session_ids
        .into_iter()
        .collect::<std::collections::BTreeSet<_>>()
    {
        let session = Uuid::parse_str(&raw).map_err(|_| AppError::NotFound)?;
        let c = authorized(s, actor, org, session).await?;
        states.push((session, export_state(s, session).await?));
        let mut cursor = None;
        let mut all_turns = vec![];
        loop {
            let page = detail(
                s,
                &c,
                Page {
                    limit: Some(100),
                    cursor,
                },
                headers,
            )
            .await?;
            for turn in &page.turns {
                turn_count += 1;
                if turn_count > 1000 {
                    return Err(AppError::Unprocessable(
                        "Trace export exceeds turn limit".into(),
                    ));
                }
                let prefix = format!("{session}/{}", turn.exchange_id);
                let shared = body.mode == TraceExportMode::SharedContent
                    && turn.access == TraceContentAccess::Shared;
                if shared {
                    let mut after = None;
                    let mut page = 0;
                    loop {
                        let q = HistoryQuery {
                            runtime_id: None,
                            exchange_id: Some(turn.exchange_id.clone()),
                            after_rank: after,
                            limit: Some(100),
                        };
                        let permission = wire(history_access(s, actor, &c, &q).await?)?;
                        let mut params = vec![("limit", "100".into())];
                        if let Some(v) = after {
                            params.push(("after_rank", v.to_string()));
                        }
                        let result = export_result(
                            runtime_read(
                                s,
                                &c,
                                headers,
                                &format!("trace-history-turns/{}", turn.exchange_id),
                                &params,
                            )
                            .await,
                        )?;
                        let fresh = conversation(&s.pool, session).await?;
                        if permission != wire(history_access(s, actor, &fresh, &q).await?)? {
                            return Err(AppError::Forbidden);
                        }
                        let next = result["next_rank"].as_i64();
                        archive.add(format!("{prefix}/history/{page}.json"), result)?;
                        if next.is_none() {
                            break;
                        }
                        if next <= after {
                            return Err(AppError::Unavailable(
                                "Invalid trace history pagination".into(),
                            ));
                        }
                        after = next;
                        page += 1;
                    }
                }
                for kind in ["spans", "http", "model", "tool", "sse"] {
                    let items = match artifacts::indexes(s, session, &turn.exchange_id, kind).await
                    {
                        Ok(v) => v,
                        Err(AppError::NotFound) => vec![],
                        Err(e) => return Err(e),
                    };
                    archive.add(format!("{prefix}/{kind}-index.json"), json!(items))?;
                    if kind == "spans" {
                        spans.extend(items);
                        continue;
                    }
                    if !shared {
                        continue;
                    }
                    for item in items {
                        if kind == "sse" {
                            let mut lanes =
                                item["provider"].as_array().cloned().unwrap_or_default();
                            if !item["outgoing"].is_null() {
                                lanes.push(item["outgoing"].clone());
                            }
                            for lane in lanes {
                                let reference = lane["ref"].as_str().ok_or(AppError::NotFound)?;
                                if lane["headers_available"].as_bool() == Some(true) {
                                    add_evidence(
                                        &mut archive,
                                        s,
                                        actor,
                                        &c,
                                        headers,
                                        "sse-headers",
                                        &turn.exchange_id,
                                        reference,
                                        None,
                                        &[],
                                    )
                                    .await?;
                                }
                                let frames = lane["frame_count"].as_i64().unwrap_or(0);
                                for page in 0..(frames + 255) / 256 {
                                    add_evidence(
                                        &mut archive,
                                        s,
                                        actor,
                                        &c,
                                        headers,
                                        "sse-frames",
                                        &turn.exchange_id,
                                        reference,
                                        Some(page),
                                        &[],
                                    )
                                    .await?;
                                }
                            }
                        } else {
                            let reference = item["ref"].as_str().ok_or(AppError::NotFound)?;
                            if kind == "http" {
                                let mut request = 0;
                                let mut response = 0;
                                let mut page = 0;
                                loop {
                                    let params = [
                                        ("request_offset", request.to_string()),
                                        ("response_offset", response.to_string()),
                                    ];
                                    let result = artifacts::evidence(
                                        s,
                                        actor,
                                        &c,
                                        headers,
                                        kind,
                                        &turn.exchange_id,
                                        reference,
                                        None,
                                        &params,
                                    )
                                    .await;
                                    let result = export_result(result)?;
                                    let next_request =
                                        result["request_body"]["next_offset"].as_i64();
                                    let next_response =
                                        result["response_body"]["next_offset"].as_i64();
                                    archive.add(
                                        format!("{prefix}/http/{reference}-{page}.json"),
                                        result,
                                    )?;
                                    if next_request.is_none() && next_response.is_none() {
                                        break;
                                    }
                                    if next_request.is_some_and(|v| v <= request)
                                        || next_response.is_some_and(|v| v <= response)
                                    {
                                        return Err(AppError::Unavailable(
                                            "Invalid trace body pagination".into(),
                                        ));
                                    }
                                    request = next_request.unwrap_or(request);
                                    response = next_response.unwrap_or(response);
                                    page += 1;
                                }
                            } else {
                                add_evidence(
                                    &mut archive,
                                    s,
                                    actor,
                                    &c,
                                    headers,
                                    kind,
                                    &turn.exchange_id,
                                    reference,
                                    None,
                                    &[],
                                )
                                .await?;
                            }
                        }
                    }
                }
            }
            all_turns.extend(page.turns);
            cursor = page.next_cursor;
            if cursor.is_none() {
                break;
            }
        }
        let mut metadata = wire(
            detail(
                s,
                &c,
                Page {
                    limit: Some(1),
                    cursor: None,
                },
                headers,
            )
            .await?,
        )?;
        metadata["turns"] = wire(all_turns)?;
        metadata["next_cursor"] = Value::Null;
        if body.mode == TraceExportMode::MetadataOnly {
            metadata["title"] = Value::Null;
        }
        summaries.push(metadata);
    }
    archive.add(
        "manifest.json".into(),
        json!({"version":1,"mode":body.mode,"conversations":summaries}),
    )?;
    archive.add("traces.otlp.json".into(),json!({"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"fred"}}]},"scopeSpans":[{"scope":{"name":"fred.conversation"},"spans":spans}]}]}))?;
    Ok((archive, states))
}
fn export_result(result: AppResult<Value>) -> AppResult<Value> {
    match result {
        Ok(v) => Ok(v),
        Err(AppError::Unavailable(_)) | Err(AppError::NotFound) => {
            Ok(json!({"status":"unavailable"}))
        }
        Err(e) => Err(e),
    }
}
#[allow(clippy::too_many_arguments)]
async fn add_evidence(
    archive: &mut Archive,
    s: &AppState,
    actor: &str,
    c: &Conversation,
    headers: &HeaderMap,
    kind: &str,
    exchange: &str,
    reference: &str,
    index: Option<i64>,
    params: &[(&str, String)],
) -> AppResult<()> {
    let result = export_result(
        artifacts::evidence(
            s, actor, c, headers, kind, exchange, reference, index, params,
        )
        .await,
    )?;
    archive.add(
        format!(
            "{}/{exchange}/{kind}/{reference}{}.json",
            c.session_id,
            index.map(|v| format!("-{v}")).unwrap_or_default()
        ),
        result,
    )
}

async fn export_state(s: &AppState, session: Uuid) -> AppResult<Value> {
    let current = consent(&s.pool, session).await?;
    let captures:Value=sqlx::query_scalar("select coalesce(jsonb_agg(id order by id),'[]'::jsonb) from conversation_trace where session_id=$1 and not retired and expires_at>clock_timestamp()")
        .bind(session).fetch_one(&s.pool).await?;
    Ok(json!({"consent":wire(grant(current.as_ref())?)?,"captures":captures}))
}
