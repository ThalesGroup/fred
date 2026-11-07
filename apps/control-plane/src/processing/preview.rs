// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::{models::*, unavailable};
use crate::{
    api::AppState,
    db,
    documents::{Storage, object_store::ObjectStore},
    domain::Permission,
    error::{AppError, AppResult},
};
use axum::{
    body::{Body, Bytes},
    http::{HeaderMap, StatusCode, header},
    response::{IntoResponse, Response},
};
use tokio::io::AsyncReadExt;
use uuid::Uuid;

/// The descriptive subset of metadata.json consumed by the document viewer.
/// Extra fields in the artifact belong to their existing owners.
#[derive(serde::Deserialize, utoipa::ToSchema)]
pub struct MetadataPreview {
    pub identity: ExtractedFacts,
    pub extensions: Option<PreviewExtensions>,
}

#[derive(serde::Deserialize, utoipa::ToSchema)]
pub struct ExtractedFacts {
    pub title: Option<String>,
    pub author: Option<String>,
    pub created: Option<chrono::DateTime<chrono::FixedOffset>>,
}

#[derive(serde::Deserialize, utoipa::ToSchema)]
pub struct PreviewExtensions {
    pub email: Option<EmailHeaders>,
}

#[derive(serde::Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EmailHeaders {
    pub to: Vec<String>,
    pub cc: Vec<String>,
    pub message_id: Option<String>,
    pub in_reply_to: Option<String>,
}

/// Only newly emitted email facts have this contract. Old/non-email artifacts
/// remain readable. Validation occurs before publication, outside the SQL lock.
pub(super) fn validate_email_metadata(value: &serde_json::Value) -> AppResult<()> {
    let email = &value["extensions"]["email"];
    if email.is_null() {
        return Ok(());
    }
    let preview: MetadataPreview = serde_json::from_value(value.clone()).map_err(|_| invalid())?;
    let headers = preview
        .extensions
        .and_then(|e| e.email)
        .ok_or_else(invalid)?;
    fn bounded(value: &str, limit: usize) -> bool {
        !value.is_empty()
            && value.len() <= limit
            && value.trim() == value
            && !value.chars().any(char::is_control)
    }
    let facts = preview.identity;
    let valid = facts.title.as_deref().is_none_or(|s| bounded(s, 2048))
        && facts.author.as_deref().is_none_or(|s| bounded(s, 512))
        && headers
            .message_id
            .as_deref()
            .is_none_or(|s| bounded(s, 512))
        && headers
            .in_reply_to
            .as_deref()
            .is_none_or(|s| bounded(s, 512))
        && [&headers.to, &headers.cc].into_iter().all(|values| {
            values.len() <= 25
                && values.iter().all(|s| bounded(s, 512))
                && values
                    .iter()
                    .collect::<std::collections::HashSet<_>>()
                    .len()
                    == values.len()
        });
    let facts_size =
        serde_json::to_vec(&serde_json::json!({"identity": value["identity"], "email": email}))
            .map_err(|_| invalid())?
            .len();
    if !valid || facts_size > 65_536 {
        return Err(invalid());
    }
    Ok(())
}

#[derive(Default, serde::Deserialize, utoipa::IntoParams)]
#[into_params(parameter_in = Query)]
pub struct PreviewQuery {
    /// native, raw, metadata, or a relative path from the published manifest.
    #[serde(default = "raw")]
    pub artifact: String,
    /// Required for a conversation attachment; ownership is checked server-side.
    pub session_id: Option<Uuid>,
}
fn raw() -> String {
    "raw".into()
}

pub async fn preview(
    state: &AppState,
    actor: &str,
    id: Uuid,
    query: PreviewQuery,
    headers: HeaderMap,
) -> AppResult<Response> {
    let document = if let Some(session_id) = query.session_id {
        let document = db::pipeline_document(&state.pool, id).await?;
        let belongs: bool = sqlx::query_scalar("select exists(select 1 from document_current where id=$1 and session_id=$2 and deletion_id is null)")
            .bind(id).bind(session_id).fetch_one(&state.pool).await?;
        if !belongs {
            return Err(AppError::NotFound);
        }
        crate::sessions::require_owner(&state.pool, actor, document.space_id, session_id).await?;
        document
    } else {
        let document = db::document(&state.pool, id).await?;
        crate::authorization::authorize(&state.pool, actor, document.space_id, Permission::Read)
            .await
            .map_err(crate::documents::dependency_error)?;
        document
    };
    let storage = state.content.as_ref().ok_or_else(unavailable)?;
    if query.artifact == "native" && document.name.to_lowercase().ends_with(".pdf") {
        let key: String = sqlx::query_scalar(
            "select object_key from document_current where id=$1 and deletion_id is null",
        )
        .bind(id)
        .fetch_one(&state.pool)
        .await?;
        if !key.starts_with(&storage.prefix) {
            return Err(unavailable());
        }
        return stream(
            storage,
            &storage.objects,
            &key,
            document.size,
            "application/pdf",
            headers,
        )
        .await;
    }
    let processing = state.processing.as_ref().ok_or_else(unavailable)?;
    let path = match query.artifact.as_str() {
        "raw" => "output.md",
        "native" => "native.pdf",
        "metadata" => "metadata.json",
        other => other,
    };
    if !artifact_path(path) {
        return Err(AppError::NotFound);
    }
    let (prefix, size): (String, i64) = sqlx::query_as("select g.prefix, a.size from document_current d join generation g on g.id = d.published_generation join artifact a on a.generation_id = g.id and a.path = $2 where d.id = $1 and d.deletion_id is null")
        .bind(id)
        .bind(path)
        .fetch_optional(&state.pool)
        .await?
        .ok_or(AppError::NotFound)?;
    let mime = match path.rsplit('.').next().unwrap_or("") {
        "md" | "txt" => "text/plain; charset=utf-8",
        "json" => "application/json",
        "pdf" => "application/pdf",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        _ => "application/octet-stream",
    };
    stream(
        storage,
        &processing.derived,
        &format!("{prefix}{path}"),
        size,
        mime,
        headers,
    )
    .await
}

fn range(headers: &HeaderMap, size: i64) -> AppResult<Option<(i64, i64)>> {
    let Some(value) = headers.get(header::RANGE) else {
        return Ok(None);
    };
    let invalid = || {
        AppError::problem(
            StatusCode::RANGE_NOT_SATISFIABLE,
            "invalid_range",
            "A single valid byte range is required",
        )
    };
    let value = value
        .to_str()
        .map_err(|_| invalid())?
        .strip_prefix("bytes=")
        .ok_or_else(invalid)?;
    let (start, end) = value.split_once('-').ok_or_else(invalid)?;
    if value.contains(',') || size == 0 {
        return Err(invalid());
    }
    let (start, end) = if start.is_empty() {
        let suffix = end.parse::<i64>().map_err(|_| invalid())?;
        if suffix <= 0 {
            return Err(invalid());
        }
        ((size - suffix).max(0), size - 1)
    } else {
        let start = start.parse::<i64>().map_err(|_| invalid())?;
        let end = if end.is_empty() {
            size - 1
        } else {
            end.parse::<i64>().map_err(|_| invalid())?.min(size - 1)
        };
        (start, end)
    };
    if start < 0 || start >= size || end < start {
        return Err(invalid());
    }
    Ok(Some((start, end)))
}

async fn stream(
    storage: &Storage,
    objects: &ObjectStore,
    key: &str,
    size: i64,
    mime: &'static str,
    headers: HeaderMap,
) -> AppResult<Response> {
    let permit = storage
        .downloads
        .clone()
        .try_acquire_owned()
        .map_err(|_| super::capacity())?;
    let selected = range(&headers, size)?;
    let length = selected.map_or(size, |(start, end)| end - start + 1);
    let object = objects
        .get_range(
            key,
            selected.map(|(start, end)| format!("bytes={start}-{end}")),
        )
        .await
        .map_err(|_| unavailable())?;
    if object.content_length() != Some(length) {
        return Err(unavailable());
    }
    let (sender, receiver) = tokio::sync::mpsc::channel(1);
    let idle = std::time::Duration::from_secs(storage.config.limits.idle_seconds);
    let deadline = tokio::time::Instant::now()
        + std::time::Duration::from_secs(storage.config.limits.transfer_seconds);
    let task = tokio::spawn(async move {
        let _permit = permit;
        let result: std::io::Result<()> = async {
            let mut reader = object.body.into_async_read();
            let mut remaining = length;
            while remaining > 0 {
                let mut buffer = vec![0; 65536.min(remaining as usize)];
                let n = tokio::time::timeout_at(
                    deadline.min(tokio::time::Instant::now() + idle),
                    reader.read(&mut buffer),
                )
                .await
                .map_err(|_| std::io::Error::other("preview timeout"))??;
                if n == 0 {
                    return Err(std::io::Error::other("preview truncated"));
                }
                remaining -= n as i64;
                buffer.truncate(n);
                tokio::time::timeout_at(deadline, sender.send(Ok(Bytes::from(buffer))))
                    .await
                    .map_err(|_| std::io::Error::other("preview timeout"))?
                    .map_err(|_| std::io::Error::other("preview closed"))?;
            }
            Ok(())
        }
        .await;
        if let Err(error) = result {
            let _ = sender.try_send(Err(error));
        }
    });
    let body = futures::stream::unfold(
        (receiver, Abort(task)),
        |(mut receiver, guard)| async move {
            receiver
                .recv()
                .await
                .map(|chunk| (chunk, (receiver, guard)))
        },
    );
    let mut response = (
        [
            (header::CONTENT_TYPE, mime.to_owned()),
            (header::CONTENT_LENGTH, length.to_string()),
            (header::ACCEPT_RANGES, "bytes".into()),
            (header::CACHE_CONTROL, "private, no-store".into()),
            (header::X_CONTENT_TYPE_OPTIONS, "nosniff".into()),
            (
                header::CONTENT_SECURITY_POLICY,
                "sandbox; default-src 'none'".into(),
            ),
        ],
        Body::from_stream(body),
    )
        .into_response();
    if let Some((start, end)) = selected {
        *response.status_mut() = StatusCode::PARTIAL_CONTENT;
        response.headers_mut().insert(
            header::CONTENT_RANGE,
            format!("bytes {start}-{end}/{size}")
                .parse()
                .map_err(|_| unavailable())?,
        );
    }
    Ok(response)
}
struct Abort(tokio::task::JoinHandle<()>);
impl Drop for Abort {
    fn drop(&mut self) {
        self.0.abort();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn email_facts_are_optional_bounded_and_never_include_bcc() {
        use serde_json::json;
        let valid = json!({"identity":{"title":"Offre Atlas", "author":"Paul", "created":"2026-10-27T10:30:00+01:00"},
            "extensions":{"email":{"to":["Alice"],"cc":[],"message_id":"<same@example.test>","in_reply_to":null}}});
        assert!(validate_email_metadata(&valid).is_ok());
        assert!(validate_email_metadata(&json!({"identity": {}})).is_ok());
        for (pointer, value) in [
            ("/identity/title", json!("é".repeat(1025))),
            ("/identity/author", json!("bad\nheader")),
            ("/identity/created", json!("not-a-date")),
            ("/extensions/email/to", json!(["Alice", "Alice"])),
            ("/extensions/email/cc", json!(vec!["recipient"; 26])),
            ("/extensions/email/message_id", json!("x".repeat(513))),
        ] {
            let mut changed = valid.clone();
            *changed.pointer_mut(pointer).unwrap() = value;
            assert!(validate_email_metadata(&changed).is_err(), "{pointer}");
        }
        let mut changed = valid.clone();
        changed["extensions"]["email"]["bcc"] = json!(["private"]);
        assert!(validate_email_metadata(&changed).is_err());
        let empty = json!({"identity":{"title":null,"author":null,"created":null},
            "extensions":{"email":{"to":[],"cc":[],"message_id":null,"in_reply_to":null}}});
        assert!(validate_email_metadata(&empty).is_ok());
    }

    #[test]
    fn bounded_pdf_ranges() {
        for (value, expected) in [
            ("bytes=2-9", Some((2, 9))),
            ("bytes=8-", Some((8, 9))),
            ("bytes=-3", Some((7, 9))),
        ] {
            let mut headers = HeaderMap::new();
            headers.insert(header::RANGE, value.parse().unwrap());
            assert_eq!(range(&headers, 10).unwrap(), expected);
        }
        for value in ["bytes=10-", "bytes=0-1,4-5", "bytes=-0", "bytes=4-2"] {
            let mut headers = HeaderMap::new();
            headers.insert(header::RANGE, value.parse().unwrap());
            assert!(range(&headers, 10).is_err());
        }
    }
}
