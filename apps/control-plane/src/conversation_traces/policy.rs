// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(get_conversation_trace_settings))
        .routes(utoipa_axum::routes!(set_conversation_trace_settings))
        .routes(utoipa_axum::routes!(delete_conversation_traces))
        .routes(utoipa_axum::routes!(flush_conversation_trace_captures))
}
pub(super) async fn settings(pool: &PgPool, org: Uuid) -> AppResult<ConversationTraceSettings> {
    let row: (bool,i32,i32,i64,i64,i64)=sqlx::query_as("select coalesce(s.enabled,false),coalesce(s.sampling_percent,100),
        coalesce(s.retention_days,30),coalesce(s.storage_cap_bytes,20000000000),
        coalesce((select sum(coalesce(stored_bytes,0))::bigint from conversation_trace_object where organization_id=$1),0),
        coalesce((select sum(case when stored_bytes is null then reserved_bytes else 0 end)::bigint from conversation_trace_object where organization_id=$1),0)
        from (select $1::uuid as id) o left join conversation_trace_settings s on s.organization_id=o.id")
        .bind(org).fetch_one(pool).await?;
    Ok(ConversationTraceSettings {
        enabled: row.0,
        sampling_percent: row.1.into(),
        retention_days: row.2.into(),
        storage_cap_bytes: row.3,
        used_bytes: row.4,
        reserved_bytes: row.5,
        degraded: row.4 + row.5 >= row.3,
        degradation_reason: if row.4 + row.5 >= row.3 {
            Some(TraceDegradation::Capacity)
        } else {
            None
        },
    })
}
async fn admin(s: &AppState, actor: &str, org: Uuid) -> AppResult<()> {
    authorization::authorize_organization(
        &s.pool,
        actor,
        org,
        SpacePermission::AdministerOrganization,
    )
    .await?;
    Ok(())
}
#[utoipa::path(get,path="/organizations/{organization_id}/conversation-traces/settings",params(("organization_id"=Uuid,Path)),responses((status=200,body=ConversationTraceSettings)))]
async fn get_conversation_trace_settings(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(org): ApiPath<Uuid>,
) -> AppResult<Json<ConversationTraceSettings>> {
    admin(&s, &user.uid, org).await?;
    Ok(Json(settings(&s.pool, org).await?))
}
#[utoipa::path(put,path="/organizations/{organization_id}/conversation-traces/settings",params(("organization_id"=Uuid,Path)),request_body=ConversationTraceSettingsUpdate,responses((status=200,body=ConversationTraceSettings)))]
async fn set_conversation_trace_settings(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(org): ApiPath<Uuid>,
    ApiJson(body): ApiJson<ConversationTraceSettingsUpdate>,
) -> AppResult<Json<ConversationTraceSettings>> {
    let (mut tx, _) = crate::spaces::authorized_mutation(
        &s.pool,
        &user.uid,
        org,
        SpacePermission::AdministerOrganization,
    )
    .await?;
    if body
        .sampling_percent
        .is_some_and(|v| !(0..=100).contains(&v))
        || body
            .retention_days
            .is_some_and(|v| !(1..=3650).contains(&v))
        || body
            .storage_cap_bytes
            .is_some_and(|v| !(1..=10_000_000_000_000).contains(&v))
    {
        return Err(AppError::Unprocessable("Invalid trace policy".into()));
    }
    sqlx::query("insert into conversation_trace_settings(organization_id) values($1) on conflict do nothing").bind(org).execute(&mut *tx).await?;
    sqlx::query("update conversation_trace_settings set enabled=coalesce($2,enabled),sampling_percent=coalesce($3,sampling_percent),retention_days=coalesce($4,retention_days),storage_cap_bytes=coalesce($5,storage_cap_bytes) where organization_id=$1")
        .bind(org).bind(body.enabled).bind(body.sampling_percent).bind(body.retention_days).bind(body.storage_cap_bytes).execute(&mut *tx).await?;
    // A shorter retention takes effect for existing evidence as well.
    sqlx::query("update conversation_trace t set expires_at=least(t.expires_at,t.started_at+make_interval(days=>s.retention_days)) from conversation_trace_settings s where t.organization_id=$1 and s.organization_id=t.organization_id")
        .bind(org).execute(&mut *tx).await?;
    sqlx::query("update conversation_trace_consent c set expires_at=least(c.expires_at,c.updated_at+make_interval(days=>p.retention_days)) from session_metadata m join space s on s.id=m.space_id join conversation_trace_settings p on p.organization_id=s.organization_id where c.session_id=m.session_id and s.organization_id=$1")
        .bind(org).execute(&mut *tx).await?;
    retire_for_capacity(&mut tx, org, 0, None).await?;
    tx.commit().await?;
    tracing::info!(organization_id=%org,actor=%user.uid,"conversation_trace.settings.updated");
    Ok(Json(settings(&s.pool, org).await?))
}
#[utoipa::path(post,path="/organizations/{organization_id}/conversation-traces/delete",params(("organization_id"=Uuid,Path)),request_body=DeleteConversationTracesRequest,responses((status=200,body=DeleteConversationTracesResult)))]
async fn delete_conversation_traces(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(org): ApiPath<Uuid>,
    ApiJson(body): ApiJson<DeleteConversationTracesRequest>,
) -> AppResult<Json<DeleteConversationTracesResult>> {
    if body.session_ids.is_empty() || body.session_ids.len() > 100 {
        return Err(AppError::Unprocessable(
            "Select 1 to 100 conversations".into(),
        ));
    }
    let ids = body
        .session_ids
        .iter()
        .map(|v| Uuid::parse_str(v).map_err(|_| AppError::Unprocessable("Invalid session".into())))
        .collect::<AppResult<Vec<_>>>()?;
    let (mut tx, _) = crate::spaces::authorized_mutation(
        &s.pool,
        &user.uid,
        org,
        SpacePermission::AdministerOrganization,
    )
    .await?;
    let removed: i64=sqlx::query_scalar("with removed as (delete from conversation_trace where organization_id=$1 and session_id=any($2) returning session_id), revoked as (delete from conversation_trace_consent c where c.session_id=any($2) and exists(select 1 from session_metadata m join space s on s.id=m.space_id where m.session_id=c.session_id and s.organization_id=$1) returning session_id) select count(distinct session_id) from (select session_id from removed union select session_id from revoked) affected")
        .bind(org).bind(ids).fetch_one(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(DeleteConversationTracesResult { removed }))
}
#[utoipa::path(delete,path="/organizations/{organization_id}/conversation-traces/captures",params(("organization_id"=Uuid,Path)),responses((status=200,body=DeleteConversationTracesResult)))]
async fn flush_conversation_trace_captures(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(org): ApiPath<Uuid>,
) -> AppResult<Json<DeleteConversationTracesResult>> {
    let (mut tx, _) = crate::spaces::authorized_mutation(
        &s.pool,
        &user.uid,
        org,
        SpacePermission::AdministerOrganization,
    )
    .await?;
    // Retire in-place; each runtime's bounded cleanup loop removes the catalogue batches.
    let removed: i64=sqlx::query_scalar("with retired as (update conversation_trace set retired=true,expires_at=clock_timestamp() where organization_id=$1 and not retired returning session_id) select count(distinct session_id) from retired")
        .bind(org).fetch_one(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(DeleteConversationTracesResult { removed }))
}

/// Reclaim old diagnostic captures when policy shrinks or a reservation would exceed
/// capacity. Already queued erasures count toward that target until their acknowledgement.
/// Shared conversations are retained after unshared ones; current publication is excluded.
pub(super) async fn retire_for_capacity(
    tx: &mut Transaction<'_, Postgres>,
    org: Uuid,
    requested: i64,
    exclude: Option<Uuid>,
) -> AppResult<()> {
    sqlx::query("with capacity as (
        select greatest(0,coalesce((select sum(coalesce(stored_bytes,reserved_bytes)) from conversation_trace_object where organization_id=$1 and cleanup_after is null),0)+$2-s.storage_cap_bytes) as need
        from conversation_trace_settings s where s.organization_id=$1
      ), charged as (
        select t.id,t.started_at,
          exists(select 1 from conversation_trace_consent c where c.session_id=t.session_id and c.cutoff is not null and c.expires_at>clock_timestamp()) as shared,
          sum(coalesce(o.stored_bytes,o.reserved_bytes)) as bytes
        from conversation_trace t join conversation_trace_object o on o.capture_id=t.id
        where t.organization_id=$1 and not t.retired and ($3::uuid is null or t.id<>$3) and o.cleanup_after is null
        group by t.id,t.started_at,t.session_id
      ), ranked as (select id,coalesce(sum(bytes) over(order by shared,started_at,id rows between unbounded preceding and 1 preceding),0) as before from charged)
      update conversation_trace t set retired=true,expires_at=clock_timestamp() where t.id in(select r.id from ranked r cross join capacity c where r.before<c.need)")
        .bind(org).bind(requested).bind(exclude).execute(&mut **tx).await?;
    // Queue object erasure immediately so retries don't evict the same amount again.
    sqlx::query("update conversation_trace_object o set cleanup_after=clock_timestamp()+interval '1 minute' from conversation_trace t where t.id=o.capture_id and t.organization_id=$1 and t.retired and o.cleanup_after is null")
        .bind(org).execute(&mut **tx).await?;
    Ok(())
}
