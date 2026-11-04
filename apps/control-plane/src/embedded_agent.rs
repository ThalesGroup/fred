// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! HTTP admission and SSE framing for the embedded agent library.

pub(crate) mod search;

use axum::{
    extract::State,
    http::{HeaderValue, StatusCode, header},
    response::{
        IntoResponse, Response, Sse,
        sse::{Event, KeepAlive},
    },
};
use fred_rust_agent::{ExecuteError, ExecuteRequest, RequestedTarget, RuntimeEvent, Usage};
use fred_rust_sdk::inference::ModelOfferKey;
use futures::{FutureExt, StreamExt};
use sqlx::PgPool;
use tracing::{Instrument, Span};
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use crate::{
    agent_instances,
    api::AppState,
    error::{AppError, AppResult},
    extract::ApiJson,
    onboarding::AdmittedUser,
    sessions::{ModelUsage, UsageReport, persist_usage},
};

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(execute_stream))
}

/// Embedded Ralph: at most one document search per admitted turn, without saved history.
/// Direct demonstration remains a fixed response without an LLM call.
#[utoipa::path(
    post, path = "/agents/execute/stream",
    request_body = ExecuteRequest,
    responses(
        (status = 200, description = "SSE data frames containing RuntimeEvent JSON; final closes the stream without a sentinel", body = RuntimeEvent, content_type = "text/event-stream"),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn execute_stream(
    State(state): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiJson(request): ApiJson<ExecuteRequest>,
) -> AppResult<Response> {
    let target = request.validate().map_err(|error| match error {
        ExecuteError::Invalid(detail) => AppError::Unprocessable(detail.into()),
        ExecuteError::UnknownAgent => AppError::NotFound,
    })?;
    let events = if let RequestedTarget::Managed {
        instance_id,
        space_id,
        session_id,
        choice,
        reasoning,
    } = target
    {
        let instance_id = Uuid::parse_str(instance_id)
            .map_err(|_| AppError::Unprocessable("Invalid agent_instance_id.".into()))?;
        let space_id = Uuid::parse_str(space_id)
            .map_err(|_| AppError::Unprocessable("Invalid runtime_context.space_id.".into()))?;
        let session_id = Uuid::parse_str(session_id.ok_or_else(|| {
            AppError::Unprocessable("session_id is required for managed Ralph execution.".into())
        })?)
        .map_err(|_| AppError::Unprocessable("Invalid session_id.".into()))?;
        let binding = agent_instances::resolve_person_runtime_binding(
            &state,
            &user,
            space_id,
            instance_id,
            Some(session_id),
            choice.as_ref(),
            reasoning,
        )
        .await?;
        if binding.agent.runtime_id != fred_rust_agent::DEFINITION.provider
            || binding.agent.template_key != fred_rust_agent::AGENT_ID
        {
            return Err(AppError::problem(
                StatusCode::CONFLICT,
                "agent_runtime_mismatch",
                "The requested instance is not served by the embedded Ralph runtime.",
            ));
        }
        let span = tracing::info_span!("inference_turn",
            user_id = %binding.subject_id, space_id = %binding.space.id,
            organization_id = ?binding.space.organization_id,
            agent_instance_id = %binding.agent.instance_id,
            configuration_revision = binding.agent.configuration_revision,
            conversation_id = ?binding.conversation_id);
        let search = state
            .agent_catalog
            .knowledge_flow_url
            .as_deref()
            .map(|url| {
                search::Search::new(
                    url,
                    state.directory.clone(),
                    &binding.subject_id,
                    binding.agent.instance_id,
                    binding.space.id,
                )
            })
            .transpose()
            .map_err(|_| {
                AppError::problem(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "document_search_unavailable",
                    "Document search provisioning is unavailable.",
                )
            })?;
        let title_input = request.input.clone();
        let title = binding.title.map(|title| {
            let pool = state.pool.clone();
            let span = span.clone();
            let credentials = state.agent_catalog.inference_credentials.clone();
            let subject_id = binding.subject_id.clone();
            async move {
                let offer = title.inference.selection.key.clone();
                let turn = match fred_rust_agent::inference::InferenceTurn::admit(
                    title.inference,
                    &credentials,
                ) {
                    Ok(turn) => turn,
                    Err(_) => {
                        tracing::warn!(
                            event = "session_title",
                            outcome = "skipped",
                            reason = "provisioning"
                        );
                        return None;
                    }
                };
                let usage_pool = pool.clone();
                let generated = turn
                    .title(&title_input, move |usage| {
                        report_usage(usage_pool, span, space_id, session_id, offer, usage)
                    })
                    .await?;
                let body = crate::sessions::title::GeneratedTitle {
                    subject_id,
                    agent_instance_id: instance_id,
                    attempt_id: title.attempt_id,
                    title: generated,
                };
                match tokio::time::timeout(
                    std::time::Duration::from_secs(2),
                    crate::sessions::title::persist(&pool, space_id, session_id, &body),
                )
                .await
                {
                    Ok(Ok(true)) => Some(session_id.to_string()),
                    _ => {
                        tracing::info!(
                            event = "session_title",
                            outcome = "skipped",
                            reason = "not_persisted"
                        );
                        None
                    }
                }
            }
            .boxed()
        });
        let admission = binding.inference.ok_or_else(|| {
            AppError::problem(
                StatusCode::SERVICE_UNAVAILABLE,
                "inference_connection_unavailable",
                "Inference admission is unavailable.",
            )
        })?;
        let offer = admission.selection.key.clone();
        let turn = span
            .in_scope(|| {
                fred_rust_agent::inference::InferenceTurn::admit(
                    admission,
                    &state.agent_catalog.inference_credentials,
                )
            })
            .map_err(|_| {
                AppError::problem(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "inference_provisioning_unavailable",
                    "Local inference provisioning is unavailable or inconsistent.",
                )
            })?;
        let pool = state.pool.clone();
        let space_id = binding.space.id;
        let events = fred_rust_agent::inference::execute(
            turn,
            request.input,
            search.map(|search| move |query| async move { search.run(query).await }),
            move |usage| report_usage(pool, span, space_id, session_id, offer, usage),
        )
        .boxed();
        crate::sessions::title::stream(events, title)
    } else {
        fred_rust_agent::execute().boxed()
    };
    let stream = events.map(|event| Event::default().json_data(event));
    let mut response = Sse::new(stream)
        .keep_alive(KeepAlive::default())
        .into_response();
    response
        .headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache"));
    response
        .headers_mut()
        .insert("x-accel-buffering", HeaderValue::from_static("no"));
    Ok(response)
}

fn report_usage(
    pool: PgPool,
    span: Span,
    space_id: Uuid,
    session_id: Uuid,
    offer: ModelOfferKey,
    usage: Usage,
) {
    let report_id = Uuid::new_v4();
    let exchange_id = Uuid::new_v4().to_string();
    let tokens = [
        usage.input_tokens,
        usage.output_tokens,
        usage.cached_input_tokens,
        usage.cache_creation_input_tokens,
    ]
    .map(i64::try_from);
    let [
        Ok(input_tokens),
        Ok(output_tokens),
        Ok(cache_read_tokens),
        Ok(cache_creation_tokens),
    ] = tokens
    else {
        tracing::warn!(
            parent: &span,
            event = "run_usage",
            outcome = "lost",
            reason = "token_overflow"
        );
        return;
    };
    let report = UsageReport {
        occurred_at: chrono::Utc::now(),
        models: vec![ModelUsage {
            model_source_id: offer.source_id,
            upstream_model_id: offer.upstream_model_id,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_creation_tokens,
        }],
    };
    // Only the bounded accounting write survives a disconnected browser.
    // It starts before yielding the response; inference itself is never spawned.
    tokio::spawn(
        async move {
            let failure = match tokio::time::timeout(
                std::time::Duration::from_secs(2),
                persist_usage(&pool, space_id, session_id, &exchange_id, report_id, report),
            )
            .await
            {
                Ok(Ok(())) => return,
                Ok(Err(_)) => "write_failed",
                Err(_) => "timeout",
            };
            tracing::warn!(event = "run_usage", outcome = "lost", reason = failure, %report_id);
        }
        .instrument(span),
    );
}
