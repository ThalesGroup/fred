// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::collections::HashSet;

use anyhow::{Result, ensure};
use fred_rust_sdk::inference::ModelConnection;
use fred_rust_sdk::inference::ModelWire;
pub(super) use fred_rust_sdk::inference::bounded_text;
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

const MAX_DECLARED_MODELS: usize = 256;

/// Platform approval of one source. Contains references only, never secret values.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ModelSource {
    pub source_id: String,
    /// Strictly increase for every configuration change, including secret rotation.
    pub revision: i64,
    #[serde(default)]
    pub enabled: bool,
    pub inventory: SourceInventory,
    pub inference: ModelConnection,
    /// Stable provider account, model namespace and list visibility contract.
    /// A changed account/namespace/scope needs a new source_id, even with the same URL.
    pub visibility_scope: String,
    /// Explicit platform approval for internal HTTP routes; HTTPS is the default.
    #[serde(default)]
    pub allow_insecure_http: bool,
    /// Platform attestation: these exact offers compute embeddings and are never chat.
    /// Provider model lists do not establish this aptitude.
    #[schema(max_items = 256)]
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub embedding_models: Vec<String>,
}

/// Where this source's offers come from. A declared list replaces discovery for its
/// source, never supplements it, and both publish through the same refresh.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum SourceInventory {
    Discovered {
        url: String,
        authentication: DiscoveryAuthentication,
        qualification: Qualification,
        /// Platform attests that an unpaginated response lists the entire visibility scope.
        /// Without this guarantee, discovery cannot publish an authoritative inventory.
        complete_inventory_guaranteed: bool,
    },
    Declared {
        #[schema(min_items = 1, max_items = 256)]
        models: Vec<DeclaredModel>,
    },
}

/// Chat is guaranteed by this declaration, except for embedding offers or a
/// source whose inference wire attests reranking.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct DeclaredModel {
    /// Exact upstream identifier, never normalized.
    pub id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub display_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reasoning: Option<bool>,
    #[schema(minimum = 1)]
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub context_window_tokens: Option<i64>,
    #[schema(minimum = 1)]
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_input_tokens: Option<i64>,
    #[schema(minimum = 1)]
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_output_tokens: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(tag = "mode", rename_all = "snake_case", deny_unknown_fields)]
pub enum DiscoveryAuthentication {
    Public,
    Bearer {
        secret_env_var: String,
        /// Actual provider scopes, reviewed by the platform; a separate key proves nothing.
        provider_scopes: Vec<String>,
        authority: CredentialAuthority,
        #[serde(default)]
        accept_inference_authority: bool,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum CredentialAuthority {
    DiscoveryOnly,
    DiscoveryAndInference,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum Qualification {
    /// Platform guarantees chat for every advertised model: never with embedding models.
    ChatSource,
    /// Platform trusts the boolean capabilities.completion_chat and reasoning extensions.
    MixedCapabilitiesV1,
}

pub(crate) fn valid_source_id(value: &str) -> bool {
    bounded_text(value, 64)
        && value.starts_with(|c: char| c.is_ascii_alphanumeric())
        && value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
}

pub(crate) fn approved_url(value: &str, allow_http: bool) -> bool {
    bounded_text(value, 2048)
        && reqwest::Url::parse(value).is_ok_and(|url| {
            (url.scheme() == "https" || (allow_http && url.scheme() == "http"))
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none()
        })
}

pub fn validate_sources(sources: &[ModelSource]) -> Result<()> {
    let mut ids = HashSet::new();
    for source in sources {
        source.validate()?;
        ensure!(ids.insert(&source.source_id), "duplicate model source_id");
    }
    Ok(())
}

/// A platform statement: an invalid value refuses the configuration, it never becomes unknown.
fn validate_declared(models: &[DeclaredModel]) -> Result<()> {
    ensure!(
        !models.is_empty() && models.len() <= MAX_DECLARED_MODELS,
        "a declared inventory requires between 1 and {MAX_DECLARED_MODELS} models"
    );
    let mut ids = HashSet::new();
    for model in models {
        ensure!(
            bounded_text(&model.id, 256) && ids.insert(&model.id),
            "invalid or duplicate declared model id"
        );
        ensure!(
            model
                .display_name
                .as_deref()
                .is_none_or(|name| bounded_text(name, 256)),
            "invalid declared model display_name"
        );
        ensure!(
            [
                model.context_window_tokens,
                model.max_input_tokens,
                model.max_output_tokens,
            ]
            .into_iter()
            .flatten()
            .all(|limit| limit > 0),
            "declared model limits must be strictly positive"
        );
    }
    Ok(())
}

impl DiscoveryAuthentication {
    fn validate(&self) -> Result<()> {
        if let Self::Bearer {
            secret_env_var,
            provider_scopes,
            authority,
            accept_inference_authority,
        } = self
        {
            ensure!(
                bounded_text(secret_env_var, 128)
                    && secret_env_var.starts_with(|c: char| c.is_ascii_alphabetic() || c == '_')
                    && secret_env_var
                        .bytes()
                        .all(|c| c.is_ascii_alphanumeric() || c == b'_'),
                "invalid discovery secret environment reference"
            );
            ensure!(
                !provider_scopes.is_empty()
                    && provider_scopes.len() <= 32
                    && provider_scopes.iter().all(|s| bounded_text(s, 128)),
                "discovery credential requires explicit actual provider scopes"
            );
            ensure!(
                *authority != CredentialAuthority::DiscoveryAndInference
                    || *accept_inference_authority,
                "discovery credential inference authority requires explicit platform acceptance"
            );
        }
        Ok(())
    }
}

impl ModelSource {
    pub fn validate(&self) -> Result<()> {
        ensure!(valid_source_id(&self.source_id), "invalid model source_id");
        ensure!(self.revision > 0, "model source revision must be positive");
        ensure!(
            approved_url(&self.inference.api_root, self.allow_insecure_http),
            "model source requires separately approved HTTP(S) destinations without credentials, query or fragment"
        );
        self.inference.validate()?;
        ensure!(
            self.inference.wire != ModelWire::Rerank || self.embedding_models.is_empty(),
            "a rerank source cannot attest embedding models"
        );
        ensure!(
            self.inference.wire != ModelWire::Rerank
                || matches!(&self.inventory, SourceInventory::Declared { .. }),
            "a rerank source requires a declared model inventory"
        );
        ensure!(
            bounded_text(&self.visibility_scope, 256),
            "invalid model source visibility"
        );
        let mut attested = HashSet::new();
        ensure!(
            self.embedding_models.len() <= MAX_DECLARED_MODELS
                && self
                    .embedding_models
                    .iter()
                    .all(|id| bounded_text(id, 256) && attested.insert(id)),
            "invalid or duplicate embedding model attestation"
        );
        match &self.inventory {
            SourceInventory::Discovered {
                url,
                authentication,
                qualification,
                ..
            } => {
                // A source listing embedding models is mixed: its other offers are not
                // all chat. Declare them, or read the source's own capability metadata.
                ensure!(
                    *qualification != Qualification::ChatSource || self.embedding_models.is_empty(),
                    "a chat_source qualification guarantees chat for every offer; a source with embedding models is mixed: declare its models or use mixed_capabilities_v1"
                );
                ensure!(
                    approved_url(url, self.allow_insecure_http),
                    "model source requires separately approved HTTP(S) destinations without credentials, query or fragment"
                );
                authentication.validate()
            }
            SourceInventory::Declared { models } => validate_declared(models),
        }
    }

    pub(super) fn same_identity(&self, other: &Self) -> bool {
        let same_inventory = match (&self.inventory, &other.inventory) {
            (
                SourceInventory::Discovered { url, .. },
                SourceInventory::Discovered { url: other, .. },
            ) => url == other,
            (SourceInventory::Declared { .. }, SourceInventory::Declared { .. }) => true,
            _ => false,
        };
        self.source_id == other.source_id
            && same_inventory
            && self.inference.api_root == other.inference.api_root
            && self.inference.wire == other.inference.wire
            && self.inference.route == other.inference.route
            && self.visibility_scope == other.visibility_scope
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};

    fn source(changes: Value) -> Result<ModelSource> {
        let mut value = base();
        for (field, change) in changes.as_object().unwrap() {
            value["inference"][field] = change.clone();
        }
        parsed(value)
    }

    fn base() -> Value {
        json!({"source_id":"s","revision":1,"enabled":true,
            "inventory":{"kind":"discovered","url":"https://catalog.invalid/models",
                "authentication":{"mode":"public"},"qualification":"chat_source",
                "complete_inventory_guaranteed":true},
            "inference":{"credential_binding":"b","api_root":"https://gateway.invalid/v1",
                "wire":"openai_chat","route":"standard","dialect":"openai",
                "auth":{"kind":"api_key"}},
            "visibility_scope":"account"})
    }

    fn parsed(value: Value) -> Result<ModelSource> {
        let source: ModelSource = serde_json::from_value(value)?;
        source.validate()?;
        Ok(source)
    }

    fn with_inventory(inventory: Value) -> Result<ModelSource> {
        let mut value = base();
        value["inventory"] = inventory;
        parsed(value)
    }

    fn declared(models: Value) -> Result<ModelSource> {
        with_inventory(json!({"kind":"declared","models":models}))
    }

    #[test]
    fn insecure_http_needs_the_platform_approval_and_never_serves_entra() {
        let http = json!({"api_root":"http://ollama:11434/v1","auth":{"kind":"none"}});
        assert!(source(http.clone()).is_err());
        let mut approved = serde_json::to_value(source(json!({})).unwrap()).unwrap();
        approved["allow_insecure_http"] = true.into();
        approved["inventory"]["url"] = "http://ollama:11434/v1/models".into();
        approved["inference"]["api_root"] = "http://ollama:11434/v1".into();
        approved["inference"]["auth"] = json!({"kind":"none"});
        let approved: ModelSource = serde_json::from_value(approved.clone()).unwrap();
        approved.validate().unwrap();
        let mut entra = approved.clone();
        entra.inference.auth.kind = fred_rust_sdk::inference::ModelAuthKind::Entra;
        entra.inference.auth.tenant_id = Some("t".into());
        entra.inference.auth.client_id = Some("c".into());
        entra.inference.auth.scope = Some("s".into());
        assert!(entra.validate().is_err());
    }

    #[test]
    fn identity_is_the_destination_and_its_protocol_not_its_authentication() {
        let base = source(json!({})).unwrap();
        for changes in [
            json!({"api_root":"https://other.invalid/v1"}),
            json!({"wire":"openai_responses"}),
            json!({"route":"azure_deployment","api_version":"1"}),
        ] {
            assert!(
                !base.same_identity(&source(changes.clone()).unwrap()),
                "{changes}"
            );
        }
        for changes in [
            json!({"dialect":"mistral"}),
            json!({"api_version":"1"}),
            json!({"credential_binding":"other"}),
            json!({"auth":{"kind":"none"}}),
            json!({"auth":{"kind":"api_key","gateway_key_header":"x-key"}}),
        ] {
            assert!(
                base.same_identity(&source(changes.clone()).unwrap()),
                "{changes}"
            );
        }
    }

    #[test]
    fn the_former_format_is_refused() {
        assert!(source(json!({"provider":"openai"})).is_err());
        let mut value = base();
        let former = value.as_object_mut().unwrap();
        let inventory = former.remove("inventory").unwrap();
        assert!(parsed(Value::Object(former.clone())).is_err());
        former.insert("discovery_url".into(), inventory["url"].clone());
        former.insert("authentication".into(), json!({"mode":"public"}));
        former.insert("qualification".into(), json!("chat_source"));
        former.insert("complete_inventory_guaranteed".into(), json!(true));
        assert!(parsed(Value::Object(former.clone())).is_err());
    }

    #[test]
    fn an_inventory_is_one_form_or_the_other_never_a_mix() {
        for inventory in [
            json!({"kind":"declared","models":[{"id":"m"}],"url":"https://catalog.invalid/models"}),
            json!({"kind":"declared","models":[{"id":"m"}],"qualification":"chat_source"}),
            json!({"kind":"declared"}),
            json!({"kind":"discovered","url":"https://catalog.invalid/models",
                "authentication":{"mode":"public"},"qualification":"chat_source",
                "complete_inventory_guaranteed":true,"models":[{"id":"m"}]}),
            json!({"kind":"discovered","url":"https://catalog.invalid/models"}),
            json!({"kind":"static","models":[{"id":"m"}]}),
            json!({"models":[{"id":"m"}]}),
        ] {
            assert!(with_inventory(inventory.clone()).is_err(), "{inventory}");
        }
        // The rules of a discovered inventory did not change when they moved.
        for changes in [
            json!({"url":"http://catalog.invalid/models"}),
            json!({"url":"https://catalog.invalid/models?a=b"}),
            json!({"authentication":{"mode":"bearer","secret_env_var":"not a name",
                "provider_scopes":["s"],"authority":"discovery_only"}}),
            json!({"authentication":{"mode":"bearer","secret_env_var":"KEY",
                "provider_scopes":[],"authority":"discovery_only"}}),
            json!({"authentication":{"mode":"bearer","secret_env_var":"KEY",
                "provider_scopes":["s"],"authority":"discovery_and_inference"}}),
        ] {
            let mut inventory = base()["inventory"].clone();
            for (field, change) in changes.as_object().unwrap() {
                inventory[field] = change.clone();
            }
            assert!(with_inventory(inventory).is_err(), "{changes}");
        }
    }

    #[test]
    fn a_declared_list_only_accepts_valid_statements() {
        let source = declared(json!([
            {"id":"org/model:tag","display_name":"GPT-4o","reasoning":false,
                "context_window_tokens":128000,"max_input_tokens":1,"max_output_tokens":2},
            {"id":"bare"},
        ]))
        .unwrap();
        // Absent facts stay absent, so the stored configuration compares equal.
        let stored = serde_json::to_value(&source).unwrap();
        assert_eq!(stored["inventory"]["models"][1], json!({"id":"bare"}));
        assert_eq!(
            serde_json::from_value::<ModelSource>(stored).unwrap(),
            source
        );
        let at_bound = |id: &str| json!({"id":id});
        let too_many: Vec<_> = (0..=MAX_DECLARED_MODELS)
            .map(|i| at_bound(&format!("m{i}")))
            .collect();
        assert!(declared(json!(too_many[..MAX_DECLARED_MODELS])).is_ok());
        for models in [
            json!([]),
            json!(too_many),
            json!([{"id":""}]),
            json!([{"id":" padded"}]),
            json!([{"id":"control\n"}]),
            json!([{"id":"x".repeat(257)}]),
            json!([{"id":"same"},{"id":"same"}]),
            json!([{"display_name":"no id"}]),
            json!([{"id":"m","extra":true}]),
            json!([{"id":"m","display_name":""}]),
            json!([{"id":"m","display_name":"x".repeat(257)}]),
            json!([{"id":"m","context_window_tokens":0}]),
            json!([{"id":"m","max_input_tokens":-1}]),
            json!([{"id":"m","max_output_tokens":0}]),
            json!([{"id":"m","context_window_tokens":"8"}]),
            json!([{"id":"m","reasoning":"true"}]),
        ] {
            assert!(declared(models.clone()).is_err(), "{models}");
        }
        // Identifiers are compared exactly: these are two models.
        assert!(declared(json!([{"id":"Model"},{"id":"model"}])).is_ok());
    }

    /// The deployment path: YAML, not the JSON stored afterwards.
    #[test]
    fn both_inventory_forms_read_from_yaml() {
        let read = |inventory: &str| {
            let source: ModelSource = serde_yaml_ng::from_str(&format!(
                "source_id: s\nrevision: 1\nvisibility_scope: account\n\
                 inference: {{credential_binding: b, api_root: 'https://gateway.invalid/v1', \
                 wire: openai_chat, route: standard, dialect: openai_compatible, \
                 auth: {{kind: none}}}}\ninventory:\n{inventory}"
            ))?;
            source.validate()?;
            anyhow::Ok(source)
        };
        let list = read(
            "  kind: declared\n  models:\n    - id: gpt-4o\n      display_name: GPT-4o\n      \
             reasoning: false\n      context_window_tokens: 128000\n",
        )
        .unwrap();
        let SourceInventory::Declared { models } = &list.inventory else {
            panic!("declared inventory expected");
        };
        assert_eq!(models[0].id, "gpt-4o");
        assert_eq!(models[0].reasoning, Some(false));
        assert_eq!(models[0].context_window_tokens, Some(128000));
        assert_eq!(models[0].max_output_tokens, None);
        read(
            "  kind: discovered\n  url: https://catalog.invalid/models\n  authentication:\n    \
             mode: bearer\n    secret_env_var: KEY\n    provider_scopes: [list]\n    \
             authority: discovery_only\n  qualification: mixed_capabilities_v1\n  \
             complete_inventory_guaranteed: true\n",
        )
        .unwrap();
    }

    #[test]
    fn identity_keeps_the_inventory_kind_and_the_discovery_url() {
        let discovered = source(json!({})).unwrap();
        let list = declared(json!([{"id":"a"}])).unwrap();
        assert!(!discovered.same_identity(&list) && !list.same_identity(&discovered));
        let mut moved = base();
        moved["inventory"]["url"] = "https://other.invalid/models".into();
        assert!(!discovered.same_identity(&parsed(moved).unwrap()));
        let mut reviewed = base();
        reviewed["inventory"]["qualification"] = "mixed_capabilities_v1".into();
        assert!(discovered.same_identity(&parsed(reviewed).unwrap()));
        // A changed list is the same source; only its revision has to change.
        assert!(list.same_identity(&declared(json!([{"id":"b"}])).unwrap()));
    }

    #[test]
    fn a_chat_source_cannot_also_attest_embedding_models() {
        let mut value = base();
        assert!(parsed(value.clone()).is_ok());
        value["embedding_models"] = json!(["embed"]);
        assert!(
            parsed(value.clone()).is_err(),
            "unknown offers would become chat"
        );
        value["inventory"]["qualification"] = json!("mixed_capabilities_v1");
        assert!(parsed(value).is_ok());
    }

    #[test]
    fn embedding_attestation_names_distinct_bounded_offers() {
        let mut value = base();
        value["inventory"]["qualification"] = json!("mixed_capabilities_v1");
        value["embedding_models"] = json!(["mistral-embed", "text-embedding-3-small"]);
        let attested = parsed(value.clone()).unwrap();
        assert_eq!(attested.embedding_models.len(), 2);
        assert!(source(json!({})).unwrap().embedding_models.is_empty());
        for invalid in [json!(["a", "a"]), json!([""]), json!(["x".repeat(257)])] {
            value["embedding_models"] = invalid;
            assert!(parsed(value.clone()).is_err());
        }
    }
}
