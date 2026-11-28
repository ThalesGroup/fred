// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::{sync::OnceLock, time::Duration};

use axum::{
    Json,
    extract::{
        DefaultBodyLimit, Multipart, State,
        multipart::{MultipartError, MultipartRejection},
    },
    http::{StatusCode, header},
};
use fred_rust_sdk::inference::{InferenceAdmission, InferenceCredentialBinding};
use serde::{Deserialize, Serialize};
use tokio::sync::Semaphore;
use utoipa::ToSchema;
use utoipa_axum::{
    router::{OpenApiRouter, UtoipaMethodRouterExt},
    routes,
};
use uuid::Uuid;

use crate::{
    api::AppState,
    authorization,
    domain::Permission,
    error::{AppError, AppResult},
    extract::ApiPath,
    model_catalog::{config::supports_transcription, instance as models, sources},
    onboarding::AdmittedUser,
};

const MAX_AUDIO_BYTES: usize = 8 * 1024 * 1024;
const MAX_TRANSCRIPT_BYTES: usize = 256 * 1024;
static REQUESTS: Semaphore = Semaphore::const_new(8);

#[allow(dead_code)]
#[derive(ToSchema)]
struct DictationUpload {
    #[schema(value_type = String, format = Binary)]
    file: Vec<u8>,
    /// ISO 639-1 code of the speaker's language, such as `fr`. Without it the model guesses.
    language: Option<String>,
}

#[derive(Deserialize, Serialize, ToSchema)]
struct DictationTranscript {
    text: String,
}

pub(super) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(
        routes!(transcribe_agent_audio).layer(DefaultBodyLimit::max(MAX_AUDIO_BYTES + 16384)),
    )
}

#[utoipa::path(
    post, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}/transcriptions",
    params(("space_id" = Uuid, Path), ("agent_instance_id" = Uuid, Path)),
    request_body(content = DictationUpload, content_type = "multipart/form-data"),
    responses(
        (status = 200, body = DictationTranscript, headers(("Cache-Control" = String))),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 408, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 413, body = crate::error::ErrorBody),
        (status = 415, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 429, body = crate::error::ErrorBody),
        (status = 502, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody),
        (status = 504, body = crate::error::ErrorBody),
    )
)]
async fn transcribe_agent_audio(
    State(state): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, instance_id)): ApiPath<(Uuid, Uuid)>,
    body: Result<Multipart, MultipartRejection>,
) -> AppResult<(
    [(header::HeaderName, &'static str); 1],
    Json<DictationTranscript>,
)> {
    let mut tx = state.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let space = authorization::authorize(&mut *tx, &user.uid, space_id, Permission::Read).await?;
    super::require_instance_space(space.kind)?;
    let instance = super::get_for_space(&mut *tx, space_id, instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if !authorization::can_use_agent(&mut *tx, instance.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    super::require_executable(&state, &space, &instance)?;
    let choices = models::resolve_for_space(&mut tx, &space, &instance.tuning.0).await?;
    let selection = models::decide_transcription(&choices).ok_or_else(|| {
        AppError::problem(
            StatusCode::CONFLICT,
            "dictation_unavailable",
            "No available transcription model is configured for this space.",
        )
    })?;
    let admission = models::admit(&mut tx, space.organization, selection).await?;
    tx.commit().await?;

    let key = credential(&admission, &state.agent_catalog.inference_credentials)?;
    let _slot = REQUESTS.try_acquire().map_err(|_| busy())?;
    let body = body.map_err(|error| invalid_audio(error.status()))?;
    let (file, language) = tokio::time::timeout(Duration::from_secs(15), read_audio(body))
        .await
        .map_err(|_| {
            AppError::problem(
                StatusCode::REQUEST_TIMEOUT,
                "dictation_upload_timeout",
                "The audio upload timed out.",
            )
        })??;
    let mut form =
        reqwest::multipart::Form::new().text("model", admission.selection.key.upstream_model_id);
    if let Some(language) = language {
        form = form.text("language", language);
    }
    let form = form.part("file", file);
    let transcript = transcribe(&admission.connection.api_root, &key, form).await?;
    Ok(([(header::CACHE_CONTROL, "no-store")], Json(transcript)))
}

async fn read_audio(mut body: Multipart) -> AppResult<(reqwest::multipart::Part, Option<String>)> {
    let mut language = None;
    let mut part = None;
    while let Some(field) = body.next_field().await.map_err(multipart_error)? {
        match field.name() {
            Some("language") if language.is_none() => {
                language = Some(read_language(field.text().await.map_err(multipart_error)?)?);
            }
            Some("file") if part.is_none() => part = Some(read_file(field).await?),
            _ => return Err(invalid_audio(StatusCode::BAD_REQUEST)),
        }
    }
    let part = part.ok_or_else(|| invalid_audio(StatusCode::BAD_REQUEST))?;
    Ok((part, language))
}

/// Accept only a short ISO 639 code, so nothing else from the browser reaches the provider.
fn read_language(value: String) -> AppResult<String> {
    let language = value.trim().to_ascii_lowercase();
    if (2..=3).contains(&language.len()) && language.bytes().all(|byte| byte.is_ascii_lowercase()) {
        Ok(language)
    } else {
        Err(invalid_audio(StatusCode::BAD_REQUEST))
    }
}

async fn read_file(
    field: axum::extract::multipart::Field<'_>,
) -> AppResult<reqwest::multipart::Part> {
    // Build a clean filename from the MIME type rather than forwarding browser metadata.
    let (filename, mime_type) = match field
        .content_type()
        .and_then(|value| value.split(';').next())
    {
        Some("audio/webm" | "video/webm") => ("dictation.webm", "audio/webm"),
        Some("audio/ogg" | "application/ogg") => ("dictation.ogg", "audio/ogg"),
        Some("audio/mp4" | "video/mp4") => ("dictation.mp4", "audio/mp4"),
        Some("audio/wav" | "audio/x-wav") => ("dictation.wav", "audio/wav"),
        _ => return Err(invalid_audio(StatusCode::UNSUPPORTED_MEDIA_TYPE)),
    };
    let audio = field.bytes().await.map_err(multipart_error)?;
    if audio.is_empty() {
        return Err(invalid_audio(StatusCode::BAD_REQUEST));
    }
    if audio.len() > MAX_AUDIO_BYTES {
        return Err(invalid_audio(StatusCode::PAYLOAD_TOO_LARGE));
    }
    let length = audio.len() as u64;
    reqwest::multipart::Part::stream_with_length(audio, length)
        .file_name(filename)
        .mime_str(mime_type)
        .map_err(|err| AppError::Internal(err.into()))
}

fn credential(
    admission: &InferenceAdmission,
    bindings: &[InferenceCredentialBinding],
) -> AppResult<String> {
    if !supports_transcription(&admission.connection) || admission.connection.validate().is_err() {
        return Err(AppError::Unavailable(
            "The transcription connection is unsupported.".into(),
        ));
    }
    let secret = if admission.encrypted_credential.is_some() {
        sources::admitted_credential(admission)?
    } else {
        bindings
            .iter()
            .find(|binding| binding.matches(admission))
            .and_then(|binding| std::env::var(&binding.api_key_env).ok())
    };
    secret
        .filter(|value| !value.is_empty())
        .ok_or_else(|| AppError::Unavailable("The transcription credential is unavailable.".into()))
}

async fn transcribe(
    api_root: &str,
    key: &str,
    form: reqwest::multipart::Form,
) -> AppResult<DictationTranscript> {
    static CLIENT: OnceLock<Result<reqwest::Client, reqwest::Error>> = OnceLock::new();
    let client = CLIENT
        .get_or_init(|| {
            reqwest::Client::builder()
                .redirect(reqwest::redirect::Policy::none())
                .connect_timeout(Duration::from_secs(5))
                .timeout(Duration::from_secs(90))
                .build()
        })
        .as_ref()
        .map_err(|_| provider_failure())?;
    let mut response = client
        .post(format!("{api_root}/audio/transcriptions"))
        .bearer_auth(key)
        .multipart(form)
        .send()
        .await
        .map_err(request_error)?;
    match response.status() {
        StatusCode::TOO_MANY_REQUESTS => return Err(busy()),
        StatusCode::PAYLOAD_TOO_LARGE => return Err(invalid_audio(StatusCode::PAYLOAD_TOO_LARGE)),
        StatusCode::BAD_REQUEST
        | StatusCode::UNPROCESSABLE_ENTITY
        | StatusCode::UNSUPPORTED_MEDIA_TYPE => return Err(invalid_audio(StatusCode::BAD_REQUEST)),
        status if !status.is_success() => return Err(provider_failure()),
        _ => (),
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(request_error)? {
        if chunk.len() > MAX_TRANSCRIPT_BYTES - bytes.len() {
            return Err(provider_failure());
        }
        bytes.extend_from_slice(&chunk);
    }
    let result: DictationTranscript =
        serde_json::from_slice(&bytes).map_err(|_| provider_failure())?;
    Ok(DictationTranscript {
        text: result.text.trim().to_owned(),
    })
}

fn multipart_error(error: MultipartError) -> AppError {
    invalid_audio(error.status())
}

fn invalid_audio(status: StatusCode) -> AppError {
    let detail = match status {
        StatusCode::PAYLOAD_TOO_LARGE => "The recording is too large for dictation.",
        StatusCode::UNSUPPORTED_MEDIA_TYPE => "The recording format is unsupported.",
        _ => "The audio recording is invalid or could not be transcribed.",
    };
    AppError::problem(status, "invalid_dictation_audio", detail)
}

fn busy() -> AppError {
    AppError::problem(
        StatusCode::TOO_MANY_REQUESTS,
        "dictation_busy",
        "The transcription service is busy. Try again.",
    )
}

fn provider_failure() -> AppError {
    AppError::problem(
        StatusCode::BAD_GATEWAY,
        "dictation_provider_failed",
        "The transcription model is unavailable or returned an invalid response.",
    )
}

fn request_error(error: reqwest::Error) -> AppError {
    if error.is_timeout() {
        AppError::problem(
            StatusCode::GATEWAY_TIMEOUT,
            "dictation_timeout",
            "The transcription request timed out.",
        )
    } else {
        provider_failure()
    }
}

#[cfg(test)]
mod tests {
    use super::read_language;

    #[test]
    fn language_hint_accepts_only_short_iso_codes() {
        assert_eq!(read_language(" FR ".into()).unwrap(), "fr");
        assert_eq!(read_language("yue".into()).unwrap(), "yue");
        for invalid in ["", "f", "fr-FR", "french", "f1", "é"] {
            assert!(read_language(invalid.into()).is_err(), "{invalid}");
        }
    }
}
