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
        policy::require_selectable(conn, organization, &BTreeSet::from([key.clone()])).await?;
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
            "select o.metadata from model_offer o join organization_model_source a using (source_id)
             where o.source_id = $1 and o.upstream_model_id = $2 and a.organization_id = $3 for share of o, a",
        ).bind(&key.source_id).bind(&key.upstream_model_id).bind(organization).fetch_optional(conn).await?;
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
}

pub use fred_rust_sdk::inference::ModelConnection;
use fred_rust_sdk::inference::{
    EffectiveModelOptions, InferenceAdmission, InferenceSelection, ModelSelectionSource,
    ReasoningEffort,
};

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

/// Catalog facts use the caller's repeatable-read snapshot. No private connections here.
pub(crate) async fn resolve(
    conn: &mut PgConnection,
    organization: Uuid,
    tuning: &Value,
) -> AppResult<RuntimeModels> {
    let settings = SavedModelSettings::read(tuning)?;
    let policy = policy::read(conn, organization).await?;
    let inventory = store::read_inventory(conn, None, Some(organization)).await?;
    let sources: BTreeMap<_, _> = inventory
        .into_iter()
        .map(|source| (source.observation.source_id.clone(), source))
        .collect();
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
            describe_offer(key, permitted, source, &settings.model_options)
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

#[derive(Debug, Serialize, ToSchema)]
pub struct ModelPreparationError {
    pub code: ModelPreparationErrorCode,
    pub message: String,
}

impl ModelPreparationErrorCode {
    pub(crate) fn as_str(&self) -> &'static str {
        match self {
            Self::SelectionMissing => "model_selection_missing",
            Self::ReselectionRequired => "model_reselection_required",
            Self::OfferUnknown => "model_offer_unknown",
            Self::OfferForbidden => "model_offer_forbidden",
            Self::OfferUnavailable => "model_offer_unavailable",
            Self::FallbackUnavailable => "model_fallback_unavailable",
        }
    }

    fn diagnostic(self) -> ModelPreparationError {
        let message = match self {
            Self::SelectionMissing => {
                "No model is selected and neither the agent nor the organization defines a default. Choose a model in the chat, or ask an organization owner to set a default."
            }
            Self::ReselectionRequired => {
                "This agent retains an old model profile. Choose an available model in the chat."
            }
            Self::OfferUnknown => {
                "The selected model is not in this agent's available model catalog. Choose another model or ask an organization owner to check the model policy."
            }
            Self::OfferForbidden => {
                "The selected model is no longer permitted by the organization. Choose a permitted model or ask an organization owner to review the model policy."
            }
            Self::OfferUnavailable => {
                "The selected model is currently unavailable for this agent. Choose an available model or ask an organization owner to check the model source and configuration."
            }
            Self::FallbackUnavailable => {
                "The selected model was withdrawn and no permitted, usable fallback is configured. Choose an available model or ask an organization owner to update the default or fallback."
            }
        };
        ModelPreparationError {
            code: self,
            message: message.into(),
        }
    }
}

/// One decision for public preparation, trusted delegation and internal Rust admission.
/// Existing candidates tolerate discovery outages; fallback requires confirmed withdrawal.
pub(crate) fn decide(
    models: &RuntimeModels,
    choice: Option<&ModelOfferKey>,
    reasoning: bool,
) -> Result<InferenceSelection, ModelPreparationError> {
    use ModelPreparationErrorCode as Error;
    if models.requires_reselection && choice.is_none() {
        return Err(Error::ReselectionRequired.diagnostic());
    }
    let key = choice
        .or(models.recommendation.as_ref())
        .or(models.policy.default.as_ref())
        .ok_or_else(|| Error::SelectionMissing.diagnostic())?;
    let mut source = if choice.is_some() {
        ModelSelectionSource::UserChoice
    } else if models.recommendation.is_some() {
        ModelSelectionSource::InstanceRecommendation
    } else {
        ModelSelectionSource::Default
    };
    let mut offer = models
        .offers
        .iter()
        .find(|offer| &offer.key == key)
        .ok_or_else(|| Error::OfferUnknown.diagnostic())?;
    if !offer.permitted {
        return Err(Error::OfferForbidden.diagnostic());
    }
    if offer
        .diagnostics
        .iter()
        .any(|d| matches!(d, ModelDiagnostic::UnknownOffer))
    {
        return Err(Error::OfferUnknown.diagnostic());
    }
    if !offer.candidate {
        if !offer
            .diagnostics
            .iter()
            .any(|d| matches!(d, ModelDiagnostic::Withdrawn))
            || offer.diagnostics.iter().any(|d| {
                !matches!(
                    d,
                    ModelDiagnostic::Withdrawn | ModelDiagnostic::DiscoveryUnavailable
                )
            })
        {
            return Err(Error::OfferUnavailable.diagnostic());
        }
        // A source has exactly one approved provisioning/account. Never change payer.
        offer = models
            .policy
            .fallback
            .as_ref()
            .filter(|fallback| fallback.source_id == key.source_id)
            .and_then(|fallback| {
                models
                    .offers
                    .iter()
                    .find(|o| &o.key == fallback && o.candidate)
            })
            .ok_or_else(|| Error::FallbackUnavailable.diagnostic())?;
        source = ModelSelectionSource::WithdrawalFallback;
    }
    let observation = offer
        .observation
        .as_ref()
        .ok_or_else(|| Error::OfferUnavailable.diagnostic())?;
    let metadata = offer
        .metadata
        .as_ref()
        .ok_or_else(|| Error::OfferUnavailable.diagnostic())?;
    // Materialize the known ceiling, including when no instance override was saved.
    let max_tokens = [
        models.options.max_tokens,
        metadata.max_output_tokens,
        metadata.context_window_tokens,
    ]
    .into_iter()
    .flatten()
    .min()
    .and_then(|n| u64::try_from(n).ok());
    Ok(InferenceSelection {
        key: offer.key.clone(),
        source,
        options: EffectiveModelOptions {
            temperature: models.options.temperature,
            max_tokens,
            top_p: models.options.top_p,
            reasoning_effort: (reasoning
                && models.policy.reasoning_enabled.contains(&offer.key)
                && metadata.reasoning == Some(true))
            .then_some(ReasoningEffort::High),
        },
        source_revision: observation.source_revision,
        snapshot_revision: observation.snapshot_revision,
        policy_revision: models.policy.revision,
    })
}

/// Connection projection is explicit, separate from the browser-safe decision.
pub(crate) async fn admit(
    conn: &mut PgConnection,
    organization: Uuid,
    selection: InferenceSelection,
) -> AppResult<InferenceAdmission> {
    // Read only the selected connection, within the same organization snapshot.
    let connection: Option<Json<ModelConnection>> = sqlx::query_scalar(
        "select s.configuration->'inference' from model_source s
         join organization_model_source a using (source_id)
         where a.organization_id=$1 and s.source_id=$2",
    )
    .bind(organization)
    .bind(&selection.key.source_id)
    .fetch_optional(conn)
    .await?;
    let connection = connection
        .ok_or_else(|| {
            AppError::problem(
                axum::http::StatusCode::SERVICE_UNAVAILABLE,
                "inference_connection_unavailable",
                "Approved inference connection is unavailable.",
            )
        })?
        .0;
    Ok(InferenceAdmission {
        selection,
        connection,
    })
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
            metadata: Some(ModelMetadata {
                chat: Some(true),
                chat_provenance: None,
                reasoning: Some(true),
                display_name: None,
                context_window_tokens: Some(1000),
                max_input_tokens: None,
                max_output_tokens: Some(100),
            }),
            observation: Some(ModelObservation {
                source_id: "source".into(),
                source_revision: 1,
                enabled: true,
                state: "ok".into(),
                error_code: None,
                checked_at: None,
                last_success_at: None,
                snapshot_revision: 1,
                snapshot_source_revision: Some(1),
            }),
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
        decide(models, choice, false).err().map(|error| error.code)
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
    #[test]
    fn common_decision_matches_the_fixture_consumed_by_both_adapters() {
        let mut models = models();
        models.recommendation = Some(key("model"));
        models.options = ModelOptions {
            temperature: Some(0.2),
            top_p: Some(0.8),
            max_tokens: Some(50),
        };
        models.policy.reasoning_enabled = vec![key("model")];
        let connection = ModelConnection {
            provider: "openai".into(),
            api_root: "https://source.invalid/v1".into(),
            credential_binding: "source-account".into(),
        };
        let public = decide(&models, None, true).unwrap();
        let public_json = serde_json::to_string(&public).unwrap();
        assert!(!public_json.contains("api_root") && !public_json.contains("credential_binding"));
        let admitted = InferenceAdmission {
            selection: public,
            connection,
        };
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../../libs/fred-sdk/tests/fixtures/inference_admission.json"
        ))
        .unwrap();
        assert_eq!(serde_json::to_value(&admitted).unwrap(), fixture);
        // A retained decision is stable; a new admission observes revocation.
        models.offers[0].permitted = false;
        models.offers[0].candidate = false;
        assert_eq!(
            error(&models, None),
            Some(ModelPreparationErrorCode::OfferForbidden)
        );
        assert_eq!(serde_json::to_value(&admitted).unwrap(), fixture);
    }

    #[test]
    fn reasoning_requires_request_permission_and_known_capability() {
        for requested in [false, true] {
            for enabled in [false, true] {
                for capable in [None, Some(false), Some(true)] {
                    let mut models = models();
                    models.policy.default = Some(key("model"));
                    if enabled {
                        models.policy.reasoning_enabled.push(key("model"));
                    }
                    models.offers[0].metadata.as_mut().unwrap().reasoning = capable;
                    let decision = decide(&models, None, requested).unwrap();
                    assert_eq!(
                        decision.options.reasoning_effort.is_some(),
                        requested && enabled && capable == Some(true)
                    );
                    assert_eq!(decision.options.max_tokens, Some(100));
                }
            }
        }
    }

    #[test]
    fn withdrawal_never_changes_source_or_provisioning() {
        let mut models = models();
        models.policy.default = Some(key("model"));
        models.offers[0].candidate = false;
        models.offers[0].diagnostics = vec![ModelDiagnostic::Withdrawn];
        assert_eq!(
            decide(&models, None, false).unwrap().source,
            ModelSelectionSource::WithdrawalFallback
        );
        models.offers[1].key.source_id = "another-account".into();
        models.policy.fallback = Some(models.offers[1].key.clone());
        assert_eq!(
            error(&models, None),
            Some(ModelPreparationErrorCode::FallbackUnavailable)
        );
    }
}
