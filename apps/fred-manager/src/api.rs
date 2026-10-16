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
};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use tower_http::cors::{AllowOrigin, CorsLayer};
use utoipa_axum::{
    router::{OpenApiRouter, UtoipaMethodRouterExt},
    routes,
};
use uuid::Uuid;

use crate::{
    auth::{Authenticator, CurrentUser},
    bootstrap, db,
    domain::{self, Document, Folder, Permission, Role, Space, SpaceKind, SpaceRow},
    error::{ApiJson, AppError, AppResult},
    fga::Fga,
    ingestion::{DeleteDocument, IngestDocument, Ingestion, Submitted},
    keycloak::Directory,
    logging,
    onboarding::{self, AdmissionState, AdmittedUser, Onboarding, OwnUser},
    platform,
    roles::{PlatformPermission, PlatformRole, SpacePermission},
    spaces,
};

#[derive(Clone)]
pub struct AppState {
    pub auth: Arc<Authenticator>,
    pub pool: PgPool,
    pub fga: Fga,
    pub onboarding: Onboarding,
    pub ingestion: Ingestion,
    pub directory: Option<Directory>,
}

impl FromRef<AppState> for Arc<Authenticator> {
    fn from_ref(state: &AppState) -> Self {
        state.auth.clone()
    }
}

/// Business routes take `AdmittedUser`, the authenticated and consent-checked equivalent of `Depends(get_current_user)`
/// in Fred. CORS mirrors the control-plane: configured origins, bearer and JSON only.
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
        onboarding: state.onboarding.clone(),
    });
    let api = content_routes()
        .with_state(state)
        .split_for_parts()
        .0
        .merge(governance);
    // Request logging is outermost, as in fred-core: it also sees CORS and 404 answers.
    Router::new()
        .nest(base_url, api)
        .layer(cors)
        .layer(axum::middleware::from_fn(logging::request_logging))
}

async fn require(
    pool: &PgPool,
    fga: &Fga,
    user: &str,
    permission: Permission,
    space: Uuid,
) -> AppResult<()> {
    let placed = spaces::load(pool, fga, space).await?;
    spaces::require_context(pool, fga, user, placed.organization).await?;
    if fga.check(user, permission, space).await? {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}

#[derive(Serialize, utoipa::ToSchema)]
struct FrontendConfig {
    user_auth: onboarding::PublicAuth,
    gcu_version: Option<String>,
    root_bootstrap_required: bool,
    root_bootstrap_completed: bool,
}

#[utoipa::path(get, path = "/frontend/config", security(()), responses(
    (status = 200, body = FrontendConfig),
    (status = 500, body = crate::error::ErrorBody)
))]
async fn frontend_config(State(s): State<GovernanceState>) -> AppResult<axum::response::Response> {
    use axum::response::IntoResponse;
    let completed = onboarding::bootstrap_completed(&s.pool).await?;
    Ok((
        [(header::CACHE_CONTROL, "no-store")],
        Json(FrontendConfig {
            user_auth: s.onboarding.user_auth.clone(),
            gcu_version: s
                .onboarding
                .gcu_version
                .clone()
                .filter(|_| s.auth.enabled()),
            root_bootstrap_required: s.auth.enabled() && !completed,
            root_bootstrap_completed: completed,
        }),
    )
        .into_response())
}

#[derive(Serialize, utoipa::ToSchema)]
struct OnboardingStatus {
    user_id: String,
    username: String,
    gcu_version: Option<String>,
    acceptance: Option<onboarding::Acceptance>,
    root_bootstrap_required: bool,
}

#[utoipa::path(get, path = "/me/onboarding", responses(
    (status = 200, body = OnboardingStatus),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 500, body = crate::error::ErrorBody)
))]
async fn onboarding_status(
    State(s): State<GovernanceState>,
    OwnUser(user): OwnUser,
) -> AppResult<axum::response::Response> {
    use axum::response::IntoResponse;
    let acceptance = onboarding::acceptance(&s.pool, &user.uid).await?;
    let completed = onboarding::bootstrap_completed(&s.pool).await?;
    Ok((
        [(header::CACHE_CONTROL, "no-store")],
        Json(OnboardingStatus {
            user_id: user.uid,
            username: user.username,
            gcu_version: s
                .onboarding
                .gcu_version
                .clone()
                .filter(|_| s.auth.enabled()),
            acceptance,
            root_bootstrap_required: s.auth.enabled() && !completed,
        }),
    )
        .into_response())
}

#[derive(Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
struct TermsRequest {
    version: String,
}

#[utoipa::path(post, path = "/gcu", request_body = TermsRequest, responses(
    (status = 204, description = "Accepted"),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 409, body = crate::error::ErrorBody),
    (status = 422, body = crate::error::ErrorBody),
    (status = 500, body = crate::error::ErrorBody)
))]
async fn accept_terms(
    State(s): State<GovernanceState>,
    OwnUser(user): OwnUser,
    ApiJson(req): ApiJson<TermsRequest>,
) -> AppResult<StatusCode> {
    onboarding::accept(
        &s.pool,
        s.onboarding
            .gcu_version
            .as_deref()
            .filter(|_| s.auth.enabled()),
        &user.uid,
        &req.version,
    )
    .await?;
    Ok(StatusCode::NO_CONTENT)
}

// ---------------------------------------------------------------- platform

#[derive(Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
struct BootstrapRequest {
    token: String,
}

#[derive(Serialize, utoipa::ToSchema)]
struct BootstrapResponse {
    user_id: String,
    username: String,
}

/// Same contract as the control-plane's `POST /bootstrap/platform-admin`: the caller's
/// own verified bearer plus the deploy-time secret, granting platform owner to the
/// caller only, once ever.
#[utoipa::path(
    post, path = "/bootstrap/platform-admin",
    request_body = BootstrapRequest,
    responses(
        (status = 200, description = "Success", body = BootstrapResponse),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
        (status = 503, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn bootstrap_platform_admin(
    State(s): State<GovernanceState>,
    OwnUser(user): OwnUser,
    ApiJson(req): ApiJson<BootstrapRequest>,
) -> AppResult<Json<BootstrapResponse>> {
    if req.token.chars().count() < bootstrap::MIN_TOKEN_LENGTH {
        return Err(AppError::Unprocessable(
            "token: at least 16 characters".into(),
        ));
    }
    let configured = bootstrap::configured_token(s.onboarding.bootstrap_token_env_var.as_deref());
    if !configured.is_some_and(|t| bootstrap::same_secret(&t, &req.token)) {
        return Err(AppError::Denied(bootstrap::INVALID.into()));
    }
    if !s.auth.enabled() {
        return Err(AppError::Unavailable(bootstrap::AUTH_DISABLED.into()));
    }
    onboarding::require_accepted(&s.pool, s.onboarding.gcu_version.as_deref(), &user.uid).await?;
    bootstrap::grant_root(&s.pool, &s.fga, &user.uid).await?;
    tracing::info!(
        user_id = user.uid,
        "[BOOTSTRAP] Granted platform_owner via root bootstrap"
    );
    Ok(Json(BootstrapResponse {
        user_id: user.uid,
        username: user.username,
    }))
}

#[derive(Serialize, utoipa::ToSchema)]
struct Me {
    user_id: String,
    username: String,
    platform_roles: Vec<PlatformRole>,
}

#[utoipa::path(
    get, path = "/me",
    responses(
        (status = 200, description = "Success", body = Me),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn me(
    State(s): State<GovernanceState>,
    AdmittedUser(user): AdmittedUser,
) -> AppResult<Json<Me>> {
    Ok(Json(Me {
        platform_roles: s.fga.effective_platform_roles(&user.uid).await?,
        user_id: user.uid,
        username: user.username,
    }))
}

// ---------------------------------------------------------------- spaces and roles

#[derive(Serialize, utoipa::ToSchema)]
struct MySpace {
    organization_id: Uuid,
    #[serde(flatten)]
    space: Space,
    /// Effective roles, including those descending from an ancestor.
    roles: Vec<Role>,
    /// The subset of `roles` held only through an ancestor.
    inherited_roles: Vec<Role>,
}

#[utoipa::path(
    get, path = "/me/spaces",
    responses(
        (status = 200, description = "Success", body = [MySpace]),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Ambiguous organization context", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn my_spaces(
    State(s): State<GovernanceState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
) -> AppResult<Json<Vec<MySpace>>> {
    Ok(Json(
        spaces::memberships(&s.pool, &s.fga, &user)
            .await?
            .into_iter()
            .map(|m| MySpace {
                organization_id: m.space.organization,
                space: m.space,
                roles: m.roles,
                inherited_roles: m.inherited_roles,
            })
            .collect(),
    ))
}

#[derive(Deserialize, utoipa::ToSchema)]
struct CreateSpace {
    kind: SpaceKind,
    parent_id: Uuid,
    name: String,
    /// Initial administrator; creation grants the caller nothing on the new space.
    admin: String,
}

#[utoipa::path(
    post, path = "/spaces",
    request_body = CreateSpace,
    responses(
        (status = 201, description = "Success", body = Space),
        (status = 400, description = "Request failed", body = crate::error::ErrorBody),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn create_space(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
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

#[derive(Deserialize, utoipa::ToSchema)]
struct CreatePersonalSpace {
    organization_id: Uuid,
}

#[utoipa::path(
    post, path = "/me/personal-space",
    request_body = CreatePersonalSpace,
    responses(
        (status = 200, description = "Existing personal space", body = Space),
        (status = 201, description = "Created personal space", body = Space),
        (status = 400, description = "Request failed", body = crate::error::ErrorBody),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn create_personal_space(
    State(s): State<GovernanceState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    ApiJson(req): ApiJson<CreatePersonalSpace>,
) -> AppResult<(StatusCode, Json<Space>)> {
    let (space, created) =
        spaces::create_personal_space(&s.pool, &s.fga, &user, req.organization_id).await?;
    Ok((
        if created {
            StatusCode::CREATED
        } else {
            StatusCode::OK
        },
        Json(space),
    ))
}

fn parse_role(role: &str) -> AppResult<Role> {
    Role::parse(role).ok_or_else(|| AppError::BadRequest(format!("unknown role {role}")))
}

#[utoipa::path(
    put, path = "/spaces/{id}/roles/{role}/{user}",
    params(("id" = Uuid, Path), ("role" = Role, Path), ("user" = String, Path)),
    responses(
        (status = 204, description = "Success"),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn grant(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    Path((id, role, target)): Path<(Uuid, String, String)>,
) -> AppResult<StatusCode> {
    let role = parse_role(&role)?;
    if role == Role::Owner
        && !s
            .directory
            .as_ref()
            .is_some_and(|d| s.auth.directory_subjects_match(d.realm()))
    {
        return Err(AppError::Unavailable(
            "owner grants require Keycloak sub mapping in the configured realm".into(),
        ));
    }
    spaces::grant(
        &s.pool,
        &s.fga,
        s.directory.as_ref(),
        &user,
        id,
        role,
        &target,
    )
    .await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(
    delete, path = "/spaces/{id}/roles/{role}/{user}",
    params(("id" = Uuid, Path), ("role" = Role, Path), ("user" = String, Path)),
    responses(
        (status = 204, description = "Success"),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn revoke(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    Path((id, role, target)): Path<(Uuid, String, String)>,
) -> AppResult<StatusCode> {
    spaces::revoke(&s.pool, &s.fga, &user, id, parse_role(&role)?, &target).await?;
    Ok(StatusCode::NO_CONTENT)
}

// ---------------------------------------------------------------- folders

// Folder filters are not authority: validate them only after authorizing the space.
async fn require_folder_in_space(
    pool: &PgPool,
    space: Uuid,
    folder: Option<Uuid>,
) -> AppResult<()> {
    if let Some(id) = folder {
        let exists = sqlx::query_scalar::<_, bool>(
            "select exists(select 1 from folder where id = $1 and space_id = $2)",
        )
        .bind(id)
        .bind(space)
        .fetch_one(pool)
        .await?;
        if !exists {
            return Err(AppError::NotFound);
        }
    }
    Ok(())
}

#[derive(Deserialize, utoipa::ToSchema)]
struct FolderQuery {
    parent_id: Option<Uuid>,
}

#[utoipa::path(
    get, path = "/spaces/{id}/folders",
    params(("id" = Uuid, Path), ("parent_id" = Option<Uuid>, Query)),
    responses(
        (status = 200, description = "Success", body = [Folder]),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Unknown space or folder in this space", body = crate::error::ErrorBody),
        (status = 409, description = "Ambiguous organization context", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn list_folders(
    State(s): State<GovernanceState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    Path(space): Path<Uuid>,
    Query(q): Query<FolderQuery>,
) -> AppResult<Json<Vec<Folder>>> {
    require(&s.pool, &s.fga, &user, Permission::Read, space).await?;
    require_folder_in_space(&s.pool, space, q.parent_id).await?;
    Ok(Json(db::folders(&s.pool, space, q.parent_id).await?))
}

#[derive(Deserialize, utoipa::ToSchema)]
struct CreateFolder {
    space_id: Uuid,
    parent_id: Option<Uuid>,
    name: String,
}

#[utoipa::path(
    post, path = "/folders",
    request_body = CreateFolder,
    responses(
        (status = 201, description = "Success", body = Folder),
        (status = 400, description = "Request failed", body = crate::error::ErrorBody),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn create_folder(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
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

#[derive(Deserialize, utoipa::ToSchema)]
struct Rename {
    name: String,
}

#[utoipa::path(
    patch, path = "/folders/{id}",
    params(("id" = Uuid, Path)),
    request_body = Rename,
    responses(
        (status = 204, description = "Success"),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn rename_folder(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    Path(id): Path<Uuid>,
    ApiJson(req): ApiJson<Rename>,
) -> AppResult<StatusCode> {
    let folder = db::folder(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, folder.space_id).await?;
    db::folder(&mut *tx, id).await?;
    db::rename_folder(&mut *tx, id, &req.name).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(
    delete, path = "/folders/{id}",
    params(("id" = Uuid, Path)),
    responses(
        (status = 204, description = "Success"),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn delete_folder(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    Path(id): Path<Uuid>,
) -> AppResult<StatusCode> {
    let folder = db::folder(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, folder.space_id).await?;
    db::folder(&mut *tx, id).await?;
    db::delete_folder(&mut *tx, id).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

// ---------------------------------------------------------------- documents

#[derive(Deserialize, utoipa::ToSchema)]
struct DocumentQuery {
    folder_id: Option<Uuid>,
    /// Cursor: the `name` and `id` of the last document of the previous page.
    after_name: Option<String>,
    after_id: Option<Uuid>,
    limit: Option<i64>,
}

#[utoipa::path(
    get, path = "/spaces/{id}/documents",
    params(("id" = Uuid, Path), ("folder_id" = Option<Uuid>, Query), ("after_name" = Option<String>, Query), ("after_id" = Option<Uuid>, Query), ("limit" = Option<i64>, Query, description = "Defaults to 50; clamped to 1..200. Both cursor fields must be supplied together.")),
    responses(
        (status = 200, description = "Success", body = [Document]),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Unknown space or folder in this space", body = crate::error::ErrorBody),
        (status = 409, description = "Ambiguous organization context", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn list_documents(
    State(s): State<GovernanceState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    Path(space): Path<Uuid>,
    Query(q): Query<DocumentQuery>,
) -> AppResult<Json<Vec<Document>>> {
    require(&s.pool, &s.fga, &user, Permission::Read, space).await?;
    require_folder_in_space(&s.pool, space, q.folder_id).await?;
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

#[derive(Deserialize, utoipa::ToSchema)]
struct CreateDocument {
    space_id: Uuid,
    folder_id: Option<Uuid>,
    name: String,
    mime: String,
    size: i64,
    sha256: String,
}

#[derive(Serialize, utoipa::ToSchema)]
struct CreatedDocument {
    #[serde(flatten)]
    document: Document,
    storage_prefix: String,
    source_key: String,
}

#[utoipa::path(
    post, path = "/documents",
    request_body = CreateDocument,
    responses(
        (status = 201, description = "Success", body = CreatedDocument),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn create_document(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
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

#[utoipa::path(
    get, path = "/documents/{id}",
    params(("id" = Uuid, Path)),
    responses(
        (status = 200, description = "Success", body = Document),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Ambiguous organization context", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn get_document(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    Path(id): Path<Uuid>,
) -> AppResult<Json<Document>> {
    let document = db::document(&s.pool, id).await?;
    require(&s.pool, &s.fga, &user, Permission::Read, document.space_id).await?;
    Ok(Json(document))
}

#[utoipa::path(
    patch, path = "/documents/{id}",
    params(("id" = Uuid, Path)),
    request_body = Rename,
    responses(
        (status = 204, description = "Success"),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn rename_document(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    Path(id): Path<Uuid>,
    ApiJson(req): ApiJson<Rename>,
) -> AppResult<StatusCode> {
    let document = db::document(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, document.space_id).await?;
    // A deletion can commit while we wait for authorization's organization lock.
    db::document(&mut *tx, id).await?;
    db::rename_document(&mut *tx, id, &req.name).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Artefact removal is submitted before the row goes, so a failure leaves a retryable
/// document rather than orphaned chunks nobody can find.
#[utoipa::path(
    delete, path = "/documents/{id}",
    params(("id" = Uuid, Path)),
    responses(
        (status = 204, description = "Success"),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn delete_document(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    Path(id): Path<Uuid>,
) -> AppResult<StatusCode> {
    let document = db::document(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, document.space_id).await?;
    // A deletion can commit while we wait for authorization's organization lock.
    let document = db::document(&mut *tx, id).await?;
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

#[derive(Deserialize, Default, utoipa::ToSchema)]
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

#[utoipa::path(
    post, path = "/documents/{id}/ingest",
    params(("id" = Uuid, Path)),
    request_body = IngestRequest,
    responses(
        (status = 202, description = "Success"),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn ingest_document(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    Path(id): Path<Uuid>,
    body: axum::body::Bytes,
) -> AppResult<StatusCode> {
    let request = ingest_request(&body)?;
    let document = db::document(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, document.space_id).await?;
    // A deletion can commit while we wait for authorization's organization lock.
    let document = db::document(&mut *tx, id).await?;
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

#[derive(Deserialize, utoipa::ToSchema)]
struct AuthorizeDocument {
    document_id: Uuid,
    permission: Permission,
}

#[derive(Serialize, utoipa::ToSchema)]
struct Allowed {
    allowed: bool,
}

#[utoipa::path(
    post, path = "/authorize/document",
    request_body = AuthorizeDocument,
    responses(
        (status = 200, description = "Success", body = Allowed),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Ambiguous organization context", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn authorize_document(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    ApiJson(req): ApiJson<AuthorizeDocument>,
) -> AppResult<Json<Allowed>> {
    let document = db::document(&s.pool, req.document_id).await?;
    let space = spaces::load(&s.pool, &s.fga, document.space_id).await?;
    let allowed = spaces::in_organization(&s.pool, &s.fga, &user, space.organization).await?
        && s.fga
            .check(&user, req.permission, document.space_id)
            .await?;
    Ok(Json(Allowed { allowed }))
}

#[derive(Deserialize, utoipa::ToSchema)]
struct AuthorizeScope {
    space_id: Uuid,
    /// Keep only spaces of these kinds; omitted keeps every level. Never adds a space.
    #[serde(default)]
    levels: Option<Vec<SpaceKind>>,
}

#[derive(Serialize, utoipa::ToSchema)]
struct Scope {
    /// Filter for chunks and metadata: `space_id` must be one of these. The space and its
    /// ancestors, never descendants: a team conversation never sees its projects' content.
    /// A personal space's scope is itself.
    space_ids: Vec<Uuid>,
}

#[utoipa::path(
    post, path = "/authorize/scope",
    request_body = AuthorizeScope,
    responses(
        (status = 200, description = "Success", body = Scope),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Ambiguous organization context", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn authorize_scope(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    ApiJson(req): ApiJson<AuthorizeScope>,
) -> AppResult<Json<Scope>> {
    Ok(Json(Scope {
        space_ids: spaces::scope(&s.pool, &s.fga, &user, req.space_id, req.levels.as_deref())
            .await?,
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
#[utoipa::path(
    get, path = "/users/platform-roles",
    responses(
        (status = 200, description = "Success", body = [platform::Grant]),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
        (status = 503, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn list_platform_roles(
    State(s): State<GovernanceState>,
    AdmittedUser(user): AdmittedUser,
) -> AppResult<Json<Vec<platform::Grant>>> {
    require_directory_actor(&s)?;
    Ok(Json(platform::list(&s.fga, &user.uid).await?))
}
fn platform_role(name: &str) -> AppResult<PlatformRole> {
    PlatformRole::parse(name).ok_or_else(|| AppError::BadRequest("unknown platform role".into()))
}
#[utoipa::path(
    put, path = "/users/{user}/platform-roles/{role}",
    params(("user" = String, Path), ("role" = PlatformRole, Path, description = "Also accepts the owner and observer aliases.")),
    responses(
        (status = 204, description = "Success"),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
        (status = 503, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn grant_platform_role(
    State(s): State<GovernanceState>,
    AdmittedUser(user): AdmittedUser,
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
#[utoipa::path(
    delete, path = "/users/{user}/platform-roles/{role}",
    params(("user" = String, Path), ("role" = PlatformRole, Path, description = "Also accepts the owner and observer aliases.")),
    responses(
        (status = 204, description = "Success"),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Direct grant not found", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
        (status = 503, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn revoke_platform_role(
    State(s): State<GovernanceState>,
    AdmittedUser(user): AdmittedUser,
    Path((target, role)): Path<(String, String)>,
) -> AppResult<StatusCode> {
    require_directory_actor(&s)?;
    platform::revoke(&s.pool, &s.fga, &user.uid, &target, platform_role(&role)?).await?;
    Ok(StatusCode::NO_CONTENT)
}
#[derive(Deserialize, utoipa::ToSchema)]
struct PlatformCheck {
    permission: PlatformPermission,
}
#[utoipa::path(
    post, path = "/authorize/platform",
    request_body = PlatformCheck,
    responses(
        (status = 200, description = "Success", body = Allowed),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn authorize_platform(
    State(s): State<GovernanceState>,
    AdmittedUser(user): AdmittedUser,
    ApiJson(req): ApiJson<PlatformCheck>,
) -> AppResult<Json<Allowed>> {
    Ok(Json(Allowed {
        allowed: s.fga.check_platform(&user.uid, req.permission).await?,
    }))
}
#[derive(Deserialize, utoipa::ToSchema)]
struct SpaceCheck {
    space_id: Uuid,
    permission: SpacePermission,
}
#[utoipa::path(
    post, path = "/authorize/space",
    request_body = SpaceCheck,
    responses(
        (status = 200, description = "Success", body = Allowed),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Ambiguous organization context", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn authorize_space(
    State(s): State<GovernanceState>,
    AdmittedUser(user): AdmittedUser,
    ApiJson(req): ApiJson<SpaceCheck>,
) -> AppResult<Json<Allowed>> {
    let space = spaces::load(&s.pool, &s.fga, req.space_id).await?;
    Ok(Json(Allowed {
        allowed: spaces::in_organization(&s.pool, &s.fga, &user.uid, space.organization).await?
            && s.fga
                .check_space(&user.uid, req.permission, req.space_id)
                .await?,
    }))
}
#[derive(Deserialize, utoipa::ToSchema)]
struct RegistryQuery {
    after: Option<Uuid>,
}
#[utoipa::path(
    get, path = "/admin/teams",
    params(("after" = Option<Uuid>, Query, description = "Exclusive UUID cursor; at most 100 non-personal teams, ordered by ID.")),
    responses(
        (status = 200, description = "Success", body = [Space]),
        (status = 400, description = "Invalid path/query or application request", content((crate::error::ErrorBody = "application/json"), (String = "text/plain"))),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn team_registry(
    State(s): State<GovernanceState>,
    AdmittedUser(user): AdmittedUser,
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
    let teams: Vec<SpaceRow> = sqlx::query_as("select id, kind, name, personal_owner from space where kind = 'team' and personal_owner is null and ($1::uuid is null or id > $1) order by id limit 100")
        .bind(query.after).fetch_all(&s.pool).await?;
    let ids: Vec<Uuid> = teams.iter().map(|t| t.id).collect();
    let orgs: std::collections::BTreeMap<Uuid, Option<Uuid>> =
        s.fga.links_of(&ids, false).await?.into_iter().collect();
    Ok(Json(
        teams
            .into_iter()
            .map(|team| {
                let org =
                    orgs[&team.id].ok_or_else(|| anyhow::anyhow!("team has no organization"))?;
                Ok(Space::placed(team, &[org], None))
            })
            .collect::<AppResult<_>>()?,
    ))
}

/// Governance routes are usable without an ingestion client. Public configuration
/// and personal onboarding are separate from consent-gated business operations.
#[derive(Clone)]
pub struct GovernanceState {
    pub auth: Arc<Authenticator>,
    pub pool: PgPool,
    pub fga: Fga,
    pub directory: Option<Directory>,
    pub onboarding: Onboarding,
}
impl FromRef<GovernanceState> for Arc<Authenticator> {
    fn from_ref(state: &GovernanceState) -> Self {
        state.auth.clone()
    }
}
impl FromRef<GovernanceState> for AdmissionState {
    fn from_ref(s: &GovernanceState) -> Self {
        Self {
            auth: s.auth.clone(),
            pool: s.pool.clone(),
            version: s.onboarding.gcu_version.clone(),
        }
    }
}
impl FromRef<AppState> for AdmissionState {
    fn from_ref(s: &AppState) -> Self {
        Self {
            auth: s.auth.clone(),
            pool: s.pool.clone(),
            version: s.onboarding.gcu_version.clone(),
        }
    }
}

pub fn governance_router(state: GovernanceState) -> Router {
    governance_routes().with_state(state).split_for_parts().0
}

fn governance_routes() -> OpenApiRouter<GovernanceState> {
    OpenApiRouter::new()
        .routes(routes!(frontend_config))
        .routes(routes!(onboarding_status))
        .routes(routes!(accept_terms))
        .routes(routes!(bootstrap_platform_admin))
        .routes(routes!(me))
        .routes(routes!(my_spaces))
        .routes(routes!(create_personal_space))
        .routes(routes!(list_folders))
        .routes(routes!(list_documents))
        .routes(
            routes!(import_blueprint).layer(axum::extract::DefaultBodyLimit::max(
                crate::blueprint::MAX_ARCHIVE + 64 * 1024,
            )),
        )
        .routes(routes!(list_platform_roles))
        .routes(routes!(grant_platform_role, revoke_platform_role))
        .routes(routes!(team_registry))
        .routes(routes!(authorize_platform))
        .routes(routes!(authorize_space))
        .route_layer(axum::middleware::from_fn(logging::expose_route))
}

fn content_routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(health))
        .routes(routes!(create_space))
        .routes(routes!(grant, revoke))
        .routes(routes!(create_folder))
        .routes(routes!(rename_folder, delete_folder))
        .routes(routes!(create_document))
        .routes(routes!(get_document, rename_document, delete_document))
        .routes(routes!(ingest_document))
        .routes(routes!(authorize_document))
        .routes(routes!(authorize_scope))
        .route_layer(axum::middleware::from_fn(logging::expose_route))
}

#[derive(Serialize, utoipa::ToSchema)]
struct Health {
    status: &'static str,
}

#[utoipa::path(get, path = "/healthz", security(()), responses((status = 200, body = Health)))]
async fn health() -> Json<Health> {
    Json(Health { status: "ok" })
}

/// Offline contract from the same registrations used to serve requests.
/// The canonical prefix matches frontend proxy routing; no state is constructed.
pub fn openapi() -> utoipa::openapi::OpenApi {
    use utoipa::openapi::{
        ComponentsBuilder,
        security::{Http, HttpAuthScheme, SecurityRequirement, SecurityScheme},
    };
    let mut api = content_routes().into_openapi();
    api.merge(governance_routes().into_openapi());
    let mut api = OpenApiRouter::<()>::new()
        .nest("/fred-manager/v1", OpenApiRouter::with_openapi(api))
        .into_openapi();
    // utoipa's Option<T> makes both the body optional and its JSON nullable.
    // This handler accepts no body, but rejects JSON null: only presence is optional.
    if let Some(utoipa::openapi::RefOr::T(body)) = api
        .paths
        .paths
        .get_mut("/fred-manager/v1/documents/{id}/ingest")
        .unwrap()
        .post
        .as_mut()
        .unwrap()
        .request_body
        .as_mut()
    {
        body.required = Some(utoipa::openapi::Required::False);
    }
    api.info.title = "fred-manager".into();
    api.components
        .get_or_insert_with(|| ComponentsBuilder::new().build())
        .add_security_scheme(
            "bearer",
            SecurityScheme::Http(Http::new(HttpAuthScheme::Bearer)),
        );
    api.security = Some(vec![SecurityRequirement::new(
        "bearer",
        Vec::<String>::new(),
    )]);
    api
}

// A multipart contract, not a second parser: the handler validates the stream itself.
#[allow(dead_code)]
#[derive(utoipa::ToSchema)]
struct ProvisioningUpload {
    #[schema(value_type = String, format = Binary)]
    file: Vec<u8>,
}

/// Authenticate and check platform authority before constructing the body extractor.
/// Only the ZIP's file bytes are parsed, and all parsing precedes provisioning.
#[utoipa::path(
    post, path = "/import-export/import",
    request_body(content = ProvisioningUpload, content_type = "multipart/form-data"),
    responses(
        (status = 200, description = "Success", body = crate::provisioning::Report),
        (status = 400, description = "Request failed", body = crate::error::ErrorBody),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 413, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
        (status = 503, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn import_blueprint(
    State(s): State<GovernanceState>,
    AdmittedUser(user): AdmittedUser,
    request: axum::extract::Request,
) -> axum::response::Response {
    use crate::{
        blueprint::{Bundle, InputError, MAX_ARCHIVE},
        provisioning::Importer,
    };
    use axum::{
        extract::{FromRequest, Multipart},
        response::IntoResponse,
    };
    let result = async {
        require_directory_actor(&s).map_err(IntoResponse::into_response)?;
        match s.fga.is_platform_owner(&user.uid).await {
            Ok(true) => (),
            Ok(false) => return Err(AppError::Forbidden.into_response()),
            Err(_) => return Err(AppError::Unavailable("authorization unavailable".into()).into_response()),
        }
        let directory = s.directory.as_ref().filter(|d| s.auth.directory_subjects_match(d.realm()))
            .ok_or_else(|| AppError::Unavailable("import requires configured Keycloak service credentials and matching subject authentication".into()).into_response())?;
        let bearer = request.headers().get(header::AUTHORIZATION).and_then(|h| h.to_str().ok())
            .and_then(|h| h.split_once(' ')).filter(|(scheme,_)| scheme.eq_ignore_ascii_case("bearer")).map(|(_,token)| token.trim()).unwrap_or("").to_owned();
        let mut multipart = Multipart::from_request(request, &s).await.map_err(|e| upload_error(e.status()))?;
        let mut field = multipart.next_field().await.map_err(|e| upload_error(e.status()))?
            .ok_or_else(|| upload_error(StatusCode::BAD_REQUEST))?;
        if field.name() != Some("file") { return Err(upload_error(StatusCode::BAD_REQUEST)); }
        let mut bytes = Vec::new();
        while let Some(chunk) = field.chunk().await.map_err(|e| upload_error(e.status()))? {
            if chunk.len() > MAX_ARCHIVE - bytes.len() { return Err(upload_error(StatusCode::PAYLOAD_TOO_LARGE)); }
            bytes.extend_from_slice(&chunk);
        }
        drop(field); // Release multer's exclusive field handle before checking for another.
        if multipart.next_field().await.map_err(|e| upload_error(e.status()))?.is_some() { return Err(upload_error(StatusCode::BAD_REQUEST)); }
        let bundle = tokio::task::spawn_blocking(move || Bundle::parse(&bytes)).await
            .map_err(|_| (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({"detail":"import parsing failed"}))).into_response())?
            .map_err(|error| {
                let status = match error { InputError::TooLarge => StatusCode::PAYLOAD_TOO_LARGE, _ => StatusCode::UNPROCESSABLE_ENTITY };
                (status, Json(serde_json::json!({"detail":error.to_string()}))).into_response()
            })?;
        let report = Importer { pool: &s.pool, fga: &s.fga, directory, auth: &s.auth, bearer: &bearer }.run(&bundle).await
            .map_err(|error| {
                let status = error.downcast_ref::<crate::provisioning::Failure>().map(|e| e.status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
                (status, Json(serde_json::json!({"detail":error.to_string()}))).into_response()
            })?;
        Ok::<_, axum::response::Response>(Json(report).into_response())
    }.await;
    result.unwrap_or_else(|response| response)
}
fn upload_error(status: StatusCode) -> axum::response::Response {
    use axum::response::IntoResponse;
    let status = if status == StatusCode::PAYLOAD_TOO_LARGE {
        status
    } else {
        StatusCode::BAD_REQUEST
    };
    (status, Json(serde_json::json!({"detail": if status == StatusCode::PAYLOAD_TOO_LARGE { "provisioning bundle exceeds size limit" } else { "expected one multipart file" }}))).into_response()
}
