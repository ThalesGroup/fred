// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

#[derive(Deserialize, utoipa::IntoParams)]
#[into_params(parameter_in = Query)]
struct AccessQuery {
    runtime_id: String,
    exchange_id: String,
    r#ref: String,
    index: Option<i64>,
}
#[derive(Deserialize, utoipa::IntoParams)]
#[into_params(parameter_in = Query)]
struct Offsets {
    request_offset: Option<i64>,
    response_offset: Option<i64>,
}

pub(super) async fn indexes(
    s: &AppState,
    session: Uuid,
    exchange: &str,
    kind: &str,
) -> AppResult<Vec<Value>> {
    let capture = ingest::capture(&s.pool, session, exchange).await?;
    let segments = facts(&s.pool, capture.id).await?;
    let mut out = Vec::new();
    for segment in segments {
        let key = match kind {
            "http" => "http_attempts",
            "model" => "model_calls",
            "tool" => "tool_calls",
            "spans" => "otel_spans",
            _ => "sse",
        };
        if kind == "sse" {
            if !segment[key].is_null() {
                out.push(segment[key].clone());
            }
        } else if let Some(values) = segment[key].as_array() {
            out.extend(values.iter().cloned());
        }
    }
    Ok(out)
}
async fn access(
    s: &AppState,
    actor: &str,
    c: &Conversation,
    kind: &str,
    exchange: &str,
    reference: &str,
    index: Option<i64>,
) -> AppResult<Value> {
    observer(s, actor, c.organization_id).await?;
    if !valid_id(exchange, 255)
        || reference.len() != 32
        || !reference
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
    {
        return Err(AppError::NotFound);
    }
    let capture = ingest::capture(&s.pool, c.session_id, exchange).await?;
    let consent = consent(&s.pool, c.session_id).await?;
    if !covers(consent.as_ref(), exchange, capture.history_rank.into()) {
        return Err(AppError::Forbidden);
    }
    let grant = grant(consent.as_ref())?.ok_or(AppError::Forbidden)?;
    let base = json!({"grant_id":grant.grant_id,"local_content_access":false});
    let kind = if kind == "sse-header" { "sse" } else { kind };
    let items = indexes(s, c.session_id, exchange, kind).await?;
    if kind == "sse" {
        for segment in items {
            let mut lanes = segment["provider"].as_array().cloned().unwrap_or_default();
            if !segment["outgoing"].is_null() {
                lanes.push(segment["outgoing"].clone());
            }
            if let Some(lane) = lanes.iter().find(|v| v["ref"] == reference) {
                if segment["observed_through_rank"]
                    .as_i64()
                    .is_none_or(|v| v > grant.cutoff.last_rank)
                {
                    return Err(AppError::Forbidden);
                }
                let mut result = base;
                if let Some(index) = index {
                    if index < 0
                        || lane["frame_count"].as_i64().is_none_or(|v| index >= v)
                        || lane["page_starts_ms"].as_array().is_none_or(Vec::is_empty)
                    {
                        return Err(AppError::NotFound);
                    }
                    result["index"] = json!(index);
                } else if lane["headers_available"].as_bool() != Some(true) {
                    return Err(AppError::NotFound);
                }
                return Ok(result);
            }
        }
        return Err(AppError::NotFound);
    }
    let item = items
        .into_iter()
        .find(|v| v["ref"] == reference)
        .ok_or(AppError::NotFound)?;
    if item["completeness"] == "unavailable" {
        return Err(AppError::NotFound);
    }
    if item["observed_through_rank"]
        .as_i64()
        .is_none_or(|v| v > grant.cutoff.last_rank)
    {
        return Err(AppError::Forbidden);
    }
    let mut result = base;
    match kind {
        "http" => result["attempt"] = item,
        "model" => {
            result["owner_id"] = json!(c.user_id);
            result["observed_through_rank"] = item["observed_through_rank"].clone();
        }
        "tool" => result["observed_through_rank"] = item["observed_through_rank"].clone(),
        _ => return Err(AppError::NotFound),
    }
    Ok(result)
}
async fn runtime_access(
    s: &AppState,
    actor: &str,
    session: Uuid,
    q: AccessQuery,
    kind: &str,
) -> AppResult<Value> {
    let c = conversation(&s.pool, session).await?;
    if c.runtime_id != q.runtime_id {
        return Err(AppError::Forbidden);
    }
    access(s, actor, &c, kind, &q.exchange_id, &q.r#ref, q.index).await
}
#[allow(clippy::too_many_arguments)]
pub(super) async fn evidence(
    s: &AppState,
    actor: &str,
    c: &Conversation,
    headers: &HeaderMap,
    kind: &str,
    exchange: &str,
    reference: &str,
    index: Option<i64>,
    params: &[(&str, String)],
) -> AppResult<Value> {
    let permission_kind = if kind == "sse-frames" {
        "sse"
    } else if kind == "sse-headers" {
        "sse-header"
    } else {
        kind
    };
    let access_index = if kind == "sse-frames" {
        index.and_then(|v| v.checked_mul(256))
    } else {
        index
    };
    let permission = access(
        s,
        actor,
        c,
        permission_kind,
        exchange,
        reference,
        access_index,
    )
    .await?;
    let mut suffix = format!("trace-{kind}/{exchange}/{reference}");
    if let Some(index) = index {
        suffix.push_str(&format!("/{index}"));
    }
    let mut result = runtime_read(s, c, headers, &suffix, params).await?;
    if kind == "model" {
        result["origins"] = model_origins(s, c.session_id, exchange, reference).await?;
    }
    let fresh = conversation(&s.pool, c.session_id).await?;
    if permission
        != access(
            s,
            actor,
            &fresh,
            permission_kind,
            exchange,
            reference,
            access_index,
        )
        .await?
    {
        return Err(AppError::Forbidden);
    }
    Ok(result)
}

#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/http/{exchange_id}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path)),responses((status=200,body=[TraceHttpAttempt])))]
async fn list_conversation_trace_http_attempts(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange)): ApiPath<(Uuid, Uuid, String)>,
) -> AppResult<Json<Vec<TraceHttpAttempt>>> {
    authorized(&s, &user.uid, org, session).await?;
    let values = indexes(&s, session, &exchange, "http").await?;
    Ok(Json(
        values
            .into_iter()
            .filter(|v| v["tool_ref"].is_null())
            .map(decode)
            .collect::<AppResult<_>>()?,
    ))
}

#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/model/{exchange_id}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path)),responses((status=200,body=[TraceModelCall])))]
async fn list_conversation_trace_model_calls(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange)): ApiPath<(Uuid, Uuid, String)>,
) -> AppResult<Json<Vec<TraceModelCall>>> {
    authorized(&s, &user.uid, org, session).await?;
    let values = indexes(&s, session, &exchange, "model").await?;
    Ok(Json(
        values.into_iter().map(decode).collect::<AppResult<_>>()?,
    ))
}

#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/tool/{exchange_id}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path)),responses((status=200,body=[TraceToolCall])))]
async fn list_conversation_trace_tool_calls(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange)): ApiPath<(Uuid, Uuid, String)>,
) -> AppResult<Json<Vec<TraceToolCall>>> {
    authorized(&s, &user.uid, org, session).await?;
    let values = indexes(&s, session, &exchange, "tool").await?;
    Ok(Json(
        values.into_iter().map(decode).collect::<AppResult<_>>()?,
    ))
}

#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/sse/{exchange_id}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path)),responses((status=200,body=[TraceSseSegment])))]
async fn list_conversation_trace_sse_segments(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange)): ApiPath<(Uuid, Uuid, String)>,
) -> AppResult<Json<Vec<TraceSseSegment>>> {
    authorized(&s, &user.uid, org, session).await?;
    let values = indexes(&s, session, &exchange, "sse").await?;
    Ok(Json(
        values.into_iter().map(decode).collect::<AppResult<_>>()?,
    ))
}

#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/spans/{exchange_id}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path)),responses((status=200,body=[OtlpTraceSpan])))]
async fn list_conversation_trace_spans(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange)): ApiPath<(Uuid, Uuid, String)>,
) -> AppResult<Json<Vec<OtlpTraceSpan>>> {
    authorized(&s, &user.uid, org, session).await?;
    let values = indexes(&s, session, &exchange, "spans").await?;
    Ok(Json(
        values.into_iter().map(decode).collect::<AppResult<_>>()?,
    ))
}

#[utoipa::path(get,path="/admin/conversation-traces/{session_id}/http-access",params(("session_id"=Uuid,Path),AccessQuery),responses((status=200,body=TraceHttpArtifactAccess))) ]
async fn get_conversation_trace_http_access(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(session): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<AccessQuery>,
) -> AppResult<Json<TraceHttpArtifactAccess>> {
    Ok(Json(decode(
        runtime_access(&s, &user.uid, session, q, "http").await?,
    )?))
}

#[utoipa::path(get,path="/admin/conversation-traces/{session_id}/model-access",params(("session_id"=Uuid,Path),AccessQuery),responses((status=200,body=TraceModelArtifactAccess))) ]
async fn get_conversation_trace_model_access(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(session): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<AccessQuery>,
) -> AppResult<Json<TraceModelArtifactAccess>> {
    Ok(Json(decode(
        runtime_access(&s, &user.uid, session, q, "model").await?,
    )?))
}

#[utoipa::path(get,path="/admin/conversation-traces/{session_id}/tool-access",params(("session_id"=Uuid,Path),AccessQuery),responses((status=200,body=TraceToolArtifactAccess))) ]
async fn get_conversation_trace_tool_access(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(session): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<AccessQuery>,
) -> AppResult<Json<TraceToolArtifactAccess>> {
    Ok(Json(decode(
        runtime_access(&s, &user.uid, session, q, "tool").await?,
    )?))
}

#[utoipa::path(get,path="/admin/conversation-traces/{session_id}/sse-access",params(("session_id"=Uuid,Path),AccessQuery),responses((status=200,body=TraceSseArtifactAccess))) ]
async fn get_conversation_trace_sse_access(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(session): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<AccessQuery>,
) -> AppResult<Json<TraceSseArtifactAccess>> {
    Ok(Json(decode(
        runtime_access(&s, &user.uid, session, q, "sse").await?,
    )?))
}

#[utoipa::path(get,path="/admin/conversation-traces/{session_id}/sse-header-access",params(("session_id"=Uuid,Path),AccessQuery),responses((status=200,body=TraceSseHeaderAccess))) ]
async fn get_conversation_trace_sse_header_access(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(session): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<AccessQuery>,
) -> AppResult<Json<TraceSseHeaderAccess>> {
    Ok(Json(decode(
        runtime_access(&s, &user.uid, session, q, "sse-header").await?,
    )?))
}

#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/http/{exchange_id}/{ref}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path),("ref"=String,Path),Offsets),responses((status=200,body=TraceHttpEvidence))) ]
async fn get_conversation_trace_http_evidence(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange, reference)): ApiPath<(Uuid, Uuid, String, String)>,
    headers: HeaderMap,
    ApiQuery(offsets): ApiQuery<Offsets>,
) -> AppResult<Json<TraceHttpEvidence>> {
    let c = authorized(&s, &user.uid, org, session).await?;
    let request = offsets.request_offset.unwrap_or(0);
    let response = offsets.response_offset.unwrap_or(0);
    if request < 0 || response < 0 {
        return Err(AppError::Unprocessable("Invalid trace offset".into()));
    }
    let params = vec![
        ("request_offset", request.to_string()),
        ("response_offset", response.to_string()),
    ];
    Ok(Json(decode(
        evidence(
            &s, &user.uid, &c, &headers, "http", &exchange, &reference, None, &params,
        )
        .await?,
    )?))
}

#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/model/{exchange_id}/{ref}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path),("ref"=String,Path)),responses((status=200,body=TraceModelEvidence))) ]
async fn get_conversation_trace_model_evidence(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange, reference)): ApiPath<(Uuid, Uuid, String, String)>,
    headers: HeaderMap,
) -> AppResult<Json<TraceModelEvidence>> {
    let c = authorized(&s, &user.uid, org, session).await?;
    let params = vec![];
    Ok(Json(decode(
        evidence(
            &s, &user.uid, &c, &headers, "model", &exchange, &reference, None, &params,
        )
        .await?,
    )?))
}

#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/tool/{exchange_id}/{ref}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path),("ref"=String,Path)),responses((status=200,body=TraceToolEvidence))) ]
async fn get_conversation_trace_tool_evidence(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange, reference)): ApiPath<(Uuid, Uuid, String, String)>,
    headers: HeaderMap,
) -> AppResult<Json<TraceToolEvidence>> {
    let c = authorized(&s, &user.uid, org, session).await?;
    let params = vec![];
    Ok(Json(decode(
        evidence(
            &s, &user.uid, &c, &headers, "tool", &exchange, &reference, None, &params,
        )
        .await?,
    )?))
}

#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/sse/{exchange_id}/{ref}/{index}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path),("ref"=String,Path),("index"=i64,Path)),responses((status=200,body=TraceSseFrame))) ]
async fn get_conversation_trace_sse_frame(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange, reference, index)): ApiPath<(Uuid, Uuid, String, String, i64)>,
    headers: HeaderMap,
) -> AppResult<Json<TraceSseFrame>> {
    let c = authorized(&s, &user.uid, org, session).await?;
    let params = vec![];
    Ok(Json(decode(
        evidence(
            &s,
            &user.uid,
            &c,
            &headers,
            "sse",
            &exchange,
            &reference,
            Some(index),
            &params,
        )
        .await?,
    )?))
}

#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/sse-frames/{exchange_id}/{ref}/{page}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path),("ref"=String,Path),("page"=i64,Path)),responses((status=200,body=TraceSseFramePage))) ]
async fn get_conversation_trace_sse_frame_page(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange, reference, index)): ApiPath<(Uuid, Uuid, String, String, i64)>,
    headers: HeaderMap,
) -> AppResult<Json<TraceSseFramePage>> {
    let c = authorized(&s, &user.uid, org, session).await?;
    let params = vec![];
    Ok(Json(decode(
        evidence(
            &s,
            &user.uid,
            &c,
            &headers,
            "sse-frames",
            &exchange,
            &reference,
            Some(index),
            &params,
        )
        .await?,
    )?))
}

#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/sse-headers/{exchange_id}/{ref}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path),("ref"=String,Path)),responses((status=200,body=TraceSseHeaders))) ]
async fn get_conversation_trace_sse_headers(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange, reference)): ApiPath<(Uuid, Uuid, String, String)>,
    headers: HeaderMap,
) -> AppResult<Json<TraceSseHeaders>> {
    let c = authorized(&s, &user.uid, org, session).await?;
    let params = vec![];
    Ok(Json(decode(
        evidence(
            &s,
            &user.uid,
            &c,
            &headers,
            "sse-headers",
            &exchange,
            &reference,
            None,
            &params,
        )
        .await?,
    )?))
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(list_conversation_trace_http_attempts))
        .routes(utoipa_axum::routes!(list_conversation_trace_model_calls))
        .routes(utoipa_axum::routes!(list_conversation_trace_tool_calls))
        .routes(utoipa_axum::routes!(list_conversation_trace_sse_segments))
        .routes(utoipa_axum::routes!(list_conversation_trace_spans))
        .routes(utoipa_axum::routes!(get_conversation_trace_http_access))
        .routes(utoipa_axum::routes!(get_conversation_trace_model_access))
        .routes(utoipa_axum::routes!(get_conversation_trace_tool_access))
        .routes(utoipa_axum::routes!(get_conversation_trace_sse_access))
        .routes(utoipa_axum::routes!(
            get_conversation_trace_sse_header_access
        ))
        .routes(utoipa_axum::routes!(get_conversation_trace_http_evidence))
        .routes(utoipa_axum::routes!(get_conversation_trace_model_evidence))
        .routes(utoipa_axum::routes!(get_conversation_trace_tool_evidence))
        .routes(utoipa_axum::routes!(get_conversation_trace_sse_frame))
        .routes(utoipa_axum::routes!(get_conversation_trace_sse_frame_page))
        .routes(utoipa_axum::routes!(get_conversation_trace_sse_headers))
}

async fn model_origins(
    s: &AppState,
    session: Uuid,
    exchange: &str,
    reference: &str,
) -> AppResult<Value> {
    let current = consent(&s.pool, session).await?;
    let cutoff = grant(current.as_ref())?
        .ok_or(AppError::Forbidden)?
        .cutoff
        .last_rank;
    let rows:Vec<Value>=sqlx::query_scalar("with anchor as materialized (
        select t.history_rank,t.exchange_id,g.started_at,g.id,m.ordinality-1 as call_order,m.value
        from conversation_trace t join conversation_trace_segment g on g.capture_id=t.id,
        lateral jsonb_array_elements(coalesce(g.facts->'model_calls','[]')) with ordinality m(value,ordinality)
        where t.session_id=$1 and t.exchange_id=$2 and m.value->>'ref'=$3 and not t.retired and t.expires_at>clock_timestamp() limit 1
      ), winners as (
        select distinct match.exchange_id,match.history_rank,match.turn_number,match.call_id
        from anchor a, lateral jsonb_array_elements_text(coalesce(a.value->'related_tools','[]')) key(value),
        lateral (select t.exchange_id,t.history_rank,(g.facts->>'turn_number')::bigint as turn_number,i.call_id
          from conversation_trace_model_origin i join conversation_trace_segment g on g.id=i.segment_id
          join conversation_trace t on t.id=g.capture_id
          where i.fingerprint=key.value and t.session_id=$1 and not t.retired and t.expires_at>clock_timestamp()
            and i.observed_through_rank<=least($4,(a.value->>'observed_through_rank')::bigint)
            and (t.history_rank,t.exchange_id,g.started_at,g.id,i.call_order)<=(a.history_rank,a.exchange_id,a.started_at,a.id,a.call_order)
          order by t.history_rank,t.exchange_id,g.started_at,g.id,i.call_order limit 1) match
      ) select to_jsonb(winners) from winners order by history_rank,exchange_id,call_id limit 32")
        .bind(session).bind(exchange).bind(reference).bind(cutoff).fetch_all(&s.pool).await?;
    Ok(json!(rows))
}
