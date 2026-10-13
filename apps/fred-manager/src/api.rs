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
    error::{AppError, AppResult},
    fga::{Fga, Tuple},
    ingestion::{DeleteDocument, IngestDocument, Ingestion, Submitted},
};

#[derive(Clone)]
pub struct AppState {
    pub auth: Arc<Authenticator>,
    pub pool: PgPool,
    pub fga: Fga,
    pub bootstrap_token_env_var: Option<String>,
    pub ingestion: Ingestion,
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
        .allow_headers([header::CONTENT_TYPE, header::AUTHORIZATION]);
    let api = Router::new()
        .route(
            "/healthz",
            get(|| async { Json(serde_json::json!({ "status": "ok" })) }),
        )
        .route("/bootstrap/platform-admin", post(bootstrap_platform_admin))
        .route("/me", get(me))
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
        .with_state(state);
    Router::new().nest(base_url, api).layer(cors)
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
    Json(req): Json<BootstrapRequest>,
) -> AppResult<Json<BootstrapResponse>> {
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
    platform_roles: Vec<&'static str>,
}

async fn me(State(s): State<AppState>, user: CurrentUser) -> AppResult<Json<Me>> {
    let admin = s.fga.is_platform_admin(&user.uid).await?;
    Ok(Json(Me {
        platform_roles: if admin {
            vec!["platform_admin"]
        } else {
            Vec::new()
        },
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
    Json(req): Json<CreateSpace>,
) -> AppResult<(StatusCode, Json<Space>)> {
    let parent = db::space(&s.pool, req.parent_id).await?;
    domain::check_parent(req.kind, Some(&parent))?;
    require(&s.fga, &user, Permission::Manage, parent.id).await?;
    if !s.fga.check(&req.admin, Permission::Read, parent.id).await? {
        return Err(AppError::Conflict(
            "the administrator must be able to read the parent space".into(),
        ));
    }
    let id = Uuid::new_v4();
    let space = Space {
        id,
        kind: req.kind,
        name: req.name,
        parent_id: Some(parent.id),
        personal_owner: None,
        path: domain::space_path(Some(&parent), id),
    };
    persist_space(
        &s,
        &space,
        &[Tuple {
            user: &req.admin,
            role: Role::Admin,
            space: id,
        }],
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
    Json(req): Json<CreatePersonalSpace>,
) -> AppResult<(StatusCode, Json<Space>)> {
    let org = db::space(&s.pool, req.organization_id).await?;
    domain::check_parent(SpaceKind::Team, Some(&org))?;
    require(&s.fga, &user, Permission::Read, org.id).await?;
    let id = Uuid::new_v4();
    let space = Space {
        id,
        kind: SpaceKind::Team,
        name: user.clone(),
        parent_id: Some(org.id),
        personal_owner: Some(user.clone()),
        path: domain::space_path(Some(&org), id),
    };
    let tuples = [
        Tuple {
            user: &user,
            role: Role::Member,
            space: id,
        },
        Tuple {
            user: &user,
            role: Role::Editor,
            space: id,
        },
    ];
    persist_space(&s, &space, &tuples).await?;
    Ok((StatusCode::CREATED, Json(space)))
}

/// Row and initial roles land together: the row commits only after OpenFGA accepted the
/// tuples. A failed commit leaves roles on a space id that never existed, which grant nothing.
pub async fn persist_space_with(
    pool: &PgPool,
    fga: &Fga,
    space: &Space,
    tuples: &[Tuple<'_>],
) -> AppResult<()> {
    let mut tx = pool.begin().await?;
    db::insert_space(&mut tx, space).await?;
    fga.write(tuples, &[]).await?;
    tx.commit().await?;
    Ok(())
}

async fn persist_space(s: &AppState, space: &Space, tuples: &[Tuple<'_>]) -> AppResult<()> {
    persist_space_with(&s.pool, &s.fga, space, tuples).await
}

fn parse_role(role: &str) -> AppResult<Role> {
    Role::parse(role).ok_or_else(|| AppError::BadRequest(format!("unknown role {role}")))
}

async fn grant(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path((id, role, target)): Path<(Uuid, String, String)>,
) -> AppResult<StatusCode> {
    let role = parse_role(&role)?;
    let space = db::space(&s.pool, id).await?;
    if space.personal_owner.is_some() {
        return Err(AppError::Conflict(
            "a personal space has a fixed single member".into(),
        ));
    }
    require(&s.fga, &user, Permission::Manage, id).await?;
    if let Some(parent) = space.parent_id
        && !s.fga.check(&target, Permission::Read, parent).await?
    {
        return Err(AppError::Conflict(
            "the user must first be able to read the parent space".into(),
        ));
    }
    s.fga
        .write(
            &[Tuple {
                user: &target,
                role,
                space: id,
            }],
            &[],
        )
        .await?;
    Ok(StatusCode::NO_CONTENT)
}

async fn revoke(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path((id, role, target)): Path<(Uuid, String, String)>,
) -> AppResult<StatusCode> {
    let role = parse_role(&role)?;
    let space = db::space(&s.pool, id).await?;
    if space.personal_owner.is_some() {
        return Err(AppError::Conflict(
            "a personal space has a fixed single member".into(),
        ));
    }
    require(&s.fga, &user, Permission::Manage, id).await?;
    let held = s.fga.roles_of(&target).await?;
    let on_space: Vec<Role> = held
        .iter()
        .filter(|(s, _)| *s == id)
        .map(|(_, r)| *r)
        .collect();
    let children = db::child_space_ids(&s.pool, id).await?;
    let in_child = held.iter().any(|(s, _)| children.contains(s));
    if domain::revocation_blocked(role, &on_space, in_child) {
        return Err(AppError::Conflict(
            "remove the user from the child spaces first".into(),
        ));
    }
    s.fga
        .write(
            &[],
            &[Tuple {
                user: &target,
                role,
                space: id,
            }],
        )
        .await?;
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
    Json(req): Json<CreateFolder>,
) -> AppResult<(StatusCode, Json<Folder>)> {
    require(&s.fga, &user, Permission::Write, req.space_id).await?;
    let parent = match req.parent_id {
        Some(p) => Some(db::folder(&s.pool, p).await?),
        None => None,
    };
    if parent.as_ref().is_some_and(|p| p.space_id != req.space_id) {
        return Err(AppError::BadRequest(
            "the parent folder belongs to another space".into(),
        ));
    }
    let id = Uuid::new_v4();
    let folder = Folder {
        id,
        space_id: req.space_id,
        parent_id: req.parent_id,
        name: req.name,
        path: domain::folder_path(parent.as_ref(), id),
    };
    db::insert_folder(&s.pool, &folder).await?;
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
    Json(req): Json<Rename>,
) -> AppResult<StatusCode> {
    let folder = db::folder(&s.pool, id).await?;
    require(&s.fga, &user, Permission::Write, folder.space_id).await?;
    db::rename_folder(&s.pool, id, &req.name).await?;
    Ok(StatusCode::NO_CONTENT)
}

async fn delete_folder(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path(id): Path<Uuid>,
) -> AppResult<StatusCode> {
    let folder = db::folder(&s.pool, id).await?;
    require(&s.fga, &user, Permission::Write, folder.space_id).await?;
    db::delete_folder(&s.pool, id).await?;
    Ok(StatusCode::NO_CONTENT)
}

// ---------------------------------------------------------------- documents

#[derive(Deserialize)]
struct DocumentQuery {
    folder_id: Option<Uuid>,
    after: Option<Uuid>,
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
    Ok(Json(
        db::documents(&s.pool, space, q.folder_id, q.after, limit).await?,
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
    Json(req): Json<CreateDocument>,
) -> AppResult<(StatusCode, Json<CreatedDocument>)> {
    require(&s.fga, &user, Permission::Write, req.space_id).await?;
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
    db::insert_document(&s.pool, &document).await?;
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
    Json(req): Json<Rename>,
) -> AppResult<StatusCode> {
    let document = db::document(&s.pool, id).await?;
    require(&s.fga, &user, Permission::Write, document.space_id).await?;
    db::rename_document(&s.pool, id, &req.name).await?;
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
    require(&s.fga, &user, Permission::Write, document.space_id).await?;
    s.ingestion
        .delete(DeleteDocument {
            document_id: id,
            space_id: document.space_id,
            storage_prefix: domain::storage_prefix(document.space_id, id),
        })
        .await?;
    db::delete_document(&s.pool, id).await?;
    Ok(StatusCode::NO_CONTENT)
}

#[derive(Deserialize, Default)]
struct IngestRequest {
    profile: Option<String>,
}

async fn ingest_document(
    State(s): State<AppState>,
    CurrentUser { uid: user, .. }: CurrentUser,
    Path(id): Path<Uuid>,
    body: Option<Json<IngestRequest>>,
) -> AppResult<StatusCode> {
    let document = db::document(&s.pool, id).await?;
    require(&s.fga, &user, Permission::Write, document.space_id).await?;
    let folder_path = match document.folder_id {
        Some(f) => db::folder(&s.pool, f).await?.path,
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
        profile: body
            .and_then(|Json(b)| b.profile)
            .unwrap_or_else(|| "medium".into()),
        requested_by: user,
    };
    match s.ingestion.ingest(input).await? {
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
    Json(req): Json<AuthorizeDocument>,
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
    Json(req): Json<AuthorizeScope>,
) -> AppResult<Json<Scope>> {
    let space = db::space(&s.pool, req.space_id).await?;
    require(&s.fga, &user, Permission::Read, space.id).await?;
    Ok(Json(Scope {
        space_ids: space.path,
    }))
}
