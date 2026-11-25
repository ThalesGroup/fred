// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! The approved SQL destination is the only authority for an outgoing connection.
//! UI assets receive no credentials; API requests forward only the verified user
//! bearer. Redirects are refused, including browser redirects from the upstream.
use crate::{
    api::AppState,
    error::{AppError, AppResult},
    onboarding::AdmittedUser,
};
use axum::{
    Router,
    body::{Body, to_bytes},
    extract::{OriginalUri, Path, Request, State},
    http::{Method, StatusCode, header},
    response::{IntoResponse, Response},
    routing::{any, get},
};
use std::{sync::OnceLock, time::Duration};
use uuid::Uuid;

const MAX_REQUEST: usize = 16 * 1024 * 1024;
const MAX_RESPONSE: usize = 64 * 1024 * 1024;
const TIMEOUT: Duration = Duration::from_secs(180);

pub(crate) fn routes() -> Router<AppState> {
    Router::new()
        .route("/apps/{application}/", get(ui))
        .route("/apps/{application}/{*path}", get(ui))
        .route("/app-services/{application}/teams/{space}", any(api))
        .route("/app-services/{application}/teams/{space}/", any(api))
        .route(
            "/app-services/{application}/teams/{space}/{*path}",
            any(api),
        )
}

/// Internal service hosts are intentional, but credentials, ambiguous paths and
/// non-HTTP schemes are never destinations. The organization Owner approves the trusted service.
pub(super) fn destination(raw: &str) -> AppResult<reqwest::Url> {
    let invalid = || {
        AppError::Unprocessable("Use an absolute HTTP(S) service directory URL, without credentials, query or fragment.".into())
    };
    if !crate::model_catalog::config::approved_url(raw, true)
        || !raw.ends_with('/')
        || raw.contains('\\')
    {
        return Err(invalid());
    }
    let url = reqwest::Url::parse(raw).map_err(|_| invalid())?;
    // Url parsing normalizes dot segments. Validate the raw path first.
    let raw_path = raw
        .split_once("://")
        .and_then(|(_, rest)| rest.find('/').map(|index| &rest[index..]))
        .ok_or_else(invalid)?;
    safe_path(raw_path.trim_start_matches('/')).map_err(|_| invalid())?;
    if raw_path.starts_with("//") {
        return Err(invalid());
    }
    Ok(url)
}

fn safe_path(raw: &str) -> AppResult<String> {
    let mut result = Vec::new();
    for segment in raw.split('/') {
        let decoded = percent_encoding::percent_decode_str(segment)
            .decode_utf8()
            .map_err(|_| AppError::BadRequest("Invalid application path.".into()))?;
        if matches!(decoded.as_ref(), "." | "..")
            || decoded
                .chars()
                .any(|c| c.is_control() || "/\\%?#".contains(c))
        {
            return Err(AppError::BadRequest("Invalid application path.".into()));
        }
        result.push(decoded.into_owned());
    }
    if raw.contains("//") {
        return Err(AppError::BadRequest("Invalid application path.".into()));
    }
    Ok(result.join("/"))
}

fn upstream(base: &str, path: &str, query: Option<&str>) -> AppResult<reqwest::Url> {
    let mut url = destination(base)?;
    let suffix = safe_path(path)?;
    let path = format!("{}{}", url.path(), suffix);
    url.set_path(&path);
    url.set_query(query);
    Ok(url)
}
fn unavailable() -> AppError {
    AppError::Unavailable("Application service unavailable.".into())
}

fn client() -> AppResult<reqwest::Client> {
    static CLIENT: OnceLock<reqwest::Client> = OnceLock::new();
    if let Some(client) = CLIENT.get() {
        return Ok(client.clone());
    }
    let client = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(5))
        .timeout(TIMEOUT)
        .no_proxy()
        .build()
        .map_err(|_| unavailable())?;
    let _ = CLIENT.set(client.clone());
    Ok(client)
}

async fn ui(
    State(s): State<AppState>,
    Path(params): Path<std::collections::HashMap<String, String>>,
    OriginalUri(uri): OriginalUri,
    request: Request,
) -> AppResult<Response> {
    let name = params.get("application").ok_or(AppError::NotFound)?;
    let id = name.parse::<Uuid>().map_err(|_| AppError::NotFound)?;
    let app = super::by_id(&mut *s.pool.acquire().await?, id).await?;
    if !app.enabled {
        return Err(AppError::NotFound);
    }
    let prefix = format!("/apps/{name}");
    let path = uri
        .path()
        .strip_prefix(&prefix)
        .ok_or(AppError::NotFound)?
        .strip_prefix('/')
        .unwrap_or("");
    forward(
        upstream(&app.ui_base_url, path, uri.query())?,
        request,
        false,
    )
    .await
}

async fn api(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    Path(params): Path<std::collections::HashMap<String, String>>,
    OriginalUri(uri): OriginalUri,
    request: Request,
) -> AppResult<Response> {
    if user.service_account {
        return Err(AppError::Forbidden);
    }
    let name = params.get("application").ok_or(AppError::NotFound)?;
    let space: Uuid = params
        .get("space")
        .and_then(|id| id.parse().ok())
        .ok_or(AppError::NotFound)?;
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let organization = crate::db::space(&mut *tx, space).await?.organization_id;
    let app = super::by_name(&mut tx, organization, name).await?;
    super::authorize(&mut tx, &user.uid, space, &app).await?;
    tx.commit().await?;
    let prefix = format!("/app-services/{name}/teams/{space}");
    let suffix = uri.path().strip_prefix(&prefix).ok_or(AppError::NotFound)?;
    if !suffix.is_empty() && !suffix.starts_with('/') {
        return Err(AppError::BadRequest("Invalid application path.".into()));
    }
    let path = format!("teams/{space}{suffix}");
    forward(
        upstream(
            app.api_base_url.as_deref().ok_or(AppError::NotFound)?,
            &path,
            uri.query(),
        )?,
        request,
        true,
    )
    .await
}

async fn forward(url: reqwest::Url, request: Request, authenticated: bool) -> AppResult<Response> {
    let (parts, body) = request.into_parts();
    if !matches!(
        parts.method,
        Method::GET
            | Method::HEAD
            | Method::POST
            | Method::PUT
            | Method::PATCH
            | Method::DELETE
            | Method::OPTIONS
    ) {
        return Err(AppError::BadRequest(
            "Unsupported application method.".into(),
        ));
    }
    let mut outgoing = client()?.request(parts.method.clone(), url);
    // Allowlisting strips cookies, host, forwarding and hop-by-hop headers. The
    // upstream cannot choose a different credential destination via a header.
    for name in [
        header::ACCEPT,
        header::CONTENT_TYPE,
        header::IF_NONE_MATCH,
        header::IF_MODIFIED_SINCE,
        header::RANGE,
    ] {
        if let Some(value) = parts.headers.get(&name) {
            outgoing = outgoing.header(name, value);
        }
    }
    if authenticated {
        let token = crate::auth::bearer(&parts)
            .filter(|v| !v.is_empty())
            .ok_or(AppError::Forbidden)?;
        outgoing = outgoing.bearer_auth(token);
    }
    let body = tokio::time::timeout(Duration::from_secs(60), to_bytes(body, MAX_REQUEST))
        .await
        .map_err(|_| {
            AppError::problem(
                StatusCode::REQUEST_TIMEOUT,
                "application_body_timeout",
                "Application request timed out.",
            )
        })?
        .map_err(|_| {
            AppError::problem(
                StatusCode::PAYLOAD_TOO_LARGE,
                "application_body_too_large",
                "Application request body exceeds the limit.",
            )
        })?;
    let response = outgoing
        .body(body)
        .send()
        .await
        .map_err(|_| unavailable())?;
    if response.status().is_redirection() && response.status() != StatusCode::NOT_MODIFIED {
        return Err(unavailable());
    }
    if response
        .content_length()
        .is_some_and(|n| n > MAX_RESPONSE as u64)
    {
        return Err(unavailable());
    }
    let status = response.status();
    let mut headers = axum::http::HeaderMap::new();
    for name in [
        header::CONTENT_TYPE,
        header::CONTENT_DISPOSITION,
        header::CONTENT_RANGE,
        header::ACCEPT_RANGES,
        header::ETAG,
        header::LAST_MODIFIED,
        header::CONTENT_ENCODING,
        header::RETRY_AFTER,
    ] {
        if let Some(value) = response.headers().get(&name) {
            headers.insert(name, value.clone());
        }
    }
    // Availability and permission changes must not be bypassed by cached responses.
    headers.insert(
        header::CACHE_CONTROL,
        axum::http::HeaderValue::from_static("no-store"),
    );
    let stream =
        futures::stream::try_unfold((response, 0usize), |(mut response, count)| async move {
            let chunk = response
                .chunk()
                .await
                .map_err(|_| std::io::Error::other("application stream failed"))?;
            match chunk {
                Some(chunk) if count + chunk.len() <= MAX_RESPONSE => {
                    let count = count + chunk.len();
                    Ok(Some((chunk, (response, count))))
                }
                Some(_) => Err(std::io::Error::other("application response exceeds limit")),
                None => Ok(None),
            }
        });
    Ok((status, headers, Body::from_stream(stream)).into_response())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn approved_destination_preserves_directory_and_rejects_ambiguous_paths() {
        assert_eq!(
            upstream(
                "http://evaluator:8080/apps/evaluation/",
                "assets/a.js",
                Some("v=1")
            )
            .unwrap()
            .as_str(),
            "http://evaluator:8080/apps/evaluation/assets/a.js?v=1"
        );
        for bad in [
            "file:///tmp/",
            "http://user:secret@host/",
            "http://host/?x=1",
            "http://host/#f",
            "http://host/../",
            "http://host/%2e%2e/",
            "http://host//x/",
            "http://host/no-trailing-slash",
        ] {
            assert!(destination(bad).is_err(), "{bad}");
        }
        for bad in [
            "../x",
            "%2e%2e/x",
            "%252e%252e/x",
            "x%2fy",
            "x%5cy",
            "x\\y",
            "//host",
            "a/../b",
            "a%00",
            "a%3fb",
        ] {
            assert!(
                upstream("https://approved/api/", bad, None).is_err(),
                "{bad}"
            );
        }
    }
    #[tokio::test]
    async fn transport_caps_bodies_and_refuses_redirects_without_following() {
        use std::sync::{
            Arc,
            atomic::{AtomicUsize, Ordering},
        };
        let hits = Arc::new(AtomicUsize::new(0));
        let observed = hits.clone();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("http://{}/", listener.local_addr().unwrap());
        let app = Router::new().fallback(move |request: Request| {
            let observed = observed.clone();
            async move {
                observed.fetch_add(1, Ordering::SeqCst);
                if request.uri().path() == "/redirect" {
                    return (
                        StatusCode::TEMPORARY_REDIRECT,
                        [(header::LOCATION, "/leak")],
                    )
                        .into_response();
                }
                let stream = futures::stream::iter(
                    (0..65).map(|_| Ok::<_, std::io::Error>(vec![0_u8; 1024 * 1024])),
                );
                Body::from_stream(stream).into_response()
            }
        });
        let server = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        let request = Request::builder()
            .method("POST")
            .header(header::AUTHORIZATION, "Bearer secret")
            .body(Body::from(vec![0_u8; MAX_REQUEST + 1]))
            .unwrap();
        assert!(matches!(
            forward(upstream(&base, "large", None).unwrap(), request, true).await,
            Err(AppError::Problem {
                status: StatusCode::PAYLOAD_TOO_LARGE,
                ..
            })
        ));
        assert_eq!(hits.load(Ordering::SeqCst), 0);
        let request = Request::builder()
            .header(header::AUTHORIZATION, "Bearer secret")
            .body(Body::empty())
            .unwrap();
        assert!(
            forward(upstream(&base, "redirect", None).unwrap(), request, true)
                .await
                .is_err()
        );
        assert_eq!(hits.load(Ordering::SeqCst), 1);
        let response = forward(
            upstream(&base, "large", None).unwrap(),
            Request::new(Body::empty()),
            false,
        )
        .await
        .unwrap();
        assert!(
            to_bytes(response.into_body(), MAX_RESPONSE + 1024 * 1024)
                .await
                .is_err()
        );
        server.abort();
    }
}
