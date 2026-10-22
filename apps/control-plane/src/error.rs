// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};

use crate::domain::RuleError;

/// JSON error envelope shared by application, authentication and import failures.
#[derive(serde::Serialize, utoipa::ToSchema)]
pub struct ErrorBody {
    pub detail: String,
    pub code: String,
}

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("not found")]
    NotFound,
    #[error("forbidden")]
    Forbidden,
    #[error("{0}")]
    Denied(String),
    #[error("{0}")]
    Unavailable(String),
    #[error("{0}")]
    BadRequest(String),
    #[error("{0}")]
    Conflict(String),
    #[error("{0}")]
    Unprocessable(String),
    #[error("{detail}")]
    Problem {
        status: StatusCode,
        code: &'static str,
        detail: &'static str,
    },
    #[error(transparent)]
    Internal(anyhow::Error),
}

pub type AppResult<T> = Result<T, AppError>;

impl AppError {
    pub fn problem(status: StatusCode, code: &'static str, detail: &'static str) -> Self {
        Self::Problem {
            status,
            code,
            detail,
        }
    }
}

impl From<anyhow::Error> for AppError {
    fn from(error: anyhow::Error) -> Self {
        if error.is::<crate::fga::Conflict>() {
            Self::Conflict(error.to_string())
        } else if error.is::<crate::fga::InvalidTuple>() {
            Self::Unprocessable(error.to_string())
        } else {
            Self::Internal(error)
        }
    }
}

impl From<RuleError> for AppError {
    fn from(e: RuleError) -> Self {
        AppError::BadRequest(e.to_string())
    }
}

impl From<sqlx::Error> for AppError {
    fn from(e: sqlx::Error) -> Self {
        match &e {
            sqlx::Error::RowNotFound => AppError::NotFound,
            // Unique and foreign-key violations are caller errors: duplicate name, non-empty folder...
            sqlx::Error::Database(db)
                if db.is_unique_violation() || db.is_foreign_key_violation() =>
            {
                AppError::Conflict("conflicting name or resource reference".into())
            }
            sqlx::Error::Io(_)
            | sqlx::Error::Tls(_)
            | sqlx::Error::PoolTimedOut
            | sqlx::Error::PoolClosed => {
                AppError::Unavailable("database temporarily unavailable".into())
            }
            sqlx::Error::Database(db)
                if matches!(
                    db.code().as_deref(),
                    Some("55P03" | "57014" | "40001" | "40P01")
                ) =>
            {
                AppError::Unavailable("database temporarily busy".into())
            }
            _ => AppError::Internal(e.into()),
        }
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let status = match &self {
            AppError::NotFound => StatusCode::NOT_FOUND,
            AppError::Forbidden | AppError::Denied(_) => StatusCode::FORBIDDEN,
            AppError::Unavailable(_) => StatusCode::SERVICE_UNAVAILABLE,
            AppError::BadRequest(_) => StatusCode::BAD_REQUEST,
            AppError::Conflict(_) => StatusCode::CONFLICT,
            AppError::Unprocessable(_) => StatusCode::UNPROCESSABLE_ENTITY,
            AppError::Problem { status, .. } => *status,
            AppError::Internal(e) => {
                tracing::error!(error = ?e, "internal error");
                StatusCode::INTERNAL_SERVER_ERROR
            }
        };
        let message = match &self {
            AppError::Internal(_) => "internal error".to_string(),
            other => other.to_string(),
        };
        let code = match &self {
            AppError::Problem { code, .. } => *code,
            AppError::NotFound => "not_found",
            AppError::Forbidden => "forbidden",
            AppError::Denied(_) => "admission_required",
            AppError::Unavailable(_) => "dependency_unavailable",
            AppError::BadRequest(_) => "invalid_request",
            AppError::Conflict(_) => "conflict",
            AppError::Unprocessable(_) => "invalid_fields",
            AppError::Internal(_) => "internal_error",
        };
        let mut response = (
            status,
            Json(ErrorBody {
                detail: message,
                code: code.into(),
            }),
        )
            .into_response();
        if status == StatusCode::TOO_MANY_REQUESTS || code == "upload_in_progress" {
            response.headers_mut().insert(
                axum::http::header::RETRY_AFTER,
                axum::http::HeaderValue::from_static("5"),
            );
        }
        response
    }
}

/// `Json` whose rejections answer like FastAPI: 422 with a `detail`, never plain text.
pub struct ApiJson<T>(pub T);

impl<T, S> axum::extract::FromRequest<S> for ApiJson<T>
where
    Json<T>: axum::extract::FromRequest<S, Rejection = axum::extract::rejection::JsonRejection>,
    S: Send + Sync,
{
    type Rejection = AppError;

    async fn from_request(req: axum::extract::Request, state: &S) -> Result<Self, AppError> {
        match Json::<T>::from_request(req, state).await {
            Ok(Json(value)) => Ok(ApiJson(value)),
            Err(rejection) => Err(AppError::Unprocessable(rejection.body_text())),
        }
    }
}
