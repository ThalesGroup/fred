// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Organization-owned source configuration. Discovery, publication and policy stay
//! in the existing catalogue; only this module handles the encrypted credential.
use super::{
    config::{
        DeclaredModel, DiscoveryAuthentication, ModelSource, Qualification, SourceInventory,
        public_reference_url, valid_source_id,
    },
    policy,
};
use crate::{
    api::AppState,
    domain::Permission,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, present},
    onboarding::AdmittedUser,
    spaces,
};
use axum::{Json, extract::State, http::StatusCode};
use base64::{Engine, engine::general_purpose::STANDARD};
use fred_rust_sdk::inference::{
    ModelAuth, ModelAuthKind, ModelConnection, ModelDialect, ModelRoute, ModelWire,
};
use ring::{
    aead,
    rand::{SecureRandom, SystemRandom},
};
use serde::Deserialize;
use sqlx::{PgConnection, types::Json as SqlJson};
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateModelCatalog {
    pub name: String,
    /// Catalogue discovery URL. Supply either this or one declared model.
    pub url: Option<String>,
    /// Model registered directly using the inference root.
    pub model: Option<SingleModel>,
    /// Explicitly approved inference root, independent of the catalogue URL.
    pub api_root: String,
    /// Optional models.dev provider ID. Omit to derive it from the source hostname.
    pub metadata_provider: Option<String>,
    /// Defaults to true when omitted.
    pub models_dev_enabled: Option<bool>,
    pub platform_terms_url: Option<String>,
    /// Write-only: the public inventory never returns this value.
    #[schema(write_only)]
    pub token: String,
    pub dialect: ModelDialect,
    pub wire: ModelWire,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SingleModel {
    #[schema(min_length = 1, max_length = 256)]
    pub id: String,
    pub usage: SingleModelUse,
}

#[derive(Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum SingleModelUse {
    Chat,
    Embedding,
    AudioTranscription,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateModelCatalog {
    pub expected_revision: i64,
    pub name: String,
    /// Omit to keep the value; null restores hostname-based detection.
    #[serde(default, deserialize_with = "present")]
    pub metadata_provider: Option<Option<String>>,
    /// Omit to keep the synchronization setting.
    pub models_dev_enabled: Option<bool>,
    /// Omit to keep the configured link. Null removes it.
    #[serde(default, deserialize_with = "present")]
    pub platform_terms_url: Option<Option<String>>,
    /// Omit to keep the existing token. A rotation retains the same provider
    /// account/namespace; another account must be registered as another catalogue.
    #[schema(write_only)]
    pub token: Option<String>,
}

#[utoipa::path(put,path="/organizations/{organization_id}/model-sources/{source_id}",params(("organization_id"=Uuid,Path),("source_id"=String,Path)),request_body=UpdateModelCatalog,
    responses((status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn update_model_catalog(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization, source_id)): ApiPath<(Uuid, String)>,
    ApiJson(input): ApiJson<UpdateModelCatalog>,
) -> AppResult<StatusCode> {
    if input.name.trim().is_empty()
        || input.name.len() > 128
        || input.token.as_ref().is_some_and(|token| {
            token.is_empty() || token.len() > 8192 || token.chars().any(char::is_control)
        })
    {
        return Err(AppError::Unprocessable(
            "A name and a valid provider token are required.".into(),
        ));
    }
    if input
        .platform_terms_url
        .as_ref()
        .and_then(|url| url.as_deref())
        .is_some_and(|url| !public_reference_url(url))
    {
        return Err(AppError::Unprocessable(
            "Platform terms require a public HTTPS URL.".into(),
        ));
    }
    let (mut tx, _) = spaces::governance_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(organization),
        Permission::Manage,
    )
    .await?;
    let source:SqlJson<ModelSource>=sqlx::query_scalar("select s.configuration from model_source s join organization_model_catalog c using(source_id) where s.source_id=$1 and c.organization_id=$2 and c.deleted_at is null for update of s,c")
        .bind(&source_id).bind(organization).fetch_one(&mut *tx).await?;
    let mut source = source.0;
    if source.revision != input.expected_revision {
        return Err(AppError::Conflict(
            "Catalogue changed; reload before saving.".into(),
        ));
    }
    let encrypted = input
        .token
        .as_ref()
        .map(|token| seal(&source_id, &source.inference.api_root, token))
        .transpose()?;
    let token_changed = encrypted.is_some();
    if let Some(provider) = input.metadata_provider {
        if provider.as_deref().is_some_and(|id| !valid_source_id(id)) {
            return Err(AppError::Unprocessable(
                "Invalid model metadata provider ID.".into(),
            ));
        }
        source.metadata_provider = provider;
    }
    if let Some(enabled) = input.models_dev_enabled {
        source.models_dev_enabled = Some(enabled);
    }
    if let Some(url) = input.platform_terms_url {
        source.platform_terms_url = url;
    }
    source.revision = source
        .revision
        .checked_add(1)
        .ok_or_else(|| AppError::Conflict("Catalogue revision exhausted.".into()))?;
    sqlx::query("update organization_model_catalog set name=$2,encrypted_token=coalesce($3,encrypted_token) where source_id=$1")
        .bind(&source_id).bind(input.name.trim()).bind(encrypted).execute(&mut *tx).await?;
    sqlx::query(
        "update model_source set configuration=$2,
           snapshot_source_revision=case
               when not $3 and snapshot_source_revision=(configuration->>'revision')::bigint
               then snapshot_source_revision+1 else snapshot_source_revision end,
           state=case when $3 then 'not_observed' else state end,
           checked_at=case when $3 then null else checked_at end,
           error_code=case when $3 then null else error_code end,
           refresh_token=null where source_id=$1",
    )
    .bind(&source_id)
    .bind(SqlJson(&source))
    // Changing enrichment does not invalidate the provider's inventory.
    .bind(token_changed)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

fn credential_unavailable() -> AppError {
    AppError::problem(
        StatusCode::SERVICE_UNAVAILABLE,
        "model_catalog_key_unavailable",
        "The model catalogue credential store is unavailable.",
    )
}

fn key() -> AppResult<aead::LessSafeKey> {
    let value =
        std::env::var("MODEL_CATALOG_ENCRYPTION_KEY").map_err(|_| credential_unavailable())?;
    let bytes = STANDARD
        .decode(value)
        .map_err(|_| credential_unavailable())?;
    let key =
        aead::UnboundKey::new(&aead::AES_256_GCM, &bytes).map_err(|_| credential_unavailable())?;
    Ok(aead::LessSafeKey::new(key))
}

fn seal(source_id: &str, api_root: &str, token: &str) -> AppResult<Vec<u8>> {
    let mut nonce = [0; 12];
    SystemRandom::new()
        .fill(&mut nonce)
        .map_err(|_| credential_unavailable())?;
    let mut bytes = token.as_bytes().to_vec();
    let associated = format!("{source_id}\n{api_root}");
    key()?
        .seal_in_place_append_tag(
            aead::Nonce::assume_unique_for_key(nonce),
            aead::Aad::from(associated.as_bytes()),
            &mut bytes,
        )
        .map_err(|_| credential_unavailable())?;
    Ok([nonce.to_vec(), bytes].concat())
}

pub(crate) async fn credential(
    conn: &mut PgConnection,
    source_id: &str,
) -> AppResult<Option<String>> {
    let encrypted: Option<(Vec<u8>,String)> = sqlx::query_as("select c.encrypted_token,s.configuration->'inference'->>'api_root' from organization_model_catalog c join model_source s using(source_id) where c.source_id=$1 and c.deleted_at is null")
        .bind(source_id).fetch_optional(conn).await?;
    let Some((bytes, api_root)) = encrypted else {
        return Ok(None);
    };
    open(source_id, &api_root, bytes).map(Some)
}

fn open(source_id: &str, api_root: &str, mut bytes: Vec<u8>) -> AppResult<String> {
    if bytes.len() < 28 {
        return Err(credential_unavailable());
    }
    let nonce: [u8; 12] = bytes[..12]
        .try_into()
        .map_err(|_| credential_unavailable())?;
    let associated = format!("{source_id}\n{api_root}");
    let clear = key()?
        .open_in_place(
            aead::Nonce::assume_unique_for_key(nonce),
            aead::Aad::from(associated.as_bytes()),
            &mut bytes[12..],
        )
        .map_err(|_| credential_unavailable())?;
    String::from_utf8(clear.to_vec()).map_err(|_| credential_unavailable())
}

pub(crate) fn admitted_credential(
    admission: &fred_rust_sdk::inference::InferenceAdmission,
) -> AppResult<Option<String>> {
    admission
        .encrypted_credential
        .as_ref()
        .map(|envelope| {
            let bytes = STANDARD
                .decode(envelope.split_whitespace().collect::<String>())
                .map_err(|_| credential_unavailable())?;
            open(
                &admission.selection.key.source_id,
                &admission.connection.api_root,
                bytes,
            )
        })
        .transpose()
}

pub(super) async fn configured(
    conn: &mut PgConnection,
    organization: Uuid,
    source_id: &str,
) -> AppResult<ModelSource> {
    policy::require_assigned(
        conn,
        organization,
        &std::collections::BTreeSet::from([source_id.to_owned()]),
    )
    .await?;
    let source: SqlJson<ModelSource> = sqlx::query_scalar("select s.configuration from model_source s left join organization_model_catalog c using(source_id) where s.source_id=$1 and (not s.managed or (c.organization_id=$2 and c.deleted_at is null))")
        .bind(source_id).bind(organization).fetch_one(conn).await?;
    Ok(source.0)
}

#[utoipa::path(post, path="/organizations/{organization_id}/model-sources", params(("organization_id"=Uuid,Path)), request_body=CreateModelCatalog,
    responses((status=201,body=String),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn create_model_catalog(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization): ApiPath<Uuid>,
    ApiJson(input): ApiJson<CreateModelCatalog>,
) -> AppResult<(StatusCode, Json<String>)> {
    if input.name.trim().is_empty()
        || input.name.len() > 128
        || input.token.is_empty()
        || input.token.len() > 8192
        || input.token.chars().any(char::is_control)
    {
        return Err(AppError::Unprocessable(
            "A name and a valid provider token are required.".into(),
        ));
    }
    let (inventory, embedding_models) = match (input.url, input.model) {
        (Some(url), None) => (
            SourceInventory::Discovered {
                url,
                authentication: DiscoveryAuthentication::Managed,
                qualification: Qualification::MixedCapabilitiesV1,
                complete_inventory_guaranteed: true,
            },
            Vec::new(),
        ),
        (None, Some(model)) => {
            let embedding_models = if matches!(model.usage, SingleModelUse::Embedding) {
                vec![model.id.clone()]
            } else {
                Vec::new()
            };
            let model = DeclaredModel {
                id: model.id,
                audio_transcription: matches!(model.usage, SingleModelUse::AudioTranscription)
                    .then_some(true),
                display_name: None,
                reasoning: None,
                context_window_tokens: None,
                max_input_tokens: None,
                max_output_tokens: None,
            };
            (
                SourceInventory::Declared {
                    models: vec![model],
                },
                embedding_models,
            )
        }
        _ => {
            return Err(AppError::Unprocessable(
                "Provide either a catalogue URL or one declared model.".into(),
            ));
        }
    };
    let source_id = format!("catalog-{}", Uuid::new_v4());
    let source = ModelSource {
        source_id: source_id.clone(),
        revision: 1,
        enabled: true,
        metadata_provider: input.metadata_provider,
        models_dev_enabled: input.models_dev_enabled,
        platform_terms_url: input.platform_terms_url,
        inventory,
        inference: ModelConnection {
            credential_binding: source_id.clone(),
            api_root: input.api_root,
            wire: input.wire,
            route: ModelRoute::Standard,
            api_version: None,
            dialect: input.dialect,
            auth: ModelAuth {
                kind: ModelAuthKind::ApiKey,
                tenant_id: None,
                client_id: None,
                scope: None,
                gateway_key_header: None,
            },
        },
        visibility_scope: source_id.clone(),
        allow_insecure_http: false,
        embedding_models,
    };
    source.validate().map_err(|_| {
        AppError::Unprocessable("Invalid catalogue or inference connection.".into())
    })?;
    let (mut tx, _) = spaces::governance_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(organization),
        Permission::Manage,
    )
    .await?;
    let encrypted = seal(&source_id, &source.inference.api_root, &input.token)?;
    let assigned:i64=sqlx::query_scalar("select count(*) from organization_model_source a join model_source s using(source_id) where a.organization_id=$1 and (s.configuration->>'enabled')::boolean")
        .bind(organization).fetch_one(&mut *tx).await?;
    if assigned >= 64 {
        return Err(AppError::Unprocessable(
            "An organization can connect at most 64 active model catalogues.".into(),
        ));
    }
    sqlx::query("insert into model_source(source_id,configuration,managed) values($1,$2,true)")
        .bind(&source_id)
        .bind(SqlJson(&source))
        .execute(&mut *tx)
        .await?;
    sqlx::query("insert into organization_model_catalog(source_id,organization_id,name,encrypted_token) values($1,$2,$3,$4)")
        .bind(&source_id).bind(organization).bind(input.name.trim()).bind(encrypted).execute(&mut *tx).await?;
    policy::assign_sources(&mut tx, organization, std::slice::from_ref(&source_id)).await?;
    tx.commit().await?;
    Ok((StatusCode::CREATED, Json(source_id)))
}

#[utoipa::path(delete, path="/organizations/{organization_id}/model-sources/{source_id}",params(("organization_id"=Uuid,Path),("source_id"=String,Path)),
    responses((status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody)))]
async fn delete_model_catalog(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization, source_id)): ApiPath<(Uuid, String)>,
) -> AppResult<StatusCode> {
    let (mut tx, _) = spaces::governance_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(organization),
        Permission::Manage,
    )
    .await?;
    let changed = sqlx::query("update organization_model_catalog set deleted_at=coalesce(deleted_at,clock_timestamp()),encrypted_token=null where source_id=$1 and organization_id=$2")
        .bind(&source_id).bind(organization).execute(&mut *tx).await?;
    if changed.rows_affected() == 0 {
        return Err(AppError::NotFound);
    }
    // Preserve referenced identities, including a locked embedding model. They are
    // unavailable and absent from the catalogue, never silently substituted.
    sqlx::query("update model_source set configuration=jsonb_set(jsonb_set(configuration,'{enabled}','false'),'{revision}',to_jsonb((configuration->>'revision')::bigint+1)),refresh_token=null,state='unavailable',error_code='catalogue_deleted' where source_id=$1")
        .bind(&source_id).execute(&mut *tx).await?;
    sqlx::query("update model_offer set advertised=false,withdrawn_at=coalesce(withdrawn_at,clock_timestamp()) where source_id=$1").bind(&source_id).execute(&mut *tx).await?;
    sqlx::query("update organization_vector_reindex set admission=admission-'encrypted_credential',status=case when status in ('pending','running') then 'failed' else status end,error_code=case when status in ('pending','running') then 'catalogue_deleted' else error_code end,lease=null,lease_until=null where organization_id=$1 and admission->'selection'->'key'->>'source_id'=$2")
        .bind(organization).bind(&source_id).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

pub(super) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(create_model_catalog))
        .routes(routes!(update_model_catalog, delete_model_catalog))
}
