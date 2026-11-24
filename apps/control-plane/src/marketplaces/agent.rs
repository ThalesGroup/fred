// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Agent snapshots cross the same runtime-owned validation boundary as ordinary creation.
//! All network and original staging work happens outside SQL transactions.

use axum::http::{HeaderValue, StatusCode};
use base64::{Engine, engine::general_purpose::STANDARD};
use futures::{StreamExt, TryStreamExt};
use serde::de::DeserializeOwned;
use serde_json::{Value, json};
use sqlx::{Postgres, Transaction};
use std::collections::BTreeMap;
use tokio::io::{AsyncReadExt, AsyncSeekExt};
use uuid::Uuid;

use super::{
    models::*,
    store::{conflict, hash},
};
use crate::{
    agent_instances::{self, AgentInstance, CreateAgentInstanceRequest, NewAgentInstance, tuning},
    agents,
    api::AppState,
    auth::CurrentUser,
    authorization,
    capability_preparation::{self, FileChange},
    documents::powerpoint::{
        self, PowerPointChange, PowerPointFile, PowerPointTarget, PowerPointUpload,
    },
    documents::{copies::CopyContent, models::FileMetadata},
    domain::{Permission, Space},
    error::{AppError, AppResult},
};

const POD_SEGMENT: &percent_encoding::AsciiSet = &percent_encoding::NON_ALPHANUMERIC
    .remove(b'_')
    .remove(b'-')
    .remove(b'.')
    .remove(b'~');

pub(super) struct AgentExport {
    pub package: AgentPackage,
    pub basis: String,
    pub files: Vec<CopyContent>,
}

/// Bytes exist only across the pod boundary; catalogue packages store descriptors.
#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct CapabilityExport {
    schema_version: String,
    config: BTreeMap<String, Value>,
    files: BTreeMap<String, String>,
}

pub(super) struct AgentInstall {
    pub instance: NewAgentInstance,
    pub powerpoint: Option<FileChange>,
    pub word_template: Option<powerpoint::word::LibraryChange>,
}

fn incompatible(message: &'static str) -> AppError {
    AppError::problem(
        StatusCode::UNPROCESSABLE_ENTITY,
        "agent_configuration_incompatible",
        message,
    )
}

async fn response<T: DeserializeOwned>(
    request: reqwest::RequestBuilder,
    limit: usize,
) -> AppResult<T> {
    let mut response = request
        .send()
        .await
        .map_err(|_| AppError::Unavailable("Agent configuration owner unavailable".into()))?;
    let status = response.status();
    let limit = if status == StatusCode::UNPROCESSABLE_ENTITY {
        16 * 1024
    } else {
        limit
    };
    let bytes = tuning::read_limited(&mut response, limit)
        .await
        .ok_or_else(|| incompatible("Agent export exceeds the supported package bounds"))?;
    match status {
        StatusCode::OK => serde_json::from_slice(&bytes)
            .map_err(|_| incompatible("Invalid response from the configuration owner")),
        StatusCode::FORBIDDEN | StatusCode::UNAUTHORIZED => Err(AppError::Forbidden),
        StatusCode::UNPROCESSABLE_ENTITY => Err(AppError::problem(
            status,
            "agent_configuration_incompatible",
            tuning::rejection_detail(&bytes)
                .unwrap_or_else(|| "The owning pod rejected this configuration.".into()),
        )),
        StatusCode::NOT_FOUND => Err(incompatible(
            "The owning pod cannot export or install this complete configuration",
        )),
        _ => Err(AppError::Unavailable(
            "Agent configuration owner unavailable".into(),
        )),
    }
}

/// Recomputed in the final mutation transaction, including resolved configuration files.
pub(super) async fn source(
    tx: &mut Transaction<'_, Postgres>,
    actor: &str,
    request: &SubmitProposalRequest,
) -> AppResult<(AgentInstance, Space, Option<PowerPointFile>, String)> {
    let space =
        authorization::authorize(&mut **tx, actor, request.source_space_id, Permission::Write)
            .await?;
    let mut record =
        agent_instances::get_for_space(&mut **tx, space.id, request.source_resource_id)
            .await?
            .ok_or(AppError::NotFound)?;
    if request.expected_revision.parse::<i64>().ok() != Some(record.configuration_revision) {
        return Err(conflict(
            "source_changed",
            "The agent changed; reload before submitting.",
        ));
    }
    if !authorization::can_use_agent(&mut **tx, record.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    let selected = tuning::saved_selection(&record.tuning.0)?;
    let usable =
        agents::enablement::usable_capability_ids(&mut **tx, &space, &record.source_runtime_id)
            .await?;
    for id in &selected {
        if !usable.contains(id) {
            return Err(agents::enablement::not_enabled(id));
        }
    }
    if record.preparation_state != "ready" {
        return Err(incompatible(
            "The agent's configuration preparation is not ready",
        ));
    }
    capability_preparation::bind_result(tx, &mut record, space.organization).await?;
    let file = if selected.iter().any(|id| id == "ppt_builder") {
        powerpoint::snapshot_file(
            &mut *tx,
            &space,
            record.agent_instance_id,
            &record.source_runtime_id,
        )
        .await?
    } else {
        None
    };
    let word_files: Vec<PowerPointFile> = if selected.iter().any(|id| id == "word_template") {
        sqlx::query_as("select f.* from powerpoint_file f where f.capability_id='word_template' and f.runtime_id=$2 and f.status='stored' and (f.agent_instance_id=$1 or (f.agent_instance_id is null and f.space_id=$3 and f.effective and not exists(select 1 from powerpoint_file own where own.agent_instance_id=$1 and own.capability_id='word_template' and own.status='stored'))) order by f.slot")
            .bind(record.agent_instance_id).bind(&record.source_runtime_id).bind(space.organization).fetch_all(&mut **tx).await?
    } else {
        vec![]
    };
    let basis = hash(
        &json!({"revision":record.configuration_revision,"tuning":record.tuning.0,
        "name":record.display_name,"logical_name":record.logical_name,"description":record.description,
        "template":record.template_id,"file":file,"word_files":word_files}),
    )?;
    Ok((record, space, file, basis))
}

pub(super) async fn export(
    s: &AppState,
    actor: &str,
    catalogue: Uuid,
    key: Uuid,
    request: &SubmitProposalRequest,
    authorization: Option<&HeaderValue>,
) -> AppResult<AgentExport> {
    let mut tx = super::read_snapshot(&s.pool, actor, catalogue).await?;
    let (record, space, file, basis) = source(&mut tx, actor, request).await?;
    super::require_destination(&space, catalogue)?;
    tx.commit().await?;
    let file_bytes = if let Some(file) = file {
        if file.size > 32 * 1024 * 1024 {
            return Err(incompatible("Agent configuration files exceed 32 MiB"));
        }
        let storage = s
            .content
            .as_ref()
            .ok_or_else(|| AppError::Unavailable("Content storage unavailable".into()))?;
        let download = storage
            .download_powerpoint(
                actor,
                space.id,
                Some(record.agent_instance_id),
                file.id,
                &record.source_runtime_id,
            )
            .await?;
        Some(
            STANDARD.encode(
                axum::body::to_bytes(download.into_body(), 32 * 1024 * 1024)
                    .await
                    .map_err(|_| incompatible("Configuration file export failed"))?,
            ),
        )
    } else {
        None
    };
    let mut word_bytes = Vec::new();
    if let Some(entries) = record
        .tuning
        .0
        .pointer("/capability_config/word_template/config/template_library")
        .and_then(Value::as_array)
    {
        let storage = s
            .content
            .as_ref()
            .ok_or_else(crate::documents::unavailable)?;
        for entry in entries {
            let id = entry
                .get("template_key")
                .and_then(Value::as_str)
                .and_then(|key| {
                    key.strip_prefix("prepared-")
                        .and_then(|key| key.strip_suffix(".docx"))
                })
                .and_then(|key| Uuid::parse_str(key).ok())
                .ok_or_else(|| incompatible("Invalid prepared Word template"))?;
            let download = storage.preparation_file(id).await?;
            let bytes = axum::body::to_bytes(download.into_body(), 32 * 1024 * 1024)
                .await
                .map_err(|_| incompatible("Configuration file export failed"))?;
            word_bytes.push(STANDARD.encode(bytes));
        }
    }
    let selected = tuning::saved_selection(&record.tuning.0)?;
    if selected.len() > 32 {
        return Err(incompatible(
            "An agent snapshot supports at most 32 capabilities",
        ));
    }
    let export_capabilities = futures::stream::iter(selected)
        .map(|id: String| {
            let record = &record;
            let file_bytes = &file_bytes;
            let word_bytes = &word_bytes;
            async move {
                let config = record
                    .tuning
                    .0
                    .get("capability_config")
                    .and_then(|v| v.get(&id))
                    .ok_or_else(|| incompatible("Selected capability configuration is missing"))?;
                if id.starts_with("managed-mcp:") {
                    if config != &json!({"schema_version":"1","config":{}}) {
                        return Err(incompatible(
                            "Managed MCP has no portable agent-owned configuration",
                        ));
                    }
                    return Ok((
                        id,
                        CapabilityExport {
                            schema_version: "1".into(),
                            config: BTreeMap::new(),
                            files: BTreeMap::new(),
                        },
                    ));
                }
                let files = if id == "ppt_builder" {
                    file_bytes
                        .as_ref()
                        .map(|bytes| json!({"template": [bytes]}))
                        .unwrap_or_else(|| json!({}))
                } else if id == "word_template" && !word_bytes.is_empty() {
                    json!({"word_template_library":word_bytes})
                } else {
                    json!({})
                };
                let encoded = percent_encoding::utf8_percent_encode(&id, POD_SEGMENT);
                let request = tuning::capability_request(
                    &s.agent_catalog,
                    &record.source_runtime_id,
                    authorization,
                    &format!("{encoded}/export-config"),
                )?
                .json(&json!({
                    "space_id": space.id,
                    "agent_instance_id": record.agent_instance_id,
                    "config": config,
                    "files_by_slot": files,
                }));
                let result: CapabilityExport = response(request, 48 * 1024 * 1024).await?;
                Ok::<_, AppError>((id, result))
            }
        })
        .buffer_unordered(4)
        .try_fold(
            BTreeMap::<String, CapabilityExport>::new(),
            |mut caps, (id, cap)| async move {
                caps.insert(id, cap);
                let files: Vec<_> = caps.values().flat_map(|cap| cap.files.values()).collect();
                if files.len() > 128
                    || files.iter().map(|file| file.len()).sum::<usize>()
                        > 4 * (32_usize * 1024 * 1024).div_ceil(3)
                {
                    return Err(incompatible("Configuration files exceed export bounds"));
                }
                Ok(caps)
            },
        );
    let export_fields = async {
        let values = record
            .tuning
            .0
            .get("values")
            .cloned()
            .unwrap_or_else(|| json!({}));
        if let Some(exported) = agents::export_native_tuning(
            &record.source_runtime_id,
            &record.source_agent_id,
            &values,
        ) {
            return exported;
        }
        let template = percent_encoding::utf8_percent_encode(&record.source_agent_id, POD_SEGMENT);
        let request = tuning::pod_request(
            &s.agent_catalog,
            &record.source_runtime_id,
            authorization,
            &format!("templates/{template}/export-tuning"),
        )?
        .json(&json!({"space_id": space.id, "values": values}));
        response::<Value>(request, 2 * 1024 * 1024).await
    };
    let (exports, fields) = tokio::try_join!(export_capabilities, export_fields)?;
    let mut capabilities = BTreeMap::new();
    let mut originals = Vec::new();
    for (id, capability) in exports {
        if !capability.files.is_empty() {
            if !matches!(id.as_str(), "ppt_builder" | "word_template")
                || capability.files.len() > if id == "word_template" { 8 } else { 1 }
            {
                return Err(incompatible(
                    "This capability has no Weaver owner for its configuration files",
                ));
            }
            for (asset, encoded) in capability.files {
                let bytes = STANDARD
                    .decode(encoded)
                    .map_err(|_| incompatible("Invalid exported configuration file"))?;
                let storage = s
                    .content
                    .as_ref()
                    .ok_or_else(crate::documents::unavailable)?;
                let mime = if id == "word_template" {
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                } else {
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                };
                let name = if id == "word_template" {
                    format!("template-{}.docx", originals.len())
                } else {
                    asset.rsplit('/').next().unwrap_or(&asset).to_owned()
                };
                let spool = storage.spool_bytes(&name, mime, &bytes).await?;
                originals.push((id.clone(), asset, spool));
            }
        }
        capabilities.insert(
            id,
            ExportedCapability {
                schema_version: capability.schema_version,
                config: capability.config,
                files: BTreeMap::new(),
            },
        );
    }
    let settings = crate::model_catalog::instance::SavedModelSettings::read(&record.tuning.0)?;
    let mut package = AgentPackage {
        runtime_id: record.source_runtime_id,
        template_agent_id: record.source_agent_id,
        logical_name: record.logical_name,
        display_name: record.display_name,
        description: record.description,
        role: record
            .tuning
            .0
            .get("role")
            .and_then(Value::as_str)
            .ok_or_else(|| incompatible("Missing agent role"))?
            .to_owned(),
        usage_statement: record
            .tuning
            .0
            .get("usage_statement")
            .and_then(Value::as_str)
            .ok_or_else(|| incompatible("Missing usage statement"))?
            .to_owned(),
        tuning_field_values: serde_json::from_value(
            fields
                .get("values")
                .cloned()
                .ok_or_else(|| incompatible("Missing exported fields"))?,
        )
        .map_err(anyhow::Error::from)?,
        capabilities,
        recommended_model: settings.recommended_model,
        model_options: settings.model_options,
    };
    validate_bounds(&package)?;
    let mut files = Vec::new();
    for (capability_id, asset, spool) in originals {
        let storage = s
            .content
            .as_ref()
            .ok_or_else(crate::documents::unavailable)?;
        if !storage.config.uploads_enabled {
            return Err(crate::documents::unavailable());
        }
        let _permit = storage.uploads.clone().try_acquire_owned().map_err(|_| {
            AppError::problem(
                StatusCode::TOO_MANY_REQUESTS,
                "transfer_capacity",
                "All transfer slots are busy",
            )
        })?;
        let mut tx = crate::spaces::storage_transaction(&s.pool, catalogue, true).await?;
        super::require_audience(&mut tx, actor, catalogue).await?;
        let organization = crate::spaces::load_organization(&mut *tx, catalogue).await?;
        let fingerprint = hash(&(catalogue, request))?;
        let file = FileMetadata {
            name: spool.name.clone(),
            mime: spool.mime.clone(),
            size: spool.size,
            sha256: spool.sha256(),
        };
        let reservation_key = Uuid::new_v5(
            &key,
            format!("marketplace:configuration:{capability_id}:{asset}").as_bytes(),
        );
        let copy = storage
            .reserve_copy(
                &mut tx,
                actor,
                &organization,
                reservation_key,
                "marketplace",
                file.size,
                Some(&fingerprint),
                &file,
            )
            .await?;
        let Some(copy) = copy else {
            let (recorded, status): (Option<String>, crate::documents::models::UploadStatus) = sqlx::query_as(
                "select request_fingerprint,status from document_upload where actor=$1 and request_key=$2")
                .bind(actor).bind(reservation_key).fetch_one(&mut *tx).await?;
            if recorded.as_deref() != Some(fingerprint.as_str()) {
                return Err(conflict(
                    "idempotency_conflict",
                    "This key belongs to another submission.",
                ));
            }
            crate::documents::replayed(status)?;
            return Err(crate::documents::in_progress());
        };
        tx.commit().await?;
        if let Err(error) = storage
            .transfer_upload(copy.id, &copy.object_key, spool)
            .await
        {
            if let Err(cleanup) = storage.fail(copy.id, "marketplace_copy_interrupted").await {
                tracing::warn!(operation_id=%copy.id, error=%cleanup, "Marketplace copy awaits reconciliation");
            }
            return Err(error);
        }
        package
            .capabilities
            .get_mut(&capability_id)
            .ok_or_else(|| incompatible("Missing file owner"))?
            .files
            .insert(
                asset,
                MarketplaceFile {
                    document_id: copy.id,
                    file,
                },
            );
        files.push(copy);
    }
    Ok(AgentExport {
        package,
        basis,
        files,
    })
}

fn validate_bounds(package: &AgentPackage) -> AppResult<()> {
    if package.capabilities.len() > 32 {
        return Err(incompatible(
            "An agent snapshot supports at most 32 capabilities",
        ));
    }
    let mut count = 0;
    let mut size = 0;
    for capability in package.capabilities.values() {
        if capability.schema_version.is_empty() {
            return Err(incompatible("Missing capability schema version"));
        }
        for file in capability.files.values() {
            count += 1;
            if file.file.size < 0 || file.file.size > 32 * 1024 * 1024 {
                return Err(incompatible("Configuration file exceeds export bounds"));
            }
            size += file.file.size;
            if count > 9 || size > 32 * 1024 * 1024 {
                return Err(incompatible("Configuration files exceed export bounds"));
            }
        }
    }
    let mut config = serde_json::to_value(package).map_err(anyhow::Error::from)?;
    if let Some(capabilities) = config
        .get_mut("capabilities")
        .and_then(Value::as_object_mut)
    {
        for capability in capabilities.values_mut() {
            if let Some(object) = capability.as_object_mut() {
                object.remove("files");
            }
        }
    }
    if serde_json::to_vec(&config)
        .map_err(anyhow::Error::from)?
        .len()
        > 2 * 1024 * 1024
    {
        return Err(incompatible("Agent configuration exceeds 2 MiB"));
    }
    Ok(())
}

pub(super) async fn prepare_install(
    s: &AppState,
    user: &CurrentUser,
    authorization: Option<&HeaderValue>,
    key: Uuid,
    request: &InstallRequest,
    package: &AgentPackage,
) -> AppResult<AgentInstall> {
    let InstallOptions::Agent {
        logical_name,
        display_name,
    } = &request.options
    else {
        return Err(incompatible("Agent installation requires agent options"));
    };
    validate_bounds(package)?;
    let space = authorization::authorize(
        &s.pool,
        &user.uid,
        request.destination_space_id,
        Permission::Write,
    )
    .await?;
    agent_instances::require_instance_space(space.kind)?;
    let template_id = agents::template_id(
        space.organization,
        &package.runtime_id,
        &package.template_agent_id,
    );
    if !authorization::can_use_agent(&s.pool, template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    let (template, _) =
        agents::enrollable_template(&s.pool, &s.agent_catalog, space.organization, template_id)
            .await?;
    let selected: Vec<_> = package.capabilities.keys().cloned().collect();
    tuning::require_inventory(&template, &selected)?;
    let usable =
        agents::enablement::usable_capability_ids(&s.pool, &space, &package.runtime_id).await?;
    for id in &selected {
        if !usable.contains(id) {
            return Err(agents::enablement::not_enabled(id));
        }
    }
    // Revalidate all named fields; ordinary enrollment otherwise ignores unknown keys.
    if package.tuning_field_values.keys().any(|key| {
        !template
            .default_tuning_fields
            .iter()
            .any(|f| f.get("key").and_then(Value::as_str) == Some(key))
    }) {
        return Err(incompatible(
            "The local template no longer accepts all exported fields",
        ));
    }
    let draft = Uuid::new_v5(&key, user.uid.as_bytes());
    let mut assets = BTreeMap::new();
    for (id, capability) in &package.capabilities {
        let mut files = BTreeMap::new();
        for (asset, file) in &capability.files {
            if !matches!(id.as_str(), "ppt_builder" | "word_template")
                || capability.files.len() > if id == "word_template" { 8 } else { 1 }
            {
                return Err(incompatible(
                    "This capability has no Weaver owner for its configuration files",
                ));
            }
            let storage = s
                .content
                .as_ref()
                .ok_or_else(crate::documents::unavailable)?;
            let object: String = sqlx::query_scalar("select c.object_key from document d join document_content c on c.id=d.current_content_id where d.id=$1 and d.space_id=$2 and d.purpose='marketplace' and d.deletion_id is null and c.cleaned_at is null and c.size=$3 and c.sha256=$4 and c.mime=$5")
                .bind(file.document_id).bind(space.organization).bind(file.file.size).bind(&file.file.sha256).bind(&file.file.mime)
                .fetch_optional(&s.pool).await?.ok_or_else(|| conflict("publication_changed", "The publication's configuration file is no longer current."))?;
            let bytes = tokio::time::timeout(storage.deadline(), async {
                let _permit = storage
                    .downloads
                    .acquire()
                    .await
                    .map_err(|_| crate::documents::unavailable())?;
                let mut spool = storage
                    .spool_object(
                        &object,
                        file.file.name.clone(),
                        file.file.mime.clone(),
                        file.file.size,
                        &file.file.sha256,
                    )
                    .await?;
                spool
                    .file
                    .rewind()
                    .await
                    .map_err(|_| crate::documents::unavailable())?;
                let mut bytes = Vec::new();
                spool
                    .file
                    .read_to_end(&mut bytes)
                    .await
                    .map_err(|_| crate::documents::unavailable())?;
                Ok::<_, AppError>(bytes)
            })
            .await
            .map_err(|_| crate::documents::unavailable())??;
            files.insert(asset.clone(), STANDARD.encode(bytes));
        }
        assets.insert(id.clone(), files);
    }
    let configurations = futures::future::try_join_all(
        package.capabilities.iter().map(|(id, capability)| {
            let files = &assets[id];
            async move {
            if id.starts_with("managed-mcp:") {
                if capability.schema_version != "1" || !capability.config.is_empty() || !capability.files.is_empty() {
                    return Err(incompatible("Managed MCP has no portable agent-owned configuration"));
                }
                // The selection is portable; connection facts are resolved again at admission.
                return Ok((id.clone(), BTreeMap::new()));
            }
            let encoded = percent_encoding::utf8_percent_encode(id, POD_SEGMENT);
            let request = tuning::capability_request(
                &s.agent_catalog, &package.runtime_id, authorization,
                &format!("{encoded}/copy-config"),
            )?.json(&json!({
                "target_space_id": space.id,
                "target_agent_instance_id": draft,
                "config": {"schema_version": capability.schema_version, "config": capability.config},
                "asset_files": files,
            }));
            let result: Value = response(request, 2 * 1024 * 1024).await?;
            let config: BTreeMap<String, Value> = serde_json::from_value(
                result.get("config").cloned().ok_or_else(|| incompatible("Missing copied configuration"))?,
            ).map_err(anyhow::Error::from)?;
            Ok::<_, AppError>((id.clone(), config))
        }}),
    ).await?;
    if serde_json::to_vec(
        &json!({"values": package.tuning_field_values, "capabilities": configurations}),
    )
    .map_err(anyhow::Error::from)?
    .len()
        > 2 * 1024 * 1024
    {
        return Err(incompatible("Upgraded agent configuration exceeds 2 MiB"));
    }
    let mut powerpoint = None;
    let mut word_template = None;
    for (capability, files) in &assets {
        let mut word_files = Vec::new();
        for (slot, (name, bytes)) in files.iter().enumerate() {
            let storage = s
                .content
                .as_ref()
                .ok_or_else(crate::documents::unavailable)?;
            let original = &package.capabilities[capability].files[name];
            let file = storage
                .upload_powerpoint(
                    user,
                    PowerPointTarget {
                        space_id: space.id,
                        agent: Some(draft),
                        runtime: &package.runtime_id,
                        capability,
                        slot: slot as i16,
                    },
                    Uuid::new_v5(&key, format!("{capability}:{name}").as_bytes()),
                    PowerPointChange {
                        expected_file_id: None,
                    },
                    PowerPointUpload::Snapshot {
                        name: original.file.name.clone(),
                        bytes: STANDARD
                            .decode(bytes)
                            .map_err(|_| incompatible("Invalid configuration file"))?,
                    },
                    true,
                )
                .await?;
            if capability == "ppt_builder" {
                powerpoint = Some(FileChange {
                    file_id: Some(file.id),
                    expected_file_id: None,
                });
            } else {
                let label = package.capabilities[capability]
                    .config
                    .get("template_library")
                    .and_then(Value::as_array)
                    .and_then(|entries| {
                        entries.iter().find(|entry| {
                            entry.get("template_key").and_then(Value::as_str) == Some(name)
                        })
                    })
                    .and_then(|entry| entry.get("label"))
                    .and_then(Value::as_str)
                    .unwrap_or(&original.file.name)
                    .to_owned();
                word_files.push(powerpoint::word::LibraryEntry {
                    file_id: file.id,
                    label,
                });
            }
        }
        if !word_files.is_empty() {
            word_template = Some(powerpoint::word::LibraryChange {
                files: word_files,
                expected_file_ids: vec![],
            });
        }
    }
    let mut body = CreateAgentInstanceRequest {
        powerpoint,
        word_template,
        template_id,
        display_name: display_name.clone(),
        logical_name: logical_name.clone(),
        description: package.description.clone(),
        role: Some(package.role.clone()),
        usage_statement: package.usage_statement.clone(),
        tuning_field_values: Some(
            serde_json::from_value(json!(package.tuning_field_values))
                .map_err(anyhow::Error::from)?,
        ),
        capability_ids: Some(selected.clone()),
        capability_config_values: Some(configurations.into_iter().collect()),
        recommended_model: package.recommended_model.clone(),
        model_options: Some(package.model_options.clone()),
    };
    let mut instance =
        agent_instances::prepare_create(s, user, space.id, authorization, &mut body).await?;
    let actual = tuning::saved_selection(&instance.tuning)?;
    if actual.iter().collect::<std::collections::BTreeSet<_>>() != selected.iter().collect() {
        return Err(incompatible(
            "The local template changed the exported capability selection",
        ));
    }
    instance.agent_instance_id = draft;
    Ok(AgentInstall {
        instance,
        powerpoint: body.powerpoint,
        word_template: body.word_template,
    })
}
