// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! A single optional attempt on the existing session row, fenced by manual rename.

use axum::{extract::State, http::StatusCode};
use serde::Deserialize;
use sqlx::PgPool;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    api::AppState,
    authorization::RuntimeCaller,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
};

/// Called only by actual admitted executions, never by preparation/catalog reads.
/// No retry after failure: eligibility is consumed even when no title model is usable.
pub(crate) async fn claim(
    pool: &PgPool,
    subject: &str,
    space: Uuid,
    session: Uuid,
    instance: Uuid,
    generate: bool,
) -> AppResult<Option<Uuid>> {
    let attempt = generate.then(Uuid::new_v4);
    let claimed: Option<Uuid> = sqlx::query_scalar(
        "update session_metadata set title_pending = false, title_attempt = $5
         where session_id = $1 and space_id = $2 and user_id = $3
             and agent_instance_id = $4 and deletion_id is null and title_pending
         returning session_id",
    )
    .bind(session)
    .bind(space)
    .bind(subject)
    .bind(instance)
    .bind(attempt)
    .fetch_optional(pool)
    .await?;
    Ok(claimed.and(attempt))
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct GeneratedTitle {
    pub subject_id: String,
    pub agent_instance_id: Uuid,
    pub attempt_id: Uuid,
    #[schema(min_length = 1, max_length = 80)]
    pub title: String,
}

/// Uses immutable admitted provenance, not refreshed organization/agent rights.
/// The row predicate still enforces resource deletion and the manual-rename fence.
pub(crate) async fn persist(
    pool: &PgPool,
    space: Uuid,
    session: Uuid,
    body: &GeneratedTitle,
) -> AppResult<bool> {
    if body.title.trim().is_empty()
        || body.title.chars().count() > 80
        || body.title.chars().any(char::is_control)
        || !body.title.chars().any(char::is_alphabetic)
    {
        return Err(AppError::Unprocessable("Invalid generated title.".into()));
    }
    let result = sqlx::query(
        "update session_metadata set title = $6, title_attempt = null
         where session_id = $1 and space_id = $2 and user_id = $3
             and agent_instance_id = $4 and title_attempt = $5 and deletion_id is null",
    )
    .bind(session)
    .bind(space)
    .bind(&body.subject_id)
    .bind(body.agent_instance_id)
    .bind(body.attempt_id)
    .bind(&body.title)
    .execute(pool)
    .await?;
    Ok(result.rows_affected() == 1)
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new().routes(utoipa_axum::routes!(record_title))
}

#[utoipa::path(post, path = "/spaces/{space_id}/sessions/{session_id}/generated-title",
    params(("space_id" = Uuid, Path), ("session_id" = Uuid, Path)), request_body = GeneratedTitle,
    responses((status = 204, description = "Applied"),
        (status = 409, description = "Attempt superseded, consumed or session removed", body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody), (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn record_title(
    State(state): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath((space, session)): ApiPath<(Uuid, Uuid)>,
    ApiJson(body): ApiJson<GeneratedTitle>,
) -> AppResult<StatusCode> {
    if !state.auth.accepts_runtime_delegation(&caller) {
        return Err(AppError::Forbidden);
    }
    if persist(&state.pool, space, session, &body).await? {
        Ok(StatusCode::NO_CONTENT)
    } else {
        Err(AppError::Conflict(
            "Title attempt is no longer applicable.".into(),
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    mod database {
        include!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/support/database.rs"
        ));
    }

    #[tokio::test]
    #[ignore = "needs disposable Postgres: CONTROL_PLANE_IT_POSTGRES"]
    async fn title_attempts_are_atomic_and_manual_rename_fences_identical_text() {
        let pool = database::database().await;
        let session = Uuid::new_v4();
        let space = Uuid::new_v4();
        let instance = Uuid::new_v4();
        sqlx::query(
            "insert into space(id,kind,name,organization_id) values($1,'organization','Titles',$1)",
        )
        .bind(space)
        .execute(&pool)
        .await
        .unwrap();
        sqlx::query("insert into agent_instance(agent_instance_id,space_id,template_id,source_runtime_id,source_agent_id,display_name,tuning,created_by,logical_name) values($1,$2,$1,'fixture','template','Fixture','{}','alice','fixture')")
            .bind(instance).bind(space).execute(&pool).await.unwrap();
        sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision,title,title_pending) values($1,'alice',$2,$3,$3,'fixture','Fixture',1,'Initial',true)")
            .bind(session).bind(space).bind(instance).execute(&pool).await.unwrap();
        assert!(
            claim(&pool, "bob", space, session, instance, true)
                .await
                .unwrap()
                .is_none()
        );
        assert!(
            claim(&pool, "alice", Uuid::new_v4(), session, instance, true)
                .await
                .unwrap()
                .is_none()
        );
        let (a, b) = tokio::join!(
            claim(&pool, "alice", space, session, instance, true),
            claim(&pool, "alice", space, session, instance, true),
        );
        let attempts: Vec<_> = [a.unwrap(), b.unwrap()].into_iter().flatten().collect();
        assert_eq!(attempts.len(), 1);
        let body = GeneratedTitle {
            subject_id: "alice".into(),
            agent_instance_id: instance,
            attempt_id: attempts[0],
            title: "A generated title".into(),
        };
        // A different process/connection writes the exact initial string. The
        // durable fence, not string inequality, decides which result may apply.
        sqlx::query("update session_metadata set title='Initial',title_pending=false,title_attempt=null where session_id=$1")
            .bind(session).execute(&pool).await.unwrap();
        assert!(!persist(&pool, space, session, &body).await.unwrap());
        assert!(
            claim(&pool, "alice", space, session, instance, true)
                .await
                .unwrap()
                .is_none()
        );
        sqlx::query("update session_metadata set title_attempt=$2 where session_id=$1")
            .bind(session)
            .bind(body.attempt_id)
            .execute(&pool)
            .await
            .unwrap();
        assert!(
            !persist(&pool, Uuid::new_v4(), session, &body)
                .await
                .unwrap()
        );
        assert!(persist(&pool, space, session, &body).await.unwrap());
        assert!(!persist(&pool, space, session, &body).await.unwrap());
        let resumed = Uuid::new_v4();
        sqlx::query("insert into session_metadata(session_id,user_id,space_id,agent_instance_id,template_id,runtime_id,agent_display_name,agent_configuration_revision,title,title_pending) values($1,'alice',$2,$3,$3,'fixture','Fixture',1,'Initial',true)")
            .bind(resumed).bind(space).bind(instance).execute(&pool).await.unwrap();
        // A resume, or an unusable admitted title model, consumes eligibility.
        assert!(
            claim(&pool, "alice", space, resumed, instance, false)
                .await
                .unwrap()
                .is_none()
        );
        assert!(
            claim(&pool, "alice", space, resumed, instance, true)
                .await
                .unwrap()
                .is_none()
        );
        let deletion = Uuid::new_v4();
        sqlx::query("insert into deletion(id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at) values($1,$2,'session',$3,$3,'alice',now(),now())")
            .bind(deletion).bind(session).bind(space).execute(&pool).await.unwrap();
        sqlx::query(
            "update session_metadata set deletion_id=$2,title_attempt=$3 where session_id=$1",
        )
        .bind(session)
        .bind(deletion)
        .bind(body.attempt_id)
        .execute(&pool)
        .await
        .unwrap();
        assert!(!persist(&pool, space, session, &body).await.unwrap());
        sqlx::query("delete from session_metadata where session_id=$1")
            .bind(session)
            .execute(&pool)
            .await
            .unwrap();
        assert!(!persist(&pool, space, session, &body).await.unwrap());
    }
}
