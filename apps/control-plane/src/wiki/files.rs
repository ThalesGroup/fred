// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! A Wiki file is a frozen copy of a conversation file, taken when it is proposed
//! (D14). It reuses the upload journal: reserve, copy and verify outside SQL, publish.
use super::{
    access::{self, Access, Query},
    store::by_slug,
    *,
};
use crate::{
    api::AppState,
    auth::CurrentUser,
    documents::{
        Storage, conflict, exceeded, in_progress, models::UploadStatus, replayed, unavailable,
    },
    domain::Permission,
};
use axum::http::{HeaderMap, StatusCode};
use sha2::{Digest, Sha256};

/// The current content of a conversation output, then its live PDF preview.
#[derive(sqlx::FromRow)]
struct Part {
    content_id: Option<Uuid>,
    object_key: Option<String>,
    name: String,
    mime: String,
    size: i64,
    sha256: String,
}

struct Target {
    page: Option<Uuid>,
    base: Option<Uuid>,
    title: Option<String>,
    parent: Option<Uuid>,
}

/// One journal row and one catalogue content per copied part.
struct Copy {
    id: Uuid,
    key: String,
    part: Part,
}

fn content_changed() -> Error {
    conflict(
        "content_changed",
        "The conversation file changed; read it again before proposing it",
    )
    .into()
}

/// Returns whether this request created the proposal; a replay answers the same one.
#[allow(clippy::too_many_arguments)]
pub(super) async fn propose(
    state: &AppState,
    user: &CurrentUser,
    query: &Query,
    space: Uuid,
    key: Uuid,
    body: ProposeWikiFileRequest,
    headers: &HeaderMap,
) -> Result<(bool, WikiProposal)> {
    validate_source(&body, query)?;
    let storage = state.content.as_deref().ok_or_else(unavailable)?;
    // A replay needs the live conversation too: once it is deleted, the key answers 404.
    let mut access = open(state, user, query, space, false).await?;
    let fingerprint = request_fingerprint(space, access.session, &body)?;
    if let Some((id, status)) = access.replay(key, &fingerprint).await? {
        replayed(status)?;
        let proposal = access.proposal(id).await?;
        access.tx.commit().await?;
        return Ok((false, proposal));
    }
    if !storage.config.uploads_enabled {
        return Err(unavailable().into());
    }
    let _permit = storage.uploads.clone().try_acquire_owned().map_err(|_| {
        AppError::problem(
            StatusCode::TOO_MANY_REQUESTS,
            "transfer_capacity",
            "All document transfer slots are busy",
        )
    })?;
    // Resolve only the configured pod of the checked conversation; no SQL lock
    // survives the authenticated export. The spool has no durable pathname.
    let (parts, mut exported) = if body.writable_document.is_some() || body.workspace_file.is_some()
    {
        let endpoint = export_endpoint(state, &mut access, &body).await?;
        access
            .target(
                &body,
                body.title
                    .as_deref()
                    .or_else(|| {
                        body.workspace_file
                            .as_ref()
                            .and_then(|source| source.path.rsplit('/').next())
                    })
                    .unwrap_or("document.md"),
                false,
            )
            .await?;
        access.tx.commit().await?;
        let spool = export_source(storage, &endpoint, &body, headers).await?;
        let part = Part {
            content_id: None,
            object_key: None,
            name: spool.name.clone(),
            mime: spool.mime.clone(),
            size: spool.size,
            sha256: spool.sha256(),
        };
        access = open(state, user, query, space, false).await?;
        (vec![part], Some(spool))
    } else {
        (
            access
                .source(
                    body.document_id.ok_or_else(|| invalid("Missing source"))?,
                    body.expected_content_id,
                )
                .await?,
            None,
        )
    };
    let target = access.target(&body, &parts[0].name, false).await?;
    let copies = reserve(storage, &mut access, key, &fingerprint, parts).await?;
    access.tx.commit().await?;
    // Boxed like the Drive upload path, for the debug-build test stack.
    let outcome = Box::pin(async {
        for copy in &copies {
            let spool = if let Some(spool) = exported.take() {
                spool
            } else {
                tokio::time::timeout(
                    storage.deadline(),
                    storage.spool_object(
                        copy.part.object_key.as_deref().ok_or_else(unavailable)?,
                        copy.part.name.clone(),
                        copy.part.mime.clone(),
                        copy.part.size,
                        &copy.part.sha256,
                    ),
                )
                .await
                .map_err(|_| exceeded())??
            };
            storage.transfer_upload(copy.id, &copy.key, spool).await?;
        }
        publish(storage, state, user, query, space, &body, &copies, &target).await
    })
    .await;
    if outcome.is_err() {
        for copy in &copies {
            if storage
                .fail(copy.id, "wiki_copy_interrupted")
                .await
                .is_err()
            {
                tracing::warn!(operation_id=%copy.id, outcome="uncertain", "Wiki copy awaits reconciliation");
            }
        }
    }
    outcome.map(|proposal| (true, proposal))
}

/// Sources are identities checked by their owner, never browser download URLs.
fn validate_source(body: &ProposeWikiFileRequest, query: &Query) -> Result<()> {
    let count = usize::from(body.document_id.is_some())
        + usize::from(body.writable_document.is_some())
        + usize::from(body.workspace_file.is_some());
    if count != 1 {
        return Err(invalid("Name exactly one conversation source."));
    }
    let digest_ok = |digest: &str| {
        digest.len() == 64
            && digest
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    };
    if body.destination_title.is_some()
        && (query.delegation.agent.is_some()
            || body.slug.is_some()
            || body.base_revision_id.is_some())
    {
        return Err(invalid(
            "Only a person creates a destination for new files.",
        ));
    }
    if (body.writable_document.is_some() || body.workspace_file.is_some())
        && (query.delegation.agent.is_some()
            || body.expected_content_id.is_some()
            || body.slug.is_some()
            || body.base_revision_id.is_some()
            || (body.parent_slug.is_none() && body.destination_title.is_none()))
    {
        return Err(invalid("An exported document requires a destination page."));
    }
    if let Some(source) = &body.writable_document
        && (!body.title.as_deref().is_some_and(|name| {
            name.ends_with(if source.format == Some(WritableWikiFormat::Docx) {
                ".docx"
            } else {
                ".md"
            })
        }) || source.document_id.is_empty()
            || source.document_id.len() > 128
            || !source
                .document_id
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, b'-' | b'_'))
            || !digest_ok(&source.sha256))
    {
        return Err(invalid(
            "An editable document requires its identity, saved digest and export name.",
        ));
    }
    if let Some(source) = &body.workspace_file
        && (source.path.len() > 4096
            || source.path.contains('\\')
            || source.path.contains(':')
            || source.path.chars().any(char::is_control)
            || source
                .path
                .split('/')
                .any(|part| part.is_empty() || matches!(part, "." | ".." | ".deep"))
            || !digest_ok(&source.sha256))
    {
        return Err(invalid("Invalid conversation workspace source."));
    }
    Ok(())
}

async fn export_endpoint(
    state: &AppState,
    access: &mut Access,
    body: &ProposeWikiFileRequest,
) -> Result<reqwest::Url> {
    let runtime: String =
        sqlx::query_scalar("select runtime_id from session_metadata where session_id=$1")
            .bind(access.session)
            .fetch_one(&mut *access.tx)
            .await?;
    let pod = state
        .agent_catalog
        .runtime_catalog_sources
        .iter()
        .find(|pod| pod.enabled && pod.runtime_id == runtime)
        .ok_or_else(unavailable)?;
    let mut url = reqwest::Url::parse(&pod.base_url).map_err(|_| unavailable())?;
    let session = access
        .session
        .ok_or_else(|| invalid("Missing conversation"))?
        .to_string();
    if let Some(source) = &body.writable_document {
        url.path_segments_mut()
            .map_err(|_| unavailable())?
            .pop_if_empty()
            .extend([
                "capabilities",
                "writable_document",
                "sessions",
                &session,
                "documents",
                &source.document_id,
                "export",
            ]);
        url.query_pairs_mut()
            .append_pair(
                "format",
                if source.format == Some(WritableWikiFormat::Docx) {
                    "docx"
                } else {
                    "md"
                },
            )
            .append_pair("expected_sha256", &source.sha256);
    } else if let Some(source) = &body.workspace_file {
        url.path_segments_mut()
            .map_err(|_| unavailable())?
            .pop_if_empty()
            .extend(["agents", "sessions", &session, "workspace", "content"]);
        url.query_pairs_mut().append_pair("path", &source.path);
    }
    Ok(url)
}

async fn export_source(
    storage: &Storage,
    endpoint: &reqwest::Url,
    body: &ProposeWikiFileRequest,
    headers: &HeaderMap,
) -> Result<crate::documents::Spool> {
    let client = crate::agents::catalog_client().map_err(|_| unavailable())?;
    let mut request = client.get(endpoint.clone()).timeout(storage.deadline());
    // Forward only the authenticated person's bearer to the platform-approved pod.
    if let Some(token) = headers.get(axum::http::header::AUTHORIZATION) {
        request = request.header(axum::http::header::AUTHORIZATION, token);
    }
    let mut response = request.send().await.map_err(|_| unavailable())?;
    match response.status() {
        StatusCode::OK => {}
        StatusCode::FORBIDDEN => return Err(AppError::Forbidden.into()),
        StatusCode::NOT_FOUND => return Err(AppError::NotFound.into()),
        StatusCode::CONFLICT => return Err(content_changed()),
        _ => return Err(unavailable().into()),
    }
    let source_digest = response
        .headers()
        .get("x-source-sha256")
        .and_then(|v| v.to_str().ok())
        .map(str::to_owned);
    let limit = storage.config.limits.file_bytes.min(32 * 1024 * 1024) as usize;
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| unavailable())? {
        if chunk.len() > limit.saturating_sub(bytes.len()) {
            return Err(AppError::problem(
                StatusCode::PAYLOAD_TOO_LARGE,
                "file_too_large",
                "The document exceeds the upload limit",
            )
            .into());
        }
        bytes.extend_from_slice(&chunk);
    }
    let (name, mime, digest) = if let Some(source) = &body.writable_document {
        (
            body.title.as_deref().unwrap_or("document.md"),
            if source.format == Some(WritableWikiFormat::Docx) {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            } else {
                "text/markdown"
            },
            &source.sha256,
        )
    } else if let Some(source) = &body.workspace_file {
        (
            source.path.rsplit('/').next().ok_or_else(unavailable)?,
            "text/plain",
            &source.sha256,
        )
    } else {
        return Err(invalid("Missing export source"));
    };
    let actual_digest = if body
        .writable_document
        .as_ref()
        .is_some_and(|source| source.format == Some(WritableWikiFormat::Docx))
    {
        source_digest.ok_or_else(unavailable)?
    } else {
        format!("{:x}", Sha256::digest(&bytes))
    };
    if actual_digest != *digest {
        return Err(content_changed());
    }
    Ok(storage.spool_bytes(name, mime, &bytes).await?)
}

/// Versioned JSON array: UUIDs are canonical, slugs stay exact, titles use the
/// existing NFC/trim validation. Omitted and null options are identical; absence
/// stays null, never a default read from the mutable source or Wiki tree.
fn request_fingerprint(
    space: Uuid,
    session: Option<Uuid>,
    body: &ProposeWikiFileRequest,
) -> Result<String> {
    let title = body.title.as_deref().map(title).transpose()?;
    if body.workspace_file.is_some()
        || body.destination_title.is_some()
        || body
            .writable_document
            .as_ref()
            .is_some_and(|s| s.format == Some(WritableWikiFormat::Docx))
    {
        let request = serde_json::json!([
            "wiki.conversation_file.v2",
            space,
            session,
            body.document_id,
            body.expected_content_id,
            body.writable_document
                .as_ref()
                .map(|s| (&s.document_id, &s.sha256, &s.format)),
            body.workspace_file.as_ref().map(|s| (&s.path, &s.sha256)),
            title,
            body.parent_slug,
            body.destination_title
                .as_deref()
                .map(super::title)
                .transpose()?,
            body.slug,
            body.base_revision_id,
        ]);
        return Ok(format!("{:x}", Sha256::digest(request.to_string())));
    }
    if let Some(source) = &body.writable_document {
        let request = serde_json::json!([
            "wiki.writable_file.v1",
            space,
            session,
            source.document_id,
            source.sha256,
            title,
            body.parent_slug,
        ]);
        return Ok(format!("{:x}", Sha256::digest(request.to_string())));
    }
    let request = serde_json::json!([
        "wiki.propose_file.v1",
        space,
        session,
        body.document_id,
        body.expected_content_id,
        title,
        body.parent_slug,
        body.slug,
        body.base_revision_id,
    ]);
    Ok(format!("{:x}", Sha256::digest(request.to_string())))
}

/// Every step re-checks the person's live conversation and the Wiki under the space lock.
async fn open(
    state: &AppState,
    user: &CurrentUser,
    query: &Query,
    space: Uuid,
    mutation: bool,
) -> Result<Access> {
    let mut access = access::open(state, user, query, space, Permission::Read, mutation).await?;
    access.require_enabled()?;
    let session = query
        .session_id
        .ok_or_else(|| invalid("The source conversation is required."))?;
    access.own_session(session).await?;
    Ok(access)
}

async fn reserve(
    storage: &Storage,
    access: &mut Access,
    key: Uuid,
    fingerprint: &str,
    parts: Vec<Part>,
) -> Result<Vec<Copy>> {
    storage
        .ensure_budgets(&mut access.tx, &access.space)
        .await?;
    storage.require_cleanup_capacity(&mut *access.tx).await?;
    let (owner, _) = storage.quota(&access.space)?;
    let mut copies = Vec::new();
    for (index, part) in parts.into_iter().enumerate() {
        let id = Uuid::new_v4();
        let copy = Copy {
            key: format!("{}{id}/input/{}", storage.prefix, part.name),
            id,
            part,
        };
        if copy.key.len() > 1024 {
            return Err(invalid(
                "The encoded file name exceeds the object-store key limit.",
            ));
        }
        // The primary copy reserves its bytes; the preview stays outside quota (D14).
        let (purpose, reserved, request) = if index == 0 {
            ("wiki", copy.part.size, key)
        } else {
            ("preview", 0, Uuid::new_v4())
        };
        let inserted = sqlx::query("insert into document_upload(id,request_key,actor,organization_id,space_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,put_pending,purpose,reserved_bytes,request_fingerprint) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'pending',clock_timestamp()+make_interval(secs=>$12),true,$13,$14,$15) on conflict (actor,request_key) do nothing")
            .bind(copy.id).bind(request).bind(&access.person).bind(access.space.organization).bind(access.space.id).bind(owner)
            .bind(&copy.part.name).bind(&copy.part.mime).bind(copy.part.size).bind(&copy.part.sha256).bind(&copy.key)
            .bind(storage.config.limits.lease_seconds() as f64).bind(purpose).bind(reserved)
            .bind((index == 0).then_some(fingerprint))
            .execute(&mut *access.tx).await?.rows_affected();
        if inserted == 0 {
            // A concurrent reservation won. Check its identity before answering
            // in-progress, including when it belongs to another conversation.
            if let Some((_, status)) = access.replay(request, fingerprint).await? {
                replayed(status)?;
            }
            return Err(in_progress().into());
        }
        copies.push(copy);
    }
    Ok(copies)
}

/// The proposal and its catalogue copy appear together; SQL checks the bytes still
/// match the conversation output and counts the copy in the space quota (D15).
#[allow(clippy::too_many_arguments)]
async fn publish(
    storage: &Storage,
    state: &AppState,
    user: &CurrentUser,
    query: &Query,
    space: Uuid,
    body: &ProposeWikiFileRequest,
    copies: &[Copy],
    expected_target: &Target,
) -> Result<WikiProposal> {
    let primary = &copies.first().ok_or_else(unavailable)?.part;
    let mut access = open(state, user, query, space, true).await?;
    // The copied content must still be the output's current content.
    if let Some(document) = body.document_id {
        access.source(document, primary.content_id).await?;
    }
    let target = access.target(body, &primary.name, true).await?;
    if (expected_target.parent.is_some() && target.parent != expected_target.parent)
        || target.page != expected_target.page
    {
        return Err(content_changed());
    }
    let ids: Vec<Uuid> = copies.iter().map(|c| c.id).collect();
    let id = ids[0];
    // The database runs local and organization reservation accounting.
    let stored = sqlx::query("update document_upload set status='stored',completed_at=clock_timestamp() where id=any($1) and status='pending' and not put_pending and expires_at>clock_timestamp()")
        .bind(&ids).execute(&mut *access.tx).await?.rows_affected();
    if stored != ids.len() as u64 {
        return Err(conflict("upload_expired", "This copy can no longer be published").into());
    }
    let (owner, _) = storage.quota(&access.space)?;
    sqlx::query("insert into document(id,space_id,name,created_by,quota_owner,purpose) values($1,$2,$3,$4,$5,'wiki')")
        .bind(id).bind(space).bind(&primary.name).bind(&access.person).bind(owner).execute(&mut *access.tx).await?;
    for copy in copies {
        let preview = (copy.id != id).then_some(id);
        sqlx::query("insert into document_content(id,document_id,kind,source_content_id,object_key,mime,size,sha256,published_at) values($1,$2,case when $3::uuid is null then 'primary' else 'preview' end,$3,$4,$5,$6,$7,clock_timestamp())")
            .bind(copy.id).bind(id).bind(preview).bind(&copy.key).bind(&copy.part.mime).bind(copy.part.size).bind(&copy.part.sha256)
            .execute(&mut *access.tx).await?;
    }
    // The database adjusts used storage bytes; a quota overrun answers 422.
    sqlx::query("update document set current_content_id=$1 where id=$1")
        .bind(id)
        .execute(&mut *access.tx)
        .await?;
    sqlx::query("update document_upload set target_document_id=$2,content_id=id where id=any($1)")
        .bind(&ids)
        .bind(id)
        .execute(&mut *access.tx)
        .await?;
    access
        .insert_proposal(
            id,
            "file",
            target.page,
            target.base,
            target.title.as_deref(),
            target.parent,
            "",
            body.writable_document
                .as_ref()
                .map(|source| source.document_id.as_str()),
            body.workspace_file
                .as_ref()
                .map(|source| source.path.as_str()),
        )
        .await?;
    let proposal = access.settle(id).await?;
    access.tx.commit().await?;
    tracing::info!(target:"fred.security.audit", audit_event="wiki.file_proposed", operation_id=%id, actor_uid=%access.person, space_id=%space, outcome="succeeded", "Wiki file proposed");
    Ok(proposal)
}

impl Access {
    /// The receipt owns request identity even before publication or after deletion.
    async fn replay(
        &mut self,
        key: Uuid,
        fingerprint: &str,
    ) -> Result<Option<(Uuid, UploadStatus)>> {
        let prior: Option<(Uuid, Option<String>, UploadStatus)> = sqlx::query_as(
            "select id,request_fingerprint,status from document_upload where actor=$1 and request_key=$2",
        )
        .bind(&self.person)
        .bind(key)
        .fetch_optional(&mut *self.tx)
        .await?;
        let Some((id, prior_fingerprint, status)) = prior else {
            return Ok(None);
        };
        if prior_fingerprint.as_deref() != Some(fingerprint) {
            return Err(conflict(
                "idempotency_conflict",
                "This request key identifies another write",
            )
            .into());
        }
        Ok(Some((id, status)))
    }

    /// The current content of an output of the checked conversation, as its reader saw
    /// it, then its live preview.
    async fn source(&mut self, document: Uuid, expected: Option<Uuid>) -> Result<Vec<Part>> {
        let parts: Vec<Part> = sqlx::query_as("select c.id as content_id,c.object_key,
            case when c.kind='preview' then d.name||'.pdf' else d.name end as name,c.mime,c.size,c.sha256
            from document d join document_content c on c.id=d.current_content_id
                or (c.source_content_id=d.current_content_id and c.published_at is not null and c.cleaned_at is null)
            where d.id=$1 and d.space_id=$2 and d.session_id=$3 and (d.purpose='output' or ($4 and d.purpose='source')) and d.deletion_id is null
            order by c.kind='preview'")
            .bind(document).bind(self.space.id).bind(self.session).bind(!self.delegated).fetch_all(&mut *self.tx).await?;
        let current = parts
            .first()
            .ok_or(AppError::NotFound)?
            .content_id
            .ok_or(AppError::NotFound)?;
        if expected.is_some_and(|expected| expected != current) {
            return Err(content_changed());
        }
        Ok(parts)
    }

    /// A new file entry, or a new version of the same type of an unchanged file (Q1).
    async fn target(
        &mut self,
        body: &ProposeWikiFileRequest,
        name: &str,
        create_destination: bool,
    ) -> Result<Target> {
        match (
            &body.slug,
            body.base_revision_id,
            &body.title,
            &body.parent_slug,
        ) {
            (Some(slug), Some(base), None, None) => {
                let current = by_slug(&mut self.tx, self.space.id, slug).await?;
                if current.page.kind != "file" {
                    return Err(invalid("Only a Wiki file receives a new file version."));
                }
                same_extension(&current.page.title, name)?;
                if current.revision_id != Some(base) {
                    return Err(conflict(
                        "revision_changed",
                        "The Wiki file changed; read it again before proposing a version",
                    )
                    .into());
                }
                Ok(Target {
                    page: Some(current.page.page_id),
                    base: Some(base),
                    title: None,
                    parent: None,
                })
            }
            (None, None, title_value, parent) => {
                let title = title(title_value.as_deref().unwrap_or(name))?;
                same_extension(&title, name)?;
                let parent = if let Some(destination) = &body.destination_title {
                    if !self.editor {
                        return Err(AppError::Forbidden.into());
                    }
                    self.file_destination(
                        parent.as_deref(),
                        destination,
                        &title,
                        create_destination,
                    )
                    .await?
                } else {
                    self.new_entry(parent.as_deref(), &title).await?
                };
                Ok(Target {
                    page: None,
                    base: None,
                    title: Some(title),
                    parent,
                })
            }
            _ => Err(invalid(
                "A new version names its file and base revision only; a new file names neither.",
            )),
        }
    }
}
