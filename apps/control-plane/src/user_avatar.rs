// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Personal and team avatars share the content store and its durable orphan cleanup.
//! SQL owns publication; no transaction is held during decoding or S3 I/O.
use std::io::Cursor;

use axum::{
    extract::{DefaultBodyLimit, Multipart, State, multipart::MultipartRejection},
    http::{StatusCode, header},
    response::{IntoResponse, Response},
};
use image::{ImageFormat, ImageReader, Limits};
use sqlx::{Postgres, Transaction};
use utoipa_axum::{
    router::{OpenApiRouter, UtoipaMethodRouterExt},
    routes,
};
use uuid::Uuid;

use crate::{
    api::AppState,
    auth::CurrentUser,
    documents::{Storage, unavailable},
    domain::{Permission, SpaceKind},
    error::{AppError, AppResult},
    extract::ApiPath,
    onboarding::AdmittedUser,
    spaces,
};

const MAX_UPLOAD: usize = 5 * 1024 * 1024;
const MAX_STORED: usize = 256 * 1024;

fn invalid_image() -> AppError {
    AppError::Unprocessable(
        "Expected a valid JPEG, PNG or WebP image, at most 4096 x 4096 pixels".into(),
    )
}

/// Decode with explicit allocation/dimension limits and strip metadata by re-encoding.
/// This runs on the blocking pool, retaining the shared upload permit if cancelled.
fn normalize(bytes: Vec<u8>) -> AppResult<Vec<u8>> {
    let format = image::guess_format(&bytes).map_err(|_| invalid_image())?;
    if !matches!(
        format,
        ImageFormat::Jpeg | ImageFormat::Png | ImageFormat::WebP
    ) {
        return Err(invalid_image());
    }
    let mut reader = ImageReader::with_format(Cursor::new(bytes), format);
    let mut limits = Limits::default();
    limits.max_image_width = Some(4096);
    limits.max_image_height = Some(4096);
    limits.max_alloc = Some(64 * 1024 * 1024);
    reader.limits(limits);
    let decoded = reader.decode().map_err(|_| invalid_image())?;
    let mut output = Cursor::new(Vec::new());
    decoded
        .resize_to_fill(192, 192, image::imageops::FilterType::Triangle)
        .to_rgba8()
        .write_to(&mut output, ImageFormat::Png)
        .map_err(|_| invalid_image())?;
    let bytes = output.into_inner();
    if bytes.len() > MAX_STORED {
        return Err(invalid_image());
    }
    Ok(bytes)
}

fn multipart_error(status: StatusCode) -> AppError {
    if status == StatusCode::PAYLOAD_TOO_LARGE {
        AppError::problem(status, "file_too_large", "The photo exceeds 5 MiB")
    } else {
        AppError::BadRequest("Expected exactly one multipart file part".into())
    }
}

async fn read_upload(mut multipart: Multipart) -> AppResult<Vec<u8>> {
    let mut field = multipart
        .next_field()
        .await
        .map_err(|e| multipart_error(e.status()))?
        .ok_or_else(|| multipart_error(StatusCode::BAD_REQUEST))?;
    if field.name() != Some("file") {
        return Err(multipart_error(StatusCode::BAD_REQUEST));
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = field
        .chunk()
        .await
        .map_err(|e| multipart_error(e.status()))?
    {
        if bytes.len() + chunk.len() > MAX_UPLOAD {
            return Err(multipart_error(StatusCode::PAYLOAD_TOO_LARGE));
        }
        bytes.extend_from_slice(&chunk);
    }
    drop(field); // Release multer's exclusive field handle before checking for another.
    if multipart
        .next_field()
        .await
        .map_err(|e| multipart_error(e.status()))?
        .is_some()
    {
        return Err(multipart_error(StatusCode::BAD_REQUEST));
    }
    Ok(bytes)
}

/// One lifecycle and content store for both avatar owners.
#[derive(Clone, Copy)]
enum Owner<'a> {
    User(&'a str),
    SpaceUser(&'a str, Uuid),
    Team(Uuid),
}

impl<'a> Owner<'a> {
    fn user_id(self) -> Option<&'a str> {
        match self {
            Self::User(uid) | Self::SpaceUser(uid, _) => Some(uid),
            Self::Team(_) => None,
        }
    }
    fn space_id(self) -> Option<Uuid> {
        match self {
            Self::User(_) | Self::SpaceUser(_, _) => None,
            Self::Team(id) => Some(id),
        }
    }
    async fn transaction(
        self,
        s: &AppState,
        caller: &str,
    ) -> AppResult<Transaction<'static, Postgres>> {
        let mut tx = match self {
            Self::User(_) => s.pool.begin().await?,
            Self::SpaceUser(_, _) => return Err(AppError::Forbidden),
            Self::Team(id) => {
                let (tx, space) =
                    spaces::authorized_mutation(&s.pool, caller, id, Permission::Manage).await?;
                if space.kind != SpaceKind::Team {
                    return Err(AppError::NotFound);
                }
                tx
            }
        };
        // Organization guard precedes the per-avatar lock, never held during S3 I/O.
        let key = match self {
            Self::User(uid) | Self::SpaceUser(uid, _) => format!("user:{uid}"),
            Self::Team(id) => format!("team:{id}"),
        };
        sqlx::query("select pg_advisory_xact_lock(992, hashtext($1))")
            .bind(key)
            .execute(&mut *tx)
            .await?;
        Ok(tx)
    }
    async fn require_read(self, s: &AppState, caller: &str) -> AppResult<()> {
        if let Self::Team(id) = self {
            crate::team_discovery::metadata(&s.pool, caller, id).await?;
        }
        if let Self::SpaceUser(uid, space) = self {
            crate::authorization::authorize(&s.pool, caller, space, Permission::Read).await?;
            crate::authorization::authorize(&s.pool, uid, space, Permission::Read).await?;
        }
        Ok(())
    }
}

fn require_person(user: &crate::auth::CurrentUser) -> AppResult<()> {
    if user.is_workload() {
        return Err(AppError::Forbidden);
    }
    Ok(())
}

fn storage(s: &AppState) -> AppResult<&Storage> {
    s.content.as_deref().ok_or_else(unavailable)
}

/// Read only the caller's photo. No public URL, delegated subject or S3 credential.
#[utoipa::path(get, path = "/users/me/avatar", responses(
    (status = 200, body = String, content_type = "image/png"),
    (status = 204, description = "No photo"),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 429, body = crate::error::ErrorBody),
    (status = 503, body = crate::error::ErrorBody)
))]
async fn get_my_avatar(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
) -> AppResult<Response> {
    get_avatar(&s, &user, Owner::User(&user.uid)).await
}

/// A profile photo is visible to people sharing a readable space with its owner.
#[utoipa::path(get, path = "/spaces/{space_id}/users/{user_id}/avatar",
    params(("space_id" = Uuid, Path), ("user_id" = String, Path)),
    responses((status = 200, body = String, content_type = "image/png"),
        (status = 204, description = "No photo"),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 429, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)))]
async fn get_user_avatar(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, subject)): ApiPath<(Uuid, String)>,
) -> AppResult<Response> {
    get_avatar(&s, &user, Owner::SpaceUser(&subject, space)).await
}

async fn get_avatar(s: &AppState, user: &CurrentUser, owner: Owner<'_>) -> AppResult<Response> {
    require_person(user)?;
    owner.require_read(s, &user.uid).await?;
    let key: Option<String> = sqlx::query_scalar(
        "select object_key from avatar where (user_id=$1 or space_id=$2) and status='active'",
    )
    .bind(owner.user_id())
    .bind(owner.space_id())
    .fetch_optional(&s.pool)
    .await?;
    let Some(key) = key else {
        return Ok((
            StatusCode::NO_CONTENT,
            [(header::CACHE_CONTROL, "private, no-store")],
        )
            .into_response());
    };
    let storage = storage(s)?;
    let _permit = storage
        .downloads
        .clone()
        .try_acquire_owned()
        .map_err(|_| capacity())?;
    let bytes = tokio::time::timeout(storage.deadline(), async {
        let mut object = storage.objects.get(&key).await.map_err(|_| unavailable())?;
        let mut bytes = Vec::new();
        while let Some(chunk) = object.body.try_next().await.map_err(|_| unavailable())? {
            if bytes.len() + chunk.len() > MAX_STORED {
                return Err(unavailable());
            }
            bytes.extend_from_slice(&chunk);
        }
        Ok::<_, AppError>(bytes)
    })
    .await
    .map_err(|_| unavailable())??;
    owner.require_read(s, &user.uid).await?;
    Ok((
        [
            (header::CONTENT_TYPE, "image/png"),
            (header::CACHE_CONTROL, "private, no-store"),
            (header::X_CONTENT_TYPE_OPTIONS, "nosniff"),
        ],
        bytes,
    )
        .into_response())
}

fn capacity() -> AppError {
    AppError::problem(
        StatusCode::TOO_MANY_REQUESTS,
        "transfer_capacity",
        "All content transfer slots are busy",
    )
}

/// Replace the caller's photo after validation. Content is normalized to a 192px PNG.
#[utoipa::path(put, path = "/users/me/avatar", request_body(content=crate::documents::http::FileUpload, content_type="multipart/form-data"), responses(
    (status = 204, description = "Photo replaced"),
    (status = 400, body = crate::error::ErrorBody),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 408, body = crate::error::ErrorBody),
    (status = 409, body = crate::error::ErrorBody),
    (status = 413, body = crate::error::ErrorBody),
    (status = 422, body = crate::error::ErrorBody),
    (status = 429, body = crate::error::ErrorBody),
    (status = 503, body = crate::error::ErrorBody)
))]
async fn put_my_avatar(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    multipart: Result<Multipart, MultipartRejection>,
) -> AppResult<StatusCode> {
    put_avatar(&s, &user, Owner::User(&user.uid), multipart).await
}

async fn put_avatar(
    s: &AppState,
    user: &CurrentUser,
    owner: Owner<'_>,
    multipart: Result<Multipart, MultipartRejection>,
) -> AppResult<StatusCode> {
    require_person(user)?;
    // Refuse before reading or decoding an unauthorized upload.
    owner.transaction(s, &user.uid).await?.commit().await?;
    let storage = storage(s)?;
    if !storage.config.uploads_enabled {
        return Err(unavailable());
    }
    let permit = storage
        .uploads
        .clone()
        .try_acquire_owned()
        .map_err(|_| capacity())?;
    let multipart = multipart.map_err(|_| multipart_error(StatusCode::BAD_REQUEST))?;
    let bytes = tokio::time::timeout(storage.idle(), read_upload(multipart))
        .await
        .map_err(|_| {
            AppError::problem(
                StatusCode::REQUEST_TIMEOUT,
                "upload_timeout",
                "The photo transfer timed out",
            )
        })??;
    let (_permit, bytes) = tokio::task::spawn_blocking(move || (permit, normalize(bytes)))
        .await
        .map_err(|_| unavailable())?;
    let bytes = bytes?;
    let spool = storage
        .spool_bytes("avatar.png", "image/png", &bytes)
        .await?;
    let id = Uuid::new_v4();
    let key = format!("{}{id}/input/avatar.png", storage.prefix);
    let mut tx = owner.transaction(s, &user.uid).await?;
    storage.require_cleanup_capacity(&mut *tx).await?;
    sqlx::query("insert into avatar(id,user_id,object_key,size,status,expires_at,space_id) values($1,$2,$3,$4,'pending',clock_timestamp()+make_interval(secs=>$5),$6)")
        .bind(id).bind(owner.user_id()).bind(&key).bind(spool.size).bind(storage.config.limits.lease_seconds() as f64).bind(owner.space_id()).execute(&mut *tx).await?;
    tx.commit().await?;
    // A durable pending row protects the immutable key from the shared sweeper.
    // On cancellation or an uncertain PUT, expiry and the inventory recover it.
    let (_, outcome) = storage
        .objects
        .put_file(&key, spool.file, spool.size, &spool.digest)
        .await;
    let stored = match outcome {
        Ok(()) => {
            storage
                .objects
                .verify(&key, spool.size, &spool.digest)
                .await
        }
        Err(error) => Err(error),
    };
    if stored.is_err() {
        // Release the per-user pending slot, but retain protection for an uncertain PUT.
        sqlx::query("update avatar set status='retired' where id=$1 and status='pending'")
            .bind(id)
            .execute(&s.pool)
            .await?;
        return Err(unavailable());
    }
    crate::documents::token_current(user)?;
    crate::onboarding::require_admitted(&s.pool, &s.auth, &user.uid).await?;
    let mut tx = owner.transaction(s, &user.uid).await?;
    let pending: Option<Uuid> = sqlx::query_scalar("select id from avatar where id=$1 and status='pending' and expires_at>clock_timestamp() for update")
        .bind(id).fetch_optional(&mut *tx).await?;
    if pending.is_none() {
        return Err(AppError::Conflict(
            "Photo upload expired or was removed".into(),
        ));
    }
    sqlx::query(
        "update avatar set status='retired' where (user_id=$1 or space_id=$2) and status='active'",
    )
    .bind(owner.user_id())
    .bind(owner.space_id())
    .execute(&mut *tx)
    .await?;
    sqlx::query("update avatar set status='active' where id=$1")
        .bind(id)
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Idempotent removal also prevents a previously admitted upload from publishing.
#[utoipa::path(delete, path = "/users/me/avatar", responses(
    (status = 204, description = "Photo removed"),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 503, body = crate::error::ErrorBody)
))]
async fn delete_my_avatar(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
) -> AppResult<StatusCode> {
    delete_avatar(&s, &user, Owner::User(&user.uid)).await
}

async fn delete_avatar(
    s: &AppState,
    user: &CurrentUser,
    owner: Owner<'_>,
) -> AppResult<StatusCode> {
    require_person(user)?;
    let mut tx = owner.transaction(s, &user.uid).await?;
    sqlx::query("update avatar set status='retired' where (user_id=$1 or space_id=$2) and status<>'retired'")
        .bind(owner.user_id())
        .bind(owner.space_id())
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(get, path = "/spaces/{id}/avatar", params(("id" = Uuid, Path)), responses(
    (status = 200, body = String, content_type = "image/png"),
    (status = 204, description = "No photo"),
    (status = 404, body = crate::error::ErrorBody),
    (status = 409, body = crate::error::ErrorBody),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 429, body = crate::error::ErrorBody),
    (status = 503, body = crate::error::ErrorBody)
))]
async fn get_team_avatar(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Response> {
    get_avatar(&s, &user, Owner::Team(id)).await
}

#[utoipa::path(put, path = "/spaces/{id}/avatar", request_body(content=crate::documents::http::FileUpload, content_type="multipart/form-data"), params(("id" = Uuid, Path)), responses(
    (status = 204, description = "Photo replaced"),
    (status = 400, body = crate::error::ErrorBody),
    (status = 404, body = crate::error::ErrorBody),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 408, body = crate::error::ErrorBody),
    (status = 409, body = crate::error::ErrorBody),
    (status = 413, body = crate::error::ErrorBody),
    (status = 422, body = crate::error::ErrorBody),
    (status = 429, body = crate::error::ErrorBody),
    (status = 503, body = crate::error::ErrorBody)
))]
async fn put_team_avatar(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    multipart: Result<Multipart, MultipartRejection>,
) -> AppResult<StatusCode> {
    put_avatar(&s, &user, Owner::Team(id), multipart).await
}

#[utoipa::path(delete, path = "/spaces/{id}/avatar", params(("id" = Uuid, Path)), responses(
    (status = 204, description = "Photo removed"),
    (status = 404, body = crate::error::ErrorBody),
    (status = 409, body = crate::error::ErrorBody),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 503, body = crate::error::ErrorBody)
))]
async fn delete_team_avatar(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<StatusCode> {
    delete_avatar(&s, &user, Owner::Team(id)).await
}

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(get_user_avatar))
        .routes(
            routes!(get_my_avatar, put_my_avatar, delete_my_avatar)
                .layer(DefaultBodyLimit::max(MAX_UPLOAD + 64 * 1024)),
        )
        .routes(
            routes!(get_team_avatar, put_team_avatar, delete_team_avatar)
                .layer(DefaultBodyLimit::max(MAX_UPLOAD + 64 * 1024)),
        )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn multipart_accepts_one_file_and_rejects_a_second_part() {
        use axum::{body::Body, extract::FromRequest, http::Request};

        let part = "--avatar-boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"avatar.png\"\r\nContent-Type: image/png\r\n\r\nimage-bytes\r\n";
        for count in [1, 2] {
            let body = format!("{}--avatar-boundary--\r\n", part.repeat(count));
            let request = Request::builder()
                .header(
                    "content-type",
                    "multipart/form-data; boundary=avatar-boundary",
                )
                .body(Body::from(body))
                .unwrap();
            let multipart = Multipart::from_request(request, &()).await.unwrap();
            let result = read_upload(multipart).await;
            if count == 1 {
                assert_eq!(result.unwrap(), b"image-bytes");
            } else {
                assert!(matches!(result, Err(AppError::BadRequest(_))));
            }
        }
    }

    #[test]
    fn supported_images_become_small_pngs() {
        for format in [ImageFormat::Jpeg, ImageFormat::Png, ImageFormat::WebP] {
            let mut input = Cursor::new(Vec::new());
            image::DynamicImage::new_rgb8(300, 200)
                .write_to(&mut input, format)
                .unwrap();
            let output = normalize(input.into_inner()).unwrap();
            assert_eq!(image::guess_format(&output).unwrap(), ImageFormat::Png);
            let decoded = image::load_from_memory(&output).unwrap();
            assert_eq!((decoded.width(), decoded.height()), (192, 192));
            assert!(output.len() <= MAX_STORED);
        }
    }

    #[test]
    fn declared_extensions_cannot_bypass_image_validation_or_dimension_limits() {
        assert!(normalize(b"<svg xmlns='http://www.w3.org/2000/svg'/>".to_vec()).is_err());
        assert!(normalize(b"\x89PNG\r\n\x1a\ntruncated".to_vec()).is_err());
        let mut input = Cursor::new(Vec::new());
        image::DynamicImage::new_rgb8(4097, 1)
            .write_to(&mut input, ImageFormat::Png)
            .unwrap();
        assert!(normalize(input.into_inner()).is_err());
    }
}
