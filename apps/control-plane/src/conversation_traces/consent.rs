// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(get_trace_consent))
        .routes(utoipa_axum::routes!(set_trace_consent))
        .routes(utoipa_axum::routes!(revoke_trace_consent))
        .routes(utoipa_axum::routes!(get_trace_incident_offer))
        .routes(utoipa_axum::routes!(share_trace_incident))
}
async fn owner(s: &AppState, user: &str, space: Uuid, session: Uuid) -> AppResult<Conversation> {
    crate::sessions::require_owner(&s.pool, user, space, session).await?;
    conversation(&s.pool, session).await
}
fn state(
    c: Option<&Consent>,
    cutoff: Option<TraceHistoryBoundary>,
    unavailable: bool,
) -> AppResult<TraceConsentState> {
    Ok(TraceConsentState {
        consent: grant(c)?,
        consent_version: c.map(|v| v.version.to_string()),
        available_cutoff: cutoff,
        history_unavailable: unavailable,
    })
}
#[utoipa::path(get,path="/spaces/{space_id}/sessions/{session_id}/trace-consent",params(("space_id"=Uuid,Path),("session_id"=Uuid,Path)),responses((status=200,body=TraceConsentState)))]
async fn get_trace_consent(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, session)): ApiPath<(Uuid, Uuid)>,
    headers: HeaderMap,
) -> AppResult<Json<TraceConsentState>> {
    let c = owner(&s, &user.uid, space, session).await?;
    let boundary = runtime_read(&s, &c, &headers, "trace-history-boundary", &[]).await;
    owner(&s, &user.uid, space, session).await?;
    let current = consent(&s.pool, session).await?;
    let unavailable = boundary.is_err();
    let cutoff = match boundary {
        Ok(v) if !v.is_null() => Some(decode(v)?),
        _ => None,
    };
    Ok(Json(state(current.as_ref(), cutoff, unavailable)?))
}
#[utoipa::path(put,path="/spaces/{space_id}/sessions/{session_id}/trace-consent",params(("space_id"=Uuid,Path),("session_id"=Uuid,Path)),request_body=TraceConsentRequest,responses((status=200,body=TraceConsentState)))]
async fn set_trace_consent(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, session)): ApiPath<(Uuid, Uuid)>,
    headers: HeaderMap,
    ApiJson(body): ApiJson<TraceConsentRequest>,
) -> AppResult<Json<TraceConsentState>> {
    let c = owner(&s, &user.uid, space, session).await?;
    let cutoff: TraceHistoryBoundary = decode(
        runtime_read(
            &s,
            &c,
            &headers,
            "trace-history-boundary",
            &[("exchange_id", body.exchange_id.clone())],
        )
        .await?,
    )?;
    let share_title = title_covered(&s, &c, &headers, &cutoff).await;
    save(&s, &user.uid, &c, body, cutoff, None, share_title)
        .await
        .map(Json)
}
async fn save(
    s: &AppState,
    actor: &str,
    c: &Conversation,
    body: TraceConsentRequest,
    cutoff: TraceHistoryBoundary,
    incident: Option<TraceHistoryIncident>,
    share_title: bool,
) -> AppResult<TraceConsentState> {
    if cutoff.exchange_id != body.exchange_id
        || cutoff.last_rank != body.last_rank
        || cutoff.first_rank < 0
        || cutoff.last_rank < cutoff.first_rank
    {
        return Err(AppError::Conflict("trace_consent_turn_changed".into()));
    }
    let mut tx = crate::sessions::lock_owner(&s.pool, actor, c.space_id, c.session_id).await?;
    let previous:Option<Consent>=sqlx::query_as("select version,cutoff,title,incidents from conversation_trace_consent where session_id=$1 for update")
        .bind(c.session_id).fetch_optional(&mut *tx).await?;
    if previous.as_ref().map(|v| v.version.to_string()) != body.expected_version {
        return Err(AppError::Conflict("trace_consent_changed".into()));
    }
    if previous
        .as_ref()
        .and_then(|v| v.cutoff.as_ref())
        .and_then(|v| v["last_rank"].as_i64())
        .is_some_and(|v| v > cutoff.last_rank)
    {
        return Err(AppError::Conflict("trace_consent_does_not_extend".into()));
    }
    let mut incidents = previous
        .as_ref()
        .and_then(|v| v.incidents.as_array())
        .cloned()
        .unwrap_or_default();
    if let Some(incident) = incident
        && !incidents
            .iter()
            .any(|v| v["support_error_ref"] == incident.support_error_ref)
    {
        if incidents.len() >= 100 {
            return Err(AppError::Unprocessable(
                "Too many reported incidents".into(),
            ));
        }
        incidents.push(wire(incident)?);
    }
    let version = Uuid::new_v4();
    // A renamed title is shared only when this owner explicitly renews consent.
    let current_title: Option<String> =
        sqlx::query_scalar("select title from session_metadata where session_id=$1")
            .bind(c.session_id)
            .fetch_one(&mut *tx)
            .await?;
    let title = if share_title && current_title == c.title {
        current_title
    } else {
        None
    };
    sqlx::query("insert into conversation_trace_consent(session_id,version,cutoff,title,incidents,expires_at) values($1,$2,$3,$4,$5,clock_timestamp()+make_interval(days=>coalesce((select p.retention_days from session_metadata m join space s on s.id=m.space_id left join conversation_trace_settings p on p.organization_id=s.organization_id where m.session_id=$1),30))) on conflict(session_id) do update set version=excluded.version,cutoff=excluded.cutoff,title=excluded.title,incidents=excluded.incidents,updated_at=clock_timestamp(),expires_at=excluded.expires_at")
        .bind(c.session_id).bind(version).bind(wire(&cutoff)?).bind(&title).bind(json!(incidents)).execute(&mut *tx).await?;
    tx.commit().await?;
    tracing::info!(session_id=%c.session_id,actor,grant_id=%version,"conversation_trace.consent.granted");
    Ok(TraceConsentState {
        consent: Some(TraceConsentGrant {
            grant_id: version.to_string(),
            cutoff: cutoff.clone(),
        }),
        consent_version: Some(version.to_string()),
        available_cutoff: Some(cutoff),
        history_unavailable: false,
    })
}
#[utoipa::path(delete,path="/spaces/{space_id}/sessions/{session_id}/trace-consent",params(("space_id"=Uuid,Path),("session_id"=Uuid,Path)),responses((status=204)))]
async fn revoke_trace_consent(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, session)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<StatusCode> {
    let mut tx = crate::sessions::lock_owner(&s.pool, &user.uid, space, session).await?;
    sqlx::query("insert into conversation_trace_consent(session_id,version) values($1,$2) on conflict(session_id) do update set version=excluded.version,cutoff=null,title=null,incidents='[]',updated_at=clock_timestamp()")
        .bind(session).bind(Uuid::new_v4()).execute(&mut *tx).await?;
    tx.commit().await?;
    tracing::info!(session_id=%session,actor=%user.uid,"conversation_trace.consent.revoked");
    Ok(StatusCode::NO_CONTENT)
}
async fn incident(
    s: &AppState,
    user: &str,
    space: Uuid,
    session: Uuid,
    error: &str,
    headers: &HeaderMap,
) -> AppResult<(Conversation, TraceHistoryIncident)> {
    if error.len() != 32
        || !error
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return Err(AppError::NotFound);
    }
    let c = owner(s, user, space, session).await?;
    let incident: TraceHistoryIncident = decode(
        runtime_read(
            s,
            &c,
            headers,
            &format!("trace-history-incident/{error}"),
            &[],
        )
        .await?,
    )?;
    if incident.support_error_ref != error {
        return Err(AppError::NotFound);
    }
    Ok((c, incident))
}
#[utoipa::path(get,path="/spaces/{space_id}/sessions/{session_id}/trace-incident/{error_ref}",params(("space_id"=Uuid,Path),("session_id"=Uuid,Path),("error_ref"=String,Path)),responses((status=200,body=TraceIncidentOffer)))]
async fn get_trace_incident_offer(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, session, error)): ApiPath<(Uuid, Uuid, String)>,
    headers: HeaderMap,
) -> AppResult<Json<TraceIncidentOffer>> {
    let (_, incident) = incident(&s, &user.uid, space, session, &error, &headers).await?;
    owner(&s, &user.uid, space, session).await?;
    let c = consent(&s.pool, session).await?;
    let available = ingest::capture(&s.pool, session, &incident.cutoff.exchange_id)
        .await
        .is_ok();
    let reported = c
        .as_ref()
        .and_then(|v| v.incidents.as_array())
        .is_some_and(|v| v.iter().any(|i| i["support_error_ref"] == error));
    Ok(Json(TraceIncidentOffer {
        cutoff: incident.cutoff,
        consent_version: c.as_ref().map(|v| v.version.to_string()),
        consent_cutoff: grant(c.as_ref())?.map(|v| v.cutoff),
        capture_available: available,
        reported,
    }))
}
#[utoipa::path(put,path="/spaces/{space_id}/sessions/{session_id}/trace-incident/{error_ref}",params(("space_id"=Uuid,Path),("session_id"=Uuid,Path),("error_ref"=String,Path)),request_body=TraceConsentRequest,responses((status=200,body=TraceConsentState)))]
async fn share_trace_incident(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, session, error)): ApiPath<(Uuid, Uuid, String)>,
    headers: HeaderMap,
    ApiJson(body): ApiJson<TraceConsentRequest>,
) -> AppResult<Json<TraceConsentState>> {
    let (c, incident) = incident(&s, &user.uid, space, session, &error, &headers).await?;
    let share_title = title_covered(&s, &c, &headers, &incident.cutoff).await;
    save(
        &s,
        &user.uid,
        &c,
        body,
        incident.cutoff.clone(),
        Some(incident),
        share_title,
    )
    .await
    .map(Json)
}

async fn title_covered(
    s: &AppState,
    c: &Conversation,
    headers: &HeaderMap,
    cutoff: &TraceHistoryBoundary,
) -> bool {
    let Ok(latest) = runtime_read(s, c, headers, "trace-history-boundary", &[]).await else {
        return false;
    };
    latest["exchange_id"] == cutoff.exchange_id && latest["last_rank"] == cutoff.last_rank
}
