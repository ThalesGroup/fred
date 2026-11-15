// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space-local restrictions over the existing organization catalogue. No grants.
use std::collections::BTreeSet;

use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use sqlx::PgConnection;
use utoipa::ToSchema;
use uuid::Uuid;

use super::{
    instance::{self, ModelOfferKey, RuntimeModels},
    policy,
};
use crate::{
    api::AppState,
    authorization,
    domain::{Permission, Space, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
    spaces,
};

#[derive(Clone, Default, Serialize, ToSchema)]
pub struct SpaceModelPolicy {
    pub revision: i64,
    #[schema(required = true)]
    pub default: Option<ModelOfferKey>,
    pub disabled: Vec<ModelOfferKey>,
    /// Preference only; organization permission and reported aptitude still apply.
    pub reasoning_default_on: Vec<ModelOfferKey>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReplaceSpaceModelPolicy {
    pub expected_revision: i64,
    #[serde(deserialize_with = "Option::deserialize")]
    #[schema(required = true)]
    pub default: Option<ModelOfferKey>,
    #[schema(max_items = 4096)]
    pub disabled: Vec<ModelOfferKey>,
    #[schema(max_items = 4096)]
    pub reasoning_default_on: Vec<ModelOfferKey>,
}

#[derive(Serialize, ToSchema)]
pub struct SpaceModels {
    pub policy: SpaceModelPolicy,
    /// Public catalogue projection: no connection, credential or ancestor role.
    pub models: RuntimeModels,
    pub parent_permitted: Vec<ModelOfferKey>,
    #[schema(required = true)]
    pub inherited_default: Option<ModelOfferKey>,
}

pub(crate) async fn read(conn: &mut PgConnection, id: Uuid) -> AppResult<SpaceModelPolicy> {
    let row: Option<(i64, Option<String>, Option<String>)> = sqlx::query_as(
        "select revision, default_source_id, default_upstream_model_id from space_model_policy where space_id=$1")
        .bind(id).fetch_optional(&mut *conn).await?;
    let Some((revision, source, model)) = row else {
        return Ok(SpaceModelPolicy::default());
    };
    let rows: Vec<(String, String, bool, bool)> = sqlx::query_as(
        "select source_id, upstream_model_id, disabled, reasoning_default_on from space_model_setting where space_id=$1 order by source_id, upstream_model_id")
        .bind(id).fetch_all(conn).await?;
    let mut result = SpaceModelPolicy {
        revision,
        default: source
            .zip(model)
            .map(|(source_id, upstream_model_id)| ModelOfferKey {
                source_id,
                upstream_model_id,
            }),
        ..Default::default()
    };
    for (source_id, upstream_model_id, disabled, reasoning) in rows {
        let key = ModelOfferKey {
            source_id,
            upstream_model_id,
        };
        if disabled {
            result.disabled.push(key.clone());
        }
        if reasoning {
            result.reasoning_default_on.push(key);
        }
    }
    Ok(result)
}

/// At most the team/project path, within the caller's snapshot. A local policy
/// can only remove organization permissions; defaults never authorize a model.
pub(crate) async fn apply(
    conn: &mut PgConnection,
    space: &Space,
    models: &mut RuntimeModels,
) -> AppResult<()> {
    for id in &space.path {
        let local = read(conn, *id).await?;
        apply_policy(models, local);
    }
    Ok(())
}

pub(super) fn apply_policy(models: &mut RuntimeModels, local: SpaceModelPolicy) {
    for key in local
        .default
        .iter()
        .chain(&local.disabled)
        .chain(&local.reasoning_default_on)
    {
        if !models.offers.iter().any(|offer| &offer.key == key) {
            models.offers.push(instance::RuntimeModelOffer {
                key: key.clone(),
                permitted: false,
                candidate: false,
                selectable: false,
                diagnostics: vec![instance::ModelDiagnostic::NotPermitted],
                metadata: None,
                observation: None,
            });
        }
    }
    if let Some(default) = local.default {
        models.default = Some(default);
    }
    if local.revision > 0 {
        models.reasoning_default_on = local.reasoning_default_on;
    }
    for offer in &mut models.offers {
        if local.disabled.contains(&offer.key) {
            offer.permitted = false;
            offer.candidate = false;
            offer.selectable = false;
            offer
                .diagnostics
                .push(instance::ModelDiagnostic::NotPermitted);
        }
    }
}

// Governing a policy is not content Read. Conversely, an agent editor must be
// able to inspect choices without receiving Manage. Both require a direct role.
fn require_model_read(facts: &authorization::SpaceFacts) -> AppResult<()> {
    authorization::decide(facts, Permission::Read.into()).or_else(|error| {
        if matches!(error, AppError::Forbidden) {
            authorization::decide(facts, Permission::Manage.into())
        } else {
            Err(error)
        }
    })
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new().routes(utoipa_axum::routes!(
        space_models,
        replace_space_model_policy
    ))
}

#[utoipa::path(get, path="/spaces/{space_id}/models", params(("space_id"=Uuid, Path)), responses((status=200, body=SpaceModels), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody), (status=404, body=crate::error::ErrorBody)))]
async fn space_models(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<SpaceModels>> {
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let facts = authorization::load_facts(&mut *tx, &user.uid, id).await?;
    require_model_read(&facts)?;
    let space: Space = facts.space.into();
    let mut parent = space.clone();
    parent.path.pop();
    let mut models = instance::resolve_for_space(&mut tx, &parent, &serde_json::json!({})).await?;
    let parent_permitted = models
        .offers
        .iter()
        .filter(|offer| offer.permitted)
        .map(|offer| offer.key.clone())
        .collect();
    let inherited_default = models.default.clone();
    let policy = read(&mut tx, id).await?;
    apply_policy(&mut models, policy.clone());
    let result = SpaceModels {
        policy,
        models,
        parent_permitted,
        inherited_default,
    };
    tx.commit().await?;
    require_model_read(&authorization::load_facts(&s.pool, &user.uid, id).await?)?;
    Ok(Json(result))
}

#[utoipa::path(put, path="/spaces/{space_id}/model-policy", params(("space_id"=Uuid, Path)), request_body=ReplaceSpaceModelPolicy, responses((status=204), (status=401, body=crate::error::ErrorBody), (status=403, body=crate::error::ErrorBody), (status=404, body=crate::error::ErrorBody), (status=409, body=crate::error::ErrorBody), (status=422, body=crate::error::ErrorBody)))]
async fn replace_space_model_policy(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(body): ApiJson<ReplaceSpaceModelPolicy>,
) -> AppResult<StatusCode> {
    let disabled: BTreeSet<_> = body.disabled.iter().cloned().collect();
    let reasoning: BTreeSet<_> = body.reasoning_default_on.iter().cloned().collect();
    if body.expected_revision < 0
        || disabled.len() != body.disabled.len()
        || reasoning.len() != body.reasoning_default_on.len()
        || disabled.len() > 4096
        || reasoning.len() > 4096
        || !disabled.is_disjoint(&reasoning)
    {
        return Err(AppError::Unprocessable(
            "Invalid local model policy.".into(),
        ));
    }
    let (mut tx, space) =
        spaces::governance_mutation(&s.pool, &user.uid, id, Permission::Manage).await?;
    if !matches!(space.kind, SpaceKind::Team | SpaceKind::Project) {
        return Err(AppError::Unprocessable(
            "Local model policy requires a team or project.".into(),
        ));
    }
    let current = read(&mut tx, id).await?;
    if current.revision != body.expected_revision {
        return Err(AppError::Conflict(
            "Model policy changed; reload before saving.".into(),
        ));
    }
    let mut parent = space.clone();
    parent.path.pop();
    let models = instance::resolve_for_space(&mut tx, &parent, &serde_json::json!({})).await?;
    let retained: BTreeSet<_> = current
        .disabled
        .iter()
        .chain(&current.reasoning_default_on)
        .chain(current.default.iter())
        .cloned()
        .collect();
    let requested: BTreeSet<_> = disabled
        .iter()
        .chain(&reasoning)
        .chain(body.default.iter())
        .cloned()
        .collect();
    for key in &requested {
        if !retained.contains(key)
            && !models
                .offers
                .iter()
                .any(|offer| &offer.key == key && offer.permitted)
        {
            return Err(AppError::Unprocessable(
                "New local choices require a model permitted by the organization and parent space."
                    .into(),
            ));
        }
    }
    let effective_default = body.default.as_ref().or(models.default.as_ref());
    if effective_default.is_some_and(|key| disabled.contains(key)) {
        return Err(AppError::Unprocessable(
            "Choose another default before disabling this model.".into(),
        ));
    }
    let mut newly_selected: BTreeSet<_> = reasoning
        .difference(&current.reasoning_default_on.iter().cloned().collect())
        .cloned()
        .collect();
    if body.default != current.default
        && let Some(key) = &body.default
    {
        newly_selected.insert(key.clone());
    }
    for key in &newly_selected {
        if !models
            .offers
            .iter()
            .any(|offer| &offer.key == key && offer.selectable)
        {
            return Err(AppError::Unprocessable(
                "The selected model is not permitted by the parent policy.".into(),
            ));
        }
        if reasoning.contains(key)
            && (!models.policy.reasoning_enabled.contains(key)
                || !models.offers.iter().any(|offer| {
                    &offer.key == key
                        && offer
                            .metadata
                            .as_ref()
                            .is_some_and(|m| m.reasoning == Some(true))
                }))
        {
            return Err(AppError::Unprocessable(
                "Reasoning is not enabled for this model by the organization.".into(),
            ));
        }
    }
    let uses: Vec<_> = newly_selected
        .iter()
        .map(|key| (policy::Use::Chat, key))
        .collect();
    policy::require_selectable(&mut tx, space.organization, &newly_selected, &uses).await?;
    sqlx::query("insert into space_model_policy(space_id,revision,default_source_id,default_upstream_model_id,updated_by) values($1,1,$2,$3,$4) on conflict(space_id) do update set revision=space_model_policy.revision+1,default_source_id=excluded.default_source_id,default_upstream_model_id=excluded.default_upstream_model_id,updated_by=excluded.updated_by,updated_at=clock_timestamp()")
        .bind(id).bind(body.default.as_ref().map(|k| &k.source_id)).bind(body.default.as_ref().map(|k| &k.upstream_model_id)).bind(&user.uid).execute(&mut *tx).await?;
    sqlx::query("delete from space_model_setting where space_id=$1")
        .bind(id)
        .execute(&mut *tx)
        .await?;
    // Bounded bulk writes, independent of the number of models in the policy.
    for (keys, disabled) in [(&body.disabled, true), (&body.reasoning_default_on, false)] {
        sqlx::query("insert into space_model_setting(space_id,source_id,upstream_model_id,disabled,reasoning_default_on) select $1,x.source_id,x.upstream_model_id,$2,not $2 from jsonb_to_recordset($3) as x(source_id text,upstream_model_id text)")
            .bind(id).bind(disabled).bind(sqlx::types::Json(keys)).execute(&mut *tx).await?;
    }
    tx.commit().await?;
    tracing::info!(target:"fred.security.audit", audit_event="model.local_policy_changed", actor_uid=%user.uid, space_id=%id);
    Ok(StatusCode::NO_CONTENT)
}
