use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use serde_json::json;

use crate::domain::RuleError;

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
    #[error(transparent)]
    Internal(#[from] anyhow::Error),
}

pub type AppResult<T> = Result<T, AppError>;

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
                AppError::Conflict(db.message().to_string())
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
            AppError::Internal(e) => {
                tracing::error!(error = ?e, "internal error");
                StatusCode::INTERNAL_SERVER_ERROR
            }
        };
        let message = match &self {
            AppError::Internal(_) => "internal error".to_string(),
            other => other.to_string(),
        };
        (status, Json(json!({ "detail": message }))).into_response()
    }
}
