// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space-owned packages. Access and mutation use the shared space primitives.

use crate::{
    authorization,
    domain::Space,
    error::{AppError, AppResult},
};
use serde::{Deserialize, Serialize};
use sqlx::{PgConnection, types::Json};
use std::collections::BTreeMap;
use utoipa::ToSchema;
use uuid::Uuid;

mod defaults;
pub mod http;
pub(crate) mod package;
use package::Files;

#[derive(Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PackageSummary {
    pub name: String,
    pub description: String,
    pub argument_hint: Option<String>,
    pub builtin: bool,
    pub user_invocable: bool,
    pub disable_model_invocation: bool,
}

#[derive(Clone, Deserialize, Serialize, ToSchema)]
pub struct SkillSummary {
    pub skill_id: Uuid,
    pub space_id: Uuid,
    pub space_name: String,
    #[serde(flatten)]
    pub package: PackageSummary,
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

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct SpaceSkill {
    pub skill_id: Uuid,
    pub space_id: Uuid,
    pub name: String,
    pub revision: String,
    #[sqlx(json)]
    pub summary: PackageSummary,
}

#[derive(Serialize, ToSchema)]
pub struct SkillDetail {
    pub skill: SkillSummary,
    pub revision: String,
    pub content: String,
}

#[derive(Serialize, ToSchema)]
pub struct SkillSnapshot {
    pub catalog: SkillCatalog,
    pub files: BTreeMap<String, String>,
}

/// Current space and readable parents, from the shared space path in this admission.
/// Identity and owning space distinguish homonyms without a precedence rule.
pub async fn resolve(
    conn: &mut PgConnection,
    subject: &str,
    space: &Space,
    content: bool,
) -> AppResult<SkillSnapshot> {
    let scope = authorization::readable_path(&mut *conn, subject, &space.path, None).await?;
    let rows: Vec<(Uuid, Uuid, String, Json<PackageSummary>, String)> = sqlx::query_as(
        "select k.skill_id, k.space_id, s.name, k.summary, k.revision from skill k join space s on s.id=k.space_id where k.space_id=any($1) order by k.name, k.space_id, k.skill_id limit 65",
    )
    .bind(&scope)
    .fetch_all(&mut *conn)
    .await?;
    if rows.len() > package::MAX_SKILLS {
        return Err(AppError::Conflict("Skill scope exceeds 64 packages".into()));
    }
    let mut summaries = Vec::new();
    let mut versions = Files::new();
    for (skill_id, space_id, space_name, summary, revision) in rows {
        versions.insert(format!("{space_id}/{skill_id}"), revision);
        summaries.push(SkillSummary {
            skill_id,
            space_id,
            space_name,
            package: summary.0,
        });
    }
    let mut files = Files::new();
    if content {
        let packages: Vec<(Uuid, Json<Files>)> = sqlx::query_as(
            "select skill_id, files from skill where space_id=any($1) order by skill_id",
        )
        .bind(&scope)
        .fetch_all(&mut *conn)
        .await?;
        for (skill_id, package) in packages {
            for (path, text) in package.0 {
                files.insert(format!("/skills/{skill_id}/{path}"), text);
            }
        }
        if files.values().map(String::len).sum::<usize>() > package::MAX_BYTES {
            return Err(AppError::Conflict("Skill scope exceeds 4 MiB".into()));
        }
    }
    Ok(SkillSnapshot {
        catalog: SkillCatalog {
            availability: SkillAvailability::Available,
            supported: true,
            policy_supported: true,
            revision: package::revision(&versions),
            skills: summaries,
        },
        files,
    })
}

pub async fn list<'e>(ex: impl sqlx::PgExecutor<'e>, space: Uuid) -> AppResult<Vec<SpaceSkill>> {
    Ok(sqlx::query_as("select skill_id, space_id, name, summary, revision from skill where space_id=$1 order by name")
        .bind(space).fetch_all(ex).await?)
}

pub async fn save(
    conn: &mut PgConnection,
    space: Uuid,
    actor: &str,
    name: &str,
    files: &Files,
    expected: Option<&str>,
    builtin: bool,
) -> AppResult<()> {
    let summary = package::validate(name, files, builtin)?;
    let current: Option<String> =
        sqlx::query_scalar("select revision from skill where space_id=$1 and name=$2")
            .bind(space)
            .bind(name)
            .fetch_optional(&mut *conn)
            .await?;
    if current.as_deref() != expected {
        return Err(AppError::Conflict(
            "Skill changed; reload before replacing the package".into(),
        ));
    }
    let total: (i64, i64) = sqlx::query_as("select count(*), coalesce(sum(octet_length(files::text)),0)::bigint from skill where space_id=$1 and name<>$2")
        .bind(space).bind(name).fetch_one(&mut *conn).await?;
    if total.0 >= 64
        || total.1 as usize
            + serde_json::to_vec(files)
                .map_err(anyhow::Error::from)?
                .len()
            > package::MAX_BYTES
    {
        return Err(AppError::Unprocessable(
            "Space skill package limit exceeded".into(),
        ));
    }
    sqlx::query("insert into skill (skill_id, space_id, name, summary, files, revision, created_by, updated_by)
        values ($1,$2,$3,$4,$5,$6,$7,$7) on conflict (space_id,name) do update set summary=excluded.summary,
        files=excluded.files, revision=excluded.revision, updated_by=excluded.updated_by, updated_at=clock_timestamp()")
        .bind(Uuid::new_v4()).bind(space).bind(name).bind(Json(summary)).bind(Json(files))
        .bind(package::revision(files)).bind(actor).execute(conn).await?;
    Ok(())
}
