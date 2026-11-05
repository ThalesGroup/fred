// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Instructions advertised by a pod. Governance uses the same offers as tools;
//! instruction bytes stay in the runtime and are never accepted from the browser.

use std::collections::{BTreeMap, BTreeSet, HashSet};

use anyhow::{Context, Result, ensure};
use futures::{StreamExt, stream};
use serde::{Deserialize, Serialize};
use sqlx::PgConnection;
use utoipa::ToSchema;

use super::{catalog, enablement, inventory};
use crate::{api::AppState, domain::Space, error::AppResult};

#[derive(Clone, Deserialize, Eq, PartialEq, Serialize, ToSchema)]
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

#[derive(Serialize, ToSchema)]
pub struct PlatformSkillEntry {
    pub skill: SkillSummary,
    pub enabled: bool,
    pub runtime_ids: Vec<String>,
}

#[derive(Serialize, ToSchema)]
pub struct PlatformSkillInventory {
    pub skills: Vec<PlatformSkillEntry>,
    pub disabled_skill_names: Vec<String>,
    pub unavailable_runtime_ids: Vec<String>,
    pub unsupported_runtime_ids: Vec<String>,
    pub disabled_runtime_ids: Vec<String>,
    pub custom_runtime_ids: Vec<String>,
    pub conflicting_skill_names: Vec<String>,
}

/// Read live pod inventories through the existing Control Plane discovery path.
/// These are availability observations; PostgreSQL remains the policy authority.
pub async fn platform_inventory(state: &AppState) -> AppResult<PlatformSkillInventory> {
    let disabled_skill_names = crate::skill_policy::disabled(&state.pool).await?;
    let disabled: HashSet<_> = disabled_skill_names.iter().map(String::as_str).collect();
    let mut sources = state
        .agent_catalog
        .runtime_catalog_sources
        .iter()
        .filter(|source| source.enabled)
        .cloned()
        .collect::<Vec<_>>();
    sources.sort_by(|a, b| a.runtime_id.cmp(&b.runtime_id));
    let mut results = stream::iter(sources.into_iter().map(|source| async move {
        (
            source.runtime_id.clone(),
            inventory::fetch_raw(&source).await,
        )
    }))
    .buffered(8);
    let mut skills: BTreeMap<String, PlatformSkillEntry> = BTreeMap::new();
    let mut unavailable_runtime_ids = Vec::new();
    let mut unsupported_runtime_ids = Vec::new();
    let mut disabled_runtime_ids = Vec::new();
    let mut custom_runtime_ids = Vec::new();
    let mut conflicting_skill_names = BTreeSet::new();
    while let Some((runtime_id, result)) = results.next().await {
        let Ok(raw) = result else {
            unavailable_runtime_ids.push(runtime_id);
            continue;
        };
        if !raw.complete {
            unavailable_runtime_ids.push(runtime_id);
            continue;
        }
        let Some(catalog) = raw.skills.as_ref() else {
            unsupported_runtime_ids.push(runtime_id);
            continue;
        };
        if !catalog.policy_supported || !catalog.supported {
            unsupported_runtime_ids.push(runtime_id);
            continue;
        }
        let availability = catalog.availability.clone();
        let packaged = catalog
            .skills
            .iter()
            .filter(|skill| skill.builtin)
            .cloned()
            .collect::<Vec<_>>();
        if raw.snapshot(&runtime_id).is_err() {
            unavailable_runtime_ids.push(runtime_id);
            continue;
        }
        if matches!(availability, SkillAvailability::Unavailable) {
            unavailable_runtime_ids.push(runtime_id);
            continue;
        }
        if matches!(availability, SkillAvailability::Disabled) {
            disabled_runtime_ids.push(runtime_id);
            continue;
        }
        if packaged.is_empty() {
            custom_runtime_ids.push(runtime_id);
            continue;
        }
        for skill in packaged {
            let name = skill.name.clone();
            let entry = skills
                .entry(name.clone())
                .or_insert_with(|| PlatformSkillEntry {
                    enabled: !disabled.contains(name.as_str()),
                    skill: skill.clone(),
                    runtime_ids: Vec::new(),
                });
            if entry.skill != skill {
                conflicting_skill_names.insert(name);
            }
            entry.runtime_ids.push(runtime_id.clone());
        }
    }
    for entry in skills.values_mut() {
        entry.runtime_ids.sort();
    }
    unavailable_runtime_ids.sort();
    unsupported_runtime_ids.sort();
    disabled_runtime_ids.sort();
    custom_runtime_ids.sort();
    Ok(PlatformSkillInventory {
        skills: skills.into_values().collect(),
        disabled_skill_names,
        unavailable_runtime_ids,
        unsupported_runtime_ids,
        disabled_runtime_ids,
        custom_runtime_ids,
        conflicting_skill_names: conflicting_skill_names.into_iter().collect(),
    })
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
    disabled_platform_skills: &[String],
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
        .filter(|result| match result {
            Ok(skill) => !skill.builtin || !disabled_platform_skills.contains(&skill.name),
            Err(_) => true,
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
