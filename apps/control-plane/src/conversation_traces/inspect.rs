// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
mod artifacts;
mod export;

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(list_conversation_traces))
        .routes(utoipa_axum::routes!(list_conversation_trace_teams))
        .routes(utoipa_axum::routes!(get_conversation_trace))
        .routes(utoipa_axum::routes!(get_conversation_trace_history_access))
        .routes(utoipa_axum::routes!(get_conversation_trace_history))
        .merge(artifacts::routes())
        .merge(export::routes())
}
async fn authorized(
    s: &AppState,
    actor: &str,
    org: Uuid,
    session: Uuid,
) -> AppResult<Conversation> {
    observer(s, actor, org).await?;
    let c = conversation(&s.pool, session).await?;
    if c.organization_id != org {
        return Err(AppError::NotFound);
    }
    Ok(c)
}
pub(super) async fn facts(pool: &PgPool, id: Uuid) -> AppResult<Vec<Value>> {
    Ok(sqlx::query_scalar("select facts from conversation_trace_segment where capture_id=$1 order by started_at,id limit 64").bind(id).fetch_all(pool).await?)
}
#[derive(Deserialize, utoipa::IntoParams)]
#[into_params(parameter_in = Query)]
#[serde(default)]
struct CatalogQuery {
    #[param(required = false)]
    failed_only: bool,
    #[param(required = false)]
    outcomes: Vec<String>,
    #[param(required = false)]
    team_ids: Vec<Uuid>,
    #[param(required = false)]
    user_id: Option<String>,
    #[param(value_type=TraceConsentFilter)]
    #[param(required = false)]
    consent: String,
    #[param(required = false)]
    query: String,
    #[param(required = false)]
    query_outcomes: Vec<String>,
    #[param(required = false)]
    since: Option<DateTime<Utc>>,
    #[param(required = false)]
    until: Option<DateTime<Utc>>,
    #[param(value_type=TraceCatalogSort)]
    #[param(required = false)]
    sort: String,
    #[param(required = false)]
    direction: String,
    #[param(required = false)]
    limit: i64,
    #[param(required = false)]
    cursor: Option<String>,
}
impl Default for CatalogQuery {
    fn default() -> Self {
        Self {
            failed_only: true,
            outcomes: vec![],
            team_ids: vec![],
            user_id: None,
            consent: "all".into(),
            query: String::new(),
            query_outcomes: vec![],
            since: None,
            until: None,
            sort: "latest".into(),
            direction: "desc".into(),
            limit: 50,
            cursor: None,
        }
    }
}
fn catalog_query(raw: Option<String>) -> AppResult<CatalogQuery> {
    let url = reqwest::Url::parse(&format!("http://local/?{}", raw.unwrap_or_default()))
        .map_err(|_| AppError::Unprocessable("Invalid trace query".into()))?;
    let mut value = json!({});
    for (key, v) in url.query_pairs() {
        match key.as_ref() {
            "outcomes" | "team_ids" | "query_outcomes" => {
                let array = value
                    .as_object_mut()
                    .ok_or(AppError::NotFound)?
                    .entry(key.to_string())
                    .or_insert(json!([]));
                if let Some(array) = array.as_array_mut() {
                    array.push(json!(v));
                }
            }
            "failed_only" => {
                value[key.as_ref()] = json!(
                    v.parse::<bool>()
                        .map_err(|_| AppError::Unprocessable("Invalid boolean".into()))?
                )
            }
            "limit" => {
                value[key.as_ref()] = json!(
                    v.parse::<i64>()
                        .map_err(|_| AppError::Unprocessable("Invalid limit".into()))?
                )
            }
            _ => value[key.as_ref()] = json!(v),
        }
    }
    let query: CatalogQuery = serde_json::from_value(value)
        .map_err(|_| AppError::Unprocessable("Invalid trace query".into()))?;
    if !(1..=100).contains(&query.limit)
        || query.query.len() > 255
        || query.team_ids.len() > 500
        || query.outcomes.len() > 20
        || query.query_outcomes.len() > 20
        || query.since.zip(query.until).is_some_and(|(a, b)| a > b)
        || !["all", "shared", "masked"].contains(&query.consent.as_str())
    {
        return Err(AppError::Unprocessable("Invalid trace query".into()));
    }
    Ok(query)
}
#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces",params(("organization_id"=Uuid,Path),CatalogQuery),responses((status=200,body=ConversationTraceCatalog)))]
async fn list_conversation_traces(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(org): ApiPath<Uuid>,
    axum::extract::RawQuery(raw): axum::extract::RawQuery,
) -> AppResult<Json<ConversationTraceCatalog>> {
    observer(&s, &user.uid, org).await?;
    catalog(&s, org, catalog_query(raw)?).await.map(Json)
}
async fn catalog(s: &AppState, org: Uuid, q: CatalogQuery) -> AppResult<ConversationTraceCatalog> {
    let sort = match q.sort.as_str() {
        "latest" => "to_char(latest_started_at at time zone 'UTC','YYYY-MM-DD HH24:MI:SS.US')",
        "title" => "coalesce(title,'')",
        "user" => "user_id",
        "team" => "team_name",
        "outcome" => "outcome",
        "consent" => "access",
        _ => return Err(AppError::Unprocessable("Invalid trace sort".into())),
    };
    let direction = match q.direction.as_str() {
        "asc" => "asc",
        "desc" => "desc",
        _ => return Err(AppError::Unprocessable("Invalid trace direction".into())),
    };
    let anchor = match q.cursor {
        Some(v) => Some(
            serde_json::from_str::<(String, String)>(&v)
                .map_err(|_| AppError::Unprocessable("Invalid trace cursor".into()))?,
        ),
        None => None,
    };
    let comparison = if direction == "asc" { ">" } else { "<" };
    let sql=format!("with catalog as (
      select m.session_id::text, m.agent_display_name,
        case when c.cutoff is not null and c.title is not distinct from m.title then m.title end as title,
        m.user_id,null::text as username,null::text as user_display_name,
        m.space_id::text as team_id,sp.name as team_name,
        case when c.cutoff is not null then 'shared' else 'masked' end as access,
        coalesce(t.started_at,(c.incidents->-1->'cutoff'->>'started_at')::timestamptz,c.updated_at) as latest_started_at,
        coalesce(g.facts->>'outcome',case when jsonb_array_length(coalesce(c.incidents,'[]'))>0 then 'failed' else 'unknown' end) as outcome,
        coalesce(g.facts->>'failure_category',c.incidents->-1->>'failure_category') as failure_category,
        case when t.id is null then 'history_only' when g.facts->'storage' is not null and g.facts->'storage'<>'null' then case when coalesce((g.facts->>'http_incomplete')::boolean,false) then 'partial' else 'captured' end else 'metadata_only' end as availability,
        coalesce(g.facts->>'support_error_ref',c.incidents->-1->>'support_error_ref') as support_error_ref
      from session_metadata m join space sp on sp.id=m.space_id join space o on o.id=sp.organization_id
      left join conversation_trace_consent c on c.session_id=m.session_id and c.expires_at>clock_timestamp()
      left join lateral(select id,started_at from conversation_trace where session_id=m.session_id and not retired and expires_at>clock_timestamp() order by started_at desc,id limit 1)t on true
      left join lateral(select facts from conversation_trace_segment where capture_id=t.id order by started_at desc,id limit 1)g on true
      where sp.organization_id=$1 and sp.deletion_id is null and o.deletion_id is null and m.deletion_id is null
        and (t.id is not null or c.cutoff is not null)
        and (cardinality($2::uuid[])=0 or m.space_id=any($2)) and ($3::text is null or m.user_id=$3)
    ), ordered as (select *,{sort} as sort_key from catalog
      where (not $4 or outcome='failed') and ($5='all' or access=$5)
      and (cardinality($6::text[])=0 or outcome=any($6) or failure_category=any($6))
      and ($7='' or title ilike '%'||$7||'%' or agent_display_name ilike '%'||$7||'%' or session_id=$7 or user_id ilike '%'||$7||'%' or support_error_ref=$7 or outcome=any($8) or failure_category=any($8))
      and ($9::timestamptz is null or latest_started_at >= $9) and ($10::timestamptz is null or latest_started_at <= $10))
    select to_jsonb(ordered) from ordered where ($11::text is null or (sort_key,session_id){comparison}($11,$12)) order by sort_key {direction},session_id {direction} limit $13");
    let mut rows: Vec<Value> = sqlx::query_scalar(sqlx::AssertSqlSafe(sql))
        .bind(org)
        .bind(&q.team_ids)
        .bind(&q.user_id)
        .bind(q.failed_only)
        .bind(&q.consent)
        .bind(&q.outcomes)
        .bind(&q.query)
        .bind(&q.query_outcomes)
        .bind(q.since)
        .bind(q.until)
        .bind(anchor.as_ref().map(|v| &v.0))
        .bind(anchor.as_ref().map(|v| &v.1))
        .bind(q.limit + 1)
        .fetch_all(&s.pool)
        .await?;
    let more = rows.len() > q.limit as usize;
    rows.truncate(q.limit as usize);
    let next_cursor = if more {
        rows.last()
            .map(|v| json!([v["sort_key"], v["session_id"]]).to_string())
    } else {
        None
    };
    Ok(ConversationTraceCatalog {
        conversations: rows.into_iter().map(decode).collect::<AppResult<_>>()?,
        next_cursor,
    })
}
#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/teams",params(("organization_id"=Uuid,Path)),responses((status=200,body=[TraceTeamOption])))]
async fn list_conversation_trace_teams(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(org): ApiPath<Uuid>,
) -> AppResult<Json<Vec<TraceTeamOption>>> {
    observer(&s, &user.uid, org).await?;
    let rows:Vec<(String,String)>=sqlx::query_as("select id::text,name from space where organization_id=$1 and deletion_id is null and exists(select 1 from session_metadata m where m.space_id=space.id and m.deletion_id is null and exists(select 1 from conversation_trace t where t.session_id=m.session_id and not t.retired)) order by name,id limit 500")
        .bind(org).fetch_all(&s.pool).await?;
    Ok(Json(
        rows.into_iter()
            .map(|(team_id, name)| TraceTeamOption { team_id, name })
            .collect(),
    ))
}
#[derive(Deserialize, utoipa::IntoParams)]
#[into_params(parameter_in = Query)]
struct Page {
    limit: Option<i64>,
    cursor: Option<String>,
}
#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),Page),responses((status=200,body=ConversationTraceDetail)))]
async fn get_conversation_trace(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(page): ApiQuery<Page>,
    headers: HeaderMap,
) -> AppResult<Json<ConversationTraceDetail>> {
    let c = authorized(&s, &user.uid, org, session).await?;
    detail(&s, &c, page, &headers).await.map(Json)
}
async fn detail(
    s: &AppState,
    c: &Conversation,
    page: Page,
    headers: &HeaderMap,
) -> AppResult<ConversationTraceDetail> {
    let limit = page.limit.unwrap_or(50);
    if !(1..=100).contains(&limit) {
        return Err(AppError::Unprocessable("Invalid trace page".into()));
    }
    let after = match page.cursor {
        Some(v) => Some(
            serde_json::from_str::<(i32, String)>(&v)
                .map_err(|_| AppError::Unprocessable("Invalid trace cursor".into()))?,
        ),
        None => None,
    };
    let captures:Vec<ingest::Capture>=sqlx::query_as("select id,session_id,organization_id,exchange_id,history_rank,started_at from conversation_trace where session_id=$1 and not retired and expires_at>clock_timestamp() and ($2::integer is null or (history_rank,exchange_id)>($2,$3)) order by history_rank,exchange_id limit $4")
        .bind(c.session_id).bind(after.as_ref().map(|v|v.0)).bind(after.as_ref().map(|v|&v.1)).bind(limit+1).fetch_all(&s.pool).await?;
    let consent = consent(&s.pool, c.session_id).await?;
    let mut turns = Vec::new();
    let mut ranks: std::collections::BTreeMap<String, i64> = captures
        .iter()
        .map(|v| (v.exchange_id.clone(), i64::from(v.history_rank)))
        .collect();
    for capture in captures {
        let segments = facts(&s.pool, capture.id).await?;
        let latest = segments.last().cloned().unwrap_or(json!({}));
        let duration = segments
            .iter()
            .filter_map(|v| v["duration_ms"].as_i64())
            .sum::<i64>();
        let has_evidence = segments.iter().any(|v| !v["storage"].is_null());
        let partial = segments
            .iter()
            .any(|v| v["http_incomplete"].as_bool() == Some(true) || !v["degradation"].is_null());
        let pending = segments
            .iter()
            .any(|v| v["evidence_pending"].as_bool() == Some(true));
        let call_ids: std::collections::BTreeSet<String> = segments
            .iter()
            .filter_map(|v| v["call_ids"].as_array())
            .flatten()
            .filter_map(|v| v.as_str().map(str::to_owned))
            .collect();
        let access = if covers(
            consent.as_ref(),
            &capture.exchange_id,
            capture.history_rank.into(),
        ) {
            TraceContentAccess::Shared
        } else {
            TraceContentAccess::Masked
        };
        turns.push(ConversationTraceTurn {
            exchange_id: capture.exchange_id.clone(),
            turn_number: latest["turn_number"].as_i64(),
            started_at: capture.started_at,
            duration_ms: Some(duration),
            outcome: decode(latest.get("outcome").cloned().unwrap_or(json!("unknown")))?,
            checkpoint_status: decode(
                latest
                    .get("checkpoint_status")
                    .cloned()
                    .unwrap_or(json!("unknown")),
            )?,
            failure_category: decode(
                latest
                    .get("failure_category")
                    .cloned()
                    .unwrap_or(Value::Null),
            )?,
            availability: if has_evidence {
                if partial {
                    TraceAvailability::Partial
                } else {
                    TraceAvailability::Captured
                }
            } else {
                TraceAvailability::MetadataOnly
            },
            capture_status: Some(
                if pending {
                    "saving"
                } else if partial {
                    "partial"
                } else {
                    "complete"
                }
                .into(),
            ),
            degradation_reason: decode(latest.get("degradation").cloned().unwrap_or(Value::Null))?,
            call_ids: call_ids.into_iter().collect(),
            trace_id: latest["trace_id"].as_str().map(str::to_owned),
            span_id: latest["span_id"].as_str().map(str::to_owned),
            access,
            retained_cutoff: None,
            support_error_ref: latest["support_error_ref"].as_str().map(str::to_owned),
            reported_failures: vec![],
        });
    }
    if grant(consent.as_ref())?.is_some() {
        let mut params = vec![("limit", (limit + 1).to_string())];
        if let Some((rank, exchange)) = &after {
            params.push(("after_rank", rank.to_string()));
            params.push(("after_exchange", exchange.clone()));
        }
        let retained = match runtime_read(s, c, headers, "trace-history-turns", &params).await {
            Ok(value) => decode::<Vec<TraceHistoryBoundary>>(value)?,
            Err(AppError::Unavailable(_)) => vec![],
            Err(error) => return Err(error),
        };
        // This independent read must not release an old title or consent snapshot.
        conversation(&s.pool, c.session_id).await?;
        if wire(grant(consent.as_ref())?)?
            != wire(grant(
                super::consent(&s.pool, c.session_id).await?.as_ref(),
            )?)?
        {
            return Err(AppError::Forbidden);
        }
        for boundary in retained {
            if !covers(consent.as_ref(), &boundary.exchange_id, boundary.first_rank) {
                continue;
            }
            ranks.insert(boundary.exchange_id.clone(), boundary.first_rank);
            if let Some(turn) = turns
                .iter_mut()
                .find(|v| v.exchange_id == boundary.exchange_id)
            {
                turn.retained_cutoff = Some(boundary);
            } else {
                turns.push(history_turn(boundary, None));
            }
        }
    }
    if let Some(incidents) = consent.as_ref().and_then(|v| v.incidents.as_array()) {
        for raw in incidents {
            let incident: TraceHistoryIncident = decode(raw.clone())?;
            if let Some(turn) = turns
                .iter_mut()
                .find(|v| v.exchange_id == incident.cutoff.exchange_id)
            {
                turn.retained_cutoff = Some(incident.cutoff.clone());
                turn.reported_failures.push(TraceReportedFailure {
                    support_error_ref: incident.support_error_ref,
                    failure_category: incident.failure_category,
                });
            } else if after.as_ref().is_none_or(|(rank, exchange)| {
                (
                    incident.cutoff.first_rank,
                    incident.cutoff.exchange_id.as_str(),
                ) > (i64::from(*rank), exchange.as_str())
            }) {
                ranks.insert(
                    incident.cutoff.exchange_id.clone(),
                    incident.cutoff.first_rank,
                );
                turns.push(ConversationTraceTurn {
                    exchange_id: incident.cutoff.exchange_id.clone(),
                    turn_number: Some(incident.cutoff.turn_number),
                    started_at: incident.cutoff.started_at,
                    duration_ms: None,
                    outcome: TraceOutcome::Failed,
                    checkpoint_status: TraceCheckpointStatus::Unknown,
                    failure_category: incident.failure_category,
                    availability: TraceAvailability::HistoryOnly,
                    capture_status: None,
                    degradation_reason: None,
                    call_ids: vec![],
                    trace_id: None,
                    span_id: None,
                    access: TraceContentAccess::Shared,
                    retained_cutoff: Some(incident.cutoff),
                    support_error_ref: Some(incident.support_error_ref),
                    reported_failures: vec![],
                });
            }
        }
    }
    turns.sort_by(|a, b| {
        (ranks.get(&a.exchange_id), &a.exchange_id)
            .cmp(&(ranks.get(&b.exchange_id), &b.exchange_id))
    });
    let more = turns.len() > limit as usize;
    turns.truncate(limit as usize);
    let next_cursor = if more {
        turns
            .last()
            .map(|v| json!([ranks.get(&v.exchange_id), v.exchange_id]).to_string())
    } else {
        None
    };
    Ok(ConversationTraceDetail {
        session_id: c.session_id.to_string(),
        title: consent
            .as_ref()
            .filter(|v| v.cutoff.is_some() && v.title == c.title)
            .and_then(|_| c.title.clone()),
        agent_display_name: c.agent_display_name.clone(),
        team_id: c.space_id.to_string(),
        turns,
        next_cursor,
        consent_cutoff: grant(consent.as_ref())?.map(|v| v.cutoff),
        consent_version: consent.as_ref().map(|v| v.version.to_string()),
        can_renew_title_consent: false,
        local_content_access: false,
        retained_after_delete: false,
    })
}
fn history_turn(
    boundary: TraceHistoryBoundary,
    failure: Option<TraceFailureCategory>,
) -> ConversationTraceTurn {
    ConversationTraceTurn {
        exchange_id: boundary.exchange_id.clone(),
        turn_number: Some(boundary.turn_number),
        started_at: boundary.started_at,
        duration_ms: None,
        outcome: if failure.is_some() {
            TraceOutcome::Failed
        } else {
            TraceOutcome::Unknown
        },
        checkpoint_status: TraceCheckpointStatus::Unknown,
        failure_category: failure,
        availability: TraceAvailability::HistoryOnly,
        capture_status: None,
        degradation_reason: None,
        call_ids: vec![],
        trace_id: None,
        span_id: None,
        access: TraceContentAccess::Shared,
        retained_cutoff: Some(boundary),
        support_error_ref: None,
        reported_failures: vec![],
    }
}
#[derive(Deserialize, utoipa::IntoParams)]
#[into_params(parameter_in = Query)]
struct HistoryQuery {
    runtime_id: Option<String>,
    exchange_id: Option<String>,
    after_rank: Option<i64>,
    limit: Option<i64>,
}
async fn history_access(
    s: &AppState,
    actor: &str,
    c: &Conversation,
    q: &HistoryQuery,
) -> AppResult<TraceHistoryAccess> {
    observer(s, actor, c.organization_id).await?;
    if q.runtime_id.as_ref().is_some_and(|v| v != &c.runtime_id) {
        return Err(AppError::Forbidden);
    }
    let consent = consent(&s.pool, c.session_id).await?;
    let grant = grant(consent.as_ref())?.ok_or(AppError::Forbidden)?;
    let mut cutoff = grant.cutoff.clone();
    if let Some(exchange) = &q.exchange_id
        && let Ok(capture) = ingest::capture(&s.pool, c.session_id, exchange).await
        && !covers(consent.as_ref(), exchange, capture.history_rank.into())
    {
        return Err(AppError::Forbidden);
    }
    // The runtime verifies an uncaptured exchange's own durable history boundary.
    // The runtime clips transcript reads to this immutable owner-approved boundary.
    cutoff.last_rank = cutoff.last_rank.min(i32::MAX.into());
    Ok(TraceHistoryAccess {
        owner_id: c.user_id.clone(),
        cutoff: Some(cutoff),
        grant_id: Some(grant.grant_id),
        local_content_access: false,
        captured_rank: None,
    })
}
#[utoipa::path(get,path="/admin/conversation-traces/{session_id}/history-access",params(("session_id"=Uuid,Path),HistoryQuery),responses((status=200,body=TraceHistoryAccess)))]
async fn get_conversation_trace_history_access(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(session): ApiPath<Uuid>,
    ApiQuery(q): ApiQuery<HistoryQuery>,
) -> AppResult<Json<TraceHistoryAccess>> {
    let c = conversation(&s.pool, session).await?;
    history_access(&s, &user.uid, &c, &q).await.map(Json)
}
#[derive(Deserialize, utoipa::IntoParams)]
#[into_params(parameter_in=Query)]
struct HistoryPage {
    after_rank: Option<i64>,
    limit: Option<i64>,
}
#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/{session_id}/history/{exchange_id}",params(("organization_id"=Uuid,Path),("session_id"=Uuid,Path),("exchange_id"=String,Path),HistoryPage),responses((status=200,body=TraceHistoryTranscript)))]
async fn get_conversation_trace_history(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((org, session, exchange)): ApiPath<(Uuid, Uuid, String)>,
    ApiQuery(page): ApiQuery<HistoryPage>,
    headers: HeaderMap,
) -> AppResult<Json<TraceHistoryTranscript>> {
    let c = authorized(&s, &user.uid, org, session).await?;
    if !valid_id(&exchange, 255) {
        return Err(AppError::NotFound);
    }
    let q = HistoryQuery {
        runtime_id: None,
        exchange_id: Some(exchange.clone()),
        after_rank: page.after_rank,
        limit: page.limit,
    };
    let access = wire(history_access(&s, &user.uid, &c, &q).await?)?;
    let mut params = vec![];
    if let Some(v) = q.after_rank {
        if v < -1 {
            return Err(AppError::Unprocessable("Invalid history rank".into()));
        }
        params.push(("after_rank", v.to_string()));
    }
    if let Some(v) = q.limit {
        if !(1..=100).contains(&v) {
            return Err(AppError::Unprocessable("Invalid history limit".into()));
        }
        params.push(("limit", v.to_string()));
    }
    if let Some(v) = &q.exchange_id {
        params.push(("exchange_id", v.clone()));
    }
    let result = runtime_read(
        &s,
        &c,
        &headers,
        &format!("trace-history-turns/{exchange}"),
        &params,
    )
    .await?;
    let fresh = conversation(&s.pool, session).await?;
    if access != wire(history_access(&s, &user.uid, &fresh, &q).await?)? {
        return Err(AppError::Forbidden);
    }
    Ok(Json(decode(result)?))
}
