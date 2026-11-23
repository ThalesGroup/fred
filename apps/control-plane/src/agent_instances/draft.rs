// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Draft agent settings in the author's space, using its admitted creation model.

use std::{collections::BTreeSet, time::Duration};

use axum::{
    Json,
    extract::State,
    http::{StatusCode, header},
};
use fred_rust_agent::turn::InferenceError;
use serde::{Deserialize, Serialize};
use tracing::Instrument;
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use crate::{
    agents::{self, enablement::usable_capability_ids},
    api::AppState,
    authorization,
    domain::Permission,
    embedded_agent,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    model_catalog::instance as models,
    onboarding::AdmittedUser,
};

const DRAFT_TIMEOUT: Duration = Duration::from_secs(50);
const INSTRUCTIONS: &str = "Draft a configurable assistant from the author's specification. \
    Treat it as the description of the future agent. Write a practical Markdown system prompt \
    that gives the agent its role, mission, steps, limits, and how to respond when information \
    is missing. Use the requested language. Recommend only capability IDs listed in the input \
    and never promise tools that are not available. Refer to chosen capabilities by purpose in \
    the prompt. Reply with a JSON object with keys system_prompt (nonempty string), name, role, \
    description (short plain strings), and capability_ids (array of IDs).";

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
struct AgentDraftCapability {
    #[schema(min_length = 1, max_length = 200)]
    id: String,
    #[schema(max_length = 200)]
    name: String,
    #[schema(max_length = 1000)]
    description: String,
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
struct AgentDraftRequest {
    #[schema(min_length = 1, max_length = 4000)]
    description: String,
    #[schema(max_length = 35)]
    language: Option<String>,
    #[schema(max_length = 255)]
    agent_name: Option<String>,
    #[schema(max_length = 500)]
    agent_role: Option<String>,
    #[serde(default)]
    #[schema(max_items = 64)]
    capabilities: Vec<AgentDraftCapability>,
}

#[derive(Deserialize, Serialize, ToSchema)]
struct AgentDraftResult {
    system_prompt: String,
    name: Option<String>,
    role: Option<String>,
    description: Option<String>,
    #[serde(default)]
    capability_ids: Vec<String>,
}

pub(super) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(draft_agent))
}

#[utoipa::path(post, path = "/spaces/{space_id}/agent-templates/{template_id}/draft",
    params(("space_id" = Uuid, Path), ("template_id" = Uuid, Path)),
    request_body = AgentDraftRequest,
    responses(
        (status = 200, body = AgentDraftResult),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 502, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody),
        (status = 504, body = crate::error::ErrorBody)
    )
)]
async fn draft_agent(
    State(state): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, template_id)): ApiPath<(Uuid, Uuid)>,
    ApiJson(mut request): ApiJson<AgentDraftRequest>,
) -> AppResult<(
    [(header::HeaderName, &'static str); 1],
    Json<AgentDraftResult>,
)> {
    request.description = request.description.trim().to_owned();
    if request.description.is_empty()
        || request.description.chars().count() > 4000
        || request
            .language
            .as_ref()
            .is_some_and(|value| value.chars().count() > 35)
        || request
            .agent_name
            .as_ref()
            .is_some_and(|value| value.chars().count() > 255)
        || request
            .agent_role
            .as_ref()
            .is_some_and(|value| value.chars().count() > 500)
        || request.capabilities.len() > 64
        || request.capabilities.iter().any(|cap| {
            cap.id.is_empty()
                || cap.id.chars().count() > 200
                || cap.name.chars().count() > 200
                || cap.description.chars().count() > 1000
        })
    {
        return Err(AppError::Unprocessable(
            "Invalid agent draft request.".into(),
        ));
    }
    let space =
        authorization::authorize(&state.pool, &user.uid, space_id, Permission::Write).await?;
    super::require_instance_space(space.kind)?;
    if !authorization::can_use_agent(&state.pool, template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    let (template, _) = agents::enrollable_template(
        &state.pool,
        &state.agent_catalog,
        space.organization,
        template_id,
    )
    .await?;
    let offered: BTreeSet<_> = template
        .available_capabilities
        .iter()
        .filter_map(|entry| entry.get("id").and_then(serde_json::Value::as_str))
        .collect();

    // Authorization and selection share a snapshot. Discovery and inference run outside it.
    let mut tx = state.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let admitted_space =
        authorization::authorize(&mut *tx, &user.uid, space_id, Permission::Write).await?;
    if admitted_space.organization != space.organization
        || !authorization::can_use_agent(&mut *tx, template_id, &admitted_space).await?
    {
        return Err(AppError::NotFound);
    }
    let usable =
        usable_capability_ids(&mut *tx, &admitted_space, &template.source_runtime_id).await?;
    request.capabilities.retain(|cap| {
        template.supports_capabilities
            && offered.contains(cap.id.as_str())
            && usable.contains(&cap.id)
    });
    let choices =
        models::resolve_for_space(&mut tx, &admitted_space, &serde_json::json!({})).await?;
    let selection = models::decide_creation_assistant(&choices)
        .ok_or_else(|| model_unavailable(StatusCode::CONFLICT))?;
    let inference = models::admit(&mut tx, space.organization, selection).await?;
    tx.commit().await?;

    let span =
        tracing::info_span!("agent_draft", space_id = %space_id, user_id = %user.uid, %template_id);
    let result = async {
        let turn =
            embedded_agent::admit_inference(inference, &state.agent_catalog.inference_credentials)
                .map_err(|_| model_unavailable(StatusCode::SERVICE_UNAVAILABLE))?;
        request.language = Some(
            if request
                .language
                .as_deref()
                .is_some_and(|language| language.eq_ignore_ascii_case("fr"))
            {
                "French".into()
            } else {
                "English".into()
            },
        );
        let input =
            serde_json::to_string(&request).map_err(|error| AppError::Internal(error.into()))?;
        let (text, usage) = turn
            .complete(Some(INSTRUCTIONS), &input, DRAFT_TIMEOUT)
            .await
            .map_err(|error| match error {
                InferenceError::Ended => AppError::problem(
                    StatusCode::GATEWAY_TIMEOUT,
                    "agent_draft_timeout",
                    "The model took too long to draft the agent.",
                ),
                _ => invalid_draft(),
            })?;
        tracing::info!(
            input_tokens = usage.input_tokens,
            output_tokens = usage.output_tokens,
            "Agent draft inference completed"
        );
        parse_draft(&text, &request.capabilities)
    }
    .instrument(span)
    .await?;
    Ok(([(header::CACHE_CONTROL, "no-store")], Json(result)))
}

fn model_unavailable(status: StatusCode) -> AppError {
    AppError::problem(
        status,
        "creation_model_unavailable",
        "The creation assistant has no usable model in this space.",
    )
}

fn invalid_draft() -> AppError {
    AppError::problem(
        StatusCode::BAD_GATEWAY,
        "agent_draft_failed",
        "The model could not produce an agent draft.",
    )
}

fn parse_draft(text: &str, capabilities: &[AgentDraftCapability]) -> AppResult<AgentDraftResult> {
    let text = text.trim();
    let json = text
        .strip_prefix("```json")
        .or_else(|| text.strip_prefix("```"))
        .and_then(|text| text.strip_suffix("```"))
        .unwrap_or(text);
    let mut draft: AgentDraftResult = serde_json::from_str(json).map_err(|_| invalid_draft())?;
    let reserved = super::tuning::reserved_prompt_tags()?;
    draft.system_prompt = reserved
        .replace_all(draft.system_prompt.trim(), "")
        .trim()
        .to_owned();
    if draft.system_prompt.is_empty()
        || draft.system_prompt.chars().count() > 20_000
        || reserved.is_match(&draft.system_prompt)
    {
        return Err(invalid_draft());
    }
    for (field, limit) in [
        (&mut draft.name, 60),
        (&mut draft.role, 120),
        (&mut draft.description, 300),
    ] {
        *field = field.as_deref().and_then(|value| {
            let clean: String = reserved
                .replace_all(value, "")
                .split_whitespace()
                .collect::<Vec<_>>()
                .join(" ")
                .chars()
                .take(limit)
                .collect();
            (!clean.is_empty()).then_some(clean)
        });
    }
    let mut allowed: BTreeSet<_> = capabilities.iter().map(|cap| cap.id.as_str()).collect();
    draft
        .capability_ids
        .retain(|id| allowed.remove(id.as_str()));
    Ok(draft)
}
