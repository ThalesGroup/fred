// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! SQL owns schedule admission and delivery leases; Temporal owns collection retries.
use super::*;
use crate::{
    lifecycle::policy::TemporalConfig,
    processing::dispatch::{WorkflowDelivery, connect_temporal, deliver_workflow},
};
use anyhow::Result;
use std::time::Duration;
use temporalio_client::Client;

#[derive(sqlx::FromRow)]
struct Delivery {
    id: Uuid,
    workflow_id: String,
    task_queue: String,
    temporal_run_id: Option<String>,
    delivered_at: Option<DateTime<Utc>>,
    deadline_at: DateTime<Utc>,
}

async fn expire(s: &AppState, id: Option<Uuid>, code: &str) -> Result<()> {
    let rows:Vec<(Uuid,Uuid)>=sqlx::query_as("select r.id,s.organization_id from kb_run r join space s on s.id=r.space_id join space o on o.id=s.organization_id left join space p on p.id=s.parent_id join folder f on f.id=r.folder_id where r.state in ('pending','running') and (r.id=$1 or r.deadline_at<=clock_timestamp() or s.deletion_id is not null or o.deletion_id is not null or p.deletion_id is not null or f.deletion_id is not null) order by r.deadline_at,r.id limit 20").bind(id).fetch_all(&s.pool).await?;
    for (run, organization) in rows {
        let mut tx = s.pool.begin().await?;
        crate::spaces::lock_organization_id(&mut tx, organization).await?;
        sqlx::query("update kb_run set state='failed',completed_at=clock_timestamp(),error_code=$2 where id=$1 and state in ('pending','running')").bind(run).bind(code).execute(&mut *tx).await?;
        tx.commit().await?;
    }
    Ok(())
}
async fn admit_scheduled(s: &AppState) -> Result<()> {
    let candidates:Vec<(Uuid,Uuid)>=sqlx::query_as("select i.id,s.organization_id from kb_instance i join space s on s.id=i.space_id join space o on o.id=s.organization_id left join space p on p.id=s.parent_id join folder f on f.id=i.folder_id where not i.paused and i.interval_seconds is not null and i.next_run_at<=clock_timestamp() and s.deletion_id is null and o.deletion_id is null and (p.id is null or p.deletion_id is null) and f.deletion_id is null order by i.next_run_at,i.id limit 20").fetch_all(&s.pool).await?;
    for (instance, organization) in candidates {
        let mut tx = s.pool.begin().await?;
        crate::spaces::lock_organization_id(&mut tx, organization).await?;
        let due:Option<DateTime<Utc>>=sqlx::query_scalar("select next_run_at from kb_instance where id=$1 and not paused and next_run_at<=clock_timestamp() for update").bind(instance).fetch_optional(&mut *tx).await?.flatten();
        let Some(due) = due else { continue };
        // If unavailable or already running, reconsider at the next configured interval.
        // A savepoint keeps expected admission refusal separate from SQL failures.
        sqlx::query("savepoint kb_schedule")
            .execute(&mut *tx)
            .await?;
        if let Err(error) = super::enqueue(
            &mut tx,
            s,
            instance,
            &format!("schedule:{}", due.timestamp_micros()),
            "scheduler",
        )
        .await
        {
            if !matches!(
                error,
                AppError::Forbidden | AppError::Conflict(_) | AppError::Problem { .. }
            ) {
                return Err(error.into());
            }
            sqlx::query("rollback to savepoint kb_schedule")
                .execute(&mut *tx)
                .await?;
            sqlx::query("update kb_instance set next_run_at=clock_timestamp()+make_interval(secs=>interval_seconds) where id=$1").bind(instance).execute(&mut *tx).await?;
        }
        tx.commit().await?;
    }
    Ok(())
}
async fn tick(s: &AppState, config: &TemporalConfig, client: &Client) -> Result<()> {
    let owner = Uuid::new_v4();
    let rows:Vec<Delivery>=sqlx::query_as("with candidates as (select id from kb_run where state in ('pending','running') and delivery_due_at<=clock_timestamp() and (dispatch_until is null or dispatch_until<clock_timestamp()) order by delivery_due_at,id for update skip locked limit 20) update kb_run r set dispatch_owner=$1,dispatch_until=clock_timestamp()+make_interval(secs=>$2) from candidates c where r.id=c.id returning r.id,r.workflow_id,r.task_queue,r.temporal_run_id,r.delivered_at,r.deadline_at").bind(owner).bind((config.rpc_timeout_seconds*20+30) as f64).fetch_all(&s.pool).await?;
    for row in rows {
        let mut client = client.clone();
        let input = serde_json::json!(row.id.to_string());
        let result = tokio::time::timeout(
            Duration::from_secs(config.rpc_timeout_seconds),
            deliver_workflow(
                &mut client,
                config,
                WorkflowDelivery {
                    id: row.id,
                    workflow_id: &row.workflow_id,
                    run_id: row.temporal_run_id.as_deref(),
                    task_queue: &row.task_queue,
                    workflow_type: "SyncKnowledgeBase",
                    submission: &input,
                    deadline_at: row.deadline_at,
                    may_start: row.delivered_at.is_none(),
                    describe_first: true,
                },
            ),
        )
        .await;
        match result {
            Ok(Ok((run, closed))) => {
                sqlx::query("update kb_run set temporal_run_id=$3,delivered_at=coalesce(delivered_at,clock_timestamp()),dispatch_until=null,delivery_due_at=clock_timestamp()+interval '30 seconds' where id=$1 and dispatch_owner=$2").bind(row.id).bind(owner).bind(run).execute(&s.pool).await?;
                if closed {
                    expire(s, Some(row.id), "worker_stopped").await?;
                }
            }
            _ => {
                sqlx::query("update kb_run set dispatch_until=null,delivery_due_at=clock_timestamp()+interval '15 seconds' where id=$1 and dispatch_owner=$2").bind(row.id).bind(owner).execute(&s.pool).await?;
                tracing::warn!(run_id=%row.id,"Knowledge base delivery will be reconciled");
            }
        }
    }
    Ok(())
}
pub async fn run(s: AppState, config: TemporalConfig) {
    let mut interval = tokio::time::interval(Duration::from_secs(5));
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut client = None;
    loop {
        interval.tick().await;
        if expire(&s, None, "run_expired").await.is_err() || admit_scheduled(&s).await.is_err() {
            tracing::warn!("Knowledge base schedule will retry");
            continue;
        }
        let pending = sqlx::query_scalar::<_, bool>(
            "select exists(select 1 from kb_run where state in ('pending','running'))",
        )
        .fetch_one(&s.pool)
        .await
        .unwrap_or(false);
        if !pending {
            continue;
        }
        if client.is_none() {
            client = connect_temporal(&config, 86400).await.ok();
        }
        if let Some(c) = &client
            && tick(&s, &config, c).await.is_err()
        {
            client = None;
            tracing::warn!("Knowledge base dispatcher will retry");
        }
    }
}
