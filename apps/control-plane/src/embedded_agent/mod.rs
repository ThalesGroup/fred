// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! HTTP admission and SSE framing for the embedded agent library.

pub(crate) mod kf_search;
pub mod store;
mod title;
mod usage;

use axum::{
    extract::State,
    http::{HeaderValue, StatusCode, header},
    response::{
        IntoResponse, Response, Sse,
        sse::{Event, KeepAlive},
    },
};
use fred_rust_agent::{ExecuteError, ExecuteRequest, RequestedTarget, RuntimeEvent};
use futures::StreamExt;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use crate::{
    agent_instances,
    api::AppState,
    error::{AppError, AppResult},
    extract::ApiJson,
    onboarding::AdmittedUser,
};

/// Whether an agent template is the one this runtime embeds.
pub(crate) fn serves(runtime_id: &str, template: &str) -> bool {
    runtime_id == fred_rust_agent::DEFINITION.provider && template == fred_rust_agent::AGENT_ID
}

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
        if !serves(&binding.agent.runtime_id, &binding.agent.template_key) {
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
                kf_search::Search::new(
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
        let title = binding.title.map(|attempt| {
            title::generate(
                &state,
                span.clone(),
                title::TitledTurn {
                    subject_id: binding.subject_id.clone(),
                    instance_id,
                    space_id,
                    session_id,
                },
                request.input.clone(),
                attempt,
            )
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
                fred_rust_agent::turn::InferenceTurn::admit(
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
        let events = fred_rust_agent::answer::execute(
            turn,
            request.input,
            None::<(store::ConversationStore, String)>,
            search.map(|search| move |query| async move { search.run(query).await }),
            move |tokens| usage::report(pool, span, space_id, session_id, offer, tokens),
        )
        .boxed();
        title::stream(events, title)
    } else {
        fred_rust_agent::demo::execute().boxed()
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
