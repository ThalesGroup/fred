// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Temporal owns retries and history; activities own SQL, OpenFGA and clocks.
use super::{cleanup, policy::LifecycleConfig};
use crate::fga::Fga;
use anyhow::{Context, Result};
use sqlx::PgPool;
use std::{sync::Arc, time::Duration};
use temporalio_client::{
    Client, ClientOptions, ConnectionOptions, Url,
    schedules::{
        CreateScheduleOptions, ScheduleAction, ScheduleDescriptionAction, ScheduleError,
        ScheduleOverlapPolicy, ScheduleSpec,
    },
};
use temporalio_common::RetryPolicy;
use temporalio_macros::{activities, workflow, workflow_methods};
use temporalio_sdk::{
    ActivityOptions, Runtime, Worker, WorkerOptions, WorkflowContext, WorkflowResult,
    activities::{ActivityContext, ActivityError},
};
use uuid::Uuid;

pub struct CleanupActivities {
    pub pool: PgPool,
    pub fga: Fga,
    pub config: LifecycleConfig,
}
// A Temporal timeout signals cancellation; it does not drop Rust activity futures.
// Keep local work shorter than start-to-close and release resources on shutdown.
async fn bounded<T>(
    ctx: &ActivityContext,
    work: impl std::future::Future<Output = crate::error::AppResult<T>>,
) -> Result<T, ActivityError> {
    tokio::select! {
        biased;
        _ = ctx.cancelled() => Err(ActivityError::cancelled()),
        result = tokio::time::timeout(Duration::from_secs(50), work) => match result {
            Ok(Ok(value)) => Ok(value),
            _ => Err(anyhow::anyhow!("lifecycle dependency unavailable").into()),
        }
    }
}
#[activities]
impl CleanupActivities {
    #[activity]
    pub async fn candidates(
        self: Arc<Self>,
        ctx: ActivityContext,
    ) -> Result<Vec<Uuid>, ActivityError> {
        if !self.config.enabled {
            return Ok(vec![]);
        }
        bounded(
            &ctx,
            cleanup::candidates(&self.pool, self.config.batch_size),
        )
        .await
    }
    #[activity]
    pub async fn exhausted(
        self: Arc<Self>,
        ctx: ActivityContext,
        operation: Uuid,
    ) -> Result<(), ActivityError> {
        bounded(&ctx, cleanup::retrying(&self.pool, operation)).await
    }
    #[activity]
    pub async fn clean(
        self: Arc<Self>,
        ctx: ActivityContext,
        operation: Uuid,
    ) -> Result<(), ActivityError> {
        if !self.config.enabled {
            return Ok(());
        }
        bounded(&ctx, cleanup::batch(&self.pool, &self.fga, operation)).await
    }
}
#[workflow]
#[derive(Default)]
pub struct SpaceDeletionSweep;
#[workflow_methods]
impl SpaceDeletionSweep {
    #[run]
    pub async fn run(ctx: &mut WorkflowContext<Self>) -> WorkflowResult<()> {
        let options = || {
            let mut options = ActivityOptions::with_close_timeouts(
                temporalio_common::ActivityCloseTimeouts::ScheduleAndStartToClose {
                    schedule_to_close: Duration::from_secs(240),
                    start_to_close: Duration::from_secs(60),
                },
            )
            .build();
            options.retry_policy = Some(RetryPolicy::builder().maximum_attempts(3).build());
            options
        };
        let ids = ctx
            .execute_activity(CleanupActivities::candidates, (), options())
            .await?;
        for id in ids {
            // Failed candidates retain their receipt; the remaining candidates still run.
            if ctx
                .execute_activity(CleanupActivities::clean, id, options())
                .await
                .is_err()
            {
                let _ = ctx
                    .execute_activity(CleanupActivities::exhausted, id, options())
                    .await;
            }
        }
        Ok(())
    }
}
const OWNER: &str = "fred-manager space lifecycle v1";
fn action(config: &LifecycleConfig) -> ScheduleAction {
    ScheduleAction::start_workflow(
        SpaceDeletionSweep::run,
        (),
        &config.temporal.task_queue,
        format!("{}-sweep", config.temporal.workflow_id_prefix),
    )
}
/// Describe and CAS update; an unrelated schedule is never adopted or overwritten.
pub async fn reconcile(client: &Client, config: &LifecycleConfig) -> Result<()> {
    let id = format!("{}-schedule", config.temporal.workflow_id_prefix);
    let handle = client.get_schedule_handle(&id);
    for _ in 0..3 {
        let result = tokio::time::timeout(Duration::from_secs(config.temporal.rpc_timeout_seconds), async {
            let description = match handle.describe(Default::default()).await {
                Ok(description) => description,
                Err(ScheduleError::Rpc(status)) if status.code() == temporalio_client::tonic::Code::NotFound => {
                    if !config.enabled { return Ok::<_, anyhow::Error>(true); }
                    let created = client.create_schedule(&id, CreateScheduleOptions::builder()
                        .action(action(config)).spec(ScheduleSpec::from_interval(config.sweep_interval.duration()))
                        .overlap_policy(ScheduleOverlapPolicy::Skip).note(OWNER.to_owned()).build()).await;
                    return match created {
                        Ok(_) => Ok(true),
                        Err(ScheduleError::Rpc(s)) if s.code() == temporalio_client::tonic::Code::AlreadyExists => Ok(false),
                        Err(_) => anyhow::bail!("lifecycle schedule creation failed"),
                    };
                }
                Err(_) => anyhow::bail!("lifecycle schedule lookup failed"),
            };
            anyhow::ensure!(description.note() == Some(OWNER), "lifecycle schedule ownership conflict");
            match description.action() {
                ScheduleDescriptionAction::StartWorkflow(a) => anyhow::ensure!(a.workflow_type() == "SpaceDeletionSweep", "lifecycle workflow ownership conflict"),
                _ => anyhow::bail!("unsupported lifecycle schedule action"),
            }
            let conflict_token = description.conflict_token().to_vec();
            let mut update = description.into_update();
            update.set_spec(ScheduleSpec::from_interval(config.sweep_interval.duration()))
                .set_paused(!config.enabled).set_overlap_policy(ScheduleOverlapPolicy::Skip).set_note(OWNER);
            let mut schedule = update.into_raw();
            let Some(temporalio_common::protos::temporal::api::schedule::v1::schedule_action::Action::StartWorkflow(workflow)) = schedule.action.as_mut().and_then(|a| a.action.as_mut()) else { anyhow::bail!("missing lifecycle action"); };
            workflow.task_queue.as_mut().context("missing lifecycle queue")?.name = config.temporal.task_queue.clone();
            workflow.workflow_id = format!("{}-sweep", config.temporal.workflow_id_prefix);
            let request = temporalio_common::protos::temporal::api::workflowservice::v1::UpdateScheduleRequest {
                namespace: config.temporal.namespace.clone(), schedule_id: id.clone(), schedule: Some(schedule),
                conflict_token, identity: "fred-manager-worker".into(), request_id: Uuid::new_v4().to_string(), ..Default::default()
            };
            // SDK 1.0's high-level send_update omits the conflict token; preserve CAS here.
            use temporalio_client::grpc::WorkflowService;
            match client.clone().update_schedule(temporalio_client::tonic::Request::new(request)).await {
                Ok(_) => Ok(true),
                Err(s) if s.code() == temporalio_client::tonic::Code::FailedPrecondition => Ok(false),
                Err(_) => anyhow::bail!("lifecycle schedule update failed"),
            }
        }).await.context("lifecycle schedule RPC timeout")??;
        if result {
            return Ok(());
        }
    }
    anyhow::bail!("lifecycle schedule changed concurrently; retry startup")
}
pub async fn connect(config: &LifecycleConfig) -> Result<Client> {
    tokio::time::timeout(
        Duration::from_secs(config.temporal.connect_timeout_seconds),
        Client::connect(
            ConnectionOptions::new(Url::parse(&format!("http://{}", config.temporal.host))?)
                .identity("fred-manager-worker")
                .build(),
            ClientOptions::new(&config.temporal.namespace).build(),
        ),
    )
    .await
    .context("lifecycle Temporal connection timeout")?
    .map_err(|_| anyhow::anyhow!("lifecycle Temporal unavailable"))
}
pub async fn run(pool: PgPool, fga: Fga, config: LifecycleConfig, listen: &str) -> Result<()> {
    let client = match connect(&config).await {
        Ok(client) => client,
        Err(error) if !config.enabled => {
            tracing::warn!(
                error_code = "temporal_unavailable",
                "Disabled lifecycle cannot pause its schedule"
            );
            let _ = error;
            shutdown_signal().await?;
            return Ok(());
        }
        Err(error) => return Err(error),
    };
    reconcile(&client, &config).await?;
    let runtime = Runtime::from_current_tokio(Default::default())?;
    let options = WorkerOptions::new(&config.temporal.task_queue)
        .graceful_shutdown_period(Duration::from_secs(2))
        .register_workflow::<SpaceDeletionSweep>()?
        .register_activities(CleanupActivities { pool, fga, config })
        .build();
    let mut worker = Worker::new(&runtime, client, options)?;
    let shutdown = worker.shutdown_handle();
    let listener = tokio::net::TcpListener::bind(listen).await?;
    let health = tokio::spawn(async move {
        axum::serve(
            listener,
            axum::Router::new().route("/healthz", axum::routing::get(|| async { "ok" })),
        )
        .await
    });
    let signal = tokio::spawn(async move {
        shutdown_signal().await?;
        shutdown();
        Ok::<_, std::io::Error>(())
    });
    let result = worker.run().await;
    health.abort();
    signal.abort();
    result.map_err(|_| anyhow::anyhow!("lifecycle worker stopped unexpectedly"))
}

async fn shutdown_signal() -> std::io::Result<()> {
    let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    tokio::select! { result = tokio::signal::ctrl_c() => result, _ = term.recv() => Ok(()) }
}
