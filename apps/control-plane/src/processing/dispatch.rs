// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! SQL is the delivery outbox. No Temporal RPC runs in an admission transaction.
use super::{config::ProcessingConfig, store::Row};
use anyhow::{Context, Result};
use chrono::Utc;
use sqlx::PgPool;
use std::time::Duration;
use temporalio_client::{
    Client, ClientOptions, ConnectionOptions, Url,
    grpc::WorkflowService,
    tonic::{Code, Request},
};
use temporalio_common::protos::temporal::api::{
    common::v1::{Payload, Payloads, WorkflowExecution, WorkflowType},
    taskqueue::v1::TaskQueue,
    workflowservice::v1::{
        DescribeNamespaceRequest, DescribeWorkflowExecutionRequest, StartWorkflowExecutionRequest,
    },
};
use uuid::Uuid;

async fn connect(config: &ProcessingConfig) -> Result<Client> {
    let mut client = tokio::time::timeout(
        Duration::from_secs(config.temporal.connect_timeout_seconds),
        Client::connect(
            ConnectionOptions::new(Url::parse(&format!("http://{}", config.temporal.host))?)
                .identity("control-plane-processing")
                .build(),
            ClientOptions::new(&config.temporal.namespace).build(),
        ),
    )
    .await
    .context("processing Temporal connection timeout")?
    .map_err(|_| anyhow::anyhow!("processing Temporal unavailable"))?;
    let namespace = tokio::time::timeout(
        Duration::from_secs(config.temporal.rpc_timeout_seconds),
        client.describe_namespace(Request::new(DescribeNamespaceRequest {
            namespace: config.temporal.namespace.clone(),
            ..Default::default()
        })),
    )
    .await??
    .into_inner();
    let retention = namespace
        .config
        .and_then(|c| c.workflow_execution_retention_ttl)
        .map(|d| d.seconds)
        .unwrap_or(0);
    anyhow::ensure!(
        retention > config.limits.queue_seconds as i64,
        "Temporal retention must exceed the processing admission horizon"
    );
    Ok(client)
}

/// Lease a bounded batch with SKIP LOCKED, then release all SQL locks before RPCs.
pub async fn expire(pool: &PgPool, config: &ProcessingConfig) -> Result<()> {
    sqlx::query("update document_processing set status='failed',error_code=case when stage='queued' then 'delivery_unknown' else 'deadline_exceeded' end,completed_at=clock_timestamp(),revision=revision+1 where status in ('pending','running') and (deadline_at<=clock_timestamp() or (stage='queued' and created_at+make_interval(secs=>$1)<=clock_timestamp()))")
        .bind(config.limits.queue_seconds as f64).execute(pool).await?;
    Ok(())
}
pub async fn tick(pool: &PgPool, config: &ProcessingConfig, client: &mut Client) -> Result<()> {
    expire(pool, config).await?;
    let owner = Uuid::new_v4();
    let rows:Vec<Row>=sqlx::query_as("with candidates as (select id from document_processing where status in ('pending','running') and delivery_due_at<=clock_timestamp() and (dispatch_until is null or dispatch_until<clock_timestamp()) order by delivery_due_at,id for update skip locked limit $1) update document_processing p set dispatch_owner=$2,dispatch_until=clock_timestamp()+make_interval(secs=>$3),first_dispatch_at=coalesce(first_dispatch_at,clock_timestamp()),delivery_attempts=delivery_attempts+1 from candidates c where p.id=c.id returning p.*")
        .bind(config.limits.batch as i64).bind(owner).bind((config.temporal.rpc_timeout_seconds*config.limits.batch as u64+30) as f64).fetch_all(pool).await?;
    for row in rows {
        let result = tokio::time::timeout(
            Duration::from_secs(config.temporal.rpc_timeout_seconds),
            deliver(client, config, &row),
        )
        .await;
        match result {
            Ok(Ok((run_id, closed))) => {
                // A closed workflow with no committed result cannot be silently restarted.
                sqlx::query("update document_processing set run_id=$3,delivered_at=coalesce(delivered_at,clock_timestamp()),dispatch_until=null,delivery_due_at=clock_timestamp()+interval '30 seconds',status=case when $4 then 'failed' else status end,error_code=case when $4 then coalesce(error_code,'worker_failed') else error_code end,completed_at=case when $4 then clock_timestamp() else completed_at end,revision=revision+case when $4 then 1 else 0 end where id=$1 and dispatch_owner=$2 and status in ('pending','running')")
                    .bind(row.summary.id).bind(owner).bind(run_id).bind(closed).execute(pool).await?;
            }
            _ => {
                sqlx::query("update document_processing set dispatch_until=null,delivery_due_at=clock_timestamp()+interval '15 seconds' where id=$1 and dispatch_owner=$2")
                    .bind(row.summary.id).bind(owner).execute(pool).await?;
                tracing::warn!(operation_id=%row.summary.id,error_code="temporal_delivery_uncertain","Processing delivery will be reconciled");
            }
        }
    }
    Ok(())
}
async fn deliver(
    client: &mut Client,
    config: &ProcessingConfig,
    row: &Row,
) -> Result<(String, bool)> {
    // On subsequent attempts describe first: even history expiry must not create a second run.
    if row.first_dispatch_at.is_some() || row.run_id.is_some() {
        match describe(client, config, row).await {
            Ok(result) => return Ok(result),
            Err(error)
                if error.code() == Code::NotFound
                    && row.delivered_at.is_none()
                    && row.summary.stage == super::models::Stage::Queued => {}
            Err(_) => anyhow::bail!("processing history unavailable"),
        }
    }
    let now = Utc::now();
    anyhow::ensure!(
        row.deadline_at > now
            && row.summary.created_at
                + chrono::Duration::seconds(config.limits.queue_seconds as i64)
                > now,
        "processing admission horizon expired"
    );
    let payload = Payload {
        metadata: [("encoding".into(), b"json/plain".to_vec())].into(),
        data: serde_json::to_vec(&row.submission.0)?,
        ..Default::default()
    };
    let seconds = (row.deadline_at - Utc::now()).num_seconds().max(1) as u64;
    let request = StartWorkflowExecutionRequest {
        namespace: config.temporal.namespace.clone(),
        workflow_id: row.workflow_id.clone(),
        workflow_type: Some(WorkflowType {
            name: "ProcessPush".into(),
        }),
        task_queue: Some(TaskQueue {
            name: config.temporal.task_queue.clone(),
            ..Default::default()
        }),
        input: Some(Payloads {
            payloads: vec![payload],
        }),
        identity: "control-plane-processing".into(),
        request_id: row.summary.id.to_string(),
        workflow_id_reuse_policy: 3, // WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE, including closed runs.
        workflow_id_conflict_policy: 1, // FAIL for a running run; reconcile below.
        workflow_execution_timeout: Some(Duration::from_secs(seconds).try_into()?),
        ..Default::default()
    };
    match client.start_workflow_execution(Request::new(request)).await {
        Ok(reply) => Ok((reply.into_inner().run_id, false)),
        Err(e) if e.code() == Code::AlreadyExists => {
            describe(client, config, row).await.map_err(Into::into)
        }
        Err(_) => anyhow::bail!("processing start uncertain"),
    }
}
async fn describe(
    client: &mut Client,
    config: &ProcessingConfig,
    row: &Row,
) -> std::result::Result<(String, bool), temporalio_client::tonic::Status> {
    let result = client
        .describe_workflow_execution(Request::new(DescribeWorkflowExecutionRequest {
            namespace: config.temporal.namespace.clone(),
            execution: Some(WorkflowExecution {
                workflow_id: row.workflow_id.clone(),
                run_id: row.run_id.clone().unwrap_or_default(),
            }),
        }))
        .await?
        .into_inner();
    let info = result
        .workflow_execution_info
        .ok_or_else(|| temporalio_client::tonic::Status::data_loss("missing execution"))?;
    let execution = info
        .execution
        .ok_or_else(|| temporalio_client::tonic::Status::data_loss("missing identity"))?;
    Ok((execution.run_id, info.status != 1))
}
pub async fn run(pool: PgPool, config: ProcessingConfig) {
    let mut interval = tokio::time::interval(Duration::from_secs(config.limits.poll_seconds));
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut client = None;
    loop {
        interval.tick().await;
        // Disabling admission still drains and reconciles previously accepted work.
        if client.is_none() {
            client = connect(&config).await.ok();
        }
        if let Some(c) = client.as_mut() {
            if tick(&pool, &config, c).await.is_err() {
                client = None;
                tracing::warn!(
                    error_code = "processing_dispatch_retry",
                    "Processing dispatcher will reconnect"
                );
            }
        } else {
            // Expire queued work even during an extended Temporal outage.
            let _ = expire(&pool, &config).await;
            tracing::warn!(
                error_code = "temporal_unavailable",
                "Processing dispatcher will reconnect"
            );
        }
    }
}
