// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! The optional title of an embedded turn: generated beside the answer, persisted by
//! the session owner, announced in the answer's stream.

use fred_rust_agent::RuntimeEvent;
use futures::{FutureExt, StreamExt, future::BoxFuture, stream::BoxStream};
use tracing::Span;
use uuid::Uuid;

use crate::{
    agent_instances::TitleAdmission,
    api::AppState,
    sessions::title::{GeneratedTitle, persist},
};

/// The admitted turn a title belongs to.
pub(super) struct TitledTurn {
    pub(super) subject_id: String,
    pub(super) instance_id: Uuid,
    pub(super) space_id: Uuid,
    pub(super) session_id: Uuid,
}

pub(super) fn generate(
    state: &AppState,
    span: Span,
    turn: TitledTurn,
    input: String,
    title: TitleAdmission,
) -> BoxFuture<'static, Option<String>> {
    let pool = state.pool.clone();
    let credentials = state.agent_catalog.inference_credentials.clone();
    let TitledTurn {
        subject_id,
        instance_id,
        space_id,
        session_id,
    } = turn;
    async move {
        let offer = title.inference.selection.key.clone();
        let Ok(turn) = fred_rust_agent::turn::InferenceTurn::admit(title.inference, &credentials)
        else {
            tracing::warn!(
                event = "session_title",
                outcome = "skipped",
                reason = "provisioning"
            );
            return None;
        };
        let usage_pool = pool.clone();
        let generated = turn
            .title(&input, move |tokens| {
                super::usage::report(usage_pool, span, space_id, session_id, offer, tokens)
            })
            .await?;
        let body = GeneratedTitle {
            subject_id,
            agent_instance_id: instance_id,
            attempt_id: title.attempt_id,
            title: generated,
        };
        match tokio::time::timeout(
            std::time::Duration::from_secs(2),
            persist(&pool, space_id, session_id, &body),
        )
        .await
        {
            Ok(Ok(true)) => Some(session_id.to_string()),
            _ => {
                tracing::info!(
                    event = "session_title",
                    outcome = "skipped",
                    reason = "not_persisted"
                );
                None
            }
        }
    }
    .boxed()
}

/// Both futures live in the polled SSE stream: dropping it cancels inference.
/// Preserve the final frame until the optional two-second title grace has ended.
pub(super) fn stream(
    events: BoxStream<'static, RuntimeEvent>,
    title: Option<BoxFuture<'static, Option<String>>>,
) -> BoxStream<'static, RuntimeEvent> {
    futures::stream::unfold((events, title, None, 0_u64), |(mut events, mut title, mut pending, mut sequence)| async move {
        loop {
            let event = if let Some(event) = pending.take() {
                Some(event)
            } else if let Some(work) = title.as_mut() {
                tokio::select! {
                    result = &mut *work => {
                        title = None;
                        result.map(|session_id| RuntimeEvent::SessionTitle { sequence: 0, session_id })
                    }
                    event = events.next() => {
                        match event {
                            Some(final_event @ RuntimeEvent::Final { .. }) => {
                                let generated = tokio::time::timeout(std::time::Duration::from_secs(2), work).await.ok().flatten();
                                title = None;
                                if let Some(session_id) = generated {
                                    pending = Some(final_event);
                                    Some(RuntimeEvent::SessionTitle { sequence: 0, session_id })
                                } else { Some(final_event) }
                            }
                            Some(error @ RuntimeEvent::Error { .. }) => { title = None; Some(error) }
                            None => return None,
                            other => other,
                        }
                    }
                }
            } else { match events.next().await { Some(event) => Some(event), None => return None } };
            if let Some(event) = event {
                sequence += 1;
                return Some((event.with_sequence(sequence), (events, title, pending, sequence)));
            }
        }
    }).boxed()
}

#[cfg(test)]
mod tests {
    use super::*;
    use futures::stream;

    #[tokio::test]
    async fn title_grace_keeps_final_last_and_drops_slow_work() {
        let final_event = || RuntimeEvent::Final {
            sequence: 1,
            content: "answer".into(),
            sources: vec![],
            finish_reason: "stop",
        };
        let events = super::stream(
            stream::iter([final_event()]).boxed(),
            Some(
                async {
                    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
                    Some("session".into())
                }
                .boxed(),
            ),
        )
        .collect::<Vec<_>>()
        .await;
        assert!(matches!(
            &events[..],
            [
                RuntimeEvent::SessionTitle { sequence: 1, .. },
                RuntimeEvent::Final { sequence: 2, .. }
            ]
        ));
        let events = super::stream(
            stream::iter([final_event()]).boxed(),
            Some(
                async {
                    tokio::time::sleep(std::time::Duration::from_secs(10)).await;
                    Some("late".into())
                }
                .boxed(),
            ),
        )
        .collect::<Vec<_>>()
        .await;
        assert!(matches!(&events[..], [RuntimeEvent::Final { .. }]));
    }

    #[tokio::test]
    async fn title_insertion_preserves_trace_order_and_sequences_the_whole_stream() {
        let events = super::stream(
            stream::iter([
                RuntimeEvent::ToolCall {
                    sequence: 80,
                    tool_name: "search_documents",
                    call_id: "search".into(),
                    arguments: serde_json::Map::new(),
                },
                RuntimeEvent::ToolResult {
                    sequence: 81,
                    tool_name: "search_documents",
                    call_id: "search".into(),
                    content: "[]".into(),
                    is_error: false,
                    latency_ms: 1,
                },
                RuntimeEvent::Final {
                    sequence: 82,
                    content: "answer".into(),
                    sources: vec![],
                    finish_reason: "stop",
                },
            ])
            .boxed(),
            Some(async { Some("session".into()) }.boxed()),
        )
        .collect::<Vec<_>>()
        .await;
        let wire: Vec<_> = events
            .iter()
            .map(|event| serde_json::to_value(event).unwrap())
            .collect();
        assert_eq!(wire.len(), 4);
        for (index, event) in wire.iter().enumerate() {
            assert_eq!(event["sequence"], index + 1);
        }
        assert_eq!(wire.last().unwrap()["kind"], "final");
        assert_eq!(
            wire.iter()
                .filter_map(|event| event["kind"].as_str())
                .filter(|kind| kind.starts_with("tool_"))
                .collect::<Vec<_>>(),
            ["tool_call", "tool_result"]
        );
    }
}
