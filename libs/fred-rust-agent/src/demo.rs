// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! The direct demonstration: a fixed reply, without any LLM or managed-instance authority.

use std::time::Duration;

use futures::{Stream, StreamExt, stream};

use crate::RuntimeEvent;

/// Produce the fixed response after host admission; no caller context enters the stream.
pub fn execute() -> impl Stream<Item = RuntimeEvent> {
    let events = [
        RuntimeEvent::Status {
            sequence: 1,
            status: "running",
        },
        RuntimeEvent::AssistantDelta {
            sequence: 2,
            delta: "Hello ".into(),
        },
        RuntimeEvent::AssistantDelta {
            sequence: 3,
            delta: "world!".into(),
        },
        RuntimeEvent::Final {
            sequence: 4,
            content: "Hello world!".into(),
            sources: vec![],
            finish_reason: "stop",
        },
    ];
    // Dropping the stream cancels the async delay; there is no detached producer.
    stream::iter(events).then(|event| async move {
        if matches!(&event, RuntimeEvent::AssistantDelta { .. }) {
            tokio::time::sleep(Duration::from_millis(150)).await;
        }
        event
    })
}
