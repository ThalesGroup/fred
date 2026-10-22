// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Request extractors for every route. Rejections answer `ErrorBody` JSON with fixed
//! messages that never echo input: an unreadable JSON body is 400, well-formed path,
//! query or body values that do not match their type are 422.

use axum::{
    Json,
    extract::{FromRequest, FromRequestParts, Path, Query, Request, rejection::JsonRejection},
    http::{StatusCode, request::Parts},
};
use serde::de::DeserializeOwned;

use crate::error::AppError;

fn invalid_fields() -> AppError {
    AppError::problem(
        StatusCode::UNPROCESSABLE_ENTITY,
        "invalid_fields",
        "Invalid request fields",
    )
}

pub struct ApiPath<T>(pub T);
impl<T: DeserializeOwned + Send, S: Send + Sync> FromRequestParts<S> for ApiPath<T> {
    type Rejection = AppError;
    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, AppError> {
        Path::<T>::from_request_parts(parts, state)
            .await
            .map(|Path(value)| Self(value))
            .map_err(|_| invalid_fields())
    }
}

pub struct ApiQuery<T>(pub T);
impl<T: DeserializeOwned, S: Send + Sync> FromRequestParts<S> for ApiQuery<T> {
    type Rejection = AppError;
    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, AppError> {
        Query::<T>::from_request_parts(parts, state)
            .await
            .map(|Query(value)| Self(value))
            .map_err(|_| invalid_fields())
    }
}

pub struct ApiJson<T>(pub T);
impl<T, S> FromRequest<S> for ApiJson<T>
where
    Json<T>: FromRequest<S, Rejection = JsonRejection>,
    S: Send + Sync,
{
    type Rejection = AppError;
    async fn from_request(req: Request, state: &S) -> Result<Self, AppError> {
        Json::<T>::from_request(req, state)
            .await
            .map(|Json(value)| Self(value))
            .map_err(|rejection| match rejection {
                JsonRejection::JsonDataError(_) => invalid_fields(),
                rejection if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE => {
                    AppError::problem(
                        StatusCode::PAYLOAD_TOO_LARGE,
                        "request_too_large",
                        "The request body exceeds the limit",
                    )
                }
                _ => AppError::problem(
                    StatusCode::BAD_REQUEST,
                    "invalid_json",
                    "Expected a valid JSON request",
                ),
            })
    }
}
