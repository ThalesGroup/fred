// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::{fmt::Debug, time::Duration};

use k8s_openapi::api::{
    apps::v1::{DaemonSet, Deployment, StatefulSet},
    core::v1::Pod,
    events::v1::Event,
};
use k8s_openapi::jiff::Timestamp;
use kube::{Api, Client, Resource, ResourceExt, api::ListParams};
use serde::{Serialize, de::DeserializeOwned};
use utoipa::ToSchema;

const PAGE_SIZE: u32 = 500;
const MAX_PAGES: usize = 4;
const EVENT_LIMIT: usize = 100;
const EVENT_WINDOW_SECONDS: i64 = 3600;

#[derive(Clone)]
pub struct Kubernetes {
    client: Client,
    namespace: String,
}

#[derive(Clone, Copy, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum Source {
    Deployments,
    StatefulSets,
    DaemonSets,
    Pods,
    Events,
}

#[derive(Debug, PartialEq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ServiceState {
    Ready,
    Degraded,
    Updating,
    Inactive,
    Unknown,
}

#[derive(Serialize, ToSchema)]
pub struct ServiceStatus {
    pub name: String,
    pub kind: String,
    pub desired: i32,
    pub ready: i32,
    pub state: ServiceState,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ContainerStatus {
    pub pod: String,
    pub container: String,
    pub init: bool,
    pub phase: String,
    pub ready: bool,
    /// Kubernetes' cumulative count for this container in this pod, not an hourly rate.
    pub restarts: i32,
    pub reason: Option<String>,
    pub last_exit_reason: Option<String>,
    pub last_exit_at: Option<String>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct RecentEvent {
    pub uid: String,
    pub observed_at: String,
    pub severity: String,
    pub reason: String,
    pub object: String,
    pub message: String,
    pub count: i32,
}

#[derive(Serialize, ToSchema)]
pub struct Snapshot {
    pub observed_at: String,
    pub namespace: String,
    pub services: Vec<ServiceStatus>,
    pub containers: Vec<ContainerStatus>,
    pub events: Vec<RecentEvent>,
    /// An empty list from an unavailable source is not evidence of a healthy namespace.
    pub unavailable_sources: Vec<Source>,
    /// Sources exceeding the bounded Kubernetes pagination budget.
    pub truncated_sources: Vec<Source>,
    pub events_limited: bool,
    pub event_window_seconds: i64,
}

struct Collection<T> {
    items: Vec<T>,
    truncated: bool,
}

impl Kubernetes {
    pub fn new(client: Client, namespace: String) -> Self {
        Self { client, namespace }
    }

    pub async fn snapshot(&self) -> Snapshot {
        let client = &self.client;
        let ns = &self.namespace;
        let (deployments, stateful_sets, daemon_sets, pods, events) = tokio::join!(
            collect(Api::<Deployment>::namespaced(client.clone(), ns)),
            collect(Api::<StatefulSet>::namespaced(client.clone(), ns)),
            collect(Api::<DaemonSet>::namespaced(client.clone(), ns)),
            collect(Api::<Pod>::namespaced(client.clone(), ns)),
            collect(Api::<Event>::namespaced(client.clone(), ns)),
        );
        let now = Timestamp::now();
        let mut result = Snapshot {
            observed_at: now.to_string(),
            namespace: ns.clone(),
            services: Vec::new(),
            containers: Vec::new(),
            events: Vec::new(),
            unavailable_sources: Vec::new(),
            truncated_sources: Vec::new(),
            events_limited: false,
            event_window_seconds: EVENT_WINDOW_SECONDS,
        };
        for item in result.accept(Source::Deployments, deployments) {
            let desired = item.spec.as_ref().and_then(|s| s.replicas).unwrap_or(1);
            let status = item.status.as_ref();
            let ready = status.and_then(|s| s.ready_replicas).unwrap_or(0);
            result.services.push(ServiceStatus {
                name: item.name_any(),
                kind: "Deployment".into(),
                desired,
                ready,
                state: service_state(
                    desired,
                    ready,
                    status.and_then(|s| s.updated_replicas).unwrap_or(0),
                    item.metadata.generation,
                    status.and_then(|s| s.observed_generation),
                ),
            });
        }
        for item in result.accept(Source::StatefulSets, stateful_sets) {
            let desired = item.spec.as_ref().and_then(|s| s.replicas).unwrap_or(1);
            let status = item.status.as_ref();
            let ready = status.and_then(|s| s.ready_replicas).unwrap_or(0);
            result.services.push(ServiceStatus {
                name: item.name_any(),
                kind: "StatefulSet".into(),
                desired,
                ready,
                state: service_state(
                    desired,
                    ready,
                    status.and_then(|s| s.updated_replicas).unwrap_or(0),
                    item.metadata.generation,
                    status.and_then(|s| s.observed_generation),
                ),
            });
        }
        for item in result.accept(Source::DaemonSets, daemon_sets) {
            let status = item.status.as_ref();
            let desired = status.map(|s| s.desired_number_scheduled).unwrap_or(0);
            let ready = status.map(|s| s.number_ready).unwrap_or(0);
            result.services.push(ServiceStatus {
                name: item.name_any(),
                kind: "DaemonSet".into(),
                desired,
                ready,
                state: service_state(
                    desired,
                    ready,
                    status.and_then(|s| s.updated_number_scheduled).unwrap_or(0),
                    item.metadata.generation,
                    status.and_then(|s| s.observed_generation),
                ),
            });
        }
        result
            .services
            .sort_by(|a, b| (&a.name, &a.kind).cmp(&(&b.name, &b.kind)));
        result.containers = result
            .accept(Source::Pods, pods)
            .iter()
            .flat_map(containers)
            .collect();
        result
            .containers
            .sort_by(|a, b| (&a.pod, &a.container).cmp(&(&b.pod, &b.container)));
        result.events = recent_events(result.accept(Source::Events, events), now);
        result.events_limited = result.events.len() > EVENT_LIMIT;
        result.events.truncate(EVENT_LIMIT);
        result
    }
}

impl Snapshot {
    fn accept<T>(&mut self, source: Source, collection: Option<Collection<T>>) -> Vec<T> {
        match collection {
            Some(collection) => {
                if collection.truncated {
                    self.truncated_sources.push(source);
                }
                collection.items
            }
            None => {
                self.unavailable_sources.push(source);
                Vec::new()
            }
        }
    }
}

async fn collect<K>(api: Api<K>) -> Option<Collection<K>>
where
    K: Resource + Clone + DeserializeOwned + Debug,
    K::DynamicType: Default,
{
    let fetch = async {
        let mut items = Vec::new();
        let mut params = ListParams::default().limit(PAGE_SIZE);
        for _ in 0..MAX_PAGES {
            let page = api.list(&params).await?;
            items.extend(page.items);
            match page.metadata.continue_.filter(|s| !s.is_empty()) {
                Some(next) => params = params.continue_token(&next),
                None => {
                    return Ok::<_, kube::Error>(Collection {
                        items,
                        truncated: false,
                    });
                }
            }
        }
        Ok(Collection {
            items,
            truncated: true,
        })
    };
    match tokio::time::timeout(Duration::from_secs(5), fetch).await {
        Ok(Ok(result)) => Some(result),
        Ok(Err(error)) => {
            tracing::warn!(%error, "Kubernetes collection failed");
            None
        }
        Err(_) => {
            tracing::warn!("Kubernetes collection timed out");
            None
        }
    }
}

fn service_state(
    desired: i32,
    ready: i32,
    updated: i32,
    generation: Option<i64>,
    observed: Option<i64>,
) -> ServiceState {
    match (generation, observed) {
        (_, None) => ServiceState::Unknown,
        (Some(generation), Some(observed)) if observed < generation => ServiceState::Updating,
        _ if desired == 0 => ServiceState::Inactive,
        _ if ready < desired => ServiceState::Degraded,
        _ if updated < desired => ServiceState::Updating,
        _ => ServiceState::Ready,
    }
}

fn containers(pod: &Pod) -> Vec<ContainerStatus> {
    let unknown_status = Default::default();
    let status = pod.status.as_ref().unwrap_or(&unknown_status);
    // A successful migration Job is not an unhealthy service.
    if status.phase.as_deref() == Some("Succeeded") {
        return Vec::new();
    }
    let mut rows = Vec::new();
    for (init, statuses) in [
        (true, &status.init_container_statuses),
        (false, &status.container_statuses),
    ] {
        for c in statuses.iter().flatten() {
            let state = c.state.as_ref();
            let last = c.last_state.as_ref().and_then(|s| s.terminated.as_ref());
            let reason = state
                .and_then(|s| s.waiting.as_ref())
                .and_then(|s| s.reason.clone())
                .or_else(|| {
                    state
                        .and_then(|s| s.terminated.as_ref())
                        .and_then(|s| s.reason.clone())
                });
            rows.push(ContainerStatus {
                pod: pod.name_any(),
                container: c.name.clone(),
                init,
                phase: status.phase.clone().unwrap_or_else(|| "Unknown".into()),
                ready: c.ready,
                restarts: c.restart_count,
                reason,
                last_exit_reason: last.and_then(|s| s.reason.clone()),
                last_exit_at: last
                    .and_then(|s| s.finished_at.as_ref())
                    .map(|t| t.0.to_string()),
            });
        }
    }
    // Pending pods may have no container statuses yet: retain evidence of failed scheduling.
    if rows.is_empty() {
        rows.push(ContainerStatus {
            pod: pod.name_any(),
            container: String::new(),
            init: false,
            phase: status.phase.clone().unwrap_or_else(|| "Unknown".into()),
            ready: false,
            restarts: 0,
            reason: status
                .conditions
                .as_ref()
                .and_then(|cs| cs.iter().find(|c| c.status == "False"))
                .and_then(|c| c.reason.clone()),
            last_exit_reason: None,
            last_exit_at: None,
        });
    }
    rows
}

fn recent_events(events: Vec<Event>, now: Timestamp) -> Vec<RecentEvent> {
    let cutoff = now.as_second() - EVENT_WINDOW_SECONDS;
    let mut rows: Vec<_> = events
        .into_iter()
        .filter_map(|e| {
            let time = e
                .series
                .as_ref()
                .map(|s| s.last_observed_time.0)
                .or_else(|| e.deprecated_last_timestamp.as_ref().map(|t| t.0))
                .or_else(|| e.event_time.as_ref().map(|t| t.0))
                .or_else(|| e.metadata.creation_timestamp.as_ref().map(|t| t.0))?;
            if time.as_second() < cutoff {
                return None;
            }
            Some((
                time,
                RecentEvent {
                    uid: e.uid().unwrap_or_else(|| e.name_any()),
                    observed_at: time.to_string(),
                    severity: e.type_.unwrap_or_else(|| "Normal".into()),
                    reason: e.reason.unwrap_or_default(),
                    object: e
                        .regarding
                        .map(|o| {
                            format!(
                                "{}/{}",
                                o.kind.unwrap_or_default(),
                                o.name.unwrap_or_default()
                            )
                        })
                        .unwrap_or_default(),
                    message: e.note.unwrap_or_default().chars().take(2048).collect(),
                    count: e
                        .series
                        .map(|s| s.count)
                        .or(e.deprecated_count)
                        .unwrap_or(1),
                },
            ))
        })
        .collect();
    rows.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| a.1.uid.cmp(&b.1.uid)));
    rows.into_iter().map(|(_, e)| e).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Body, http::Response};
    use serde_json::json;
    use std::sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    };

    #[test]
    fn zero_replicas_and_unobserved_rollouts_are_not_reported_as_healthy() {
        assert_eq!(
            service_state(0, 0, 0, Some(2), Some(2)),
            ServiceState::Inactive
        );
        assert_eq!(
            service_state(2, 2, 2, Some(3), Some(2)),
            ServiceState::Updating
        );
        assert_eq!(
            service_state(2, 1, 2, Some(2), Some(2)),
            ServiceState::Degraded
        );
        assert_eq!(
            service_state(1, 1, 0, Some(2), Some(2)),
            ServiceState::Updating
        );
        assert_eq!(service_state(1, 0, 0, Some(1), None), ServiceState::Unknown);
    }

    #[test]
    fn healthy_restarted_pods_keep_the_previous_exit_and_successful_jobs_are_omitted() {
        let mut pod: Pod = serde_json::from_value(json!({
            "metadata": {"name":"worker"},
            "status": {"phase":"Running", "containerStatuses":[{
                "name":"worker", "image":"worker:dev", "imageID":"sha256:abc",
                "ready":true, "restartCount":2,
                "state":{"running":{}},
                "lastState":{"terminated":{"exitCode":137,"reason":"OOMKilled","finishedAt":"2026-10-31T12:01:00Z"}}
            }]}
        })).unwrap();
        let rows = containers(&pod);
        assert_eq!(rows[0].restarts, 2);
        assert!(rows[0].ready);
        assert_eq!(rows[0].last_exit_reason.as_deref(), Some("OOMKilled"));
        pod.status.as_mut().unwrap().phase = Some("Succeeded".into());
        assert!(containers(&pod).is_empty());
        let pending: Pod = serde_json::from_value(json!({
            "metadata":{"name":"unscheduled"}, "status":{"phase":"Pending", "conditions":[{
                "type":"PodScheduled", "status":"False", "reason":"Unschedulable"
            }]}
        }))
        .unwrap();
        assert_eq!(
            containers(&pending)[0].reason.as_deref(),
            Some("Unschedulable")
        );
        let unobserved: Pod = serde_json::from_value(json!({"metadata":{"name":"new"}})).unwrap();
        assert_eq!(containers(&unobserved)[0].phase, "Unknown");
    }

    #[test]
    fn recent_event_series_use_last_observation_not_initial_creation() {
        let event: Event = serde_json::from_value(json!({
            "metadata":{"name":"pressure","uid":"event-1"},
            "eventTime":"2026-10-30T12:00:00Z", "reason":"BackOff", "type":"Warning",
            "series":{"count":8,"lastObservedTime":"2026-10-31T12:30:00Z"},
            "regarding":{"kind":"Pod","name":"worker"}
        }))
        .unwrap();
        let now: Timestamp = "2026-10-31T13:00:00Z".parse().unwrap();
        let rows = recent_events(vec![event.clone()], now);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].count, 8);
        assert_eq!(rows[0].object, "Pod/worker");
        assert!(recent_events(vec![event], "2026-10-31T15:00:00Z".parse().unwrap()).is_empty());
    }

    #[tokio::test]
    async fn a_failed_source_does_not_discard_other_collections() {
        let client = Client::new(
            tower::service_fn(
                |request: axum::http::Request<kube::client::Body>| async move {
                    let (code, body) = if request.uri().path().ends_with("/events") {
                        (
                            403,
                            json!({"kind":"Status", "apiVersion":"v1", "status":"Failure", "message":"forbidden", "reason":"Forbidden", "code":403}),
                        )
                    } else if request.uri().path().ends_with("/deployments") {
                        (
                            200,
                            json!({"metadata":{}, "items":[{
                                "metadata":{"name":"api","generation":1},
                                "spec":{"replicas":1,"selector":{"matchLabels":{"app":"api"}},"template":{"metadata":{},"spec":{"containers":[]}}},
                                "status":{"readyReplicas":1,"updatedReplicas":1,"observedGeneration":1}
                            }]}),
                        )
                    } else {
                        (200, json!({"metadata":{}, "items":[]}))
                    };
                    Ok::<_, std::io::Error>(
                        Response::builder()
                            .status(code)
                            .body(Body::from(body.to_string()))
                            .unwrap(),
                    )
                },
            ),
            "fred",
        );
        let snapshot = Kubernetes::new(client, "fred".into()).snapshot().await;
        assert_eq!(snapshot.services.len(), 1);
        assert_eq!(snapshot.services[0].state, ServiceState::Ready);
        assert!(matches!(
            snapshot.unavailable_sources.as_slice(),
            [Source::Events]
        ));
    }

    #[tokio::test]
    async fn pagination_is_bounded_and_truncation_is_explicit() {
        let calls = Arc::new(AtomicUsize::new(0));
        let count = calls.clone();
        let client = Client::new(
            tower::service_fn(move |request: axum::http::Request<kube::client::Body>| {
                count.fetch_add(1, Ordering::Relaxed);
                assert!(request.uri().query().unwrap().contains("limit=500"));
                async {
                    Ok::<_, std::io::Error>(Response::new(Body::from(
                        json!({"metadata":{"continue":"next"},"items":[]}).to_string(),
                    )))
                }
            }),
            "fred",
        );
        let result = collect(Api::<Pod>::namespaced(client, "fred"))
            .await
            .unwrap();
        assert!(result.truncated);
        assert_eq!(calls.load(Ordering::Relaxed), MAX_PAGES);
    }
}
