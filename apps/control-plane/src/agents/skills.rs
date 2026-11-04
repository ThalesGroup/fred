// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Instructions advertised by a pod. Governance uses the same offers as tools;
//! instruction bytes stay in the runtime and are never accepted from the browser.

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sqlx::PgConnection;
use utoipa::ToSchema;

use super::{catalog, enablement};
use crate::{domain::Space, error::AppResult};

#[derive(Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SkillSummary {
    pub name: String,
    pub description: String,
    pub argument_hint: Option<String>,
    pub builtin: bool,
    pub user_invocable: bool,
    pub disable_model_invocation: bool,
}

#[derive(Clone, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum SkillAvailability {
    Available,
    Disabled,
    Unavailable,
}

#[derive(Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SkillCatalog {
    pub availability: SkillAvailability,
    pub supported: bool,
    pub revision: String,
    pub skills: Vec<SkillSummary>,
    pub policy_supported: bool,
}

pub fn offer_id(name: &str) -> String {
    format!("skill:{name}")
}

impl SkillCatalog {
    pub(super) fn validate(&self) -> Result<()> {
        ensure!(self.policy_supported, "unsupported skill policy contract");
        ensure!(
            matches!(self.availability, SkillAvailability::Available) || self.skills.is_empty(),
            "unavailable catalog contains skills"
        );
        ensure!(
            self.supported || self.skills.is_empty(),
            "unsupported catalog contains skills"
        );
        ensure!(self.skills.len() <= 64, "skill count exceeds bound");
        ensure!(
            self.revision.len() == 64 && self.revision.bytes().all(|c| c.is_ascii_hexdigit()),
            "invalid skill revision"
        );
        let mut names = std::collections::HashSet::new();
        for skill in &self.skills {
            ensure!(
                (1..=64).contains(&skill.name.len())
                    && skill.name.split('-').all(|p| !p.is_empty()
                        && p.bytes()
                            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit())),
                "invalid skill name"
            );
            ensure!(names.insert(&skill.name), "duplicate skill");
            ensure!(
                !skill.description.trim().is_empty() && skill.description.len() <= 16384,
                "invalid skill description"
            );
            ensure!(
                skill
                    .argument_hint
                    .as_ref()
                    .is_none_or(|v| !v.is_empty() && v.chars().count() <= 256),
                "invalid skill hint"
            );
        }
        Ok(())
    }
}

/// Read with the admission's existing snapshot. No discovery or execution occurs.
pub async fn resolve(
    conn: &mut PgConnection,
    space: &Space,
    runtime_id: &str,
    policy: &enablement::Policy,
) -> AppResult<Option<SkillCatalog>> {
    let Some(observation) = catalog::observation(&mut *conn, runtime_id).await? else {
        return Ok(None);
    };
    let availability = match observation.skills_availability.as_deref() {
        Some("available") => SkillAvailability::Available,
        Some("disabled") => SkillAvailability::Disabled,
        Some("unavailable") => SkillAvailability::Unavailable,
        _ => return Ok(None),
    };
    let revision = observation.skills_revision.unwrap_or_default();
    if !matches!(availability, SkillAvailability::Available) {
        return Ok(Some(SkillCatalog {
            availability,
            supported: true,
            policy_supported: true,
            revision,
            skills: vec![],
        }));
    }
    let offers = catalog::capabilities(&mut *conn, runtime_id).await?;
    let skills = offers
        .into_iter()
        .filter(|offer| {
            offer.advertised
                && offer.capability_id.starts_with("skill:")
                && enablement::usable(policy, space, runtime_id, &offer.capability_id)
        })
        .map(|offer| {
            serde_json::from_value::<super::inventory::PodCapabilityDescriptor>(offer.descriptor.0)
                .and_then(|descriptor| {
                    descriptor
                        .skill
                        .ok_or_else(|| serde::de::Error::custom("missing skill description"))
                })
        })
        .collect::<Result<Vec<_>, _>>()
        .context("invalid stored skill description")?;
    Ok(Some(SkillCatalog {
        availability: SkillAvailability::Available,
        supported: true,
        policy_supported: true,
        revision,
        skills,
    }))
}
