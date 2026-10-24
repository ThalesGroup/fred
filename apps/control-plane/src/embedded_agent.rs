// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! HTTP admission and SSE framing for the embedded agent library.

use axum::{
    http::{HeaderValue, StatusCode, header},
    response::{
        IntoResponse, Response, Sse,
        sse::{Event, KeepAlive},
    },
};
use fred_rust_agent::{ExecuteError, ExecuteRequest, RuntimeEvent};
use futures::StreamExt;
use utoipa_axum::{router::OpenApiRouter, routes};

use crate::{
    api::AppState,
    error::{AppError, AppResult},
    extract::ApiJson,
    onboarding::AdmittedUser,
};

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(execute_stream))
}

/// Direct-template hello-world execution; no managed instance or business data access.
#[utoipa::path(
    post, path = "/agents/execute/stream",
    request_body = ExecuteRequest,
    responses(
        (status = 200, description = "SSE data frames containing RuntimeEvent JSON; final closes the stream without a sentinel", body = RuntimeEvent, content_type = "text/event-stream"),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 501, body = crate::error::ErrorBody)
    )
)]
async fn execute_stream(
    AdmittedUser(_user): AdmittedUser,
    ApiJson(request): ApiJson<ExecuteRequest>,
) -> AppResult<Response> {
    let events = fred_rust_agent::execute(request).map_err(|error| match error {
        ExecuteError::Invalid(detail) => AppError::Unprocessable(detail.into()),
        ExecuteError::UnknownAgent => AppError::NotFound,
        ExecuteError::ManagedUnsupported => AppError::problem(
            StatusCode::NOT_IMPLEMENTED,
            "managed_execution_unsupported",
            "Managed execution is unavailable for the embedded hello-world agent.",
        ),
    })?;
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
