// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use crate::{
    lifecycle::policy::TemporalConfig,
    processing::dispatch::{WorkflowDelivery, connect_temporal, deliver_workflow},
};
use anyhow::Result;
use chrono::{DateTime, Utc};
use sqlx::PgPool;
use std::time::Duration;
use temporalio_client::Client;
use uuid::Uuid;

#[derive(sqlx::FromRow)]
struct Delivery {
    id: Uuid,
    workflow_id: String,
    task_queue: String,
    run_id: Option<String>,
    delivered_at: Option<DateTime<Utc>>,
    deadline_at: DateTime<Utc>,
}

async fn fail(pool: &PgPool, id: Option<Uuid>, error: &str) -> Result<()> {
    let rows:Vec<(Uuid,Uuid)>=sqlx::query_as("select p.id,f.organization_id from capability_preparation p join powerpoint_file f on f.id=p.file_id where p.state='pending' and (p.id=$1 or p.deadline_at<=clock_timestamp()) order by p.deadline_at limit 20").bind(id).fetch_all(pool).await?;
    for (preparation, organization) in rows {
        let mut tx = pool.begin().await?;
        // Same lock order as saves and callbacks; no Temporal call under this lock.
        crate::spaces::lock_organization_id(&mut tx, organization).await?;
        sqlx::query("update capability_preparation set state='failed',error=$2 where id=$1 and state='pending'")
            .bind(preparation).bind(error).execute(&mut *tx).await?;
        sqlx::query("update agent_instance a set preparation_state='failed',preparation_error=p.error from capability_preparation p where p.id=$1 and a.preparation_id=p.id and a.configuration_revision=p.configuration_revision and p.state='failed' and a.preparation_state='pending'")
            .bind(preparation).execute(&mut *tx).await?;
        tx.commit().await?;
    }
    Ok(())
}
pub async fn tick(pool: &PgPool, config: &TemporalConfig, client: &Client) -> Result<()> {
    fail(
        pool,
        None,
        "Preparation deadline exceeded. Retry or replace the PowerPoint file.",
    )
    .await?;
    let owner = Uuid::new_v4();
    let rows:Vec<Delivery>=sqlx::query_as("with candidates as (select id from capability_preparation where state='pending' and delivery_due_at<=clock_timestamp() and (dispatch_until is null or dispatch_until<clock_timestamp()) order by delivery_due_at,id for update skip locked limit 20) update capability_preparation p set dispatch_owner=$1,dispatch_until=clock_timestamp()+make_interval(secs=>$2) from candidates c where p.id=c.id returning p.id,p.workflow_id,p.task_queue,p.run_id,p.delivered_at,p.deadline_at").bind(owner).bind((config.rpc_timeout_seconds*20+30) as f64).fetch_all(pool).await?;
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
                    run_id: row.run_id.as_deref(),
                    task_queue: &row.task_queue,
                    workflow_type: "PrepareCapability",
                    submission: &input,
                    deadline_at: row.deadline_at,
                    may_start: row.delivered_at.is_none(),
                    describe_first: true,
                },
            ),
        )
        .await;
        if let Ok(Ok((run, closed))) = result {
            sqlx::query("update capability_preparation set run_id=$3,delivered_at=coalesce(delivered_at,clock_timestamp()),dispatch_until=null,delivery_due_at=clock_timestamp()+interval '30 seconds' where id=$1 and dispatch_owner=$2").bind(row.id).bind(owner).bind(run).execute(pool).await?;
            if closed {
                fail(pool,Some(row.id),"Preparation worker stopped before confirmation. Retry or replace the PowerPoint file.").await?;
            }
        } else {
            sqlx::query("update capability_preparation set dispatch_until=null,delivery_due_at=clock_timestamp()+interval '15 seconds' where id=$1 and dispatch_owner=$2").bind(row.id).bind(owner).execute(pool).await?;
        }
    }
    Ok(())
}
pub async fn run(pool: PgPool, config: TemporalConfig) {
    let mut interval = tokio::time::interval(Duration::from_secs(5));
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut client = None;
    loop {
        interval.tick().await;
        let _ = fail(
            &pool,
            None,
            "Preparation deadline exceeded. Retry or replace the PowerPoint file.",
        )
        .await;
        let pending = sqlx::query_scalar::<_, bool>(
            "select exists(select 1 from capability_preparation where state='pending')",
        )
        .fetch_one(&pool)
        .await
        .unwrap_or(false);
        if !pending {
            continue;
        }
        if client.is_none() {
            client = connect_temporal(&config, 7200).await.ok();
        }
        if let Some(c) = &client {
            if tick(&pool, &config, c).await.is_err() {
                client = None;
            }
        } else {
            let _ = fail(
                &pool,
                None,
                "Preparation deadline exceeded while Temporal was unavailable.",
            )
            .await;
        }
    }
}
