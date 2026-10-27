// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Instance model settings and the data contract for the existing runtime resolver.

use std::collections::{BTreeMap, BTreeSet};

use anyhow::Context;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::{PgConnection, types::Json};
use utoipa::ToSchema;
use uuid::Uuid;

pub use super::policy::{ModelOfferKey, OrganizationModelPolicy};
use super::{ModelInventory, ModelMetadata, ModelObservation, policy, store};
use crate::error::{AppError, AppResult};

/// Only explicit overrides. Missing/null members supply no value, not a provider default.
#[derive(Debug, Default, Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ModelOptions {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub temperature: Option<f64>,
    #[schema(minimum = 1)]
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_tokens: Option<i64>,
    #[schema(minimum = 0, maximum = 1)]
    #[serde(skip_serializing_if = "Option::is_none")]
    pub top_p: Option<f64>,
}

impl ModelOptions {
    pub(crate) fn validate(&self) -> AppResult<()> {
        if self.temperature.is_some_and(|v| !v.is_finite())
            || self.max_tokens.is_some_and(|v| v <= 0)
            || self
                .top_p
                .is_some_and(|v| !v.is_finite() || !(0.0..=1.0).contains(&v))
        {
            return Err(AppError::Unprocessable("temperature must be finite, max_tokens a positive integer and top_p finite in [0, 1]".into()));
        }
        Ok(())
    }

    fn fits(&self, metadata: &ModelMetadata) -> bool {
        self.max_tokens.is_none_or(|tokens| {
            [metadata.max_output_tokens, metadata.context_window_tokens]
                .into_iter()
                .flatten()
                .all(|limit| tokens <= limit)
        })
    }
}

#[derive(Default, Deserialize)]
pub(crate) struct SavedModelSettings {
    pub recommended_model: Option<ModelOfferKey>,
    #[serde(default)]
    pub model_options: ModelOptions,
    pub recommended_chat_profile_id: Option<String>,
}

impl SavedModelSettings {
    pub(crate) fn read(tuning: &Value) -> AppResult<Self> {
        serde_json::from_value(tuning.clone())
            .context("invalid saved model settings")
            .map_err(Into::into)
    }
}

/// Caller holds the existing organization lock, which also serializes M2 policy writes.
/// The shared M2 selection guard locks the source/offer through the instance commit.
pub(crate) async fn validate_write(
    conn: &mut PgConnection,
    organization: Uuid,
    tuning: &Value,
    new_recommendation: bool,
) -> AppResult<()> {
    let settings = SavedModelSettings::read(tuning)?;
    settings.model_options.validate()?;
    let policy = policy::read(conn, organization).await?;
    if new_recommendation && let Some(key) = &settings.recommended_model {
        if !policy.permitted.contains(key) {
            return Err(AppError::Unprocessable(
                "The recommended model must be permitted by the owning organization.".into(),
            ));
        }
        policy::require_selectable(conn, &BTreeSet::from([key.clone()])).await?;
    }
    // Check the known effective recommendation/default, never an arbitrary first offer.
    // A legacy profile has no offer identity and cannot be resolved by name.
    let selected = settings.recommended_model.as_ref().or_else(|| {
        settings
            .recommended_chat_profile_id
            .is_none()
            .then_some(policy.default.as_ref())
            .flatten()
    });
    if let Some(key) = selected {
        let metadata: Option<Json<ModelMetadata>> = sqlx::query_scalar(
            "select metadata from model_offer where source_id = $1 and upstream_model_id = $2 for share",
        ).bind(&key.source_id).bind(&key.upstream_model_id).fetch_optional(conn).await?;
        if metadata.is_some_and(|metadata| !settings.model_options.fits(&metadata)) {
            return Err(AppError::Unprocessable(
                "max_tokens exceeds the model's known output or context limit.".into(),
            ));
        }
    }
    Ok(())
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ModelDiagnostic {
    UnknownOffer,
    NotPermitted,
    SourceDisabled,
    SourceRevisionUnobserved,
    DiscoveryUnavailable,
    Withdrawn,
    ChatNotEstablished,
    OptionsExceedKnownLimit,
}

#[derive(Serialize, ToSchema)]
pub struct RuntimeModelOffer {
    pub key: ModelOfferKey,
    pub permitted: bool,
    /// Necessary known facts only; local support, credentials and connectivity remain unproven.
    pub candidate: bool,
    /// New selection writes additionally require successful current discovery (M2).
    pub selectable: bool,
    pub diagnostics: Vec<ModelDiagnostic>,
    pub metadata: Option<ModelMetadata>,
    pub observation: Option<ModelObservation>,
    /// Only trusted delegated runtime callers receive this, and only for candidate offers.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub connection: Option<ModelConnection>,
}

/// Deliberately excludes discovery URL, authentication and secret references.
#[derive(Deserialize, Serialize, ToSchema)]
pub struct ModelConnection {
    pub provider: String,
    pub api_root: String,
    /// Platform-approved reference to pod-local inference provisioning, never a secret value.
    pub credential_binding: String,
}

#[derive(Serialize, ToSchema)]
pub struct RuntimeModels {
    pub policy: OrganizationModelPolicy,
    pub recommendation: Option<ModelOfferKey>,
    pub options: ModelOptions,
    /// Diagnostic only. Never an alternative resolution key.
    pub legacy_profile_id: Option<String>,
    pub requires_reselection: bool,
    /// Union of permitted keys and retained recommendation/default/fallback references.
    pub offers: Vec<RuntimeModelOffer>,
}

/// All reads use the caller's repeatable-read snapshot, including connection approvals.
pub(crate) async fn resolve(
    conn: &mut PgConnection,
    organization: Uuid,
    tuning: &Value,
    include_connections: bool,
) -> AppResult<RuntimeModels> {
    let settings = SavedModelSettings::read(tuning)?;
    let policy = policy::read(conn, organization).await?;
    let inventory = store::read_inventory(conn, None).await?;
    let sources: BTreeMap<_, _> = inventory
        .into_iter()
        .map(|source| (source.observation.source_id.clone(), source))
        .collect();
    let mut connections: BTreeMap<String, Json<ModelConnection>> = BTreeMap::new();
    if include_connections {
        let rows: Vec<(String, Json<ModelConnection>)> = sqlx::query_as(
            "select source_id, configuration->'inference' from model_source order by source_id",
        )
        .fetch_all(&mut *conn)
        .await?;
        connections.extend(rows);
    }
    let keys: BTreeSet<_> = policy
        .permitted
        .iter()
        .chain(settings.recommended_model.iter())
        .chain(policy.default.iter())
        .chain(policy.fallback.iter())
        .cloned()
        .collect();
    let offers = keys
        .into_iter()
        .map(|key| {
            let source = sources.get(&key.source_id);
            let permitted = policy.permitted.contains(&key);
            let mut offer = describe_offer(key, permitted, source, &settings.model_options);
            if offer.candidate {
                offer.connection = connections
                    .get(&offer.key.source_id)
                    .map(|c| ModelConnection {
                        provider: c.provider.clone(),
                        api_root: c.api_root.clone(),
                        credential_binding: c.credential_binding.clone(),
                    });
            }
            offer
        })
        .collect();
    Ok(RuntimeModels {
        requires_reselection: settings.recommended_model.is_none()
            && settings.recommended_chat_profile_id.is_some(),
        policy,
        recommendation: settings.recommended_model,
        options: settings.model_options,
        legacy_profile_id: settings.recommended_chat_profile_id,
        offers,
    })
}

fn describe_offer(
    key: ModelOfferKey,
    permitted: bool,
    source: Option<&ModelInventory>,
    options: &ModelOptions,
) -> RuntimeModelOffer {
    let mut diagnostics = Vec::new();
    if !permitted {
        diagnostics.push(ModelDiagnostic::NotPermitted);
    }
    let stored = source.and_then(|s| {
        s.offers
            .iter()
            .find(|o| o.upstream_model_id == key.upstream_model_id)
    });
    if stored.is_none() {
        diagnostics.push(ModelDiagnostic::UnknownOffer);
    }
    let current = source.is_some_and(|s| {
        s.observation.snapshot_source_revision == Some(s.observation.source_revision)
    });
    let enabled = source.is_some_and(|s| s.observation.enabled);
    let observed_ok = source.is_some_and(|s| s.observation.state == "ok");
    if source.is_some() {
        if !enabled {
            diagnostics.push(ModelDiagnostic::SourceDisabled);
        }
        if !current {
            diagnostics.push(ModelDiagnostic::SourceRevisionUnobserved);
        }
        if !observed_ok {
            diagnostics.push(ModelDiagnostic::DiscoveryUnavailable);
        }
    }
    if let Some(stored) = stored {
        if !stored.advertised {
            diagnostics.push(ModelDiagnostic::Withdrawn);
        }
        if stored.metadata.chat != Some(true) {
            diagnostics.push(ModelDiagnostic::ChatNotEstablished);
        }
        if !options.fits(&stored.metadata) {
            diagnostics.push(ModelDiagnostic::OptionsExceedKnownLimit);
        }
    }
    let candidate = permitted
        && enabled
        && current
        && stored.is_some_and(|o| {
            o.advertised && o.metadata.chat == Some(true) && options.fits(&o.metadata)
        });
    RuntimeModelOffer {
        key,
        permitted,
        candidate,
        selectable: candidate && observed_ok,
        diagnostics,
        metadata: stored.map(|o| o.metadata.0.clone()),
        observation: source.map(|s| s.observation.clone()),
        connection: None,
    }
}

#[derive(Debug, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ModelPreparationErrorCode {
    SelectionMissing,
    ReselectionRequired,
    OfferUnknown,
    OfferForbidden,
    OfferUnavailable,
    FallbackUnavailable,
}

#[derive(Serialize, ToSchema)]
pub struct ModelPreparationError {
    pub code: ModelPreparationErrorCode,
    pub message: String,
}

impl ModelPreparationErrorCode {
    fn diagnostic(self) -> ModelPreparationError {
        let message = match self {
            Self::SelectionMissing => {
                "No model is selected and neither the agent nor the organization defines a default. Choose a model in the chat, or ask an organization administrator to set a default."
            }
            Self::ReselectionRequired => {
                "This agent retains an old model profile. Choose an available model in the chat."
            }
            Self::OfferUnknown => {
                "The selected model is not in this agent's available model catalog. Choose another model or ask an organization administrator to check the model policy."
            }
            Self::OfferForbidden => {
                "The selected model is no longer permitted by the organization. Choose a permitted model or ask an organization administrator to review the model policy."
            }
            Self::OfferUnavailable => {
                "The selected model is currently unavailable for this agent. Choose an available model or ask an organization administrator to check the model source and configuration."
            }
            Self::FallbackUnavailable => {
                "The selected model was withdrawn and no permitted, usable fallback is configured. Choose an available model or ask an organization administrator to update the default or fallback."
            }
        };
        ModelPreparationError {
            code: self,
            message: message.into(),
        }
    }
}

/// Early diagnostic over the same model facts used at turn admission.
/// Preparation is not a grant: the runtime still enforces its fresh turn snapshot.
/// Existing candidates tolerate a discovery outage; newly selectable offers do not.
pub(crate) fn preparation_error(
    models: &RuntimeModels,
    choice: Option<&ModelOfferKey>,
) -> Option<ModelPreparationError> {
    use ModelPreparationErrorCode as Error;
    let reject = |code: Error| Some(code.diagnostic());
    if models.requires_reselection && choice.is_none() {
        return reject(Error::ReselectionRequired);
    }
    let Some(key) = choice
        .or(models.recommendation.as_ref())
        .or(models.policy.default.as_ref())
    else {
        return reject(Error::SelectionMissing);
    };
    let Some(offer) = models.offers.iter().find(|offer| &offer.key == key) else {
        return reject(Error::OfferUnknown);
    };
    if !offer.permitted {
        return reject(Error::OfferForbidden);
    }
    if offer
        .diagnostics
        .iter()
        .any(|d| matches!(d, ModelDiagnostic::UnknownOffer))
    {
        return reject(Error::OfferUnknown);
    }
    if offer.candidate {
        return None;
    }
    let withdrawn = offer
        .diagnostics
        .iter()
        .any(|d| matches!(d, ModelDiagnostic::Withdrawn));
    if !withdrawn
        || offer.diagnostics.iter().any(|d| {
            !matches!(
                d,
                ModelDiagnostic::Withdrawn | ModelDiagnostic::DiscoveryUnavailable
            )
        })
    {
        return reject(Error::OfferUnavailable);
    }
    if models.policy.fallback.as_ref().is_some_and(|key| {
        models
            .offers
            .iter()
            .any(|offer| &offer.key == key && offer.permitted && offer.candidate)
    }) {
        None
    } else {
        reject(Error::FallbackUnavailable)
    }
}

#[cfg(test)]
mod preparation_tests {
    use super::*;

    fn key(name: &str) -> ModelOfferKey {
        ModelOfferKey {
            source_id: "source".into(),
            upstream_model_id: name.into(),
        }
    }

    fn candidate(name: &str) -> RuntimeModelOffer {
        RuntimeModelOffer {
            key: key(name),
            permitted: true,
            candidate: true,
            selectable: true,
            diagnostics: vec![],
            metadata: None,
            observation: None,
            connection: None,
        }
    }

    fn models() -> RuntimeModels {
        RuntimeModels {
            policy: OrganizationModelPolicy {
                organization_id: Uuid::nil(),
                revision: 1,
                permitted: vec![key("model"), key("fallback")],
                reasoning_enabled: vec![],
                default: None,
                fallback: Some(key("fallback")),
                created_by: None,
                created_at: None,
                updated_by: None,
                updated_at: None,
            },
            recommendation: None,
            options: ModelOptions::default(),
            legacy_profile_id: None,
            requires_reselection: false,
            offers: vec![candidate("model"), candidate("fallback")],
        }
    }

    fn error(
        models: &RuntimeModels,
        choice: Option<&ModelOfferKey>,
    ) -> Option<ModelPreparationErrorCode> {
        preparation_error(models, choice).map(|error| error.code)
    }

    #[test]
    fn missing_selection_does_not_pick_an_offer_or_fallback() {
        let models = models();
        assert_eq!(
            error(&models, None),
            Some(ModelPreparationErrorCode::SelectionMissing)
        );
        assert_eq!(error(&models, Some(&key("model"))), None);
        assert_eq!(
            error(&models, Some(&key("unknown"))),
            Some(ModelPreparationErrorCode::OfferUnknown)
        );
    }

    #[test]
    fn explicit_choice_then_recommendation_then_default_without_silent_substitution() {
        let mut models = models();
        models.policy.default = Some(key("model"));
        assert_eq!(error(&models, None), None);
        models.recommendation = Some(key("unknown"));
        assert_eq!(
            error(&models, None),
            Some(ModelPreparationErrorCode::OfferUnknown)
        );
        assert_eq!(error(&models, Some(&key("model"))), None);
        models.requires_reselection = true;
        assert_eq!(
            error(&models, None),
            Some(ModelPreparationErrorCode::ReselectionRequired)
        );
        assert_eq!(error(&models, Some(&key("model"))), None);
    }

    #[test]
    fn fallback_is_only_for_withdrawal_never_revocation_or_other_unavailability() {
        let mut models = models();
        models.policy.default = Some(key("model"));
        models.offers[0].candidate = false;
        models.offers[0].diagnostics = vec![
            ModelDiagnostic::Withdrawn,
            ModelDiagnostic::DiscoveryUnavailable,
        ];
        assert_eq!(error(&models, None), None);
        models.offers[0].permitted = false;
        assert_eq!(
            error(&models, None),
            Some(ModelPreparationErrorCode::OfferForbidden)
        );
        models.offers[0].permitted = true;
        models.offers[0]
            .diagnostics
            .push(ModelDiagnostic::SourceDisabled);
        assert_eq!(
            error(&models, None),
            Some(ModelPreparationErrorCode::OfferUnavailable)
        );
        models.offers[0].diagnostics = vec![ModelDiagnostic::Withdrawn];
        models.offers[1].candidate = false;
        assert_eq!(
            error(&models, None),
            Some(ModelPreparationErrorCode::FallbackUnavailable)
        );
    }

    #[test]
    fn existing_candidate_survives_discovery_outage() {
        let mut models = models();
        models.offers[0].selectable = false;
        models.offers[0].diagnostics = vec![ModelDiagnostic::DiscoveryUnavailable];
        assert_eq!(error(&models, Some(&key("model"))), None);
    }
}
