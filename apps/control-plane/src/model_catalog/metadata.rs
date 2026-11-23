// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Field provenance and persistent complements. The organization owns its display
//! label, and the provider owns the technical facts it reports.
use super::{
    config::{ModelSource, SourceInventory, public_reference_url},
    discovery::{DiscoveredOffer, ModelLicense, ModelMetadata},
    policy,
};
use crate::{
    api::AppState,
    domain::Permission,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
    spaces,
};
use axum::{Json, extract::State};
use serde::Deserialize;
use serde_json::Value;
use sqlx::types::Json as SqlJson;
use std::{
    collections::BTreeMap,
    sync::{Arc, OnceLock},
    time::{Duration, Instant},
};
use tokio::sync::Mutex;
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

const FIELDS: &[&str] = &[
    "chat",
    "embedding",
    "audio_transcription",
    "vision",
    "reasoning",
    "display_name",
    "license",
    "context_window_tokens",
    "max_input_tokens",
    "max_output_tokens",
    "reasoning_required",
    "reasoning_efforts",
    "reasoning_default",
    "reasoning_transport",
    "reasoning_replay",
    "tool_calling",
    "structured_output",
];

pub(super) fn project(detected: &Value, complements: &Value) -> AppResult<ModelMetadata> {
    let mut result = detected.clone();
    let mut provenance: BTreeMap<String, String> = serde_json::from_value(
        result
            .get("provenance")
            .cloned()
            .unwrap_or_else(|| serde_json::json!({})),
    )
    .map_err(anyhow::Error::from)?;
    if let Some(values) = complements.as_object() {
        for (field, value) in values {
            if !FIELDS.contains(&field.as_str()) {
                return Err(AppError::Unprocessable(
                    "Unknown model metadata field.".into(),
                ));
            }
            let provider = |key: &str, value: bool| {
                detected["provenance"][key] == "provider" && detected[key] == value
            };
            let conflicts = (field == "embedding" && provider("chat", true))
                || (field == "chat" && provider("embedding", true))
                || (field.starts_with("reasoning_") && provider("reasoning", false));
            if !conflicts
                && (field == "display_name"
                    || provenance
                        .get(field)
                        .is_none_or(|origin| origin != "provider"))
            {
                result[field] = value.clone();
                provenance.insert(field.clone(), "manual".into());
            }
        }
    }
    result["provenance"] = serde_json::to_value(provenance).map_err(anyhow::Error::from)?;
    let metadata: ModelMetadata = serde_json::from_value(result)
        .map_err(|_| AppError::Unprocessable("Invalid model metadata value.".into()))?;
    if metadata
        .license
        .as_ref()
        .is_some_and(|license| !license.is_valid())
    {
        return Err(AppError::Unprocessable(
            "Model license requires a valid name or HTTPS reference.".into(),
        ));
    }
    if [
        metadata.context_window_tokens,
        metadata.max_input_tokens,
        metadata.max_output_tokens,
    ]
    .into_iter()
    .flatten()
    .any(|v| v <= 0)
        || (metadata.reasoning_required == Some(true) && metadata.reasoning == Some(false))
        || (metadata.embedding == Some(true) && metadata.chat == Some(true))
        || metadata.reasoning_default.as_ref().is_some_and(|v| {
            metadata
                .reasoning_efforts
                .as_ref()
                .is_some_and(|efforts| !efforts.contains(v))
        })
        || metadata.reasoning_efforts.as_ref().is_some_and(|values| {
            values.len() > 16 || values.iter().any(|v| !super::config::bounded_text(v, 64))
        })
        || metadata
            .display_name
            .as_ref()
            .is_some_and(|v| !super::config::bounded_text(v, 256))
        || metadata.reasoning_transport.as_deref().is_some_and(|v| {
            ![
                "responses",
                "reasoning_content",
                "content_blocks",
                "text_tags",
            ]
            .contains(&v)
        })
        || metadata.reasoning_replay.as_deref().is_some_and(|v| {
            ![
                "server_reference",
                "opaque_items",
                "assistant_message",
                "none",
            ]
            .contains(&v)
        })
    {
        return Err(AppError::Unprocessable(
            "Inconsistent model metadata.".into(),
        ));
    }
    Ok(metadata)
}

struct RegistrySnapshot {
    expires_at: Instant,
    value: Option<Arc<Registry>>,
}

struct Registry {
    providers: Value,
    models: Option<Value>,
}

async fn registry() -> Option<Arc<Registry>> {
    // A single public response serves concurrent catalogue refreshes.
    static CACHE: Mutex<Option<RegistrySnapshot>> = Mutex::const_new(None);
    let mut cache = CACHE.lock().await;
    if let Some(snapshot) = cache
        .as_ref()
        .filter(|entry| entry.expires_at > Instant::now())
    {
        return snapshot.value.clone();
    }
    let value = fetch_registry().await.map(Arc::new);
    let lifetime = Duration::from_secs(if value.is_some() { 60 } else { 2 });
    *cache = Some(RegistrySnapshot {
        expires_at: Instant::now() + lifetime,
        value: value.clone(),
    });
    value
}

async fn fetch_registry() -> Option<Registry> {
    let (providers, models) = tokio::join!(
        fetch_registry_file("https://models.dev/api.json"),
        fetch_registry_file("https://models.dev/models.json"),
    );
    Some(Registry {
        providers: providers?,
        models,
    })
}

async fn fetch_registry_file(url: &str) -> Option<Value> {
    static CLIENT: OnceLock<Option<reqwest::Client>> = OnceLock::new();
    let client = CLIENT
        .get_or_init(|| {
            reqwest::Client::builder()
                .redirect(reqwest::redirect::Policy::none())
                .timeout(Duration::from_secs(20))
                .build()
                .ok()
        })
        .as_ref()?;
    let mut response = client.get(url).send().await.ok()?.error_for_status().ok()?;
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.ok()? {
        if bytes.len() + chunk.len() > 8 * 1024 * 1024 {
            return None;
        }
        bytes.extend_from_slice(&chunk);
    }
    // Decode the bounded external catalogue off Tokio's worker threads.
    tokio::task::spawn_blocking(move || {
        serde_json::from_slice(&bytes).ok().filter(Value::is_object)
    })
    .await
    .ok()
    .flatten()
}

fn registry_provider(source: &ModelSource) -> Option<String> {
    source.metadata_provider.clone().or_else(|| {
        let address = match &source.inventory {
            SourceInventory::Discovered { url, .. } => url,
            SourceInventory::Declared { .. } => &source.inference.api_root,
        };
        reqwest::Url::parse(address)
            .ok()?
            .domain()?
            .trim_end_matches('.')
            .rsplit('.')
            .nth(1)
            .filter(|label| super::config::valid_source_id(label))
            .map(str::to_owned)
    })
}

#[derive(Debug, PartialEq, Eq)]
pub(super) enum MetadataRefresh {
    Complete,
    Disabled,
    Unavailable,
}

pub(super) async fn enrich(
    source: &ModelSource,
    offers: &mut [DiscoveredOffer],
) -> MetadataRefresh {
    enrich_with_registry(source, offers, registry()).await
}

async fn enrich_with_registry(
    source: &ModelSource,
    offers: &mut [DiscoveredOffer],
    load: impl Future<Output = Option<Arc<Registry>>>,
) -> MetadataRefresh {
    let enabled = source.models_dev_enabled.unwrap_or(true);
    let provider = registry_provider(source);
    let should_sync = enabled && provider.is_some() && !offers.is_empty();
    let registry = if should_sync { load.await } else { None };
    let models = registry
        .as_ref()
        .and_then(|registry| registry.models.as_ref());
    enrich_offers(
        offers,
        registry
            .as_deref()
            .and_then(|registry| registry.providers.get(provider.as_deref()?)?.get("models")),
        models,
    );
    if !enabled {
        MetadataRefresh::Disabled
    } else if should_sync && models.is_none() {
        tracing::warn!(source_id=%source.source_id, "Optional model metadata enrichment unavailable; provider inventory retained");
        MetadataRefresh::Unavailable
    } else {
        MetadataRefresh::Complete
    }
}

fn registry_license(model: &Value) -> Option<ModelLicense> {
    let url = model["links"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|link| link["type"] == "license")
        .filter_map(|link| link["url"].as_str())
        .find(|url| public_reference_url(url));
    ModelLicense::from_fields(model["license"].as_str(), url)
}

fn enrich_offers(offers: &mut [DiscoveredOffer], records: Option<&Value>, models: Option<&Value>) {
    for offer in offers {
        let Ok(mut values) = serde_json::to_value(&offer.metadata) else {
            continue;
        };
        let mut provenance = BTreeMap::new();
        for field in FIELDS {
            if values.get(*field).is_some_and(|v| !v.is_null()) {
                provenance.insert((*field).to_owned(), "provider".to_owned());
            }
        }
        if let Some(record) = records.and_then(|records| records.get(&offer.upstream_model_id)) {
            let mut fallback = serde_json::json!({});
            if let Some(license) = record["canonical_model_id"]
                .as_str()
                .and_then(|id| models?.get(id))
                .and_then(registry_license)
            {
                fallback["license"] = serde_json::json!(license);
            }
            for (field, key) in [
                ("reasoning", "reasoning"),
                ("tool_calling", "tool_call"),
                ("structured_output", "structured_output"),
            ] {
                if let Some(value) = record.get(key).and_then(Value::as_bool) {
                    fallback[field] = value.into();
                }
            }
            for (field, key) in [
                ("context_window_tokens", "context"),
                ("max_input_tokens", "input"),
                ("max_output_tokens", "output"),
            ] {
                if let Some(value) = record
                    .get("limit")
                    .and_then(|v| v.get(key))
                    .and_then(Value::as_i64)
                    .filter(|v| *v > 0)
                {
                    fallback[field] = value.into();
                }
            }
            if let Some(inputs) = record
                .get("modalities")
                .and_then(|v| v.get("input"))
                .and_then(Value::as_array)
            {
                fallback["vision"] = inputs.iter().any(|v| v.as_str() == Some("image")).into();
                if values["chat"].is_null() && values["embedding"] != true {
                    // Retrieval and other specialized models can also declare text in/out.
                    fallback["chat"] = (record["type"].is_null()
                        && inputs.iter().any(|v| v.as_str() == Some("text"))
                        && record
                            .get("modalities")
                            .and_then(|v| v.get("output"))
                            .and_then(Value::as_array)
                            .is_some_and(|out| out.iter().any(|v| v.as_str() == Some("text"))))
                    .into();
                }
            }
            if let Some(options) = record.get("reasoning_options").and_then(Value::as_array)
                && let Some(values) = options
                    .iter()
                    .find(|v| v["type"] == "effort")
                    .and_then(|v| v.get("values"))
            {
                fallback["reasoning_efforts"] = values.clone();
            }
            if record
                .get("interleaved")
                .and_then(|v| v.get("field"))
                .and_then(Value::as_str)
                == Some("reasoning_content")
            {
                fallback["reasoning_transport"] = "reasoning_content".into();
            }
            if let Some(fields) = fallback.as_object() {
                for (field, value) in fields {
                    if values[field].is_null() {
                        values[field] = value.clone();
                        provenance.insert(field.clone(), "models_dev".into());
                    }
                }
            }
        }
        values["provenance"] = serde_json::to_value(provenance).unwrap_or_default();
        if let Ok(metadata) = serde_json::from_value(values) {
            offer.metadata = metadata;
        }
    }
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReplaceModelComplements {
    pub expected_revision: i64,
    pub upstream_model_id: String,
    /// An omitted field follows detection. Null explicitly records an unknown value.
    /// Provider-confirmed technical fields are locked. The display name can
    /// always be customized. An empty object resets all.
    pub values: BTreeMap<String, Value>,
}

#[utoipa::path(put,path="/organizations/{organization_id}/model-sources/{source_id}/metadata",params(("organization_id"=Uuid,Path),("source_id"=String,Path)),request_body=ReplaceModelComplements,
    responses((status=200,body=ModelMetadata),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn replace_model_complements(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization, source_id)): ApiPath<(Uuid, String)>,
    ApiJson(input): ApiJson<ReplaceModelComplements>,
) -> AppResult<Json<ModelMetadata>> {
    let (mut tx, _) = spaces::governance_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(organization),
        Permission::Manage,
    )
    .await?;
    policy::require_assigned(
        &mut tx,
        organization,
        &std::collections::BTreeSet::from([source_id.clone()]),
    )
    .await?;
    let (detected, revision):(Value,i64) = sqlx::query_as("select o.metadata,coalesce(m.revision,0) from model_offer o left join organization_model_metadata m on m.organization_id=$3 and m.source_id=o.source_id and m.upstream_model_id=o.upstream_model_id where o.source_id=$1 and o.upstream_model_id=$2 and o.advertised for update of o")
        .bind(&source_id).bind(&input.upstream_model_id).bind(organization).fetch_one(&mut *tx).await?;
    if revision != input.expected_revision {
        return Err(AppError::Conflict(
            "Model metadata changed; reload before saving.".into(),
        ));
    }
    let values = serde_json::to_value(input.values).map_err(anyhow::Error::from)?;
    let metadata = project(&detected, &values)?;
    sqlx::query("insert into organization_model_metadata(organization_id,source_id,upstream_model_id,complements,revision) values($1,$2,$3,$4,1) on conflict(organization_id,source_id,upstream_model_id) do update set complements=excluded.complements,revision=organization_model_metadata.revision+1")
        .bind(organization).bind(&source_id).bind(&input.upstream_model_id).bind(SqlJson(values)).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(metadata))
}

pub(super) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(replace_model_complements))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn source(url: &str) -> ModelSource {
        serde_json::from_value(json!({
            "source_id":"test", "revision":1, "enabled":true, "visibility_scope":"test",
            "inventory":{"kind":"discovered", "url":url, "authentication":{"mode":"public"},
                "qualification":"mixed_capabilities_v1", "complete_inventory_guaranteed":true},
            "inference":{"credential_binding":"test", "api_root":"https://gateway.invalid/v1",
                "wire":"openai_chat", "route":"standard", "dialect":"openai_compatible", "auth":{"kind":"none"}}
        })).unwrap()
    }

    #[test]
    fn automatic_sync_extracts_the_catalogue_domain_label() {
        for (url, provider) in [
            ("https://api.openai.com/v1/models", Some("openai")),
            ("https://xxxxxxx.ia/v1/models", Some("xxxxxxx")),
            ("https://integrate.api.nvidia.com/v1/models", Some("nvidia")),
            ("https://api.EXAMPLE.fr.:8443/v2/models", Some("example")),
            ("http://127.0.0.1:8000/v1/models", None),
            ("http://localhost:8000/v1/models", None),
        ] {
            assert_eq!(
                registry_provider(&source(url)).as_deref(),
                provider,
                "{url}"
            );
        }
        let mut configured = source("https://private.example.ia/v1/models");
        configured.metadata_provider = Some("other-provider".into());
        assert_eq!(
            registry_provider(&configured).as_deref(),
            Some("other-provider")
        );
    }

    #[tokio::test]
    async fn sync_uses_the_domain_without_a_published_api_and_is_optional() {
        let mut source = source("https://api.example.ia/v1/models");
        let fresh_offer = || DiscoveredOffer {
            upstream_model_id: "chat-model".into(),
            metadata: ModelMetadata {
                max_output_tokens: Some(4096),
                ..Default::default()
            },
        };
        let providers =
            json!({"example":{"models":{"chat-model":{"limit":{"context":32000,"output":1024}}}}});
        let registry = Arc::new(Registry {
            providers: providers.clone(),
            models: Some(json!({})),
        });
        let mut offers = [fresh_offer()];
        assert_eq!(
            enrich_with_registry(&source, &mut offers, std::future::ready(Some(registry))).await,
            MetadataRefresh::Complete
        );
        assert_eq!(offers[0].metadata.context_window_tokens, Some(32000));
        assert_eq!(offers[0].metadata.max_output_tokens, Some(4096));

        let mut offers = [fresh_offer()];
        let without_licenses = Arc::new(Registry {
            providers,
            models: None,
        });
        assert_eq!(
            enrich_with_registry(
                &source,
                &mut offers,
                std::future::ready(Some(without_licenses))
            )
            .await,
            MetadataRefresh::Unavailable
        );
        assert_eq!(offers[0].metadata.context_window_tokens, Some(32000));

        let mut offers = [fresh_offer()];
        assert_eq!(
            enrich_with_registry(&source, &mut offers, std::future::ready(None)).await,
            MetadataRefresh::Unavailable
        );
        assert_eq!(offers[0].metadata.chat, None);
        assert_eq!(
            offers[0].metadata.provenance["max_output_tokens"],
            "provider"
        );

        source.models_dev_enabled = Some(false);
        assert_eq!(
            enrich_with_registry(&source, &mut offers, async {
                panic!("disabled synchronization contacted models.dev")
            })
            .await,
            MetadataRefresh::Disabled
        );
    }

    #[test]
    fn registry_enriches_exact_offers_and_excludes_typed_retrieval_models_from_chat() {
        let mut offers = ["lab/conversation", "lab/retrieval", "unknown", "override"].map(|id| {
            DiscoveredOffer {
                upstream_model_id: id.into(),
                metadata: ModelMetadata::default(),
            }
        });
        offers[3].metadata.chat = Some(false);
        enrich_offers(
            &mut offers,
            Some(&json!({
                "lab/conversation": {
                    "modalities": {"input": ["text", "image"], "output": ["text"]}, "limit": {"context": 256000}
                },
                "lab/retrieval": {
                    "type": "embedding", "modalities": {"input": ["text", "image"], "output": ["text"]}
                },
                "override": {"modalities": {"input": ["text"], "output": ["text"]}}
            })),
            None,
        );
        assert_eq!(offers[0].metadata.chat, Some(true));
        assert_eq!(offers[0].metadata.provenance["chat"], "models_dev");
        assert_eq!(offers[0].metadata.context_window_tokens, Some(256000));
        assert_eq!(offers[1].metadata.chat, Some(false));
        assert_eq!(offers[1].metadata.embedding, None);
        assert_eq!(offers[2].metadata.chat, None);
        assert_eq!(offers[3].metadata.chat, Some(false));
        assert_eq!(offers[3].metadata.provenance["chat"], "provider");
    }

    #[test]
    fn follows_canonical_model_ids_for_licenses_and_never_guesses_from_the_offer_name() {
        let mut offers = ["alias", "another-lab/model", "unknown"].map(|id| DiscoveredOffer {
            upstream_model_id: id.into(),
            metadata: ModelMetadata::default(),
        });
        enrich_offers(
            &mut offers,
            Some(&json!({
                "alias": {"canonical_model_id":"lab/model"},
                "another-lab/model": {},
                "unknown": {"canonical_model_id":"lab/unsafe"}
            })),
            Some(&json!({
                "lab/model": {"license":"MIT","links":[
                    {"type":"docs","url":"https://example.com/docs"},
                    {"type":"license","url":"https://example.com/model#license"}
                ]},
                "another-lab/model": {"license":"Apache-2.0"},
                "lab/unsafe": {"links":[{"type":"license","url":"javascript:alert(1)"}]}
            })),
        );
        let license = offers[0].metadata.license.as_ref().unwrap();
        assert_eq!(license.name.as_deref(), Some("MIT"));
        assert_eq!(
            license.url.as_deref(),
            Some("https://example.com/model#license")
        );
        assert_eq!(offers[0].metadata.provenance["license"], "models_dev");
        assert!(offers[1].metadata.license.is_none());
        assert!(offers[2].metadata.license.is_none());
    }

    #[test]
    fn manual_license_replaces_the_reference_as_a_whole() {
        let detected = json!({"license":{"name":"MIT","url":"https://example.com/mit"},"provenance":{"license":"models_dev"}});
        let metadata = project(&detected, &json!({"license":{"name":"Apache-2.0"}})).unwrap();
        assert_eq!(metadata.provenance["license"], "manual");
        let license = metadata.license.unwrap();
        assert_eq!(license.name.as_deref(), Some("Apache-2.0"));
        assert!(license.url.is_none());
        assert!(
            project(
                &detected,
                &json!({"license":{"url":"https://user:password@example.com/"}})
            )
            .is_err()
        );
        assert!(project(&detected, &json!({"license":{}})).is_err());
    }

    #[test]
    fn provider_facts_win_and_complements_fill_enrichment_or_unknown() {
        let detected = json!({
            "chat": true, "reasoning": true, "max_output_tokens": 100,
            "context_window_tokens": 200, "display_name": "Provider name",
            "provenance": {
                "chat": "provider", "max_output_tokens": "provider",
                "context_window_tokens": "models_dev", "display_name": "provider"
            }
        });
        let result = project(
            &detected,
            &json!({"max_output_tokens":10,"context_window_tokens":300,"vision":true,
                "reasoning":null,"display_name":"Weaver name"}),
        )
        .unwrap();
        assert_eq!(result.max_output_tokens, Some(100));
        assert_eq!(result.context_window_tokens, Some(300));
        assert_eq!(result.vision, Some(true));
        assert_eq!(result.reasoning, None);
        assert_eq!(result.provenance["max_output_tokens"], "provider");
        assert_eq!(result.provenance["context_window_tokens"], "manual");
        assert_eq!(result.display_name.as_deref(), Some("Weaver name"));
        assert_eq!(result.provenance["display_name"], "manual");
        let reset = project(&detected, &json!({})).unwrap();
        assert_eq!(reset.context_window_tokens, Some(200));
        assert_eq!(reset.display_name.as_deref(), Some("Provider name"));
    }

    #[test]
    fn later_provider_facts_suppress_contradictory_complements() {
        let detected = json!({"chat":true,"reasoning":false,"provenance":{"chat":"provider","reasoning":"provider"}});
        let result = project(
            &detected,
            &json!({"embedding":true,"reasoning_required":true,"vision":true}),
        )
        .unwrap();
        assert_eq!(result.embedding, None);
        assert_eq!(result.reasoning_required, None);
        assert_eq!(result.vision, Some(true));
    }

    #[test]
    fn invalid_or_inconsistent_complements_are_refused() {
        for values in [
            json!({"api_root":"https://elsewhere.invalid"}),
            json!({"context_window_tokens":0}),
            json!({"reasoning":false,"reasoning_required":true}),
            json!({"reasoning_default":"high","reasoning_efforts":["low"]}),
            json!({"reasoning_transport":"made_up"}),
            json!({"tool_calling":"yes"}),
        ] {
            assert!(project(&json!({}), &values).is_err(), "{values}");
        }
    }
}
