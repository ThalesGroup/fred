// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! One admitted turn: the immutable Control Plane decision bound to its model, its
//! credential and its deadline. No discovery or policy lookup.

use std::{future::Future, sync::LazyLock, time::Duration};

use fred_rust_sdk::inference::{InferenceAdmission, InferenceCredentialBinding, ReasoningEffort};
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

/// Rig's wire facts for an admitted destination. Fred's sources are OpenAI-compatible,
/// but Rig's Mistral dialect knows better: no `stream_options`, usage on the last chunk,
/// and paths that carry their own `/v1`.
fn wire_config(api_root: &str, secret: String) -> Result<OpenAIConfig, InferenceError> {
    let root = api_root.trim_end_matches('/');
    let host = reqwest::Url::parse(root)
        .map_err(|_| InferenceError::Provisioning)?
        .host_str()
        .map(str::to_owned);
    let (dialect, base_url): (&Dialect, &str) = if host.as_deref() == Some("api.mistral.ai") {
        (&MISTRAL, root.strip_suffix("/v1").unwrap_or(root))
    } else {
        (&OPENAI, root)
    };
    Ok(OpenAIConfig::with_key(dialect, secret).with_base_url(base_url))
}

/// Owned by one turn; the credential and all model options are fixed at construction.
pub struct InferenceTurn {
    admission: InferenceAdmission,
    model: DynModel<Completion>,
    pub(crate) deadline: Instant,
    span: tracing::Span,
}

impl InferenceTurn {
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
            .filter(|b| b.source_id == admission.selection.key.source_id);
        let local = matching.next().ok_or(InferenceError::Provisioning)?;
        let selection = &admission.selection;
        let options = &selection.options;
        if matching.next().is_some()
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
        // Resolve only after checking source, destination, binding and exact revision.
        let secret = read(&local.api_key_env)
            .filter(|s| !s.is_empty())
            .ok_or(InferenceError::Credential)?;
        let http = HTTP.as_ref().map_err(|_| InferenceError::Provider)?.clone();
        let model = wire_config(&admission.connection.api_root, secret)?
            .connect(ReqwestClient::from(http))
            .chat(&selection.key.upstream_model_id)
            .into();
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
        agent
    }

    pub async fn title(self, input: &str, on_usage: impl FnOnce(Usage)) -> Option<String> {
        let input: String = input.chars().take(600).collect();
        let request = format!(
            "Name this chat conversation. Reply with the title only: 3 to 8 words, no quotes, no final punctuation, in the language of the user's message.\n\n{input}"
        );
        let started = Instant::now();
        let run = self.agent(self.generation()).build().prompt(request).run();
        let response = tokio::time::timeout(TITLE_TIMEOUT, run.instrument(self.span.clone())).await;
        self.observe(
            started,
            if matches!(response, Ok(Ok(_))) {
                "success"
            } else {
                "failure"
            },
        );
        let response = response.ok()?.ok()?;
        on_usage(response.usage());
        clean_title(&response.output())
    }

    /// The streamed answer: at most one search, and the second model call must answer.
    pub(crate) fn run<M, S, F>(
        &self,
        input: String,
        memory: Option<(M, String)>,
        search: Option<SearchTool<S>>,
    ) -> StreamingResult
    where
        M: rig_memory::AsyncStore + Send + Sync + 'static,
        S: FnOnce(String) -> F + Send + 'static,
        F: Future<Output = Result<Vec<SearchHit>, InferenceError>> + Send + 'static,
    {
        let _span = self.span.enter();
        let mut agent = self
            .agent(self.generation().parallel_tool_calls(false))
            .add_hook(NonemptyAnswer);
        if let Some((store, log)) = memory {
            agent = agent.memory(store).conversation(log);
        }
        match search {
            Some(search) => agent
                .preamble(search::INSTRUCTIONS)
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

    /// No provider error/body, URL, credential or prompt is recorded.
    pub(crate) fn observe(&self, started: Instant, outcome: &'static str) {
        let selection = &self.admission.selection;
        tracing::info!(target: "control_plane::inference", parent: &self.span, source_id = %selection.key.source_id, model = %selection.key.upstream_model_id,
            policy_revision = selection.policy_revision, source_revision = selection.source_revision,
            snapshot_revision = selection.snapshot_revision, selection = ?selection.source,
            latency_ms = started.elapsed().as_millis() as u64, outcome, "Inference completed");
    }
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
    fn mistral_uses_rigs_dialect_without_doubling_its_api_version() {
        let config = wire_config("https://api.mistral.ai/v1/", "key".into()).unwrap();
        assert_eq!(config.dialect, MISTRAL);
        assert_eq!(config.base_url, "https://api.mistral.ai");
        assert!(!config.dialect.quirks.stream_include_usage);
        assert_eq!(
            config.dialect.quirks.completion_path,
            "/v1/chat/completions"
        );
        let config = wire_config("https://gateway.example/v1", "key".into()).unwrap();
        assert_eq!(config.dialect, OPENAI);
        assert_eq!(config.base_url, "https://gateway.example/v1");
        assert!(matches!(
            wire_config("not a url", "key".into()),
            Err(InferenceError::Provisioning)
        ));
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

    #[test]
    fn mismatch_or_missing_provisioning_is_rejected_before_secret_read() {
        for field in [
            "source",
            "destination",
            "binding",
            "revision",
            "missing",
            "duplicate",
        ] {
            let a = admission();
            let mut local = provisioning(&a);
            match field {
                "source" => local.source_id = "other".into(),
                "destination" => local.api_root = "https://elsewhere.invalid/v1".into(),
                "binding" => local.credential_binding = "other".into(),
                "revision" => local.source_revision = 2,
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
        let a = admission();
        let local = provisioning(&a);
        assert!(matches!(
            InferenceTurn::provision(a, &[local], |_| None),
            Err(InferenceError::Credential)
        ));
    }
}
