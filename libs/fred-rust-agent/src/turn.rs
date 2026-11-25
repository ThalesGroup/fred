// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! One admitted turn: the immutable Control Plane decision bound to its model, its
//! credential and its deadline. No discovery or policy lookup.

use std::{future::Future, sync::LazyLock, time::Duration};

use fred_rust_sdk::inference::{
    InferenceAdmission, InferenceCredentialBinding, ModelConnection, ModelDialect, ModelWire,
    ReasoningEffort,
};
use futures::StreamExt;
use rig_agent::{
    AgentBuilder,
    agent::{
        AgentHook, HookContext, ModelTurnAction, ModelTurnFinished, MultiTurnStreamItem,
        StreamingResult,
    },
    completion::PromptError,
};
use rig_core::{
    DynModel,
    completion::{Effort, GenerationOptions, Usage},
    message::AssistantContent,
    operation::Completion,
    providers::openai::{
        OpenAIConfig,
        wire::{Dialect, MISTRAL, OPENAI},
    },
};
use rig_reqwest::ReqwestClient;
use tokio::time::Instant;
use tracing::Instrument;

use crate::search::{self, SearchHit, SearchTool};

pub(crate) const TURN_TIMEOUT: Duration = Duration::from_secs(120);
/// A stalled provider, not a long answer: the turn deadline bounds the whole stream.
const READ_TIMEOUT: Duration = Duration::from_secs(60);
const TITLE_TIMEOUT: Duration = Duration::from_secs(10);

/// Reject an unusable final before Rig saves the run, rather than after memory
/// has committed. A tool-call reply may legitimately have no answer text yet.
struct NonemptyAnswer;

impl AgentHook for NonemptyAnswer {
    async fn on_model_turn_finished(
        &self,
        _: &HookContext,
        event: ModelTurnFinished<'_>,
    ) -> ModelTurnAction {
        if event.content.iter().any(|part| match part {
            AssistantContent::ToolCall(_) => true,
            AssistantContent::Text(text) => !text.text.is_empty(),
            _ => false,
        }) {
            ModelTurnAction::Continue
        } else {
            ModelTurnAction::Stop("The model returned no answer text.".into())
        }
    }
}

static HTTP: LazyLock<Result<reqwest::Client, reqwest::Error>> = LazyLock::new(|| {
    reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(5))
        .read_timeout(READ_TIMEOUT)
        .pool_max_idle_per_host(32)
        .build()
});

#[derive(Debug, thiserror::Error)]
pub enum InferenceError {
    #[error("Inference provisioning is missing or inconsistent.")]
    Provisioning,
    #[error("Conversation history could not be loaded or saved.")]
    Memory,
    #[error("Inference credential is unavailable.")]
    Credential,
    #[error("Inference execution has ended or exceeded its deadline.")]
    Ended,
    #[error("The inference provider is unavailable or returned an invalid response.")]
    Provider,
    #[error("Document search is unavailable or failed.")]
    Search,
    #[error("The model requested an invalid or additional tool call.")]
    ToolCall,
}

/// Rig's wire facts for an admitted connection. Fred's sources are OpenAI-compatible,
/// but Rig's Mistral dialect knows better: no `stream_options`, usage on the last chunk.
/// `api_root` alone fixes the destination, so no dialect's own path applies: the Mistral
/// dialect assumes its bare host, where every path carries `/v1`.
fn wire_config(connection: &ModelConnection, secret: String) -> OpenAIConfig {
    let dialect: &Dialect = match connection.dialect {
        ModelDialect::Mistral => &MISTRAL,
        ModelDialect::Openai | ModelDialect::OpenaiCompatible => &OPENAI,
    };
    let mut config = OpenAIConfig::with_key(dialect, secret).with_base_url(&connection.api_root);
    config.dialect.quirks.completion_path = "/chat/completions";
    config
}

/// Owned by one turn; the credential and all model options are fixed at construction.
pub struct InferenceTurn {
    admission: InferenceAdmission,
    model: DynModel<Completion>,
    pub(crate) deadline: Instant,
    span: tracing::Span,
}

impl InferenceTurn {
    /// A server-owned catalogue credential already authenticated for this exact
    /// source/destination. Keep the same transport and option validation.
    pub fn admit_with_key(
        admission: InferenceAdmission,
        secret: String,
    ) -> Result<Self, InferenceError> {
        if admission.encrypted_credential.is_none() {
            return Err(InferenceError::Provisioning);
        }
        let binding = InferenceCredentialBinding {
            credential_binding: admission.connection.credential_binding.clone(),
            api_root: admission.connection.api_root.clone(),
            api_key_env: "MANAGED_CATALOGUE_TOKEN".into(),
        };
        Self::provision(admission, &[binding], |_| Some(secret))
    }

    pub fn admit(
        admission: InferenceAdmission,
        bindings: &[InferenceCredentialBinding],
    ) -> Result<Self, InferenceError> {
        Self::provision(admission, bindings, |name| std::env::var(name).ok())
    }

    pub(crate) fn provision(
        admission: InferenceAdmission,
        bindings: &[InferenceCredentialBinding],
        read: impl FnOnce(&str) -> Option<String>,
    ) -> Result<Self, InferenceError> {
        let mut matching = bindings
            .iter()
            .filter(|b| b.credential_binding == admission.connection.credential_binding);
        let local = matching.next().ok_or(InferenceError::Provisioning)?;
        let selection = &admission.selection;
        let options = &selection.options;
        if matching.next().is_some()
            || admission.connection.wire == ModelWire::Rerank
            || !local.matches(&admission)
            || selection.key.upstream_model_id.trim().is_empty()
            || selection.policy_revision <= 0
            || selection.snapshot_revision <= 0
            || options.temperature.is_some_and(|v| !v.is_finite())
            || options
                .top_p
                .is_some_and(|v| !v.is_finite() || !(0.0..=1.0).contains(&v))
            || options.max_tokens == Some(0)
        {
            return Err(InferenceError::Provisioning);
        }
        // Resolve only after checking binding, destination and the connection's mode.
        let secret = read(&local.api_key_env)
            .filter(|s| !s.is_empty())
            .ok_or(InferenceError::Credential)?;
        let http = HTTP.as_ref().map_err(|_| InferenceError::Provider)?.clone();
        let client = wire_config(&admission.connection, secret).connect(ReqwestClient::from(http));
        let model = match admission.connection.wire {
            ModelWire::OpenaiChat => client.chat(&selection.key.upstream_model_id).into(),
            ModelWire::OpenaiResponses => client.responses(&selection.key.upstream_model_id).into(),
            ModelWire::Rerank => return Err(InferenceError::Provisioning),
        };
        Ok(Self {
            admission,
            model,
            deadline: Instant::now() + TURN_TIMEOUT,
            span: tracing::Span::current(),
        })
    }

    fn generation(&self) -> GenerationOptions {
        let options = &self.admission.selection.options;
        let mut generation = GenerationOptions::new();
        if let Some(top_p) = options.top_p {
            generation = generation.top_p(top_p);
        }
        match options.reasoning_effort {
            Some(ReasoningEffort::High) => generation.reasoning(Effort::High),
            None => generation,
        }
    }

    /// Title and answer reuse the same admitted model and limits.
    fn agent(&self, generation: GenerationOptions) -> AgentBuilder {
        let options = &self.admission.selection.options;
        let mut agent = AgentBuilder::new(self.model.clone()).options(generation);
        if let Some(temperature) = options.temperature {
            agent = agent.temperature(temperature);
        }
        if let Some(max_tokens) = options.max_tokens {
            agent = agent.max_tokens(max_tokens);
        }
        if self.admission.connection.wire == ModelWire::OpenaiResponses {
            agent = agent.additional_params(serde_json::json!({"store": false}));
        }
        agent
    }

    pub async fn title(self, input: &str, on_usage: impl FnOnce(Usage)) -> Option<String> {
        let input: String = input.chars().take(600).collect();
        let request = format!(
            "Name this chat conversation. Reply with the title only: 3 to 8 words, no quotes, no final punctuation, in the language of the user's message.\n\n{input}"
        );
        let (text, usage) = self.complete(None, &request, TITLE_TIMEOUT).await.ok()?;
        on_usage(usage);
        clean_title(&text)
    }

    /// One generation with the already admitted connection, without history or tools.
    pub async fn complete(
        &self,
        instructions: Option<&str>,
        input: &str,
        timeout: Duration,
    ) -> Result<(String, Usage), InferenceError> {
        let started = Instant::now();
        let mut agent = self.agent(self.generation());
        if let Some(instructions) = instructions {
            agent = agent.preamble(instructions);
        }
        let run = agent.build().prompt(input).run();
        let deadline = self.deadline.min(started + timeout);
        let response = tokio::time::timeout_at(deadline, run.instrument(self.span.clone())).await;
        self.observe(
            started,
            if matches!(response, Ok(Ok(_))) {
                "success"
            } else {
                "failure"
            },
        );
        let response = response
            .map_err(|_| InferenceError::Ended)?
            .map_err(|_| InferenceError::Provider)?;
        Ok((response.output(), response.usage()))
    }

    /// The streamed answer: at most one search, and the second model call must answer.
    pub(crate) fn run<M, S, F>(
        &self,
        input: String,
        platform_prompt: Option<&str>,
        memory: Option<(M, String)>,
        search: Option<SearchTool<S>>,
    ) -> StreamingResult
    where
        M: rig_memory::AsyncStore + Send + Sync + 'static,
        S: FnOnce(String) -> F + Send + 'static,
        F: Future<Output = Result<Vec<SearchHit>, InferenceError>> + Send + 'static,
    {
        let _span = self.span.enter();
        let generation = if search.is_some() {
            self.generation().parallel_tool_calls(false)
        } else {
            self.generation()
        };
        let mut agent = self
            .agent(generation)
            .preamble(system_prompt(platform_prompt, search.is_some()))
            .add_hook(NonemptyAnswer);
        if let Some((store, log)) = memory {
            agent = agent.memory(store).conversation(log);
        }
        match search {
            Some(search) => agent
                .tool(search)
                .build()
                .prompt(input)
                .add_hook(search::AnswerAfterSearch)
                .max_turns(2)
                .stream(),
            None => agent.build().prompt(input).stream(),
        }
    }

    /// The next item of the run, within the turn deadline.
    pub(crate) async fn next(
        &self,
        run: &mut StreamingResult,
    ) -> Result<Option<MultiTurnStreamItem>, InferenceError> {
        if Instant::now() >= self.deadline {
            return Err(InferenceError::Ended);
        }
        match tokio::time::timeout_at(self.deadline, run.next()).await {
            Err(_) => Err(InferenceError::Ended),
            Ok(None) => Ok(None),
            Ok(Some(Ok(item))) => Ok(Some(item)),
            Ok(Some(Err(PromptError::Memory { .. }))) => Err(InferenceError::Memory),
            Ok(Some(Err(PromptError::MaxTurns { .. }))) => Err(InferenceError::ToolCall),
            Ok(Some(Err(_))) => Err(InferenceError::Provider),
        }
    }

    pub(crate) fn model_name(&self) -> &str {
        &self.admission.selection.key.upstream_model_id
    }

    /// No provider error/body, URL, credential or prompt is recorded.
    pub(crate) fn observe(&self, started: Instant, outcome: &'static str) {
        let selection = &self.admission.selection;
        let latency = started.elapsed();
        fred_rust_sdk::metrics::model_call(
            crate::DEFINITION.provider,
            self.model_name(),
            outcome == "success",
            latency,
        );
        tracing::info!(target: "control_plane::inference", parent: &self.span, source_id = %selection.key.source_id, model = %selection.key.upstream_model_id,
            policy_revision = selection.policy_revision, source_revision = selection.source_revision,
            snapshot_revision = selection.snapshot_revision, selection = ?selection.source,
            latency_ms = latency.as_millis() as u64, outcome, "Inference completed");
    }
}

/// One preamble for the whole tool loop; a saved empty value omits only its block.
fn system_prompt(platform_prompt: Option<&str>, search_enabled: bool) -> String {
    let blocks = [
        ("platform_instructions", crate::PLATFORM_INSTRUCTIONS),
        (
            "platform_prompt",
            platform_prompt.unwrap_or(crate::DEFAULT_PLATFORM_PROMPT),
        ),
        (
            "tools",
            if search_enabled {
                search::INSTRUCTIONS
            } else {
                ""
            },
        ),
    ];
    blocks
        .into_iter()
        .filter_map(|(tag, text)| {
            let text = text.trim();
            (!text.is_empty()).then(|| format!("<{tag}>\n{text}\n</{tag}>"))
        })
        .collect::<Vec<_>>()
        .join("\n\n")
}

fn clean_title(text: &str) -> Option<String> {
    let line: String = text
        .trim()
        .lines()
        .next()?
        .chars()
        .map(|c| {
            if c.is_alphanumeric() || c.is_whitespace() || "'’-".contains(c) {
                c
            } else {
                ' '
            }
        })
        .collect();
    let title: String = line
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .chars()
        .take(80)
        .collect();
    let title = title.trim_matches(['\'', '’', '-', ' ']);
    title
        .chars()
        .any(char::is_alphabetic)
        .then(|| title.to_owned())
}

pub(crate) fn public_error(error: &InferenceError) -> &'static str {
    match error {
        InferenceError::Memory => "Conversation history could not be loaded or saved.",
        InferenceError::Search => "Document search is unavailable or failed.",
        InferenceError::ToolCall => "The model requested an invalid or additional tool call.",
        _ => "Inference failed or exceeded its deadline.",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testing::{Provider, admission, provisioning};
    use std::sync::{Arc, Mutex};

    #[test]
    fn common_prompt_composition_keeps_runtime_and_tool_instructions() {
        for common in [None, Some(""), Some("  ")] {
            let prompt = system_prompt(common, false);
            assert!(prompt.contains(crate::PLATFORM_INSTRUCTIONS));
            assert!(!prompt.contains("<platform_prompt>"));
            assert!(!prompt.contains("<tools>"));
        }
        let prompt = system_prompt(Some("ORG RULE"), true);
        assert!(prompt.contains(search::INSTRUCTIONS));
        assert!(
            prompt.find("<platform_instructions>").unwrap()
                < prompt.find("<platform_prompt>").unwrap()
        );
        assert!(prompt.find("<platform_prompt>").unwrap() < prompt.find("<tools>").unwrap());
    }

    fn connection(api_root: &str, dialect: ModelDialect) -> ModelConnection {
        ModelConnection {
            api_root: api_root.into(),
            dialect,
            ..admission().connection
        }
    }

    #[test]
    fn the_connection_chooses_rigs_dialect_without_reading_the_host() {
        let config = wire_config(
            &connection(
                "https://gateway.example/inference/v2",
                ModelDialect::Mistral,
            ),
            "key".into(),
        );
        assert_eq!(config.dialect.name, MISTRAL.name);
        assert_eq!(config.dialect.quirks.rewrite, MISTRAL.quirks.rewrite);
        assert!(!config.dialect.quirks.stream_include_usage);
        assert_eq!(config.base_url, "https://gateway.example/inference/v2");
        let config = wire_config(
            &connection("https://api.mistral.ai/v1", ModelDialect::Openai),
            "key".into(),
        );
        assert_eq!(config.dialect, OPENAI);
        assert_eq!(config.base_url, "https://api.mistral.ai/v1");
        let config = wire_config(
            &connection("http://ollama:11434/v1", ModelDialect::OpenaiCompatible),
            "key".into(),
        );
        assert_eq!(config.dialect, OPENAI);
    }

    /// The same fixture gives Python its URLs: here is the path Rig really sends.
    #[tokio::test]
    async fn every_shared_connection_is_reached_at_its_url_or_refused_before_any_secret() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../fred-sdk/tests/fixtures/inference_connections.json"
        ))
        .unwrap();
        let mut reached = Vec::new();
        for case in fixture["valid"].as_array().unwrap() {
            let mut a = admission();
            a.connection = serde_json::from_value(case["connection"].clone()).unwrap();
            if case["ralph"] != true {
                let local = provisioning(&a);
                assert!(
                    matches!(
                        InferenceTurn::provision(a, &[local], |_| {
                            panic!("must not read a credential")
                        }),
                        Err(InferenceError::Provisioning)
                    ),
                    "{}",
                    case["name"]
                );
                continue;
            }
            let root = reqwest::Url::parse(&a.connection.api_root).unwrap();
            let provider = Provider::at(root.path()).await;
            a.connection.api_root = provider.url.clone();
            let turn = provider.turn_for(a);
            assert!(
                turn.title("question", |_| {}).await.is_some(),
                "{}",
                case["name"]
            );
            let url = reqwest::Url::parse(case["url"].as_str().unwrap()).unwrap();
            assert_eq!(
                *provider.uris.lock().unwrap(),
                [url.path()],
                "{}",
                case["name"]
            );
            reached.push(case["name"].as_str().unwrap().to_owned());
        }
        assert_eq!(
            reached,
            [
                "mistral",
                "openai-compatible",
                "Mistral dialect behind a gateway",
                "OpenAI dialect on the same gateway root"
            ]
        );
    }

    #[tokio::test]
    async fn the_title_consumes_the_admitted_decision_without_streaming() {
        let provider = Provider::start(Duration::ZERO, 200).await;
        let reports = Arc::new(Mutex::new(Vec::new()));
        let captured = reports.clone();
        let title = provider
            .turn()
            .title("question", move |usage| {
                captured.lock().unwrap().push(usage.input_tokens)
            })
            .await;
        assert_eq!(title.as_deref(), Some("simulated answer"));
        assert_eq!(*reports.lock().unwrap(), vec![Some(2)]);
        let calls = provider.calls.lock().unwrap();
        assert_eq!(calls.len(), 1);
        let (headers, body) = &calls[0];
        assert_eq!(headers["authorization"], "Bearer synthetic-inference-key");
        assert_eq!(body["model"], "model");
        assert_eq!(body["temperature"], 0.2);
        assert_eq!(body["top_p"], 0.8);
        assert_ne!(body["stream"], true);
    }

    #[tokio::test]
    async fn a_responses_completion_uses_the_bound_route_without_provider_storage() {
        use axum::{Json, Router, http::HeaderMap, routing::post};
        use serde_json::{Value, json};

        let app = Router::new().route("/v1/responses", post(|headers: HeaderMap, Json(body): Json<Value>| async move {
            assert_eq!(headers["authorization"], "Bearer synthetic-inference-key");
            assert_eq!(body["model"], "model");
            assert_eq!(body["store"], false);
            Json(json!({"id":"resp_1","object":"response","created_at":0,"status":"completed","model":"model",
                "output":[{"type":"message","id":"msg_1","role":"assistant","status":"completed",
                    "content":[{"type":"output_text","text":"draft","annotations":[]}]}],
                "usage":{"input_tokens":2,"output_tokens":3,"total_tokens":5}}))
        }));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let root = format!("http://{}/v1", listener.local_addr().unwrap());
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let mut admission = admission();
        admission.connection.api_root = root;
        admission.connection.wire = ModelWire::OpenaiResponses;
        let binding = provisioning(&admission);
        let turn = InferenceTurn::provision(admission, &[binding], |_| {
            Some("synthetic-inference-key".into())
        })
        .unwrap();
        let (text, usage) = turn
            .complete(Some("Draft agent settings"), "description", TITLE_TIMEOUT)
            .await
            .unwrap();
        server.abort();
        assert_eq!(text, "draft");
        assert_eq!(usage.output_tokens, Some(3));
    }

    #[test]
    fn mismatch_or_missing_provisioning_is_rejected_before_secret_read() {
        for field in ["destination", "binding", "missing", "duplicate"] {
            let a = admission();
            let mut local = provisioning(&a);
            match field {
                "destination" => local.api_root = "https://elsewhere.invalid/v1".into(),
                "binding" => local.credential_binding = "other".into(),
                _ => {}
            }
            let locals = match field {
                "missing" => vec![],
                "duplicate" => vec![local.clone(), local],
                _ => vec![local],
            };
            assert!(matches!(
                InferenceTurn::provision(a, &locals, |_| panic!("must not read a credential")),
                Err(InferenceError::Provisioning)
            ));
        }
        // Outside standard API-key generation: refuse before reading the secret.
        for change in [
            serde_json::json!({"auth": {"kind": "none"}}),
            serde_json::json!({"auth": {"kind": "api_key", "gateway_key_header": "x-key"}}),
        ] {
            let a = admission();
            let local = provisioning(&a);
            let mut value = serde_json::to_value(&a).unwrap();
            for (field, changed) in change.as_object().unwrap() {
                value["connection"][field] = changed.clone();
            }
            assert!(matches!(
                InferenceTurn::provision(serde_json::from_value(value).unwrap(), &[local], |_| {
                    panic!("must not read a credential")
                }),
                Err(InferenceError::Provisioning)
            ));
        }
        let a = admission();
        let local = provisioning(&a);
        assert!(matches!(
            InferenceTurn::provision(a, &[local], |_| None),
            Err(InferenceError::Credential)
        ));
    }
}
