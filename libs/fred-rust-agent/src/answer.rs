// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! The streamed answer, on Rig's agent runtime. Rig owns the model calls, the tool loop,
//! the history and the streamed parts; this module turns them into browser events and
//! one usage report.

use std::{
    future::Future,
    sync::{Arc, OnceLock},
};

use futures::{Stream, StreamExt, stream};
use rig_agent::agent::MultiTurnStreamItem;
use rig_core::{
    completion::{FinishReason, Usage},
    message::{AssistantContent, ToolResultContent},
    streaming::{Item, Part, StreamEvent},
};
use tokio::time::Instant;

use crate::{
    RuntimeEvent,
    search::{self, SearchHit, SearchTool},
    turn::{InferenceError, InferenceTurn, public_error},
};

// One report per turn, including a decoded first response followed by cancellation.
// Keeping this guard in the polled future never detaches model or search execution.
struct TurnUsage<F: FnOnce(Usage)> {
    report: Option<F>,
    total: Option<Usage>,
}

impl<F: FnOnce(Usage)> TurnUsage<F> {
    fn record(&mut self, usage: Usage) {
        *self.total.get_or_insert_default() += usage;
    }
}

impl<F: FnOnce(Usage)> Drop for TurnUsage<F> {
    fn drop(&mut self) {
        if let (Some(report), Some(total)) = (self.report.take(), self.total.take()) {
            report(total);
        }
    }
}

/// The model's reasoning as the chat's thought events. A thought stays open from its
/// first displayable text until the reply moves on. Rig ends a reasoning part with its
/// whole text: it is news only for a part that streamed no fragment.
#[derive(Default)]
struct Thoughts {
    opened: usize,
    open: Option<String>,
    streamed: Vec<Part>,
}

impl Thoughts {
    fn delta(&mut self, phase: &'static str, part: Part, delta: String) -> Vec<RuntimeEvent> {
        if delta.trim().is_empty() {
            return vec![];
        }
        self.streamed.push(part);
        let mut events = Vec::with_capacity(2);
        let thought_id = match &self.open {
            Some(thought_id) => thought_id.clone(),
            None => {
                self.opened += 1;
                let thought_id = format!("model-{}", self.opened);
                events.push(RuntimeEvent::ThoughtStart {
                    sequence: 0,
                    thought_id: thought_id.clone(),
                    phase,
                    source: "model_native",
                });
                self.open = Some(thought_id.clone());
                thought_id
            }
        };
        events.push(RuntimeEvent::ThoughtDelta {
            sequence: 0,
            thought_id,
            delta,
        });
        events
    }

    fn end(&mut self, phase: &'static str, part: Part, text: String) -> Vec<RuntimeEvent> {
        let mut events = if self.streamed.contains(&part) {
            vec![]
        } else {
            self.delta(phase, part, text)
        };
        events.extend(self.close());
        events
    }

    fn close(&mut self) -> Option<RuntimeEvent> {
        self.open.take().map(|thought_id| RuntimeEvent::ThoughtEnd {
            sequence: 0,
            thought_id,
        })
    }
}

/// Streams the admitted answer. Dropping the stream cancels Rig's run and any search
/// in flight, and reports only the model responses already received.
pub fn execute<M, S, F>(
    turn: InferenceTurn,
    input: String,
    memory: Option<(M, String)>,
    search: Option<S>,
    on_usage: impl FnOnce(Usage) + Send,
) -> impl Stream<Item = RuntimeEvent> + Send
where
    M: rig_memory::AsyncStore + Send + Sync + 'static,
    S: FnOnce(String) -> F + Send + 'static,
    F: Future<Output = Result<Vec<SearchHit>, InferenceError>> + Send + 'static,
{
    let events = async_stream::try_stream! {
        yield RuntimeEvent::Status {
            sequence: 0,
            status: "running",
        };
        let mut usage = TurnUsage {
            report: Some(on_usage),
            total: None,
        };
        let cited = Arc::new(OnceLock::new());
        let mut run = turn.run(input, memory, search.map(|search| SearchTool::new(search, cited.clone())));
        let mut started = Instant::now();
        let mut model_calls = 0;
        let mut thoughts = Thoughts::default();
        let mut pending_call = None;
        let mut finish_reason = None;
        let answer = loop {
            let phase = if model_calls == 0 { "planning" } else { "synthesis" };
            let item = match turn.next(&mut run).await {
                Ok(Some(item)) => item,
                Ok(None) => Err(InferenceError::Provider)?,
                Err(error) => {
                    turn.observe(started, "failure");
                    // A failure closes the open tool row before the terminal error.
                    if let Some(call_id) = pending_call.take() {
                        yield RuntimeEvent::ToolResult {
                            sequence: 0,
                            tool_name: search::TOOL_NAME,
                            call_id,
                            content: public_error(&error).into(),
                            is_error: true,
                            latency_ms: started.elapsed().as_millis() as u64,
                        };
                    }
                    Err(error)?
                }
            };
            match item {
                MultiTurnStreamItem::StreamAssistantItem(Item::Event(event)) => match event {
                    StreamEvent::Reasoning { part, text } => {
                        for event in thoughts.delta(phase, part, text) {
                            yield event;
                        }
                    }
                    StreamEvent::End { part, content: AssistantContent::Reasoning(block) } => {
                        for event in thoughts.end(phase, part, block.text) {
                            yield event;
                        }
                    }
                    StreamEvent::Text { text, .. } => {
                        if let Some(event) = thoughts.close() {
                            yield event;
                        }
                        yield RuntimeEvent::AssistantDelta { sequence: 0, delta: text };
                    }
                    _ => {}
                },
                MultiTurnStreamItem::ToolCall { tool_call } => {
                    if let Some(event) = thoughts.close() {
                        yield event;
                    }
                    let call_id = tool_call.id.to_string();
                    pending_call = Some(call_id.clone());
                    started = Instant::now();
                    yield RuntimeEvent::ToolCall {
                        sequence: 0,
                        tool_name: search::TOOL_NAME,
                        call_id,
                        arguments: tool_call.function.arguments,
                    };
                }
                MultiTurnStreamItem::ToolResult { tool_result } => {
                    pending_call = None;
                    yield RuntimeEvent::ToolResult {
                        sequence: 0,
                        tool_name: search::TOOL_NAME,
                        call_id: tool_result.call.to_string(),
                        content: tool_result
                            .content
                            .into_iter()
                            .filter_map(|part| match part {
                                ToolResultContent::Text(text) => Some(text.text),
                                _ => None,
                            })
                            .collect(),
                        is_error: tool_result.is_error,
                        latency_ms: started.elapsed().as_millis() as u64,
                    };
                    started = Instant::now();
                }
                MultiTurnStreamItem::CompletionCall(call) => {
                    if let Some(event) = thoughts.close() {
                        yield event;
                    }
                    turn.observe(started, "success");
                    usage.record(call.usage);
                    model_calls += 1;
                    finish_reason = call.finish_reason;
                }
                MultiTurnStreamItem::FinalResponse(response) => break response.output(),
                _ => {}
            }
        };
        if answer.is_empty() {
            Err(InferenceError::Provider)?;
        }
        // The tool holds the only other reference to what it cited.
        drop(run);
        drop(usage);
        yield RuntimeEvent::Final {
            sequence: 0,
            content: answer,
            sources: Arc::into_inner(cited)
                .and_then(OnceLock::into_inner)
                .unwrap_or_default(),
            finish_reason: match finish_reason {
                Some(FinishReason::Stop) => "stop",
                Some(FinishReason::Length) => "length",
                Some(FinishReason::ContentFilter) => "content_filter",
                _ => "other",
            },
        };
    };
    // Drop the producer (including usage accounting) before publishing an error.
    // No spawned task or queue survives the consumer; error is terminal.
    stream::unfold(Some(Box::pin(events)), |events| async move {
        let mut events = events?;
        match events.next().await {
            Some(Ok(event)) => Some((event, Some(events))),
            Some(Err(error)) => {
                drop(events);
                Some((
                    RuntimeEvent::Error {
                        sequence: 0,
                        message: public_error(&error),
                    },
                    None,
                ))
            }
            None => None,
        }
    })
    .enumerate()
    .map(|(index, event)| event.with_sequence(index as u64 + 1))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testing::Provider;
    use serde_json::{Value, json};
    use std::{sync::Mutex, time::Duration};

    use crate::turn::TURN_TIMEOUT;

    type UnusedSearch = fn(String) -> std::future::Ready<Result<Vec<SearchHit>, InferenceError>>;

    fn without_memory<S, F>(
        turn: InferenceTurn,
        input: String,
        search: Option<S>,
        on_usage: impl FnOnce(Usage) + Send,
    ) -> impl Stream<Item = RuntimeEvent> + Send
    where
        S: FnOnce(String) -> F + Send + 'static,
        F: Future<Output = Result<Vec<SearchHit>, InferenceError>> + Send + 'static,
    {
        execute(
            turn,
            input,
            None::<(rig_memory::MemoryStore, String)>,
            search,
            on_usage,
        )
    }

    fn no_search() -> Option<UnusedSearch> {
        None
    }

    fn kinds(events: &[RuntimeEvent]) -> Vec<String> {
        events
            .iter()
            .map(|event| {
                serde_json::to_value(event).unwrap()["kind"]
                    .as_str()
                    .unwrap()
                    .to_owned()
            })
            .collect()
    }

    #[tokio::test]
    async fn memory_replays_history_and_allows_a_new_search_each_turn() {
        let store = rig_memory::MemoryStore::default();
        let provider = Provider::script(vec![
            (
                Duration::ZERO,
                200,
                search_response(json!({"query":"first"})),
            ),
            (Duration::ZERO, 200, final_response()),
            (
                Duration::ZERO,
                200,
                search_response(json!({"query":"second"})),
            ),
            (Duration::ZERO, 200, final_response()),
        ])
        .await;
        for input in ["first question", "second question"] {
            let mut events = Box::pin(execute(
                provider.turn(),
                input.into(),
                Some((store.clone(), "chat".into())),
                Some(|_| async { Ok(vec![]) }),
                |_| {},
            ));
            let mut finals = 0;
            let mut searches = 0;
            while let Some(event) = events.next().await {
                assert!(!matches!(event, RuntimeEvent::Error { .. }));
                if matches!(event, RuntimeEvent::ToolCall { .. }) {
                    searches += 1;
                }
                if matches!(event, RuntimeEvent::Final { .. }) {
                    finals += 1;
                    let saved = rig_memory::load(&store, "chat").unwrap();
                    assert_eq!(
                        saved.messages().len(),
                        if input == "first question" { 4 } else { 8 }
                    );
                }
            }
            assert_eq!((finals, searches), (1, 1));
        }
        let calls = provider.calls.lock().unwrap();
        let messages = calls[2].1["messages"].as_array().unwrap();
        let text = serde_json::to_string(messages).unwrap();
        assert!(text.contains("first question"));
        assert!(text.contains("Answer [Manual, p. 2]"));
        assert!(text.contains("second question"));
        assert_eq!(calls.len(), 4);
    }

    #[tokio::test]
    async fn cancelled_turn_does_not_persist_partial_history() {
        let store = rig_memory::MemoryStore::default();
        let provider = Provider::start(Duration::ZERO, 200).await;
        let mut events = Box::pin(execute(
            provider.turn(),
            "cancelled".into(),
            Some((store.clone(), "chat".into())),
            no_search(),
            |_| {},
        ));
        while let Some(event) = events.next().await {
            if matches!(event, RuntimeEvent::AssistantDelta { .. }) {
                break;
            }
            assert!(!matches!(
                event,
                RuntimeEvent::Final { .. } | RuntimeEvent::Error { .. }
            ));
        }
        drop(events);
        assert!(
            rig_memory::load(&store, "chat")
                .unwrap()
                .messages()
                .is_empty()
        );
    }

    struct UnwritableMemory(rig_memory::MemoryStore);

    impl rig_memory::AsyncStore for UnwritableMemory {
        async fn read_log_async(&self, name: &str) -> std::io::Result<Vec<u8>> {
            rig_memory::AsyncStore::read_log_async(&self.0, name).await
        }
        async fn append_log_async(
            &self,
            _: &str,
            _: u64,
            _: &[u8],
        ) -> Result<(), rig_memory::LogWriteError> {
            Err(std::io::Error::other("private database failure").into())
        }
        async fn replace_log_async(
            &self,
            _: &str,
            _: u64,
            _: &[u8],
        ) -> Result<(), rig_memory::LogWriteError> {
            Err(std::io::Error::other("private database failure").into())
        }
        async fn read_file_async(&self, name: &str) -> std::io::Result<Vec<u8>> {
            rig_memory::AsyncStore::read_file_async(&self.0, name).await
        }
        async fn write_file_async(&self, name: &str, bytes: &[u8]) -> std::io::Result<()> {
            rig_memory::AsyncStore::write_file_async(&self.0, name, bytes).await
        }
    }

    #[tokio::test]
    async fn failed_save_replaces_final_with_a_fixed_public_error() {
        let provider = Provider::start(Duration::ZERO, 200).await;
        let events: Vec<_> = execute(
            provider.turn(),
            "question".into(),
            Some((
                UnwritableMemory(rig_memory::MemoryStore::default()),
                "chat".into(),
            )),
            no_search(),
            |_| {},
        )
        .collect()
        .await;
        assert!(
            events
                .iter()
                .any(|event| matches!(event, RuntimeEvent::AssistantDelta { .. }))
        );
        assert!(
            !events
                .iter()
                .any(|event| matches!(event, RuntimeEvent::Final { .. }))
        );
        assert!(
            matches!(events.last(), Some(RuntimeEvent::Error { message, .. }) if *message == "Conversation history could not be loaded or saved.")
        );
    }

    #[tokio::test]
    async fn stream_uses_real_rig_response_and_finishes_once() {
        let provider = Provider::start(Duration::ZERO, 200).await;
        let events: Vec<_> =
            without_memory(provider.turn(), "question".into(), no_search(), |_| {})
                .collect()
                .await;
        assert_eq!(
            kinds(&events),
            ["status", "assistant_delta", "assistant_delta", "final"]
        );
        assert!(
            matches!(&events[3], RuntimeEvent::Final { content, finish_reason: "stop", .. } if content == "simulated answer")
        );
        {
            let calls = provider.calls.lock().unwrap();
            assert_eq!(calls.len(), 1);
            assert_eq!(calls[0].1["stream"], true);
            assert_eq!(calls[0].1["temperature"], 0.2);
            assert_eq!(calls[0].1["top_p"], 0.8);
        }
        let failing = Provider::start(Duration::ZERO, 401).await;
        let events: Vec<_> = without_memory(failing.turn(), "question".into(), no_search(), |_| {
            panic!("failed inference has no usage")
        })
        .collect()
        .await;
        assert_eq!(kinds(&events), ["status", "execution_error"]);
    }

    #[tokio::test]
    async fn a_delta_reaches_the_consumer_before_the_provider_finishes() {
        let provider = Provider::script(vec![(Duration::ZERO, 200, json!({
            "gap_ms": 60_000,
            "choices":[{"index":0,"message":{"role":"assistant","content":"first second"},"finish_reason":"stop"}]
        }))])
        .await;
        let reports = Arc::new(Mutex::new(Vec::new()));
        let captured = reports.clone();
        let mut events = Box::pin(without_memory(
            provider.turn(),
            "question".into(),
            no_search(),
            move |usage| captured.lock().unwrap().push(usage),
        ));
        events.next().await;
        let delta = tokio::time::timeout(Duration::from_secs(5), events.next())
            .await
            .expect("the first fragment must not wait for the end of the answer");
        assert!(
            matches!(delta, Some(RuntimeEvent::AssistantDelta { delta, .. }) if delta == "first ")
        );
        // No decoded response yet: a browser leaving mid-answer reports nothing.
        drop(events);
        assert!(reports.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn a_stream_cut_before_its_end_is_an_error_and_not_an_answer() {
        let provider = Provider::script(vec![(Duration::ZERO, 200, json!({
            "truncated": true,
            "choices":[{"index":0,"message":{"role":"assistant","content":"partial answer"},"finish_reason":"stop"}]
        }))])
        .await;
        let events: Vec<_> =
            without_memory(provider.turn(), "question".into(), no_search(), |_| {})
                .collect()
                .await;
        assert!(matches!(events.last(), Some(RuntimeEvent::Error { .. })));
        assert!(!kinds(&events).contains(&"final".to_owned()));
    }

    #[tokio::test]
    async fn native_reasoning_uses_shared_events_without_opaque_provider_data() {
        let provider = Provider::script(vec![(Duration::ZERO, 200, json!({
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": "answer",
                "reasoning_content": "Provider explanation",
                "reasoning_details": [{"type": "reasoning.encrypted", "data": "private-opaque-payload"}]
            }}]
        }))]).await;
        let events: Vec<_> =
            without_memory(provider.turn(), "question".into(), no_search(), |_| {})
                .collect()
                .await;
        assert_eq!(
            kinds(&events),
            [
                "status",
                "thought_start",
                "thought_delta",
                "thought_end",
                "assistant_delta",
                "final"
            ]
        );
        let wire: Vec<_> = events
            .iter()
            .map(|event| serde_json::to_value(event).unwrap())
            .collect();
        assert_eq!(wire[1]["source"], "model_native");
        assert_eq!(wire[1]["phase"], "planning");
        assert_eq!(wire[2]["delta"], "Provider explanation");
        assert_eq!(wire[1]["thought_id"], wire[2]["thought_id"]);
        assert_eq!(wire[2]["thought_id"], wire[3]["thought_id"]);
        assert!(
            !serde_json::to_string(&wire)
                .unwrap()
                .contains("private-opaque-payload")
        );
        for (index, event) in wire.iter().enumerate() {
            assert_eq!(event["sequence"], index + 1);
        }
    }

    #[tokio::test]
    async fn tool_events_precede_work_and_cancellation_at_either_boundary_stops_execution() {
        for after_result in [false, true] {
            let provider = Provider::script(vec![
                (
                    Duration::ZERO,
                    200,
                    search_response(json!({"query": "question"})),
                ),
                (Duration::ZERO, 200, final_response()),
            ])
            .await;
            let searched = Arc::new(std::sync::atomic::AtomicBool::new(false));
            let called = searched.clone();
            let reports = Arc::new(Mutex::new(Vec::new()));
            let captured = reports.clone();
            let mut events = Box::pin(without_memory(
                provider.turn(),
                "question".into(),
                Some(move |_| async move {
                    called.store(true, std::sync::atomic::Ordering::SeqCst);
                    Ok(vec![])
                }),
                move |usage| captured.lock().unwrap().push(usage),
            ));
            assert!(matches!(
                events.next().await,
                Some(RuntimeEvent::Status { .. })
            ));
            assert!(matches!(
                events.next().await,
                Some(RuntimeEvent::ToolCall { .. })
            ));
            assert!(!searched.load(std::sync::atomic::Ordering::SeqCst));
            if after_result {
                assert!(matches!(
                    events.next().await,
                    Some(RuntimeEvent::ToolResult {
                        is_error: false,
                        ..
                    })
                ));
                assert!(searched.load(std::sync::atomic::Ordering::SeqCst));
            }
            drop(events);
            assert_eq!(provider.calls.lock().unwrap().len(), 1);
            let reports = reports.lock().unwrap();
            assert_eq!(reports.len(), 1);
            assert_eq!(reports[0].input_tokens, Some(2));
        }
    }

    #[tokio::test]
    async fn expired_turn_never_starts_search_after_a_trace_delivery_pause() {
        let provider = Provider::script(vec![(
            Duration::ZERO,
            200,
            search_response(json!({"query": "question"})),
        )])
        .await;
        let reports = Arc::new(Mutex::new(Vec::new()));
        let captured = reports.clone();
        let mut events = Box::pin(without_memory(
            provider.turn(),
            "question".into(),
            Some(|_| {
                std::future::poll_fn::<Result<Vec<SearchHit>, InferenceError>, _>(|_| {
                    panic!("expired turn must not invoke search")
                })
            }),
            move |usage| captured.lock().unwrap().push(usage),
        ));
        assert!(matches!(
            events.next().await,
            Some(RuntimeEvent::Status { .. })
        ));
        assert!(matches!(
            events.next().await,
            Some(RuntimeEvent::ToolCall { .. })
        ));
        tokio::time::pause();
        tokio::time::advance(TURN_TIMEOUT).await;
        assert!(matches!(
            events.next().await,
            Some(RuntimeEvent::ToolResult { is_error: true, .. })
        ));
        assert!(matches!(
            events.next().await,
            Some(RuntimeEvent::Error { .. })
        ));
        // Accounting is complete before the terminal error reaches the browser.
        assert_eq!(reports.lock().unwrap().len(), 1);
        assert!(events.next().await.is_none());
        assert_eq!(provider.calls.lock().unwrap().len(), 1);
    }

    #[tokio::test]
    async fn usage_is_reported_once_before_the_last_event_even_without_displayable_text() {
        // Rig preserves an empty completion when the model's token limit is reached.
        for (content, reason) in [("simulated answer", "stop"), ("", "length")] {
            let provider = Provider::with_response(Duration::ZERO, 200, content, reason).await;
            let reported = Arc::new(Mutex::new(Vec::new()));
            let captured = reported.clone();
            let mut events = Box::pin(without_memory(
                provider.turn(),
                "question".into(),
                no_search(),
                move |usage| {
                    captured
                        .lock()
                        .unwrap()
                        .push((usage.input_tokens, usage.output_tokens));
                },
            ));
            while let Some(event) = events.next().await {
                let terminal = matches!(
                    event,
                    RuntimeEvent::Final { .. } | RuntimeEvent::Error { .. }
                );
                assert_eq!(reported.lock().unwrap().is_empty(), !terminal);
                assert_eq!(
                    matches!(event, RuntimeEvent::Error { .. }),
                    terminal && content.is_empty()
                );
            }
            assert_eq!(*reported.lock().unwrap(), vec![(Some(2), Some(2))]);
        }
    }

    fn search_response(arguments: Value) -> Value {
        json!({"choices":[{"index":0,"message":{"role":"assistant","content":null,
            "tool_calls":[{"id":"call-search","type":"function","function":{
                "name":"search_documents","arguments":arguments.to_string()}}]},"finish_reason":"tool_calls"}]})
    }

    fn final_response() -> Value {
        json!({"choices":[{"index":0,"message":{"role":"assistant","content":"Answer [Manual, p. 2]"},"finish_reason":"stop"}]})
    }

    // Shared with the Python event contract and the chat's rendering test.
    fn shared_search_turn() -> Value {
        serde_json::from_str(include_str!(
            "../../fred-sdk/tests/fixtures/embedded_search_turn.json"
        ))
        .unwrap()
    }

    fn hits_of(contract: &Value) -> Vec<SearchHit> {
        serde_json::from_value(contract["knowledge_flow_hits"].clone()).unwrap()
    }

    #[tokio::test]
    async fn search_events_match_the_shared_chat_contract() {
        let contract = shared_search_turn();
        let hits = hits_of(&contract);
        let provider = Provider::script(vec![
            (
                Duration::ZERO,
                200,
                search_response(json!({"query":contract["query"]})),
            ),
            (Duration::ZERO, 200, final_response()),
        ])
        .await;
        let events: Vec<_> = without_memory(
            provider.turn(),
            "question".into(),
            Some(move |_| async move { Ok(hits) }),
            |_| {},
        )
        .collect()
        .await;
        let wire: Vec<_> = events
            .iter()
            .map(|event| serde_json::to_value(event).unwrap())
            .collect();
        let of = |kind: &str| {
            wire.iter()
                .find(|event| event["kind"] == kind)
                .unwrap()
                .clone()
        };
        let mut result = of("tool_result");
        result["latency_ms"] = contract["tool_result"]["latency_ms"].clone();
        assert_eq!(result, contract["tool_result"]);
        let mut last = of("final");
        last["sequence"] = contract["final"]["sequence"].clone();
        assert_eq!(last, contract["final"]);
    }

    #[tokio::test]
    async fn one_search_returns_a_correlated_result_and_one_aggregate_report() {
        let contract = shared_search_turn();
        for hits in [vec![], hits_of(&contract)] {
            let expected = search::Evidence::new("manual question", hits.clone()).unwrap();
            let provider = Provider::script(vec![
                (
                    Duration::ZERO,
                    200,
                    search_response(json!({"query":"manual question"})),
                ),
                (Duration::ZERO, 200, final_response()),
            ])
            .await;
            let reports = Arc::new(Mutex::new(Vec::new()));
            let captured = reports.clone();
            let events: Vec<_> = without_memory(
                provider.turn(),
                "question".into(),
                Some(move |query| async move {
                    assert_eq!(query, "manual question");
                    Ok(hits)
                }),
                move |usage| captured.lock().unwrap().push(usage),
            )
            .collect()
            .await;
            assert_eq!(&kinds(&events)[..3], ["status", "tool_call", "tool_result"]);
            assert!(
                matches!(&events[1], RuntimeEvent::ToolCall { call_id, arguments, .. }
                if call_id == "call-search" && arguments["query"] == "manual question")
            );
            assert!(
                matches!(&events[2], RuntimeEvent::ToolResult { call_id, content, is_error: false, .. }
                if call_id == "call-search" && *content == expected.tool_content)
            );
            assert_eq!(
                serde_json::to_value(events.last().unwrap()).unwrap()["sources"],
                serde_json::to_value(&expected.sources).unwrap()
            );
            for (index, event) in events.iter().enumerate() {
                assert_eq!(serde_json::to_value(event).unwrap()["sequence"], index + 1);
            }
            let reports = reports.lock().unwrap();
            assert_eq!(reports.len(), 1);
            assert_eq!(
                (reports[0].input_tokens, reports[0].output_tokens),
                (Some(4), Some(4))
            );
            let calls = provider.calls.lock().unwrap();
            assert_eq!(calls.len(), 2);
            assert_eq!(calls[0].1["tools"].as_array().unwrap().len(), 1);
            assert_eq!(
                calls[0].1["tools"][0]["function"]["name"],
                "search_documents"
            );
            assert_eq!(calls[0].1["parallel_tool_calls"], false);
            assert_ne!(calls[0].1["tool_choice"], "none");
            assert_eq!(calls[1].1["tool_choice"], "none");
            assert_eq!(calls[1].1["tools"], calls[0].1["tools"]);
            let messages = calls[1].1["messages"].as_array().unwrap();
            let tool = messages.last().unwrap();
            assert_eq!(tool["role"], "tool");
            assert_eq!(tool["tool_call_id"], "call-search");
            assert_eq!(tool["content"], expected.tool_content);
            let assistant = &messages[messages.len() - 2];
            assert_eq!(assistant["tool_calls"][0]["id"], "call-search");
            assert_eq!(calls[0].0["authorization"], calls[1].0["authorization"]);
            for field in [
                "model",
                "temperature",
                "top_p",
                "max_tokens",
                "reasoning_effort",
            ] {
                assert_eq!(calls[0].1[field], calls[1].1[field]);
            }
        }
    }

    #[tokio::test]
    async fn the_model_answers_a_failed_search_and_a_second_search_never_runs() {
        for failure in ["search", "arguments", "provider", "extra_call"] {
            let args = if failure == "arguments" {
                json!({"query":"question","space_id":"untrusted"})
            } else {
                json!({"query":"question"})
            };
            let provider = Provider::script(vec![
                (Duration::ZERO, 200, search_response(args)),
                (
                    Duration::ZERO,
                    if failure == "provider" { 500 } else { 200 },
                    if failure == "extra_call" {
                        search_response(json!({"query":"again"}))
                    } else {
                        final_response()
                    },
                ),
            ])
            .await;
            let searches = Arc::new(std::sync::atomic::AtomicUsize::new(0));
            let counted = searches.clone();
            let reports = Arc::new(Mutex::new(Vec::new()));
            let captured = reports.clone();
            let events: Vec<_> = without_memory(
                provider.turn(),
                "question".into(),
                Some(move |_| async move {
                    counted.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                    if failure == "search" {
                        Err(InferenceError::Search)
                    } else {
                        Ok(vec![])
                    }
                }),
                move |usage| captured.lock().unwrap().push(usage),
            )
            .collect()
            .await;
            let answered = ["search", "arguments"].contains(&failure);
            assert_eq!(
                matches!(events.last(), Some(RuntimeEvent::Final { .. })),
                answered,
                "{failure}"
            );
            assert_eq!(
                matches!(events.last(), Some(RuntimeEvent::Error { .. })),
                !answered,
                "{failure}"
            );
            assert_eq!(
                matches!(&events[2], RuntimeEvent::ToolResult { is_error: true, .. }),
                answered,
                "{failure}"
            );
            if failure == "search" {
                assert!(
                    matches!(&events[2], RuntimeEvent::ToolResult { content, .. }
                    if content == public_error(&InferenceError::Search))
                );
            }
            assert_eq!(
                searches.load(std::sync::atomic::Ordering::SeqCst),
                usize::from(failure != "arguments"),
                "invalid arguments never reach KF, and a second search never runs"
            );
            let reports = reports.lock().unwrap();
            assert_eq!(reports.len(), 1);
            // Rig fails a refused call mid-reply, before that reply reports its usage.
            let tokens = Some(if answered { 4 } else { 2 });
            assert_eq!(
                (reports[0].input_tokens, reports[0].output_tokens),
                (tokens, tokens),
                "{failure}"
            );
            assert_eq!(provider.calls.lock().unwrap().len(), 2, "{failure}");
        }
    }

    #[tokio::test]
    async fn cancellation_during_search_or_second_call_reports_the_first_response_once() {
        for during_search in [true, false] {
            let provider = Provider::script(vec![
                (
                    Duration::ZERO,
                    200,
                    search_response(json!({"query":"question"})),
                ),
                (Duration::from_secs(60), 200, final_response()),
            ])
            .await;
            let entered = Arc::new(tokio::sync::Notify::new());
            let notified = entered.clone();
            let reports = Arc::new(Mutex::new(Vec::new()));
            let captured = reports.clone();
            let mut events = Box::pin(without_memory(
                provider.turn(),
                "question".into(),
                Some(move |_| async move {
                    notified.notify_one();
                    if during_search {
                        std::future::pending::<()>().await;
                    }
                    Ok(vec![])
                }),
                move |usage| captured.lock().unwrap().push(usage),
            ));
            assert!(matches!(
                events.next().await,
                Some(RuntimeEvent::Status { .. })
            ));
            tokio::time::timeout(Duration::from_secs(5), async {
                tokio::select! {
                    _ = async {
                        while let Some(event) = events.next().await {
                            assert!(!matches!(event, RuntimeEvent::Final { .. } | RuntimeEvent::Error { .. }));
                        }
                    } => panic!("unexpected stream end"),
                    _ = async {
                        entered.notified().await;
                        if !during_search {
                            while provider.calls.lock().unwrap().len() < 2 {
                                tokio::time::sleep(Duration::from_millis(10)).await;
                            }
                        }
                    } => {}
                }
            })
            .await
            .unwrap();
            assert!(reports.lock().unwrap().is_empty());
            drop(events);
            let reports = reports.lock().unwrap();
            assert_eq!(reports.len(), 1);
            assert_eq!(
                (reports[0].input_tokens, reports[0].output_tokens),
                (Some(2), Some(2))
            );
            assert_eq!(
                provider.calls.lock().unwrap().len(),
                if during_search { 1 } else { 2 }
            );
        }
    }

    #[tokio::test]
    async fn cancellation_and_deadlines_stop_the_provider_call() {
        let provider = Provider::start(Duration::from_secs(60), 200).await;
        let mut events = Box::pin(without_memory(
            provider.turn(),
            "question".into(),
            no_search(),
            |_| {},
        ));
        assert!(matches!(
            events.next().await,
            Some(RuntimeEvent::Status { .. })
        ));
        drop(events);
        assert!(provider.calls.lock().unwrap().is_empty());
        let mut events = Box::pin(without_memory(
            provider.turn(),
            "question".into(),
            no_search(),
            |_| {},
        ));
        events.next().await;
        tokio::time::timeout(Duration::from_secs(5), async {
            tokio::select! {
                _ = events.next() => panic!("the provider has not answered"),
                _ = async {
                    while provider.calls.lock().unwrap().is_empty() {
                        tokio::time::sleep(Duration::from_millis(10)).await;
                    }
                } => {}
            }
        })
        .await
        .unwrap();
        drop(events);
        assert_eq!(provider.calls.lock().unwrap().len(), 1);
        let mut late = provider.turn();
        late.deadline = Instant::now();
        let events: Vec<_> = without_memory(late, "late".into(), no_search(), |_| {})
            .collect()
            .await;
        assert_eq!(kinds(&events), ["status", "execution_error"]);
        assert_eq!(provider.calls.lock().unwrap().len(), 1);
        let mut in_flight = provider.turn();
        in_flight.deadline = Instant::now() + Duration::from_millis(20);
        let events: Vec<_> = without_memory(in_flight, "in flight".into(), no_search(), |_| {})
            .collect()
            .await;
        assert_eq!(kinds(&events), ["status", "execution_error"]);
        assert_eq!(provider.calls.lock().unwrap().len(), 2);
    }
}
