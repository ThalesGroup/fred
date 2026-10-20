// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Wire contracts shared with the Knowledge Flow worker. Export with processing-schema.
use crate::error::{AppError, AppResult};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

macro_rules! text_enum {
    ($name:ident { $($variant:ident),+ }) => {
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, sqlx::Type, utoipa::ToSchema)]
        #[serde(rename_all="snake_case")]
        #[sqlx(type_name="text", rename_all="snake_case")]
        pub enum $name { $($variant),+ }
    };
}
text_enum!(Profile { Fast, Medium, Rich });
text_enum!(ProcessingStatus {
    Pending,
    Running,
    Succeeded,
    Failed
});
text_enum!(Stage {
    Queued,
    Preparation,
    Extraction,
    Indexing,
    Done
});
impl ProcessingStatus {
    pub fn terminal(self) -> bool {
        matches!(self, Self::Succeeded | Self::Failed)
    }
}
impl Stage {
    pub fn ordinal(self) -> u8 {
        match self {
            Self::Queued => 0,
            Self::Preparation => 1,
            Self::Extraction => 2,
            Self::Indexing => 3,
            Self::Done => 4,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct Summary {
    pub id: Uuid,
    pub document_id: Uuid,
    pub profile: Profile,
    pub status: ProcessingStatus,
    pub stage: Stage,
    pub revision: i64,
    pub error_code: Option<String>,
    pub created_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub retry_of: Option<Uuid>,
    pub chunks: i64,
    pub vectors: i64,
    pub rows: Option<i64>,
}

#[derive(Clone, Debug, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Work {
    #[schema(minimum = 1, maximum = 1)]
    pub contract_version: u8,
    pub installation_id: Uuid,
    pub processing_id: Uuid,
    pub document_id: Uuid,
    #[schema(pattern = "^[0-9a-f]{64}$")]
    pub original_sha256: String,
    pub profile: Profile,
}
impl Work {
    pub fn validate(&self) -> AppResult<()> {
        if self.contract_version != 1 || !digest(&self.original_sha256) {
            return Err(invalid());
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Start {
    pub profile: Profile,
    pub retry_of: Option<Uuid>,
}

#[derive(Clone, Debug, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Claim {
    pub work: Work,
    pub stage: Stage,
    pub execution_id: Uuid,
    pub activity_id: Uuid,
    pub attempt: u32,
}

#[derive(Clone, Debug, Serialize, Deserialize, utoipa::ToSchema)]
pub struct Descriptor {
    pub work: Work,
    pub organization_id: Uuid,
    pub space_id: Uuid,
    pub folder_id: Uuid,
    pub folder_path: String,
    pub name: String,
    pub mime: String,
    pub size: i64,
    pub actor: String,
    pub stage: Stage,
    pub generation: Uuid,
    pub expires_at: DateTime<Utc>,
    pub output_prefix: String,
    pub max_output_bytes: i64,
    pub max_artifacts: u32,
    pub max_chunks: u32,
    pub file: serde_json::Value,
    pub profile_settings: serde_json::Value,
    pub predecessor: Option<Manifest>,
    pub committed: Option<Manifest>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Artifact {
    pub path: String,
    pub size: i64,
    pub sha256: String,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub generation: Uuid,
    pub artifacts: Vec<Artifact>,
    pub chunks: i64,
    pub vectors: i64,
    pub vector_ordinals: Vec<u32>,
    pub rows: Option<i64>,
}
impl Manifest {
    pub fn validate(&self, max_bytes: i64, max_artifacts: u32, max_chunks: u32) -> AppResult<()> {
        let mut paths = std::collections::HashSet::new();
        let mut bytes = 0_i64;
        if self.artifacts.is_empty()
            || self.artifacts.len() > max_artifacts as usize
            || self.chunks < 0
            || self.chunks > max_chunks as i64
            || self.vectors < 0
            || self.vectors > self.chunks
            || self.rows.is_some_and(|v| v < 0)
        {
            return Err(invalid());
        }
        if self.vector_ordinals.len() != self.vectors as usize
            || self.vector_ordinals.windows(2).any(|w| w[0] >= w[1])
            || self.vector_ordinals.iter().any(|v| *v >= max_chunks)
        {
            return Err(invalid());
        }
        for a in &self.artifacts {
            if !artifact_path(&a.path) || a.size < 0 || !digest(&a.sha256) || !paths.insert(&a.path)
            {
                return Err(invalid());
            }
            bytes = bytes.checked_add(a.size).ok_or_else(invalid)?;
        }
        if bytes > max_bytes {
            return Err(invalid());
        }
        Ok(())
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Commit {
    pub work: Work,
    pub stage: Stage,
    pub manifest: Manifest,
}
#[derive(Clone, Debug, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Failure {
    pub work: Work,
    pub stage: Stage,
    pub generation: Option<Uuid>,
    pub code: FailureCode,
}
text_enum!(FailureCode {
    UnsupportedInput,
    AccessChanged,
    IntegrityFailure,
    ExtractionFailed,
    PreviewFailed,
    IndexingFailed,
    CapacityExceeded,
    WorkerFailed,
    DeadlineExceeded,
    DeliveryUnknown
});

pub fn artifact_path(path: &str) -> bool {
    !path.is_empty()
        && path.len() <= 255
        && path
            .split('/')
            .all(|s| !s.is_empty() && s != "." && s != "..")
        && path
            .chars()
            .all(|c| c.is_alphanumeric() || "-_. /".contains(c))
}
pub fn digest(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
pub fn invalid() -> AppError {
    AppError::problem(
        axum::http::StatusCode::UNPROCESSABLE_ENTITY,
        "invalid_processing_contract",
        "Invalid document processing contract",
    )
}

/// Internal worker persistence callbacks; Temporal retains the Python scheduler schema.
pub fn schema() -> serde_json::Value {
    use utoipa::OpenApi;
    #[derive(OpenApi)]
    #[openapi(components(schemas(Work, Claim, Descriptor, Commit, Failure, Summary, Start)))]
    struct Contracts;
    let mut schema = serde_json::json!({"$schema":"https://json-schema.org/draft-07/schema#","$defs":Contracts::openapi().components.unwrap().schemas,"$ref":"#/$defs/Work"});
    fn refs(v: &mut serde_json::Value) {
        match v {
            serde_json::Value::Object(m) => {
                if let Some(serde_json::Value::String(r)) = m.get_mut("$ref") {
                    *r = r.replace("#/components/schemas/", "#/$defs/");
                }
                for v in m.values_mut() {
                    refs(v);
                }
            }
            serde_json::Value::Array(a) => a.iter_mut().for_each(refs),
            _ => (),
        }
    }
    refs(&mut schema);
    schema
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn worker_contract_rejects_versions_credentials_and_unsafe_artifacts() {
        let mut work = Work {
            contract_version: 1,
            installation_id: Uuid::new_v4(),
            processing_id: Uuid::new_v4(),
            document_id: Uuid::new_v4(),
            original_sha256: "a".repeat(64),
            profile: Profile::Fast,
        };
        assert!(work.validate().is_ok());
        work.contract_version = 2;
        assert!(work.validate().is_err());
        let mut json = serde_json::to_value(work).unwrap();
        json["token"] = "secret".into();
        assert!(serde_json::from_value::<Work>(json).is_err());
        for path in ["../x", "/x", "a//x", "a/../x", "https://host/file", "a\\x"] {
            assert!(!artifact_path(path));
        }
    }
}
