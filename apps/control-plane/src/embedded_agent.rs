// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! HTTP admission and SSE framing for the embedded agent library.

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

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(execute_stream))
}

/// Managed inference through common admission; direct demo remains fixed and never calls an LLM.
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
        let session_id = session_id
            .map(Uuid::parse_str)
            .transpose()
            .map_err(|_| AppError::Unprocessable("Invalid session_id.".into()))?;
        let binding = agent_instances::resolve_person_runtime_binding(
            &state,
            &user,
            space_id,
            instance_id,
            session_id,
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
                "The requested instance is not served by the embedded hello-world runtime.",
            ));
        }
        let span = tracing::info_span!("inference_turn",
            user_id = %binding.subject_id, space_id = %binding.space.id,
            organization_id = ?binding.space.organization_id,
            agent_instance_id = %binding.agent.instance_id,
            configuration_revision = binding.agent.configuration_revision,
            conversation_id = ?binding.conversation_id);
        let admission = binding.inference.ok_or_else(|| {
            AppError::problem(
                StatusCode::SERVICE_UNAVAILABLE,
                "inference_connection_unavailable",
                "Inference admission is unavailable.",
            )
        })?;
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
        fred_rust_agent::inference::execute(turn, request.input).boxed()
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
