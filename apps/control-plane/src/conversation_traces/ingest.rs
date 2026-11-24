// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(admit_trace_turn))
        .routes(utoipa_axum::routes!(reconcile_trace_admission))
        .routes(utoipa_axum::routes!(finalize_trace_turn))
        .routes(utoipa_axum::routes!(reserve_trace_storage))
        .routes(utoipa_axum::routes!(settle_incremental_trace_storage))
        .routes(utoipa_axum::routes!(claim_trace_storage_cleanup))
        .routes(utoipa_axum::routes!(acknowledge_trace_storage_cleanup))
        .routes(utoipa_axum::routes!(get_trace_owner_hidden_sessions))
        .layer(axum::extract::DefaultBodyLimit::max(16 * 1024 * 1024))
}
fn worker(s: &AppState, caller: &crate::auth::CurrentUser, runtime: &str) -> AppResult<()> {
    crate::capability_preparation::worker(s, caller, runtime)
}
#[derive(sqlx::FromRow)]
pub(super) struct Capture {
    pub id: Uuid,
    pub session_id: Uuid,
    pub organization_id: Uuid,
    pub exchange_id: String,
    pub history_rank: i32,
    pub started_at: DateTime<Utc>,
}
pub(super) async fn capture(pool: &PgPool, session: Uuid, exchange: &str) -> AppResult<Capture> {
    sqlx::query_as("select id,session_id,organization_id,exchange_id,history_rank,started_at from conversation_trace where session_id=$1 and exchange_id=$2 and not retired and expires_at>clock_timestamp()")
        .bind(session).bind(exchange).fetch_optional(pool).await?.ok_or(AppError::NotFound)
}
async fn writable(
    tx: &mut Transaction<'_, Postgres>,
    runtime: &str,
    id: Uuid,
) -> AppResult<Capture> {
    // Match session retirement's row order: session first, then its diagnostic row.
    // A publisher must not insert objects after the retirement trigger has run.
    sqlx::query_scalar::<_,Uuid>("select m.session_id from session_metadata m join conversation_trace t on t.session_id=m.session_id where t.id=$1 and t.runtime_id=$2 and m.deletion_id is null for share of m")
        .bind(id).bind(runtime).fetch_optional(&mut **tx).await?.ok_or_else(conflict)?;
    sqlx::query_as("select t.id,t.session_id,t.organization_id,t.exchange_id,t.history_rank,t.started_at from conversation_trace t join session_metadata m on m.session_id=t.session_id join space s on s.id=m.space_id join space o on o.id=s.organization_id where t.id=$1 and t.runtime_id=$2 and not t.retired and t.expires_at>clock_timestamp() and m.deletion_id is null and s.deletion_id is null and o.deletion_id is null for update of t")
        .bind(id).bind(runtime).fetch_optional(&mut **tx).await?.ok_or_else(conflict)
}
#[utoipa::path(post,path="/internal/runtimes/{runtime_id}/conversation-traces/admit",params(("runtime_id"=String,Path)),request_body=TraceAdmissionRequest,responses((status=200,body=Option<TraceAdmission>)))]
async fn admit_trace_turn(
    State(s): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath(runtime): ApiPath<String>,
    headers: HeaderMap,
    ApiJson(body): ApiJson<TraceAdmissionRequest>,
) -> AppResult<Json<Option<TraceAdmission>>> {
    worker(&s, &caller, &runtime)?;
    let segment = headers
        .get("x-fred-trace-segment")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| Uuid::parse_str(v).ok())
        .ok_or_else(|| AppError::BadRequest("Trace segment required".into()))?;
    Ok(Json(admit(&s, &runtime, body, segment).await?))
}
async fn admit(
    s: &AppState,
    runtime: &str,
    body: TraceAdmissionRequest,
    segment: Uuid,
) -> AppResult<Option<TraceAdmission>> {
    let session = Uuid::parse_str(&body.session_id).map_err(|_| AppError::NotFound)?;
    let instance = Uuid::parse_str(&body.agent_instance_id).map_err(|_| AppError::NotFound)?;
    if !valid_id(&body.exchange_id, 255) || !(0..=i32::MAX as i64).contains(&body.history_rank) {
        return Err(AppError::Unprocessable("Invalid trace identity".into()));
    }
    let mut tx = s.pool.begin().await?;
    let org:Uuid=sqlx::query_scalar("select s.organization_id from session_metadata m join space s on s.id=m.space_id join space o on o.id=s.organization_id where m.session_id=$1 and m.runtime_id=$2 and m.user_id=$3 and m.agent_instance_id=$4 and m.deletion_id is null and s.deletion_id is null and o.deletion_id is null for share of m")
        .bind(session).bind(runtime).bind(&body.user_id).bind(instance).fetch_optional(&mut *tx).await?.ok_or(AppError::NotFound)?;
    let policy:Option<(bool,i32,i32)>=sqlx::query_as("select enabled,sampling_percent,retention_days from conversation_trace_settings where organization_id=$1 for share")
        .bind(org).fetch_optional(&mut *tx).await?;
    let Some((enabled, sampling, days)) = policy else {
        return Ok(None);
    };
    // Stable UUID sampling keeps resumes of the same conversation together.
    if !enabled || (session.as_u128() % 100) >= sampling as u128 {
        return Ok(None);
    }
    let id:Uuid=sqlx::query_scalar("insert into conversation_trace(id,session_id,organization_id,runtime_id,exchange_id,history_rank,expires_at) values($1,$2,$3,$4,$5,$6,clock_timestamp()+make_interval(days=>$7)) on conflict(session_id,exchange_id) do update set history_rank=least(conversation_trace.history_rank,excluded.history_rank) where not conversation_trace.retired and conversation_trace.expires_at>clock_timestamp() returning id")
        .bind(Uuid::new_v4()).bind(session).bind(org).bind(runtime).bind(&body.exchange_id).bind(body.history_rank).bind(days).fetch_optional(&mut *tx).await?.ok_or_else(conflict)?;
    let existing: Option<Uuid> =
        sqlx::query_scalar("select capture_id from conversation_trace_segment where id=$1")
            .bind(segment)
            .fetch_optional(&mut *tx)
            .await?;
    if existing.is_some_and(|v| v != id) {
        return Err(conflict());
    }
    sqlx::query("insert into conversation_trace_segment(id,capture_id) values($1,$2) on conflict do nothing").bind(segment).bind(id).execute(&mut *tx).await?;
    let offset:i64=sqlx::query_scalar("select coalesce(sum((facts->>'duration_ms')::bigint),0)::bigint from conversation_trace_segment where capture_id=$1 and id<>$2")
        .bind(id).bind(segment).fetch_one(&mut *tx).await?;
    tx.commit().await?;
    Ok(Some(TraceAdmission {
        capture_id: id.to_string(),
        segment_id: Some(segment),
        stream_offset_ms: offset.min(i32::MAX.into()),
        streaming_blocks: true,
    }))
}
#[utoipa::path(put,path="/internal/runtimes/{runtime_id}/conversation-traces/reconcile/{segment_id}",params(("runtime_id"=String,Path),("segment_id"=Uuid,Path)),request_body=TraceAdmissionReconciliation,responses((status=204)))]
async fn reconcile_trace_admission(
    State(s): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath((runtime, segment)): ApiPath<(String, Uuid)>,
    ApiJson(body): ApiJson<TraceAdmissionReconciliation>,
) -> AppResult<StatusCode> {
    worker(&s, &caller, &runtime)?;
    // Reconciliation only completes a segment that the original admission created.
    // It cannot enable capture after policy changed or revive erased evidence.
    let capture:Uuid=sqlx::query_scalar("select t.id from conversation_trace t join conversation_trace_segment g on g.capture_id=t.id join session_metadata m on m.session_id=t.session_id where g.id=$1 and t.runtime_id=$2 and t.session_id::text=$3 and t.exchange_id=$4 and m.user_id=$5 and m.agent_instance_id::text=$6")
        .bind(segment).bind(&runtime).bind(&body.admission.session_id).bind(&body.admission.exchange_id).bind(&body.admission.user_id).bind(&body.admission.agent_instance_id).fetch_optional(&s.pool).await?.ok_or_else(conflict)?;
    let mut facts = wire(body.facts)?;
    facts["segment_id"] = json!(segment);
    finalize(&s, &runtime, capture, decode(facts)?).await?;
    Ok(StatusCode::NO_CONTENT)
}
fn validate_facts(body: &TraceFinalization) -> AppResult<()> {
    if body.duration_ms < 0
        || body.duration_ms > i32::MAX.into()
        || body.call_ids.iter().any(|v| !valid_id(v, 255))
    {
        return Err(AppError::Unprocessable("Trace index exceeds bounds".into()));
    }
    let hex = |v: &str, n: usize| {
        v.len() == n
            && v.bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    };
    if body.trace_id.as_ref().is_some_and(|v| !hex(v, 32))
        || body.span_id.as_ref().is_some_and(|v| !hex(v, 16))
        || body.otel_spans.iter().any(|v| {
            !hex(&v.trace_id, 32)
                || !hex(&v.span_id, 16)
                || (!v.parent_span_id.is_empty() && !hex(&v.parent_span_id, 16))
                || v.attributes.len() > 5
                || !valid_id(&v.name, 255)
        })
    {
        return Err(AppError::Unprocessable(
            "Invalid OpenTelemetry identity".into(),
        ));
    }
    Ok(())
}
#[utoipa::path(put,path="/internal/runtimes/{runtime_id}/conversation-traces/{capture_id}",params(("runtime_id"=String,Path),("capture_id"=Uuid,Path)),request_body=TraceFinalization,responses((status=204)))]
async fn finalize_trace_turn(
    State(s): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath((runtime, id)): ApiPath<(String, Uuid)>,
    ApiJson(body): ApiJson<TraceFinalization>,
) -> AppResult<StatusCode> {
    worker(&s, &caller, &runtime)?;
    finalize(&s, &runtime, id, body).await?;
    Ok(StatusCode::NO_CONTENT)
}
async fn finalize(s: &AppState, runtime: &str, id: Uuid, body: TraceFinalization) -> AppResult<()> {
    validate_facts(&body)?;
    let segment = body.segment_id.ok_or_else(conflict)?;
    let mut tx = s.pool.begin().await?;
    writable(&mut tx, runtime, id).await?;
    let complete_before: Option<bool> = sqlx::query_scalar(
        "select complete from conversation_trace_segment where id=$1 and capture_id=$2",
    )
    .bind(segment)
    .bind(id)
    .fetch_optional(&mut *tx)
    .await?;
    match complete_before {
        Some(true) => return Ok(()), // An acknowledged completion is immutable, including on a late degraded retry.
        None => return Err(conflict()),
        Some(false) => (),
    }
    if let Some(publication) = &body.storage {
        settle(&mut tx, id, publication).await?;
    }
    for (order, call) in body.model_calls.iter().enumerate() {
        if let Some(rank) = call.observed_through_rank {
            if !(0..=i64::from(i32::MAX)).contains(&rank)
                || call.observed_invalid_tools.len() > 32
                || call.related_tools.len() > 32
            {
                return Err(AppError::Unprocessable(
                    "Invalid model evidence index".into(),
                ));
            }
            for fingerprint in &call.observed_invalid_tools {
                sqlx::query("insert into conversation_trace_model_origin(segment_id,call_order,fingerprint,call_id,observed_through_rank) values($1,$2,$3,$4,$5) on conflict do nothing")
                    .bind(segment).bind(order as i64).bind(fingerprint).bind(&call.call_id).bind(rank).execute(&mut *tx).await?;
            }
        }
    }
    let complete = !body.evidence_pending;
    let changed=sqlx::query("update conversation_trace_segment set facts=$3,complete=$4 where id=$1 and capture_id=$2 and (not complete or $4)")
        .bind(segment).bind(id).bind(wire(&body)?).bind(complete).execute(&mut *tx).await?;
    if changed.rows_affected() == 0 {
        return Err(conflict());
    }
    tx.commit().await?;
    Ok(())
}
#[utoipa::path(post,path="/internal/runtimes/{runtime_id}/conversation-traces/{capture_id}/reserve",params(("runtime_id"=String,Path),("capture_id"=Uuid,Path)),request_body=TraceStorageReservation,responses((status=200,body=TraceStorageReservationState)))]
async fn reserve_trace_storage(
    State(s): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath((runtime, id)): ApiPath<(String, Uuid)>,
    ApiJson(body): ApiJson<TraceStorageReservation>,
) -> AppResult<Json<TraceStorageReservationState>> {
    worker(&s, &caller, &runtime)?;
    if body.objects.iter().any(|(k, v)| {
        k.len() != 32
            || !k
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
            || !(0..=16777216).contains(v)
    }) {
        return Err(AppError::Unprocessable("Invalid trace reservation".into()));
    }
    let segment = body.segment_id.ok_or_else(conflict)?;
    let mut tx = s.pool.begin().await?;
    // Policy updates lock settings before captures; publishers use the same order.
    let org: Uuid = sqlx::query_scalar(
        "select organization_id from conversation_trace where id=$1 and runtime_id=$2",
    )
    .bind(id)
    .bind(&runtime)
    .fetch_optional(&mut *tx)
    .await?
    .ok_or_else(conflict)?;
    let cap: i64 = sqlx::query_scalar("select storage_cap_bytes from conversation_trace_settings where organization_id=$1 for update")
        .bind(org).fetch_one(&mut *tx).await?;
    let capture = writable(&mut tx, &runtime, id).await?;
    let valid:bool=sqlx::query_scalar("select exists(select 1 from conversation_trace_segment where id=$1 and capture_id=$2 and not complete)").bind(segment).bind(id).fetch_one(&mut *tx).await?;
    if !valid {
        return Ok(Json(TraceStorageReservationState::Fenced));
    }
    let used:i64=sqlx::query_scalar("select coalesce(sum(coalesce(stored_bytes,reserved_bytes)),0)::bigint from conversation_trace_object where organization_id=$1").bind(capture.organization_id).fetch_one(&mut *tx).await?;
    let existing:Vec<(String,i64)>=sqlx::query_as("select ref,reserved_bytes from conversation_trace_object where capture_id=$1 and publication_id=$2").bind(id).bind(body.publication_id).fetch_all(&mut *tx).await?;
    if !existing.is_empty() {
        if existing
            .into_iter()
            .collect::<std::collections::BTreeMap<_, _>>()
            != body.objects
        {
            return Err(conflict());
        }
        return Ok(Json(TraceStorageReservationState::Reserved));
    }
    let requested = body.objects.values().sum::<i64>();
    if used + requested > cap {
        if requested <= cap {
            policy::retire_for_capacity(&mut tx, capture.organization_id, requested, Some(id))
                .await?;
        }
        tx.commit().await?;
        return Ok(Json(TraceStorageReservationState::Capacity));
    }
    for (reference, size) in &body.objects {
        sqlx::query("insert into conversation_trace_object(ref,capture_id,segment_id,publication_id,organization_id,runtime_id,session_id,reserved_bytes) values($1,$2,$3,$4,$5,$6,$7,$8)")
            .bind(reference).bind(id).bind(segment).bind(body.publication_id).bind(capture.organization_id).bind(&runtime).bind(capture.session_id).bind(size).execute(&mut *tx).await?;
    }
    tx.commit().await?;
    Ok(Json(TraceStorageReservationState::Reserved))
}
async fn settle(
    tx: &mut Transaction<'_, Postgres>,
    capture: Uuid,
    body: &TraceStoragePublication,
) -> AppResult<()> {
    for (reference, size) in &body.stored {
        let changed=sqlx::query("update conversation_trace_object set stored_bytes=$4 where ref=$1 and capture_id=$2 and publication_id=$3 and cleanup_after is null and $4 between 0 and reserved_bytes and (stored_bytes is null or stored_bytes=$4)")
            .bind(reference).bind(capture).bind(body.publication_id).bind(size).execute(&mut **tx).await?;
        if changed.rows_affected() != 1 {
            return Err(conflict());
        }
    }
    // A confirmed publication owns only its enumerated objects. Uncertain or missing
    // objects are retried by durable cleanup after outstanding PUT deadlines expire.
    let refs: Vec<&String> = body.stored.keys().collect();
    sqlx::query("update conversation_trace_object set cleanup_after=coalesce(cleanup_after,clock_timestamp()+interval '1 minute') where capture_id=$1 and publication_id=$2 and not(ref=any($3))")
        .bind(capture).bind(body.publication_id).bind(refs).execute(&mut **tx).await?;
    Ok(())
}
#[utoipa::path(put,path="/internal/runtimes/{runtime_id}/conversation-traces/{capture_id}/publications/{publication_id}",params(("runtime_id"=String,Path),("capture_id"=Uuid,Path),("publication_id"=Uuid,Path)),request_body=TraceStoragePublication,responses((status=204)))]
async fn settle_incremental_trace_storage(
    State(s): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath((runtime, id, publication)): ApiPath<(String, Uuid, Uuid)>,
    ApiJson(body): ApiJson<TraceStoragePublication>,
) -> AppResult<StatusCode> {
    worker(&s, &caller, &runtime)?;
    if body.publication_id != publication {
        return Err(conflict());
    }
    let mut tx = s.pool.begin().await?;
    writable(&mut tx, &runtime, id).await?;
    settle(&mut tx, id, &body).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}
#[utoipa::path(post,path="/internal/runtimes/{runtime_id}/conversation-traces/cleanup",params(("runtime_id"=String,Path)),responses((status=200,body=Option<TraceStorageCleanup>)))]
async fn claim_trace_storage_cleanup(
    State(s): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath(runtime): ApiPath<String>,
) -> AppResult<Json<Option<TraceStorageCleanup>>> {
    worker(&s, &caller, &runtime)?;
    let mut tx = s.pool.begin().await?;
    sqlx::query("delete from conversation_trace where id in (select id from conversation_trace where runtime_id=$1 and (retired or expires_at<=clock_timestamp()) order by expires_at limit 100 for update skip locked)")
        .bind(&runtime).execute(&mut *tx).await?;
    sqlx::query("update conversation_trace_consent set cutoff=null,title=null,incidents='[]' where session_id in(select c.session_id from conversation_trace_consent c join session_metadata m on m.session_id=c.session_id where m.runtime_id=$1 and c.cutoff is not null and c.expires_at<=clock_timestamp() order by c.expires_at limit 100 for update of c skip locked)")
        .bind(&runtime).execute(&mut *tx).await?;
    // Lost publisher acknowledgements cannot reserve capacity forever.
    sqlx::query("update conversation_trace_object set cleanup_after=clock_timestamp() where ref in(select ref from conversation_trace_object where runtime_id=$1 and cleanup_after is null and stored_bytes is null and reserved_at<clock_timestamp()-interval '2 minutes' limit 100 for update skip locked)")
        .bind(&runtime).execute(&mut *tx).await?;
    let row:Option<(String,Uuid,Uuid)>=sqlx::query_as("select ref,publication_id,session_id from conversation_trace_object where runtime_id=$1 and cleanup_after<=clock_timestamp() and (leased_until is null or leased_until<clock_timestamp()) order by cleanup_after limit 1 for update skip locked")
        .bind(&runtime).fetch_optional(&mut *tx).await?;
    let Some((reference, id, session)) = row else {
        tx.commit().await?;
        return Ok(Json(None));
    };
    let lease = Uuid::new_v4();
    sqlx::query("update conversation_trace_object set lease=$2,leased_until=clock_timestamp()+interval '1 minute' where ref=$1").bind(&reference).bind(lease).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(Some(TraceStorageCleanup {
        id,
        lease,
        session_id: session.to_string(),
        refs: vec![reference],
        measure: false,
    })))
}
#[utoipa::path(put,path="/internal/runtimes/{runtime_id}/conversation-traces/cleanup/{work_id}",params(("runtime_id"=String,Path),("work_id"=Uuid,Path)),request_body=TraceStorageCleanupResult,responses((status=204)))]
async fn acknowledge_trace_storage_cleanup(
    State(s): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath((runtime, id)): ApiPath<(String, Uuid)>,
    ApiJson(body): ApiJson<TraceStorageCleanupResult>,
) -> AppResult<StatusCode> {
    worker(&s, &caller, &runtime)?;
    if body.success {
        sqlx::query("delete from conversation_trace_object where runtime_id=$1 and publication_id=$2 and lease=$3 and cleanup_after is not null").bind(runtime).bind(id).bind(body.lease).execute(&s.pool).await?;
    } else {
        sqlx::query("update conversation_trace_object set leased_until=clock_timestamp()+interval '30 seconds' where runtime_id=$1 and publication_id=$2 and lease=$3").bind(runtime).bind(id).bind(body.lease).execute(&s.pool).await?;
    }
    Ok(StatusCode::NO_CONTENT)
}
#[utoipa::path(post,path="/internal/runtimes/{runtime_id}/conversation-traces/owner-hidden",params(("runtime_id"=String,Path)),request_body=TraceOwnerVisibilityRequest,responses((status=200,body=[String])))]
async fn get_trace_owner_hidden_sessions(
    State(s): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath(runtime): ApiPath<String>,
    ApiJson(body): ApiJson<TraceOwnerVisibilityRequest>,
) -> AppResult<Json<Vec<String>>> {
    worker(&s, &caller, &runtime)?;
    if body.session_ids.len() > 100 {
        return Err(AppError::Unprocessable("Too many sessions".into()));
    }
    let visible:Vec<String>=sqlx::query_scalar("select m.session_id::text from session_metadata m join space s on s.id=m.space_id join space o on o.id=s.organization_id where m.runtime_id=$1 and m.user_id=$2 and m.session_id::text=any($3) and m.deletion_id is null and s.deletion_id is null and o.deletion_id is null")
        .bind(runtime).bind(body.user_id).bind(&body.session_ids).fetch_all(&s.pool).await?;
    Ok(Json(
        body.session_ids
            .into_iter()
            .filter(|v| !visible.contains(v))
            .collect(),
    ))
}
