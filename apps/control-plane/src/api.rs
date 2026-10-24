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

//! REST surface. Content permissions are checked on the owning space.
//! Directory responses also check write capability for the existing UI controls.

use std::sync::Arc;

use axum::{
    Json, Router,
    extract::{FromRef, State},
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
    domain::{Folder, Permission, Role, Space, SpaceKind, SpaceRow},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery},
    fga::Fga,
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
    pub lifecycle: crate::lifecycle::Lifecycle,
    pub directory: Option<Directory>,
    pub content: Option<Arc<crate::documents::Storage>>,
    pub processing: Option<Arc<crate::processing::Processing>>,
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
        .allow_headers([
            header::CONTENT_TYPE,
            header::AUTHORIZATION,
            header::HeaderName::from_static("idempotency-key"),
        ])
        .expose_headers([
            header::RETRY_AFTER,
            header::CONTENT_DISPOSITION,
            header::LOCATION,
            header::HeaderName::from_static("x-request-id"),
            header::HeaderName::from_static("x-correlation-id"),
        ]);
    // Request logging is outermost, as in fred-core: it also sees CORS and 404 answers.
    Router::new()
        .nest(base_url, routes(state))
        .layer(cors)
        .layer(axum::middleware::from_fn(logging::request_logging))
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
async fn frontend_config(State(s): State<AppState>) -> AppResult<axum::response::Response> {
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
    State(s): State<AppState>,
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
    State(s): State<AppState>,
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
    State(s): State<AppState>,
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
async fn me(State(s): State<AppState>, AdmittedUser(user): AdmittedUser) -> AppResult<Json<Me>> {
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
        (status = 409, description = "Ambiguous organization context, or a space role without its parent membership", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn my_spaces(
    State(s): State<AppState>,
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
    State(s): State<AppState>,
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
        (status = 400, description = "Invalid application request", body = crate::error::ErrorBody),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Request failed", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 422, description = "Malformed subject, or not a known identity of the user directory", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
        (status = 503, description = "User directory unavailable", body = crate::error::ErrorBody),
    )
)]
async fn grant(
    State(s): State<AppState>,
    AdmittedUser(CurrentUser { uid: user, .. }): AdmittedUser,
    ApiPath((id, role, target)): ApiPath<(Uuid, String, String)>,
) -> AppResult<StatusCode> {
    let role = parse_role(&role)?;
    if role == Role::OrganizationOwner
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
        &organization_directory(&s)?,
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
        (status = 400, description = "Invalid application request", body = crate::error::ErrorBody),
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
    ApiPath((id, role, target)): ApiPath<(Uuid, String, String)>,
) -> AppResult<StatusCode> {
    spaces::revoke(&s.pool, &s.fga, &user, id, parse_role(&role)?, &target).await?;
    Ok(StatusCode::NO_CONTENT)
}

// ---------------------------------------------------------------- folders

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
        (status = 400, description = "Invalid application request", body = crate::error::ErrorBody),
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
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(req): ApiJson<Rename>,
) -> AppResult<StatusCode> {
    let folder = db::folder(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, folder.space_id).await?;
    db::folder(&mut *tx, id).await?;
    db::rename_folder(&mut *tx, id, &spaces::folder_name(&req.name)?).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(
    delete, path = "/folders/{id}",
    params(("id" = Uuid, Path)),
    responses(
        (status = 204, description = "Success"),
        (status = 400, description = "Invalid application request", body = crate::error::ErrorBody),
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
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<StatusCode> {
    let folder = db::folder(&s.pool, id).await?;
    let mut tx = spaces::authorized_write(&s.pool, &s.fga, &user, folder.space_id).await?;
    db::folder(&mut *tx, id).await?;
    db::delete_folder(&mut *tx, id).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

// ---------------------------------------------------------------- documents

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
    let document = match db::document(&s.pool, req.document_id).await {
        Err(sqlx::Error::RowNotFound) => return Ok(Json(Allowed { allowed: false })),
        document => document?,
    };
    let decision = spaces::authorize(&s.pool, &s.fga, &user, document.space_id, req.permission)
        .await
        .map(|_| true);
    Ok(Json(Allowed {
        allowed: probe(decision)?,
    }))
}

/// A business refusal is `allowed: false`: a missing, foreign or retired space, or a
/// missing permission. An ambiguous context or a dependency failure stays an error.
fn probe(decision: AppResult<bool>) -> AppResult<bool> {
    match decision {
        Ok(allowed) => Ok(allowed),
        Err(AppError::NotFound | AppError::Forbidden) => Ok(false),
        Err(AppError::Problem { code, .. })
            if code == crate::lifecycle::store::PENDING_DELETION =>
        {
            Ok(false)
        }
        Err(error) => Err(error),
    }
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

// Platform mutation entry points require a real authenticated actor, even in dev mode.
fn require_real_authentication(s: &AppState) -> AppResult<()> {
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
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
) -> AppResult<Json<Vec<platform::Grant>>> {
    require_real_authentication(&s)?;
    Ok(Json(platform::list(&s.fga, &user.uid).await?))
}
fn platform_role(name: &str) -> AppResult<PlatformRole> {
    PlatformRole::parse(name).ok_or_else(|| AppError::BadRequest("unknown platform role".into()))
}
#[utoipa::path(
    put, path = "/users/{user}/platform-roles/{role}",
    params(("user" = String, Path), ("role" = PlatformRole, Path)),
    responses(
        (status = 204, description = "Success"),
        (status = 400, description = "Invalid application request", body = crate::error::ErrorBody),
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
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((target, role)): ApiPath<(String, String)>,
) -> AppResult<StatusCode> {
    require_real_authentication(&s)?;
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
    params(("user" = String, Path), ("role" = PlatformRole, Path)),
    responses(
        (status = 204, description = "Success"),
        (status = 400, description = "Invalid application request", body = crate::error::ErrorBody),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 404, description = "Direct grant not found", body = crate::error::ErrorBody),
        (status = 409, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
        (status = 503, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn revoke_platform_role(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((target, role)): ApiPath<(String, String)>,
) -> AppResult<StatusCode> {
    require_real_authentication(&s)?;
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
    State(s): State<AppState>,
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
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiJson(req): ApiJson<SpaceCheck>,
) -> AppResult<Json<Allowed>> {
    let decision = async {
        let space = spaces::load(&s.pool, req.space_id).await?;
        let allowed = spaces::in_organization(&s.pool, &s.fga, &user.uid, space.organization)
            .await?
            && s.fga
                .check_space(&user.uid, req.permission, req.space_id)
                .await?;
        crate::lifecycle::store::require_active(&s.pool, space.id).await?;
        Ok(allowed)
    };
    Ok(Json(Allowed {
        allowed: probe(decision.await)?,
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
        (status = 400, description = "Invalid application request", body = crate::error::ErrorBody),
        (status = 401, description = "Request failed", body = crate::error::ErrorBody),
        (status = 403, description = "Request failed", body = crate::error::ErrorBody),
        (status = 500, description = "Request failed", body = crate::error::ErrorBody),
    )
)]
async fn team_registry(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiQuery(query): ApiQuery<RegistryQuery>,
) -> AppResult<Json<Vec<Space>>> {
    if !s
        .fga
        .check_platform(&user.uid, PlatformPermission::ListAllTeams)
        .await?
    {
        return Err(AppError::Forbidden);
    }
    // Registry metadata only, bounded independently of content and FGA memberships.
    let teams: Vec<SpaceRow> = sqlx::query_as("select id, kind, name, personal_owner, parent_id, organization_id from space where kind = 'team' and personal_owner is null and deletion_id is null and ($1::uuid is null or id > $1) order by id limit 100")
        .bind(query.after).fetch_all(&s.pool).await?;
    Ok(Json(teams.into_iter().map(Space::from).collect()))
}

#[derive(Serialize, utoipa::ToSchema)]
struct OrganizationPage {
    items: Vec<Space>,
    next_cursor: Option<Uuid>,
}

#[utoipa::path(
    get, path = "/admin/organizations",
    params(("after" = Option<Uuid>, Query, description = "Exclusive UUID cursor; at most 100 active organizations.")),
    responses(
        (status = 200, body = OrganizationPage),
        (status = 400, description = "Invalid application request", body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody)
    )
)]
async fn organization_registry(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiQuery(query): ApiQuery<RegistryQuery>,
) -> AppResult<Json<OrganizationPage>> {
    platform::require_owner(&s.fga, &user.uid).await?;
    let mut rows: Vec<SpaceRow> = sqlx::query_as("select id, kind, name, personal_owner, parent_id, organization_id from space where kind = 'organization' and deletion_id is null and ($1::uuid is null or id > $1) order by id limit 101")
        .bind(query.after).fetch_all(&s.pool).await?;
    let next_cursor = (rows.len() > 100).then(|| rows[99].id);
    rows.truncate(100);
    Ok(Json(OrganizationPage {
        items: rows.into_iter().map(Space::from).collect(),
        next_cursor,
    }))
}

fn organization_directory(s: &AppState) -> AppResult<crate::users::Directory<'_>> {
    if s.onboarding.user_directory == crate::users::DirectoryKind::Local {
        return Ok(crate::users::Directory::Local(&s.pool));
    }
    if s.directory
        .as_ref()
        .is_some_and(|d| !s.auth.directory_subjects_match(d.realm()))
    {
        return Err(AppError::Unavailable(
            "directory requires matching subject authentication".into(),
        ));
    }
    Ok(crate::users::Directory::Keycloak(s.directory.as_ref()))
}

#[derive(Deserialize)]
struct CandidateQuery {
    query: String,
}

#[utoipa::path(
    get, path = "/admin/organizations/candidates",
    params(("query" = String, Query, min_length = 2)),
    responses(
        (status = 200, body = Vec<crate::users::UserSummary>),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn search_organization_candidates(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiQuery(query): ApiQuery<CandidateQuery>,
) -> AppResult<Json<Vec<crate::users::UserSummary>>> {
    platform::require_owner(&s.fga, &user.uid).await?;
    if query.query.chars().count() < 2 {
        return Err(AppError::Unprocessable(
            "query must contain at least 2 characters".into(),
        ));
    }
    Ok(Json(
        organization_directory(&s)?.search(&query.query).await?,
    ))
}

#[derive(Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
struct CreateOrganization {
    name: String,
    owner_username: String,
    admin_username: String,
}

#[utoipa::path(
    post, path = "/admin/organizations", request_body = CreateOrganization,
    responses(
        (status = 201, body = Space),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn create_organization(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiJson(req): ApiJson<CreateOrganization>,
) -> AppResult<(StatusCode, Json<Space>)> {
    let directory = organization_directory(&s)?;
    let org = spaces::create_managed_organization(
        &s.pool,
        &s.fga,
        &directory,
        &user.uid,
        &req.name,
        &req.owner_username,
        &req.admin_username,
    )
    .await?;
    Ok((StatusCode::CREATED, Json(org)))
}

impl FromRef<AppState> for AdmissionState {
    fn from_ref(s: &AppState) -> Self {
        Self {
            auth: s.auth.clone(),
            pool: s.pool.clone(),
            version: s.onboarding.gcu_version.clone(),
            user_directory: s.onboarding.user_directory,
        }
    }
}
/// Every API route, without the base URL prefix, CORS or request logging.
pub fn routes(state: AppState) -> Router {
    registrations().with_state(state).split_for_parts().0
}

/// One registration list serves both the runtime router and the OpenAPI contract.
fn registrations() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(health))
        .merge(crate::embedded_agent::routes())
        .routes(routes!(create_space))
        .routes(routes!(grant, revoke))
        .routes(routes!(rename_folder, delete_folder))
        .routes(routes!(authorize_document))
        .routes(routes!(authorize_scope))
        .merge(crate::documents::http::routes())
        .merge(crate::processing::http::routes())
        .routes(routes!(frontend_config))
        .routes(routes!(onboarding_status))
        .routes(routes!(accept_terms))
        .routes(routes!(bootstrap_platform_admin))
        .routes(routes!(me))
        .routes(routes!(my_spaces))
        .routes(routes!(delete_space))
        .routes(routes!(deletion_status))
        .routes(routes!(create_personal_space))
        .routes(routes!(create_folder))
        .routes(
            routes!(import_blueprint).layer(axum::extract::DefaultBodyLimit::max(
                crate::blueprint::MAX_ARCHIVE + 64 * 1024,
            )),
        )
        .routes(routes!(list_platform_roles))
        .routes(routes!(grant_platform_role, revoke_platform_role))
        .routes(routes!(team_registry))
        .routes(routes!(organization_registry, create_organization))
        .routes(routes!(search_organization_candidates))
        .routes(routes!(authorize_platform))
        .routes(routes!(authorize_space))
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
    let api = registrations().into_openapi();
    let mut api = OpenApiRouter::<()>::new()
        .nest("/control-plane/v1", OpenApiRouter::with_openapi(api))
        .into_openapi();
    api.info.title = "control-plane".into();
    let components = api
        .components
        .get_or_insert_with(|| ComponentsBuilder::new().build());
    components.schemas.insert(
        "EntryOrder".into(),
        <crate::documents::models::EntryOrder as utoipa::PartialSchema>::schema(),
    );
    components.add_security_scheme(
        "bearer",
        SecurityScheme::Http(Http::new(HttpAuthScheme::Bearer)),
    );
    api.security = Some(vec![SecurityRequirement::new(
        "bearer",
        Vec::<String>::new(),
    )]);
    declare_extractor_rejections(&mut api);
    api
}

/// `extract` rejects any route's parameters or body the same way; declare it once.
fn declare_extractor_rejections(api: &mut utoipa::openapi::OpenApi) {
    use utoipa::openapi::{ContentBuilder, Ref, RefOr, ResponseBuilder};
    let error = |description: &str| {
        RefOr::T(
            ResponseBuilder::new()
                .description(description)
                .content(
                    "application/json",
                    ContentBuilder::new()
                        .schema(Some(Ref::from_schema_name("ErrorBody")))
                        .build(),
                )
                .build(),
        )
    };
    for item in api.paths.paths.values_mut() {
        let operations = [
            &mut item.get,
            &mut item.put,
            &mut item.post,
            &mut item.delete,
            &mut item.patch,
        ];
        for operation in operations.into_iter().flatten() {
            let json_body = operation
                .request_body
                .as_ref()
                .is_some_and(|body| {
                    matches!(body, RefOr::T(body) if body.content.contains_key("application/json"))
                });
            let responses = &mut operation.responses.responses;
            if json_body {
                responses
                    .entry("400".into())
                    .or_insert_with(|| error("Malformed JSON body"));
            }
            if json_body || operation.parameters.as_ref().is_some_and(|p| !p.is_empty()) {
                responses
                    .entry("422".into())
                    .or_insert_with(|| error("Invalid path, query or body fields"));
            }
        }
    }
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
    State(s): State<AppState>,
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
        require_real_authentication(&s).map_err(IntoResponse::into_response)?;
        match s.fga.is_platform_owner(&user.uid).await {
            Ok(true) => (),
            Ok(false) => return Err(AppError::Forbidden.into_response()),
            Err(_) => return Err(AppError::Unavailable("authorization unavailable".into()).into_response()),
        }
        let directory = s.directory.as_ref().filter(|d| s.auth.directory_subjects_match(d.realm()))
            .ok_or_else(|| AppError::Unavailable("import requires configured Keycloak service credentials and matching subject authentication".into()).into_response())?;
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
        let report = Importer { pool: &s.pool, fga: &s.fga, directory, operator: &user.uid }.run(&bundle).await
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

#[utoipa::path(delete, path = "/spaces/{id}", params(("id" = Uuid, Path)), responses(
    (status = 202, description = "Durably accepted", body = crate::lifecycle::Receipt),
    (status = 200, description = "Already completed", body = crate::lifecycle::Receipt),
    (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
    (status = 404, body = crate::error::ErrorBody), (status = 409, body = crate::error::ErrorBody),
    (status = 503, body = crate::error::ErrorBody), (status = 500, body = crate::error::ErrorBody)
))]
async fn delete_space(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<(StatusCode, Json<crate::lifecycle::Receipt>)> {
    require_real_authentication(&s)?;
    let receipt = s.lifecycle.accept(&s.pool, &s.fga, &user.uid, id).await?;
    Ok((
        if receipt.status == crate::lifecycle::Status::Completed {
            StatusCode::OK
        } else {
            StatusCode::ACCEPTED
        },
        Json(receipt),
    ))
}
#[utoipa::path(get, path = "/deletions/{operation_id}", params(("operation_id" = Uuid, Path)), responses(
    (status = 200, body = crate::lifecycle::Receipt),
    (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
    (status = 404, body = crate::error::ErrorBody), (status = 503, body = crate::error::ErrorBody), (status = 500, body = crate::error::ErrorBody)
))]
async fn deletion_status(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<crate::lifecycle::Receipt>> {
    require_real_authentication(&s)?;
    Ok(Json(
        crate::lifecycle::store::status(&s.pool, &s.fga, &user.uid, id).await?,
    ))
}
