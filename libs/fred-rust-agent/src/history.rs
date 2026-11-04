// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Rig's durable conversation projected into the shared Python/browser history contract.

use chrono::{DateTime, SecondsFormat, Utc};
use rig_core::{
    conversation::Conversation,
    message::{AssistantContent, Message, ToolResultContent, UserContent},
};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::search::{self, SearchHit};

#[derive(Debug, Serialize, utoipa::ToSchema)]
pub struct ChatMessage {
    pub session_id: String,
    pub exchange_id: String,
    pub rank: usize,
    pub timestamp: String,
    pub role: &'static str,
    pub channel: &'static str,
    pub parts: Vec<MessagePart>,
    pub metadata: ChatMetadata,
}

#[derive(Debug, Serialize, utoipa::ToSchema)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum MessagePart {
    Text {
        text: String,
    },
    ToolCall {
        call_id: String,
        name: String,
        args: Map<String, Value>,
    },
    ToolResult {
        call_id: String,
        ok: bool,
        content: String,
    },
}

#[derive(Debug, Default, Serialize, utoipa::ToSchema)]
pub struct ChatMetadata {
    pub sources: Vec<SearchHit>,
}

/// A saved successful run contains one user request, optional tool messages and
/// one answer. Reasoning and pre-tool text are deliberately not replayed as finals.
pub fn messages(conversation: &Conversation, session_id: &str) -> Vec<ChatMessage> {
    let mut messages = Vec::new();
    let mut exchange_id = String::new();
    let mut sources = Vec::new();
    for entry in conversation.entries() {
        if entry.is_users_own() {
            exchange_id = entry.id.to_string();
            sources.clear();
        }
        let timestamp = i64::try_from(entry.made)
            .ok()
            .and_then(DateTime::<Utc>::from_timestamp_millis)
            .unwrap_or(DateTime::<Utc>::UNIX_EPOCH)
            .to_rfc3339_opts(SecondsFormat::Millis, true);
        let mut push = |role, channel, part, sources| {
            messages.push(ChatMessage {
                session_id: session_id.into(),
                exchange_id: exchange_id.clone(),
                rank: messages.len(),
                timestamp: timestamp.clone(),
                role,
                channel,
                parts: vec![part],
                metadata: ChatMetadata { sources },
            });
        };
        match entry.message {
            Message::User { content } => {
                let text: String = content
                    .iter()
                    .filter_map(|part| match part {
                        UserContent::Text(text) => Some(text.text.as_str()),
                        _ => None,
                    })
                    .collect();
                if entry.is_users_own() {
                    push("user", "final", MessagePart::Text { text }, vec![]);
                }
                for part in content {
                    if let UserContent::ToolResult(result) = part {
                        let content: String = result
                            .content
                            .iter()
                            .filter_map(|part| match part {
                                ToolResultContent::Text(text) => Some(text.text.as_str()),
                                _ => None,
                            })
                            .collect();
                        if !result.is_error && result.name.as_str() == search::TOOL_NAME {
                            #[derive(Deserialize)]
                            struct Evidence {
                                hits: Vec<SearchHit>,
                            }
                            if let Ok(evidence) = serde_json::from_str::<Evidence>(&content) {
                                sources = search::citable_sources(evidence.hits);
                            }
                        }
                        push(
                            "tool",
                            "tool_result",
                            MessagePart::ToolResult {
                                call_id: result.call.to_string(),
                                ok: !result.is_error,
                                content,
                            },
                            vec![],
                        );
                    }
                }
            }
            Message::Assistant(assistant) => {
                let mut has_calls = false;
                for part in &assistant.content {
                    if let AssistantContent::ToolCall(call) = part {
                        has_calls = true;
                        push(
                            "assistant",
                            "tool_call",
                            MessagePart::ToolCall {
                                call_id: call.id.to_string(),
                                name: call.function.name.to_string(),
                                args: call.function.arguments.clone(),
                            },
                            vec![],
                        );
                    }
                }
                if !has_calls {
                    let text: String = assistant
                        .content
                        .iter()
                        .filter_map(|part| match part {
                            AssistantContent::Text(text) => Some(text.text.as_str()),
                            _ => None,
                        })
                        .collect();
                    push(
                        "assistant",
                        "final",
                        MessagePart::Text { text },
                        std::mem::take(&mut sources),
                    );
                }
            }
            Message::System { .. } => {}
        }
    }
    messages
}

#[cfg(test)]
mod tests {
    use super::*;
    use futures::StreamExt;
    use serde_json::json;
    use std::time::Duration;

    use crate::{answer, testing::Provider};

    #[tokio::test]
    async fn saved_search_turn_matches_the_shared_history_contract() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../fred-sdk/tests/fixtures/embedded_search_turn.json"
        ))
        .unwrap();
        let provider = Provider::script(vec![
            (Duration::ZERO, 200, json!({"choices":[{"index":0,"message":{"role":"assistant","content":"Searching first",
                "tool_calls":[{"id":"call-search","type":"function","function":{
                    "name":"search_documents","arguments":"{\"query\":\"manual question\"}"}}]},"finish_reason":"tool_calls"}]})),
            (Duration::ZERO, 200, json!({"choices":[{"index":0,"message":{"role":"assistant","content":fixture["final"]["content"]},"finish_reason":"stop"}]})),
        ]).await;
        let store = rig_memory::MemoryStore::default();
        let hits: Vec<SearchHit> =
            serde_json::from_value(fixture["knowledge_flow_hits"].clone()).unwrap();
        let events: Vec<_> = answer::execute(
            provider.turn(),
            "manual question".into(),
            Some((store.clone(), "chat".into())),
            Some(|_| async move { Ok(hits) }),
            |_| {},
        )
        .collect()
        .await;
        assert!(matches!(
            events.last(),
            Some(crate::RuntimeEvent::Final { .. })
        ));
        let conversation = rig_memory::load(&store, "chat").unwrap();
        let mut wire = serde_json::to_value(messages(&conversation, "session")).unwrap();
        for row in wire.as_array_mut().unwrap() {
            assert!(!row["exchange_id"].as_str().unwrap().is_empty());
            assert!(DateTime::parse_from_rfc3339(row["timestamp"].as_str().unwrap()).is_ok());
            row["exchange_id"] = json!("exchange");
            row["timestamp"] = json!("2026-11-04T12:00:00.000Z");
        }
        assert_eq!(wire, fixture["history"]);
    }

    #[test]
    fn successive_exchanges_keep_distinct_ids_and_increasing_ranks() {
        let conversation = Conversation::from_messages([
            Message::user("first"),
            Message::assistant("answer one"),
            Message::user("second"),
            Message::assistant("answer two"),
        ]);
        let rows = messages(&conversation, "session");
        assert_eq!(rows.len(), 4);
        assert_eq!(rows[0].exchange_id, rows[1].exchange_id);
        assert_eq!(rows[2].exchange_id, rows[3].exchange_id);
        assert_ne!(rows[0].exchange_id, rows[2].exchange_id);
        assert_eq!(
            rows.iter().map(|row| row.rank).collect::<Vec<_>>(),
            [0, 1, 2, 3]
        );
        assert!(messages(&Conversation::new(), "empty").is_empty());
    }
}
