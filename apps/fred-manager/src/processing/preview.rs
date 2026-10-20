// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::{models::*, store, unavailable};
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

#[derive(Default, serde::Deserialize, utoipa::IntoParams)]
pub struct PreviewQuery {
    /// native, raw, metadata, or a relative path from the published manifest.
    #[serde(default = "raw")]
    pub artifact: String,
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
    let document = db::document(&state.pool, id).await?;
    crate::documents::authorized(
        &state.pool,
        &state.fga,
        actor,
        document.space_id,
        Permission::Read,
    )
    .await?;
    let storage = state.content.as_ref().ok_or_else(unavailable)?;
    if query.artifact == "native" && document.name.to_lowercase().ends_with(".pdf") {
        let key: String = sqlx::query_scalar("select object_key from document where id=$1")
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
    let row: store::Row = sqlx::query_as(
        "select * from document_processing where document_id=$1 and status='succeeded'",
    )
    .bind(id)
    .fetch_one(&state.pool)
    .await?;
    let manifest = row.manifest.as_ref().ok_or(AppError::NotFound)?;
    let path = match query.artifact.as_str() {
        "raw" => "output.md",
        "native" => "native.pdf",
        "metadata" => "metadata.json",
        other => other,
    };
    if !artifact_path(path) {
        return Err(AppError::NotFound);
    }
    let artifact = manifest
        .artifacts
        .iter()
        .find(|a| a.path == path)
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
    let key = format!(
        "{}{}",
        row.prefix(&processing.config.derived.prefix, manifest.generation),
        path
    );
    stream(
        storage,
        &processing.derived,
        &key,
        artifact.size,
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
