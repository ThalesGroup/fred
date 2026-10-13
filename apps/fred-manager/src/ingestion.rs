//! Temporal client submitting ingestion work to the Python workers.
//! The payload carries placement only; workers write every artefact under `storage_prefix`
//! and tag every chunk with `space_id`, `document_id` and `folder_path`.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use temporalio_client::{
    Client, ClientOptions, ConnectionOptions, Url, WorkflowStartOptions, errors::WorkflowStartError,
};
use temporalio_common::{HasWorkflowDefinition, WorkflowDefinition};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IngestDocument {
    pub document_id: Uuid,
    pub space_id: Uuid,
    pub folder_path: String,
    pub storage_prefix: String,
    pub source_key: String,
    pub mime: String,
    pub profile: String,
    pub requested_by: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeleteDocument {
    pub document_id: Uuid,
    pub space_id: Uuid,
    pub storage_prefix: String,
}

macro_rules! workflow {
    ($ty:ident, $input:ty, $name:literal) => {
        pub struct $ty;
        impl WorkflowDefinition for $ty {
            type Input = $input;
            type Output = serde_json::Value;
            fn name(&self) -> &str {
                $name
            }
        }
        impl HasWorkflowDefinition for $ty {
            type Run = Self;
        }
    };
}

workflow!(IngestDocumentWorkflow, IngestDocument, "IngestDocument");
workflow!(DeleteDocumentWorkflow, DeleteDocument, "DeleteDocument");

pub enum Submitted {
    Started,
    AlreadyRunning,
}

#[derive(Clone)]
pub struct Ingestion {
    client: Client,
    task_queue: String,
}

impl Ingestion {
    pub async fn connect(url: &str, namespace: &str, task_queue: &str) -> Result<Self> {
        let target = Url::parse(url).context("invalid TEMPORAL_URL")?;
        let client = Client::connect(
            ConnectionOptions::new(target)
                .identity("fred-manager")
                .build(),
            ClientOptions::new(namespace).build(),
        )
        .await
        .context("temporal unreachable")?;
        Ok(Self {
            client,
            task_queue: task_queue.to_string(),
        })
    }

    /// One workflow id per document and operation: a second submission while the first
    /// runs is reported, not duplicated.
    pub async fn ingest(&self, input: IngestDocument) -> Result<Submitted> {
        let id = format!("ingest-{}", input.document_id);
        let r = self
            .client
            .start_workflow(IngestDocumentWorkflow, input, self.options(id))
            .await;
        Self::submitted(r.map(|_| ()))
    }

    pub async fn delete(&self, input: DeleteDocument) -> Result<Submitted> {
        let id = format!("delete-{}", input.document_id);
        let r = self
            .client
            .start_workflow(DeleteDocumentWorkflow, input, self.options(id))
            .await;
        Self::submitted(r.map(|_| ()))
    }

    fn options(&self, workflow_id: String) -> WorkflowStartOptions {
        WorkflowStartOptions::new(self.task_queue.clone(), workflow_id).build()
    }

    fn submitted(r: Result<(), WorkflowStartError>) -> Result<Submitted> {
        match r {
            Ok(()) => Ok(Submitted::Started),
            Err(WorkflowStartError::AlreadyStarted { .. }) => Ok(Submitted::AlreadyRunning),
            Err(e) => Err(e.into()),
        }
    }
}
