// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use axum::http::StatusCode;
use serde::Serialize;
use sha2::{Digest, Sha256};
use sqlx::{PgConnection, PgPool, types::Json};
use uuid::Uuid;

use super::{models::*, require_audience};
use crate::{
    authorization,
    domain::Permission,
    error::{AppError, AppResult},
    prompts, skills, spaces,
};

pub(super) fn conflict(code: &'static str, message: &'static str) -> AppError {
    AppError::problem(StatusCode::CONFLICT, code, message)
}

pub(super) fn hash(value: &impl Serialize) -> AppResult<String> {
    // Value's ordered object representation makes field ordering irrelevant to retries.
    let bytes = serde_json::to_vec(&serde_json::to_value(value).map_err(anyhow::Error::from)?)
        .map_err(anyhow::Error::from)?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

pub(super) async fn can_write(
    conn: &mut PgConnection,
    actor: &str,
    space: Option<Uuid>,
) -> AppResult<bool> {
    let Some(space) = space else {
        return Ok(false);
    };
    let facts = authorization::load_facts(conn, actor, space).await?;
    Ok(authorization::decide(&facts, crate::roles::SpacePermission::Write).is_ok())
}

pub(super) async fn proposal(
    conn: &mut PgConnection,
    actor: &str,
    catalogue: Uuid,
    id: Uuid,
) -> AppResult<ProposalSummary> {
    let mut row: ProposalSummary = sqlx::query_as("select p.proposal_id,p.entry_id,p.marketplace_space_id,p.proposing_space_id,p.kind,p.origin_name,p.display_name,p.description,p.package_hash,p.submitted_by,p.submitted_at,p.state,p.decided_by,p.decided_at,p.decision_reason, e.publication_version, e.published_proposal_id, false as can_decide, false as can_cancel
        from marketplace_proposal p join marketplace_entry e using(entry_id)
        where p.marketplace_space_id=$1 and p.proposal_id=$2")
        .bind(catalogue).bind(id).fetch_optional(&mut *conn).await?.ok_or(AppError::NotFound)?;
    row.actions = actions(conn, actor, &row).await?;
    Ok(row)
}

pub(super) async fn actions(
    conn: &mut PgConnection,
    actor: &str,
    row: &ProposalSummary,
) -> AppResult<ProposalActions> {
    let editor = can_write(conn, actor, Some(row.marketplace_space_id)).await?;
    let proposer = can_write(conn, actor, row.proposing_space_id).await?;
    if !editor && !proposer {
        return Err(AppError::NotFound);
    }
    Ok(ProposalActions {
        can_decide: editor && row.state == ProposalState::Pending,
        can_cancel: proposer && row.state == ProposalState::Pending,
    })
}

pub(super) async fn package(conn: &mut PgConnection, id: Uuid) -> AppResult<MarketplacePackage> {
    Ok(sqlx::query_scalar::<_, Json<MarketplacePackage>>(
        "select package from marketplace_proposal where proposal_id=$1",
    )
    .bind(id)
    .fetch_one(conn)
    .await?
    .0)
}

async fn capture(
    conn: &mut PgConnection,
    actor: &str,
    request: &SubmitProposalRequest,
) -> AppResult<(MarketplacePackage, String, String)> {
    let stale = || {
        conflict(
            "source_changed",
            "The source changed; reload before submitting.",
        )
    };
    match request.kind {
        MarketplaceKind::Prompt => {
            let row = prompts::get_for_space(
                &mut *conn,
                request.source_space_id,
                request.source_resource_id,
                actor,
            )
            .await?
            .ok_or(AppError::NotFound)?;
            let expected = chrono::DateTime::parse_from_rfc3339(&request.expected_revision)
                .map_err(|_| {
                    AppError::Unprocessable("Expected the prompt updated_at timestamp".into())
                })?;
            if expected != row.metadata.updated_at {
                return Err(stale());
            }
            let content = PromptPackage {
                logical_name: row.metadata.logical_name,
                display_name: row.metadata.display_name,
                description: row.metadata.description,
                tags: row.metadata.tags,
                text: row.text,
            };
            if serde_json::to_vec(&content)
                .map_err(anyhow::Error::from)?
                .len()
                > 2 * 1024 * 1024
            {
                return Err(AppError::Unprocessable(
                    "Prompt package exceeds 2 MiB".into(),
                ));
            }
            let title = content.display_name.clone();
            let description = content.description.clone().unwrap_or_default();
            Ok((MarketplacePackage::Prompt(content), title, description))
        }
        MarketplaceKind::Skill => {
            let (name, files, revision): (String, Json<skills::package::Files>, String) =
                sqlx::query_as(
                    "select name,files,revision from skill where space_id=$1 and skill_id=$2",
                )
                .bind(request.source_space_id)
                .bind(request.source_resource_id)
                .fetch_optional(&mut *conn)
                .await?
                .ok_or(AppError::NotFound)?;
            if revision != request.expected_revision {
                return Err(stale());
            }
            let summary = skills::package::validate(&name, &files.0, false)?;
            Ok((
                MarketplacePackage::Skill(SkillPackage {
                    name: name.clone(),
                    files: files.0,
                }),
                name,
                summary.description,
            ))
        }
        MarketplaceKind::Agent => {
            Err(anyhow::anyhow!("Agent capture must use its owning pod preflight").into())
        }
    }
}

pub(crate) async fn submit(
    s: &crate::api::AppState,
    user: &crate::auth::CurrentUser,
    catalogue: Uuid,
    key: Uuid,
    request: &SubmitProposalRequest,
    authorization_header: Option<&axum::http::HeaderValue>,
) -> AppResult<MarketplaceProposal> {
    let pool = &s.pool;
    let actor = user.uid.as_str();
    let request_hash = hash(&(catalogue, request))?;
    let mut prepared: Option<super::agent::AgentExport> = None;
    loop {
        let mut tx = spaces::storage_transaction(pool, catalogue, false).await?;
        require_audience(&mut tx, actor, catalogue).await?;
        if let Some((id, recorded_hash)) = sqlx::query_as::<_, (Uuid, String)>(
        "select proposal_id,request_hash from marketplace_proposal where submitted_by=$1 and request_key=$2")
        .bind(actor).bind(key).fetch_optional(&mut *tx).await? {
        if request_hash != recorded_hash { return Err(conflict("idempotency_conflict", "This key belongs to another submission.")); }
        let row = proposal(&mut tx, actor, catalogue, id).await?;
        let package = package(&mut tx, id).await?;
        tx.commit().await?;
        return Ok(MarketplaceProposal { proposal: row, package });
    }
        let source =
            authorization::authorize(&mut *tx, actor, request.source_space_id, Permission::Write)
                .await?;
        super::require_destination(&source, catalogue)?;
        let (package, title, description) = if request.kind == MarketplaceKind::Agent {
            if let Some(export) = &prepared {
                let (_, _, _, basis) = super::agent::source(&mut tx, actor, request).await?;
                if basis != export.basis {
                    return Err(conflict(
                        "source_changed",
                        "The agent configuration changed during export.",
                    ));
                }
                (
                    MarketplacePackage::Agent(export.package.clone()),
                    export.package.display_name.clone(),
                    export.package.description.clone().unwrap_or_default(),
                )
            } else {
                tx.commit().await?;
                prepared = Some(
                    super::agent::export(s, actor, catalogue, request, authorization_header)
                        .await?,
                );
                continue;
            }
        } else {
            capture(&mut tx, actor, request).await?
        };
        let package_hash = hash(&package)?;
        let entry = if let Some(entry) = request.entry_id {
            let allowed: bool = sqlx::query_scalar(
                "select exists(select 1 from marketplace_entry e where e.entry_id=$1
            and e.marketplace_space_id=$2 and e.kind=$3)",
            )
            .bind(entry)
            .bind(catalogue)
            .bind(request.kind.as_str())
            .fetch_one(&mut *tx)
            .await?;
            if !allowed {
                return Err(AppError::NotFound);
            }
            entry
        } else {
            let entry = Uuid::new_v4();
            sqlx::query(
            "insert into marketplace_entry(entry_id,marketplace_space_id,kind) values($1,$2,$3)",
        )
        .bind(entry)
        .bind(catalogue)
        .bind(request.kind.as_str())
        .execute(&mut *tx)
        .await?;
            entry
        };
        let id = Uuid::new_v4();
        sqlx::query("insert into marketplace_proposal(proposal_id,entry_id,marketplace_space_id,kind,proposing_space_id,
        origin_name,submitted_by,request_key,request_hash,package,package_hash,display_name,description)
        values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)")
        .bind(id).bind(entry).bind(catalogue).bind(request.kind.as_str()).bind(source.id).bind(source.name)
        .bind(actor).bind(key).bind(request_hash).bind(Json(&package)).bind(package_hash).bind(title).bind(description)
        .execute(&mut *tx).await?;
        let row = proposal(&mut tx, actor, catalogue, id).await?;
        tx.commit().await?;
        return Ok(MarketplaceProposal {
            proposal: row,
            package,
        });
    }
}

pub(crate) async fn decide(
    pool: &PgPool,
    actor: &str,
    catalogue: Uuid,
    id: Uuid,
    request: &ProposalDecisionRequest,
) -> AppResult<ProposalSummary> {
    if request
        .reason
        .as_ref()
        .is_some_and(|r| r.chars().count() > 2000 || r.contains('\0'))
    {
        return Err(AppError::Unprocessable(
            "Decision reason exceeds 2000 characters or contains NUL".into(),
        ));
    }
    let (mut tx, _) =
        spaces::authorized_mutation(pool, actor, catalogue, Permission::Write).await?;
    let row = proposal(&mut tx, actor, catalogue, id).await?;
    let state = if request.approve {
        ProposalState::Approved
    } else {
        ProposalState::Rejected
    };
    if row.state != ProposalState::Pending {
        if row.state != state || row.decision_reason != request.reason {
            return Err(conflict(
                "decision_conflict",
                "This proposal already has a different decision.",
            ));
        }
        // Replaying an approval never republishes an older or withdrawn snapshot.
        tx.commit().await?;
        return Ok(row);
    }
    if request.approve && row.publication_version != request.expected_publication_version {
        return Err(conflict(
            "publication_changed",
            "The publication changed; review it again.",
        ));
    }
    sqlx::query("update marketplace_proposal set state=$2,decided_by=$3,decided_at=clock_timestamp(),decision_reason=$4 where proposal_id=$1")
        .bind(id).bind(state.as_str()).bind(actor).bind(&request.reason).execute(&mut *tx).await?;
    if request.approve {
        sqlx::query("update marketplace_entry set published_proposal_id=$2,publication_version=publication_version+1,
            published_at=clock_timestamp(),withdrawn_at=null where entry_id=$1")
            .bind(row.entry_id).bind(id).execute(&mut *tx).await?;
    }
    let row = proposal(&mut tx, actor, catalogue, id).await?;
    tx.commit().await?;
    Ok(row)
}

pub(crate) async fn cancel(
    pool: &PgPool,
    actor: &str,
    catalogue: Uuid,
    id: Uuid,
) -> AppResult<ProposalSummary> {
    let mut tx = spaces::storage_transaction(pool, catalogue, false).await?;
    require_audience(&mut tx, actor, catalogue).await?;
    let row = proposal(&mut tx, actor, catalogue, id).await?;
    if !can_write(&mut tx, actor, row.proposing_space_id).await? {
        return Err(AppError::Forbidden);
    }
    if row.state == ProposalState::Cancelled {
        tx.commit().await?;
        return Ok(row);
    }
    if row.state != ProposalState::Pending {
        return Err(conflict(
            "decision_conflict",
            "Only pending proposals can be cancelled.",
        ));
    }
    sqlx::query("update marketplace_proposal set state='cancelled',decided_by=$2,decided_at=clock_timestamp() where proposal_id=$1")
        .bind(id).bind(actor).execute(&mut *tx).await?;
    let row = proposal(&mut tx, actor, catalogue, id).await?;
    tx.commit().await?;
    Ok(row)
}

pub(crate) async fn withdraw(
    pool: &PgPool,
    actor: &str,
    catalogue: Uuid,
    entry: Uuid,
    expected: i64,
) -> AppResult<()> {
    let (mut tx, _) =
        spaces::authorized_mutation(pool, actor, catalogue, Permission::Write).await?;
    let (current, published): (i64, Option<Uuid>) = sqlx::query_as(
        "select publication_version,published_proposal_id from marketplace_entry where entry_id=$1 and marketplace_space_id=$2")
        .bind(entry).bind(catalogue).fetch_optional(&mut *tx).await?.ok_or(AppError::NotFound)?;
    if published.is_none() && current == expected.saturating_add(1) {
        tx.commit().await?;
        return Ok(());
    }
    if current != expected {
        return Err(conflict(
            "publication_changed",
            "The publication changed; reload before withdrawing.",
        ));
    }
    if published.is_some() {
        sqlx::query("update marketplace_entry set published_proposal_id=null,published_at=null,withdrawn_at=clock_timestamp(),
            publication_version=publication_version+1 where entry_id=$1")
            .bind(entry).execute(&mut *tx).await?;
    }
    tx.commit().await?;
    Ok(())
}

pub(crate) async fn install(
    s: &crate::api::AppState,
    user: &crate::auth::CurrentUser,
    catalogue: Uuid,
    entry: Uuid,
    key: Uuid,
    request: &InstallRequest,
    authorization_header: Option<&axum::http::HeaderValue>,
) -> AppResult<InstallationReceipt> {
    let pool = &s.pool;
    let actor = user.uid.as_str();
    let request_hash = hash(&(catalogue, entry, request))?;
    let mut prepared: Option<AppResult<super::agent::AgentInstall>> = None;
    loop {
        let (mut tx, destination) = spaces::authorized_mutation(
            pool,
            actor,
            request.destination_space_id,
            Permission::Write,
        )
        .await?;
        if destination.organization != catalogue {
            return Err(AppError::NotFound);
        }
        require_audience(&mut tx, actor, catalogue).await?;
        let previous: Option<(Uuid, String)> = sqlx::query_as("select installation_id,request_hash from marketplace_installation where actor=$1 and request_key=$2")
        .bind(actor).bind(key).fetch_optional(&mut *tx).await?;
        if let Some((id, recorded_hash)) = previous {
            if request_hash != recorded_hash {
                return Err(conflict(
                    "idempotency_conflict",
                    "This key belongs to another installation.",
                ));
            }
            let receipt = receipt(&mut tx, actor, request.destination_space_id, id).await?;
            tx.commit().await?;
            return Ok(receipt);
        }
        let (package, package_hash): (Json<MarketplacePackage>, String) = sqlx::query_as(
        "select p.package,p.package_hash from marketplace_entry e join marketplace_proposal p on p.proposal_id=e.published_proposal_id
        where e.entry_id=$1 and e.marketplace_space_id=$2 and p.proposal_id=$3")
        .bind(entry).bind(catalogue).bind(request.proposal_id).fetch_optional(&mut *tx).await?
        .ok_or_else(|| conflict("publication_changed", "The selected publication is no longer current."))?;
        let kind = package.0.kind();
        let resource = match (&package.0, &request.options) {
            (
                MarketplacePackage::Prompt(content),
                InstallOptions::Prompt {
                    logical_name,
                    category_id,
                },
            ) => {
                let mut body = prompts::CreatePromptRequest {
                    logical_name: logical_name.clone(),
                    display_name: content.display_name.clone(),
                    description: content.description.clone(),
                    tags: content.tags.clone(),
                    text: content.text.clone(),
                    category_id: *category_id,
                };
                prompts::validate_logical_name(&body.logical_name)?;
                prompts::validate_content(
                    Some(&mut body.display_name),
                    body.description.as_deref(),
                    Some(&body.text),
                    Some(&mut body.tags),
                )?;
                prompts::create(&mut *tx, destination.id, &body, actor)
                    .await?
                    .metadata
                    .prompt_id
            }
            (MarketplacePackage::Skill(content), InstallOptions::Skill) => {
                skills::save(
                    &mut tx,
                    destination.id,
                    actor,
                    &content.name,
                    &content.files,
                    None,
                    false,
                )
                .await?;
                sqlx::query_scalar("select skill_id from skill where space_id=$1 and name=$2")
                    .bind(destination.id)
                    .bind(&content.name)
                    .fetch_one(&mut *tx)
                    .await?
            }
            (MarketplacePackage::Agent(content), InstallOptions::Agent { .. }) => {
                if let Some(prepared) = prepared.take() {
                    let prepared = prepared?;
                    crate::agent_instances::http::save_created(
                        &mut tx,
                        user,
                        &destination,
                        &prepared.instance,
                        prepared.powerpoint.as_ref(),
                    )
                    .await?
                    .agent_instance_id
                } else {
                    tx.commit().await?;
                    // A racing successful install is looked up before a preflight error is returned.
                    prepared = Some(
                        super::agent::prepare_install(
                            s,
                            user,
                            authorization_header,
                            key,
                            request,
                            content,
                        )
                        .await,
                    );
                    continue;
                }
            }
            _ => {
                return Err(AppError::Unprocessable(
                    "Installation options do not match the published kind".into(),
                ));
            }
        };
        let id = Uuid::new_v4();
        sqlx::query("insert into marketplace_installation(installation_id,actor,request_key,request_hash,entry_id,proposal_id,package_hash,
        kind,space_id,resource_id,live_space_id,prompt_id,skill_id,agent_instance_id) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$9,$11,$12,$13)")
        .bind(id).bind(actor).bind(key).bind(request_hash).bind(entry).bind(request.proposal_id).bind(package_hash)
        .bind(kind.as_str()).bind(destination.id).bind(resource)
        .bind((kind == MarketplaceKind::Prompt).then_some(resource))
        .bind((kind == MarketplaceKind::Skill).then_some(resource))
        .bind((kind == MarketplaceKind::Agent).then_some(resource)).execute(&mut *tx).await?;
        let receipt = receipt(&mut tx, actor, destination.id, id).await?;
        tx.commit().await?;
        return Ok(receipt);
    }
}

pub(super) async fn receipt(
    conn: &mut PgConnection,
    actor: &str,
    space: Uuid,
    id: Uuid,
) -> AppResult<InstallationReceipt> {
    authorization::authorize(&mut *conn, actor, space, Permission::Read).await?;
    sqlx::query_as("select installation_id,entry_id,proposal_id,package_hash,kind,space_id,resource_id,installed_at,
        (live_space_id is not null and coalesce(prompt_id,skill_id,agent_instance_id) is not null) as resource_exists
        from marketplace_installation where installation_id=$1 and live_space_id=$2")
        .bind(id).bind(space).fetch_optional(conn).await?.ok_or(AppError::NotFound)
}
