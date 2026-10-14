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

//! REST surface. Content access costs exactly one OpenFGA check on one space;
//! governance calls (spaces, roles) may add the invariant checks they enforce.

use std::sync::Arc;

use axum::{
    Json, Router,
    extract::{FromRef, Path, Query, State},
    http::{HeaderValue, Method, StatusCode, header},
    routing::{get, post, put},
};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use tower_http::cors::{AllowOrigin, CorsLayer};
use uuid::Uuid;

use crate::{
    auth::{Authenticator, CurrentUser},
    bootstrap, db,
    domain::{self, Document, Folder, Permission, Role, Space, SpaceKind},
    error::{ApiJson, AppError, AppResult},
    fga::Fga,
    ingestion::{DeleteDocument, IngestDocument, Ingestion, Submitted},
    keycloak::Directory,
    logging, platform,
    roles::{PlatformPermission, PlatformRole, SpacePermission},
    spaces,
};

#[derive(Clone)]
pub struct AppState {
    pub auth: Arc<Authenticator>,
    pub pool: PgPool,
    pub fga: Fga,
    pub bootstrap_token_env_var: Option<String>,
    pub ingestion: Ingestion,
    pub directory: Option<Directory>,
}

impl FromRef<AppState> for Arc<Authenticator> {
    fn from_ref(state: &AppState) -> Self {
        state.auth.clone()
    }
}

/// Every route but the liveness probe takes `CurrentUser`, the `Depends(get_current_user)`
/// equivalent. CORS mirrors the control-plane: configured origins, bearer and JSON only.
pub fn router(state: AppState, base_url: &str, authorized_origins: &[String]) -> Router {
    let origins: Vec<HeaderValue> = authorized_origins
        .iter()
        .filter_map(|o| HeaderValue::from_str(o.trim_end_matches('/')).ok())
        .collect();
    let cors = CorsLayer::new()
        .allow_origin(AllowOrigin::list(origins))
        .allow_methods([
            Method::GET,
            Method::POST,
            Method::PUT,
            Method::PATCH,
            Method::DELETE,
            Method::OPTIONS,
        ])
        .allow_headers([header::CONTENT_TYPE, header::AUTHORIZATION])
        .expose_headers([
            header::HeaderName::from_static("x-request-id"),
            header::HeaderName::from_static("x-correlation-id"),
        ]);
    let governance = governance_router(GovernanceState {
        auth: state.auth.clone(),
        pool: state.pool.clone(),
        fga: state.fga.clone(),
        directory: state.directory.clone(),
    });
    let api = Router::new()
        .route(
            "/healthz",
            get(|| async { Json(serde_json::json!({ "status": "ok" })) }),
        )
        .route("/bootstrap/platform-admin", post(bootstrap_platform_admin))
        .route("/me/spaces", get(my_spaces))
        .route("/me/personal-space", post(create_personal_space))
        .route("/spaces", post(create_space))
        .route(
            "/spaces/{id}/roles/{role}/{user}",
            put(grant).delete(revoke),
        )
        .route("/spaces/{id}/folders", get(list_folders))
        .route("/spaces/{id}/documents", get(list_documents))
        .route("/folders", post(create_folder))
        .route(
            "/folders/{id}",
            axum::routing::patch(rename_folder).delete(delete_folder),
        )
        .route("/documents", post(create_document))
        .route(
            "/documents/{id}",
            get(get_document)
                .patch(rename_document)
                .delete(delete_document),
        )
        .route("/documents/{id}/ingest", post(ingest_document))
        .route("/authorize/document", post(authorize_document))
        .route("/authorize/scope", post(authorize_scope))
        .route_layer(axum::middleware::from_fn(logging::expose_route))
        .with_state(state)
        .merge(governance);
    // Request logging is outermost, as in fred-core: it also sees CORS and 404 answers.
    Router::new()
        .nest(base_url, api)
        .layer(cors)
        .layer(axum::middleware::from_fn(logging::request_logging))
}

async fn require(fga: &Fga, user: &str, permission: Permission, space: Uuid) -> AppResult<()> {
    if fga.check(user, permission, space).await? {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

// ---------------------------------------------------------------- platform

#[derive(Deserialize)]
struct BootstrapRequest {
    token: String,
}

#[derive(Serialize)]
struct BootstrapResponse {
    user_id: String,
    username: String,
}

/// Same contract as the control-plane's `POST /bootstrap/platform-admin`: the caller's
/// own verified bearer plus the deploy-time secret, granting platform admin to the
/// caller only, once ever.
async fn bootstrap_platform_admin(
    State(s): State<AppState>,
    user: CurrentUser,
    ApiJson(req): ApiJson<BootstrapRequest>,
) -> AppResult<Json<BootstrapResponse>> {
    if req.token.chars().count() < bootstrap::MIN_TOKEN_LENGTH {
        return Err(AppError::Unprocessable(
            "token: at least 16 characters".into(),
        ));
    }
    let configured = bootstrap::configured_token(s.bootstrap_token_env_var.as_deref());
    if !configured.is_some_and(|t| bootstrap::same_secret(&t, &req.token)) {
        return Err(AppError::Denied(bootstrap::INVALID.into()));
    }
    if !s.auth.enabled() {
        return Err(AppError::Unavailable(bootstrap::AUTH_DISABLED.into()));
    }
    bootstrap::grant_root(&s.pool, &s.fga, &user.uid).await?;
    tracing::info!(
        user_id = user.uid,
        "[BOOTSTRAP] Granted platform_admin via root bootstrap"
    );
    Ok(Json(BootstrapResponse {
        user_id: user.uid,
        username: user.username,
    }))
}

#[derive(Serialize)]
struct Me {
    user_id: String,
    username: String,
    platform_roles: Vec<PlatformRole>,
}

async fn me(State(s): State<GovernanceState>, user: CurrentUser) -> AppResult<Json<Me>> {
    Ok(Json(Me {
        platform_roles: s.fga.effective_platform_roles(&user.uid).await?,
        user_id: user.uid,
        username: user.username,
    }))
}

// ---------------------------------------------------------------- spaces and roles

#[derive(Serialize)]
struct MySpace {
    #[serde(flatten)]
    space: Space,
    roles: Vec<Role>,
}

async fn my_spaces(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
) -> AppResult<Json<Vec<MySpace>>> {
    let roles = s.fga.roles_of(&user).await?;
    let mut ids: Vec<Uuid> = roles.iter().map(|(id, _)| *id).collect();
    ids.sort();
    ids.dedup();
    let spaces = db::spaces(&s.pool, &ids).await?;
    Ok(Json(
        spaces
            .into_iter()
            .map(|space| MySpace {
                roles: roles
                    .iter()
                    .filter(|(id, _)| *id == space.id)
                    .map(|(_, r)| *r)
                    .collect(),
                space,
            })
            .collect(),
    ))
}

#[derive(Deserialize)]
struct CreateSpace {
    kind: SpaceKind,
    parent_id: Uuid,
    name: String,
    /// Initial administrator; creation grants the caller nothing on the new space.
    admin: String,
}

async fn create_space(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    ApiJson(req): ApiJson<CreateSpace>,
) -> AppResult<(StatusCode, Json<Space>)> {
    let space = spaces::create_space(
        &s.pool,
        &s.fga,
        &user,
        req.kind,
        req.parent_id,
        req.name,
        &req.admin,
    )
    .await?;
    Ok((StatusCode::CREATED, Json(space)))
}

#[derive(Deserialize)]
struct CreatePersonalSpace {
    organization_id: Uuid,
}

async fn create_personal_space(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    ApiJson(req): ApiJson<CreatePersonalSpace>,
) -> AppResult<(StatusCode, Json<Space>)> {
    let space = spaces::create_personal_space(&s.pool, &s.fga, &user, req.organization_id).await?;
    Ok((StatusCode::CREATED, Json(space)))
}

fn parse_role(role: &str) -> AppResult<Role> {
    Role::parse(role).ok_or_else(|| AppError::BadRequest(format!("unknown role {role}")))
}

async fn grant(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path((id, role, target)): Path<(Uuid, String, String)>,
) -> AppResult<StatusCode> {
    spaces::grant(&s.pool, &s.fga, &user, id, parse_role(&role)?, &target).await?;
    Ok(StatusCode::NO_CONTENT)
}

async fn revoke(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path((id, role, target)): Path<(Uuid, String, String)>,
) -> AppResult<StatusCode> {
    spaces::revoke(&s.pool, &s.fga, &user, id, parse_role(&role)?, &target).await?;
    Ok(StatusCode::NO_CONTENT)
}

// ---------------------------------------------------------------- folders

#[derive(Deserialize)]
struct FolderQuery {
    parent_id: Option<Uuid>,
}

async fn list_folders(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path(space): Path<Uuid>,
    Query(q): Query<FolderQuery>,
) -> AppResult<Json<Vec<Folder>>> {
    require(&s.fga, &user, Permission::Read, space).await?;
    Ok(Json(db::folders(&s.pool, space, q.parent_id).await?))
}

#[derive(Deserialize)]
struct CreateFolder {
    space_id: Uuid,
    parent_id: Option<Uuid>,
    name: String,
}

async fn create_folder(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    ApiJson(req): ApiJson<CreateFolder>,
) -> AppResult<(StatusCode, Json<Folder>)> {
    let folder = spaces::create_folder(
        &s.pool,
        &s.fga,
        &user,
        req.space_id,
        req.parent_id,
        req.name,
    )
    .await?;
    Ok((StatusCode::CREATED, Json(folder)))
}

#[derive(Deserialize)]
struct Rename {
    name: String,
}

async fn rename_folder(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path(id): Path<Uuid>,
    ApiJson(req): ApiJson<Rename>,
) -> AppResult<StatusCode> {
    let folder = db::folder(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, folder.space_id).await?;
    db::rename_folder(&mut *tx, id, &req.name).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

async fn delete_folder(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path(id): Path<Uuid>,
) -> AppResult<StatusCode> {
    let folder = db::folder(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, folder.space_id).await?;
    db::delete_folder(&mut *tx, id).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

// ---------------------------------------------------------------- documents

#[derive(Deserialize)]
struct DocumentQuery {
    folder_id: Option<Uuid>,
    /// Cursor: the `name` and `id` of the last document of the previous page.
    after_name: Option<String>,
    after_id: Option<Uuid>,
    limit: Option<i64>,
}

async fn list_documents(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path(space): Path<Uuid>,
    Query(q): Query<DocumentQuery>,
) -> AppResult<Json<Vec<Document>>> {
    require(&s.fga, &user, Permission::Read, space).await?;
    let limit = q.limit.unwrap_or(50).clamp(1, 200);
    let after = match (q.after_name.as_deref(), q.after_id) {
        (Some(name), Some(id)) => Some((name, id)),
        (None, None) => None,
        _ => {
            return Err(AppError::Unprocessable(
                "after_name and after_id go together".into(),
            ));
        }
    };
    Ok(Json(
        db::documents(&s.pool, space, q.folder_id, after, limit).await?,
    ))
}

#[derive(Deserialize)]
struct CreateDocument {
    space_id: Uuid,
    folder_id: Option<Uuid>,
    name: String,
    mime: String,
    size: i64,
    sha256: String,
}

#[derive(Serialize)]
struct CreatedDocument {
    #[serde(flatten)]
    document: Document,
    storage_prefix: String,
    source_key: String,
}

async fn create_document(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    ApiJson(req): ApiJson<CreateDocument>,
) -> AppResult<(StatusCode, Json<CreatedDocument>)> {
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, req.space_id).await?;
    let document = Document {
        id: Uuid::new_v4(),
        space_id: req.space_id,
        folder_id: req.folder_id,
        name: req.name,
        mime: req.mime,
        size: req.size,
        sha256: req.sha256,
        created_by: user,
    };
    // The composite foreign key rejects a folder from another space.
    db::insert_document(&mut *tx, &document).await?;
    tx.commit().await?;
    let storage_prefix = domain::storage_prefix(document.space_id, document.id);
    let source_key = format!("{storage_prefix}source");
    Ok((
        StatusCode::CREATED,
        Json(CreatedDocument {
            document,
            storage_prefix,
            source_key,
        }),
    ))
}

async fn get_document(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path(id): Path<Uuid>,
) -> AppResult<Json<Document>> {
    let document = db::document(&s.pool, id).await?;
    require(&s.fga, &user, Permission::Read, document.space_id).await?;
    Ok(Json(document))
}

async fn rename_document(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path(id): Path<Uuid>,
    ApiJson(req): ApiJson<Rename>,
) -> AppResult<StatusCode> {
    let document = db::document(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, document.space_id).await?;
    db::rename_document(&mut *tx, id, &req.name).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Artefact removal is submitted before the row goes, so a failure leaves a retryable
/// document rather than orphaned chunks nobody can find.
async fn delete_document(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path(id): Path<Uuid>,
) -> AppResult<StatusCode> {
    let document = db::document(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, document.space_id).await?;
    s.ingestion
        .delete(DeleteDocument {
            document_id: id,
            space_id: document.space_id,
            storage_prefix: domain::storage_prefix(document.space_id, id),
        })
        .await?;
    db::delete_document(&mut *tx, id).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[derive(Deserialize, Default)]
struct IngestRequest {
    profile: Option<String>,
}

/// The body is optional; when present it gets the same 422 contract as `ApiJson`.
fn ingest_request(body: &[u8]) -> AppResult<IngestRequest> {
    if body.is_empty() {
        return Ok(IngestRequest::default());
    }
    serde_json::from_slice(body).map_err(|e| AppError::Unprocessable(e.to_string()))
}

async fn ingest_document(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path(id): Path<Uuid>,
    body: axum::body::Bytes,
) -> AppResult<StatusCode> {
    let request = ingest_request(&body)?;
    let document = db::document(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, document.space_id).await?;
    let folder_path = match document.folder_id {
        Some(f) => db::folder(&mut *tx, f).await?.path,
        None => "/".to_string(),
    };
    let storage_prefix = domain::storage_prefix(document.space_id, id);
    let input = IngestDocument {
        document_id: id,
        space_id: document.space_id,
        folder_path,
        source_key: format!("{storage_prefix}source"),
        storage_prefix,
        mime: document.mime,
        profile: request.profile.unwrap_or_else(|| "medium".into()),
        requested_by: user,
    };
    let submitted = s.ingestion.ingest(input).await?;
    tx.commit().await?;
    match submitted {
        Submitted::Started => Ok(StatusCode::ACCEPTED),
        Submitted::AlreadyRunning => Err(AppError::Conflict("ingestion already running".into())),
    }
}

// ---------------------------------------------------------------- authorization for agents

#[derive(Deserialize)]
struct AuthorizeDocument {
    document_id: Uuid,
    permission: Permission,
}

#[derive(Serialize)]
struct Allowed {
    allowed: bool,
}

async fn authorize_document(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    ApiJson(req): ApiJson<AuthorizeDocument>,
) -> AppResult<Json<Allowed>> {
    let document = db::document(&s.pool, req.document_id).await?;
    let allowed = s
        .fga
        .check(&user, req.permission, document.space_id)
        .await?;
    Ok(Json(Allowed { allowed }))
}

#[derive(Deserialize)]
struct AuthorizeScope {
    space_id: Uuid,
}

#[derive(Serialize)]
struct Scope {
    /// Filter for chunks and metadata: `space_id` must be one of these. Ancestors only,
    /// never descendants: a team conversation never sees its projects' content.
    space_ids: Vec<Uuid>,
}

async fn authorize_scope(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    ApiJson(req): ApiJson<AuthorizeScope>,
) -> AppResult<Json<Scope>> {
    let space = db::space(&s.pool, req.space_id).await?;
    require(&s.fga, &user, Permission::Read, space.id).await?;
    Ok(Json(Scope {
        space_ids: space.path,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ingest_body_is_optional_and_never_plain_text() {
        assert_eq!(ingest_request(b"").unwrap().profile, None);
        assert_eq!(
            ingest_request(br#"{"profile":"rich"}"#)
                .unwrap()
                .profile
                .as_deref(),
            Some("rich")
        );
        assert!(matches!(
            ingest_request(b"{not json"),
            Err(AppError::Unprocessable(_))
        ));
    }
}

// Platform mutation entry points require a real authenticated actor, even in dev mode.
fn require_directory_actor(s: &GovernanceState) -> AppResult<()> {
    if !s.auth.enabled() {
        return Err(AppError::Unavailable(
            "authentication must be enabled".into(),
        ));
    }
    Ok(())
}
async fn list_platform_roles(
    State(s): State<GovernanceState>,
    user: CurrentUser,
) -> AppResult<Json<Vec<platform::Grant>>> {
    require_directory_actor(&s)?;
    Ok(Json(platform::list(&s.fga, &user.uid).await?))
}
fn platform_role(name: &str) -> AppResult<PlatformRole> {
    PlatformRole::parse(name).ok_or_else(|| AppError::BadRequest("unknown platform role".into()))
}
async fn grant_platform_role(
    State(s): State<GovernanceState>,
    user: CurrentUser,
    Path((target, role)): Path<(String, String)>,
) -> AppResult<StatusCode> {
    require_directory_actor(&s)?;
    let directory = s
        .directory
        .as_ref()
        .ok_or_else(|| AppError::Unavailable("Keycloak directory is not configured".into()))?;
    if !s.auth.directory_subjects_match(directory.realm()) {
        return Err(AppError::Unavailable(
            "directory grants require Keycloak sub mapping in the configured realm".into(),
        ));
    }
    platform::grant(
        &s.pool,
        &s.fga,
        s.directory.as_ref(),
        &user.uid,
        &target,
        platform_role(&role)?,
    )
    .await?;
    Ok(StatusCode::NO_CONTENT)
}
async fn revoke_platform_role(
    State(s): State<GovernanceState>,
    user: CurrentUser,
    Path((target, role)): Path<(String, String)>,
) -> AppResult<StatusCode> {
    require_directory_actor(&s)?;
    platform::revoke(&s.pool, &s.fga, &user.uid, &target, platform_role(&role)?).await?;
    Ok(StatusCode::NO_CONTENT)
}
#[derive(Deserialize)]
struct PlatformCheck {
    permission: PlatformPermission,
}
async fn authorize_platform(
    State(s): State<GovernanceState>,
    user: CurrentUser,
    ApiJson(req): ApiJson<PlatformCheck>,
) -> AppResult<Json<Allowed>> {
    Ok(Json(Allowed {
        allowed: s.fga.check_platform(&user.uid, req.permission).await?,
    }))
}
#[derive(Deserialize)]
struct SpaceCheck {
    space_id: Uuid,
    permission: SpacePermission,
}
async fn authorize_space(
    State(s): State<GovernanceState>,
    user: CurrentUser,
    ApiJson(req): ApiJson<SpaceCheck>,
) -> AppResult<Json<Allowed>> {
    db::space(&s.pool, req.space_id).await?;
    Ok(Json(Allowed {
        allowed: s
            .fga
            .check_space(&user.uid, req.permission, req.space_id)
            .await?,
    }))
}
#[derive(Deserialize)]
struct RegistryQuery {
    after: Option<Uuid>,
}
async fn team_registry(
    State(s): State<GovernanceState>,
    user: CurrentUser,
    Query(query): Query<RegistryQuery>,
) -> AppResult<Json<Vec<Space>>> {
    if !s
        .fga
        .check_platform(&user.uid, PlatformPermission::ListAllTeams)
        .await?
    {
        return Err(AppError::Forbidden);
    }
    // Registry metadata only, bounded independently of content and FGA memberships.
    Ok(Json(sqlx::query_as("select id, kind, name, parent_id, personal_owner, path from space where kind = 'team' and personal_owner is null and ($1::uuid is null or id > $1) order by id limit 100")
        .bind(query.after).fetch_all(&s.pool).await?))
}

/// Governance routes are usable without an ingestion client; all require CurrentUser.
#[derive(Clone)]
pub struct GovernanceState {
    pub auth: Arc<Authenticator>,
    pub pool: PgPool,
    pub fga: Fga,
    pub directory: Option<Directory>,
}
impl FromRef<GovernanceState> for Arc<Authenticator> {
    fn from_ref(state: &GovernanceState) -> Self {
        state.auth.clone()
    }
}
pub fn governance_router(state: GovernanceState) -> Router {
    Router::new()
        .route("/me", get(me))
        .route("/users/platform-roles", get(list_platform_roles))
        .route(
            "/users/{user}/platform-roles/{role}",
            put(grant_platform_role).delete(revoke_platform_role),
        )
        .route("/admin/teams", get(team_registry))
        .route("/authorize/platform", post(authorize_platform))
        .route("/authorize/space", post(authorize_space))
        .route_layer(axum::middleware::from_fn(logging::expose_route))
        .with_state(state)
}
