from __future__ import annotations

import json
from typing import cast

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from agentic_backend.agents.v2 import BidMgrDefinition
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    ArtifactPublisherPort,
    ArtifactPublishRequest,
    AwaitingHumanRuntimeEvent,
    BoundRuntimeContext,
    ChatModelFactoryPort,
    ExecutionConfig,
    GraphRuntime,
    PortableContext,
    PortableEnvironment,
    PublishedArtifact,
    RuntimeServices,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
    ToolInvokerPort,
    inspect_agent,
)
from agentic_backend.core.agents.v2.catalog import definition_to_agent_settings
from agentic_backend.core.agents.v2.runtime import FinalRuntimeEvent, RuntimeEventKind


class StaticChatModelFactory(ChatModelFactoryPort):
    def __init__(self, model: FakeMessagesListChatModel) -> None:
        self.model = model
        self.calls: list[tuple[str, str | None]] = []

    def build(self, definition, binding: BoundRuntimeContext):  # type: ignore[override]
        self.calls.append((definition.agent_id, binding.runtime_context.session_id))
        return self.model


class RecordingArtifactPublisher(ArtifactPublisherPort):
    def __init__(self) -> None:
        self.bind_calls: list[str | None] = []
        self.requests: list[ArtifactPublishRequest] = []

    def bind(self, binding: BoundRuntimeContext) -> None:
        self.bind_calls.append(binding.runtime_context.session_id)

    async def publish(self, request: ArtifactPublishRequest) -> PublishedArtifact:
        self.requests.append(request)
        return PublishedArtifact(
            scope=request.scope,
            key=request.key or "v2/demo/bid-intake-summary.md",
            file_name=request.file_name,
            size=len(request.content_bytes),
            href="https://example.test/download/bid-intake-summary.md",
            mime=request.content_type,
            title=request.title,
        )


class RecordingToolInvoker(ToolInvokerPort):
    def __init__(self) -> None:
        self.calls: list[ToolInvocationRequest] = []

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        self.calls.append(request)
        return ToolInvocationResult(
            tool_ref=request.tool_ref,
            blocks=(
                ToolContentBlock(
                    kind=ToolContentKind.JSON,
                    data={
                        "hits": [
                            {
                                "content": (
                                    "Le dossier exige une proposition technique, un "
                                    "bordereau de prix et une habilitation de securite."
                                ),
                                "uid": "rao-1",
                                "title": "RFP Principal",
                                "score": 0.98,
                                "rank": 1,
                            }
                        ]
                    },
                ),
            ),
        )


def _binding(session_id: str) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id=session_id,
            user_id="user-1",
            language="fr",
        ),
        portable_context=PortableContext(
            request_id=f"req-{session_id}",
            correlation_id=f"corr-{session_id}",
            actor="user:demo",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            session_id=session_id,
            agent_id="bid.intake.graph.v2",
        ),
    )


@pytest.mark.asyncio
async def test_bid_intake_graph_inspection_exposes_small_workflow_preview() -> None:
    definition = BidMgrDefinition()

    inspection = inspect_agent(definition)

    assert inspection.agent_id == "bid.intake.graph.v2"
    assert inspection.execution_category.value == "graph"
    assert inspection.preview.kind.value == "mermaid"
    assert "Chercher dans le corpus bid" in inspection.preview.content
    assert "Analyser le brief client" in inspection.preview.content
    assert "Demander des clarifications" in inspection.preview.content
    assert "Construire la synthese" in inspection.preview.content


def test_bid_intake_graph_exposes_tunable_routing_lexicon_field() -> None:
    definition = BidMgrDefinition()

    routing_field = next(
        field for field in definition.fields if field.key == "routing_lexicon"
    )

    assert routing_field.type == "object"
    assert isinstance(routing_field.default, dict)
    assert "bid_signals" in routing_field.default
    assert "offre" in routing_field.default["bid_signals"]
    assert "missing_information_labels" in routing_field.default


def test_bid_intake_graph_exposes_prompt_templates_as_prompt_fields() -> None:
    definition = BidMgrDefinition()

    router_prompt_field = next(
        field for field in definition.fields if field.key == "router_prompt_template"
    )
    analysis_prompt_field = next(
        field for field in definition.fields if field.key == "analysis_prompt_template"
    )

    assert router_prompt_field.type == "prompt"
    assert isinstance(router_prompt_field.default, str)
    assert "{latest_user}" in router_prompt_field.default
    assert router_prompt_field.ui is not None
    assert router_prompt_field.ui.group == "Prompts"

    assert analysis_prompt_field.type == "prompt"
    assert isinstance(analysis_prompt_field.default, str)
    assert "{brief}" in analysis_prompt_field.default
    assert "{retrieved_context}" in analysis_prompt_field.default
    assert analysis_prompt_field.ui is not None
    assert analysis_prompt_field.ui.group == "Prompts"


def test_bid_intake_graph_exposes_retrieval_chat_options_by_default() -> None:
    definition = BidMgrDefinition()

    attach_files_field = next(
        field for field in definition.fields if field.key == "chat_options.attach_files"
    )
    libraries_field = next(
        field
        for field in definition.fields
        if field.key == "chat_options.libraries_selection"
    )
    rag_scope_field = next(
        field
        for field in definition.fields
        if field.key == "chat_options.search_rag_scoping"
    )

    assert attach_files_field.default is True
    assert libraries_field.default is True
    assert rag_scope_field.default is True

    settings = definition_to_agent_settings(
        definition,
        class_path="agentic_backend.agents.v2.candidate.bid_mgr.Definition",
    )

    assert settings.chat_options.attach_files is True
    assert settings.chat_options.libraries_selection is True
    assert settings.chat_options.search_rag_scoping is True


def test_bid_intake_graph_declares_native_corpus_search_tool() -> None:
    definition = BidMgrDefinition()

    assert len(definition.tool_requirements) == 1
    assert definition.tool_requirements[0].tool_ref == "knowledge.search"


@pytest.mark.asyncio
async def test_bid_intake_graph_returns_single_pass_summary_when_brief_is_sufficient() -> (
    None
):
    definition = BidMgrDefinition()
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content=json.dumps(
                    {
                        "route": "analyze",
                        "confidence": 0.93,
                        "reason": "Demande explicite de qualification d'une opportunite client.",
                    }
                )
            ),
            AIMessage(
                content=json.dumps(
                    {
                        "customer_name": "NATO Agency",
                        "opportunity_name": "Secure ISR Support Bid",
                        "scope_summary": (
                            "The customer needs secure ISR support services with "
                            "24/7 operational availability and transition support."
                        ),
                        "requirements": [
                            "Provide 24/7 operational support for ISR systems.",
                            "Deliver a transition plan within 30 days of contract award.",
                        ],
                        "constraints": [
                            "Budget ceiling is EUR 4M.",
                            "Service must start before 1 September 2026.",
                        ],
                        "deliverables": [
                            "Technical proposal",
                            "Operational transition plan",
                        ],
                        "compliance_items": [
                            "Personnel require NATO Secret clearance."
                        ],
                        "assumptions": [
                            "The incumbent can support transition handover."
                        ],
                        "ambiguities": [],
                        "missing_information": [],
                        "needs_clarification": False,
                        "recommended_next_step": (
                            "Transformer cette qualification en pack de cadrage Gate 1."
                        ),
                    }
                )
            ),
        ]
    )
    factory = StaticChatModelFactory(model)
    artifact_publisher = RecordingArtifactPublisher()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=factory,
            artifact_publisher=artifact_publisher,
        ),
    )
    runtime.bind(_binding("bid-intake-single-pass"))
    executor = await runtime.get_executor()

    events = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message=(
                    "Nous avons un RFP pour du support ISR securise. Le client a "
                    "besoin d'un service 24/7, d'un plan de transition, de "
                    "personnels habilites NATO Secret, d'un budget plafond de "
                    "4 MEUR et d'un demarrage avant le 1er septembre 2026."
                )
            ),
            ExecutionConfig(thread_id="bid-intake-single-pass"),
        )
    ]

    assert events[-1].kind == RuntimeEventKind.FINAL
    assert all(event.kind != RuntimeEventKind.AWAITING_HUMAN for event in events)
    final_event = cast(FinalRuntimeEvent, events[-1])
    assert "Synthese De Qualification D'Offre" in final_event.content
    assert "NATO Agency" in final_event.content
    assert "Budget ceiling is EUR 4M." in final_event.content
    assert "Technical proposal" in final_event.content
    assert "copie persistante a ete enregistree" in final_event.content
    assert len(final_event.ui_parts) == 1
    assert final_event.ui_parts[0].type == "link"
    assert artifact_publisher.bind_calls == ["bid-intake-single-pass"]
    assert artifact_publisher.requests[0].file_name == "secure-isr-support-bid.md"
    assert factory.calls == [("bid.intake.graph.v2", "bid-intake-single-pass")]


@pytest.mark.asyncio
async def test_bid_intake_graph_uses_native_corpus_search_when_tool_invoker_is_available() -> (
    None
):
    definition = BidMgrDefinition()
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content=json.dumps(
                    {
                        "route": "analyze",
                        "confidence": 0.94,
                        "reason": "Demande de synthese initiale sur un dossier d'appel d'offres.",
                    }
                )
            ),
            AIMessage(
                content=json.dumps(
                    {
                        "customer_name": "Ministere X",
                        "opportunity_name": "RAO Defense Cloud",
                        "scope_summary": "Analyse initiale du dossier RAO a partir du corpus d'equipe.",
                        "requirements": ["Fournir une proposition technique complete."],
                        "constraints": ["Une habilitation de securite est requise."],
                        "deliverables": ["Bordereau de prix", "Proposition technique"],
                        "compliance_items": ["Respect des exigences de securite."],
                        "assumptions": [],
                        "ambiguities": [],
                        "missing_information": [],
                        "needs_clarification": False,
                        "recommended_next_step": "Partager la synthese avec le bid manager pour lancer le cadrage.",
                    }
                )
            ),
        ]
    )
    factory = StaticChatModelFactory(model)
    tool_invoker = RecordingToolInvoker()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=factory,
            tool_invoker=tool_invoker,
        ),
    )
    runtime.bind(_binding("bid-intake-rag"))
    executor = await runtime.get_executor()

    events = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message="Analyse le dossier d'appel d'offres de l'equipe et fais-moi la synthese initiale."
            ),
            ExecutionConfig(thread_id="bid-intake-rag"),
        )
    ]

    assert events[-1].kind == RuntimeEventKind.FINAL
    final_event = cast(FinalRuntimeEvent, events[-1])
    assert "RAO Defense Cloud" in final_event.content
    assert len(tool_invoker.calls) == 1
    assert tool_invoker.calls[0].tool_ref == "knowledge.search"
    assert tool_invoker.calls[0].payload["top_k"] == 6
    query = tool_invoker.calls[0].payload.get("query")
    assert isinstance(query, str)
    assert "appel d'offres" in query
    assert factory.calls == [("bid.intake.graph.v2", "bid-intake-rag")]


@pytest.mark.asyncio
async def test_bid_intake_graph_requests_clarification_then_finalizes() -> None:
    definition = BidMgrDefinition()
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content=json.dumps(
                    {
                        "route": "analyze",
                        "confidence": 0.88,
                        "reason": "Demande de cadrage et d'identification des informations manquantes.",
                    }
                )
            ),
            AIMessage(
                content=json.dumps(
                    {
                        "customer_name": "French MoD",
                        "opportunity_name": "Air C2 Modernization",
                        "scope_summary": (
                            "Modernize the air command and control environment."
                        ),
                        "requirements": [
                            "Provide a resilient air C2 software baseline."
                        ],
                        "constraints": [
                            "The solution must operate on sovereign hosting."
                        ],
                        "deliverables": ["Technical and commercial proposal"],
                        "compliance_items": ["Cyber accreditation expected."],
                        "assumptions": [],
                        "ambiguities": ["No clear evaluation weighting was provided."],
                        "missing_information": [
                            "Evaluation criteria / winning factors",
                            "Target submission date",
                        ],
                        "needs_clarification": True,
                        "recommended_next_step": (
                            "Clarifier les informations d'offre manquantes avant le Gate 1."
                        ),
                    }
                )
            ),
            AIMessage(
                content=json.dumps(
                    {
                        "customer_name": "French MoD",
                        "opportunity_name": "Air C2 Modernization",
                        "scope_summary": (
                            "Modernize the air command and control environment with "
                            "a sovereign and cyber-accredited solution."
                        ),
                        "requirements": [
                            "Provide a resilient air C2 software baseline.",
                            "Provide an initial deployment plan for two air bases.",
                        ],
                        "constraints": [
                            "The solution must operate on sovereign hosting.",
                            "Submission date is 15 June 2026.",
                        ],
                        "deliverables": ["Technical and commercial proposal"],
                        "compliance_items": ["Cyber accreditation expected."],
                        "assumptions": [],
                        "ambiguities": [],
                        "missing_information": [],
                        "needs_clarification": False,
                        "recommended_next_step": (
                            "Demarrer le pack de cadrage Gate 1 avec les criteres clarifies."
                        ),
                    }
                )
            ),
        ]
    )
    factory = StaticChatModelFactory(model)
    artifact_publisher = RecordingArtifactPublisher()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=factory,
            artifact_publisher=artifact_publisher,
            checkpointer=MemorySaver(),
        ),
    )
    runtime.bind(_binding("bid-intake-clarify"))
    executor = await runtime.get_executor()

    first_run = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message=(
                    "Nous avons une offre pour la modernisation du C2 air. Le client "
                    "veut une base resiliente sur hebergement souverain, mais la note "
                    "de capture ne precise pas encore le modele de notation."
                )
            ),
            ExecutionConfig(thread_id="bid-intake-clarify"),
        )
    ]

    assert first_run[-1].kind == RuntimeEventKind.AWAITING_HUMAN
    awaiting = cast(AwaitingHumanRuntimeEvent, first_run[-1])
    assert awaiting.request.stage == "bid_intake_clarification"
    assert awaiting.request.free_text is True
    assert awaiting.request.checkpoint_id is not None
    assert "repondre en texte libre" in (awaiting.request.question or "")
    assert "Criteres d'evaluation / facteurs gagnants" in (
        awaiting.request.question or ""
    )

    resumed_run = [
        event
        async for event in executor.stream(
            definition.input_model()(message="ignored-on-resume"),
            ExecutionConfig(
                thread_id="bid-intake-clarify",
                checkpoint_id=awaiting.request.checkpoint_id,
                resume_payload={
                    "answer": (
                        "Le client a confirme une repartition 60/40 entre technique "
                        "et commercial, ainsi qu'une date cible de remise au 15 juin 2026."
                    )
                },
            ),
        )
    ]

    assert resumed_run[-1].kind == RuntimeEventKind.FINAL
    final_event = cast(FinalRuntimeEvent, resumed_run[-1])
    assert "Tours de clarification : 1" in final_event.content
    assert "Submission date is 15 June 2026." in final_event.content
    assert "Demarrer le pack de cadrage Gate 1" in final_event.content
    assert len(final_event.ui_parts) == 1
    assert final_event.ui_parts[0].type == "link"
    assert artifact_publisher.bind_calls == ["bid-intake-clarify"]
    assert artifact_publisher.requests[0].file_name == "air-c2-modernization.md"
    assert factory.calls == [
        ("bid.intake.graph.v2", "bid-intake-clarify"),
    ]


@pytest.mark.asyncio
async def test_bid_intake_graph_fallback_router_uses_centralized_lexicon_without_model() -> (
    None
):
    definition = BidMgrDefinition()
    runtime = GraphRuntime(definition=definition, services=RuntimeServices())
    runtime.bind(_binding("bid-intake-fallback-lexicon"))
    executor = await runtime.get_executor()

    events = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message=(
                    "Peux-tu cadrer ce cahier des charges et me lister les "
                    "contraintes et les livrables attendus ?"
                )
            ),
            ExecutionConfig(thread_id="bid-intake-fallback-lexicon"),
        )
    ]

    assert events[-1].kind == RuntimeEventKind.AWAITING_HUMAN
    awaiting = cast(AwaitingHumanRuntimeEvent, events[-1])
    assert awaiting.request.stage == "bid_intake_clarification"
    assert "Budget ou attentes de prix" in (awaiting.request.question or "")


@pytest.mark.asyncio
async def test_bid_intake_graph_routes_semantic_bid_request_without_keyword_fallback() -> (
    None
):
    definition = BidMgrDefinition()
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content=json.dumps(
                    {
                        "route": "analyze",
                        "confidence": 0.91,
                        "reason": "La demande vise a cadrer un dossier client et a identifier les manques.",
                    }
                )
            ),
            AIMessage(
                content=json.dumps(
                    {
                        "customer_name": "Ministere des Armees",
                        "opportunity_name": "Programme C2",
                        "scope_summary": "Cadrage initial d'un dossier client avec identification des zones a completer.",
                        "requirements": [
                            "Structurer les attentes client deja visibles dans le dossier."
                        ],
                        "constraints": [],
                        "deliverables": ["Synthese initiale de qualification"],
                        "compliance_items": [],
                        "assumptions": [],
                        "ambiguities": [
                            "Le cadre contractuel n'est pas encore explicite."
                        ],
                        "missing_information": ["Budget ou attentes de prix"],
                        "needs_clarification": False,
                        "recommended_next_step": "Partager la synthese avec le bid manager pour completer le cadrage.",
                    }
                )
            ),
        ]
    )
    factory = StaticChatModelFactory(model)
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(chat_model_factory=factory),
    )
    runtime.bind(_binding("bid-intake-semantic-router"))
    executor = await runtime.get_executor()

    events = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message="Peux-tu cadrer ce dossier client et me dire ce qu'il manque avant qu'on avance ?"
            ),
            ExecutionConfig(thread_id="bid-intake-semantic-router"),
        )
    ]

    assert events[-1].kind == RuntimeEventKind.FINAL
    final_event = cast(FinalRuntimeEvent, events[-1])
    assert "Synthese De Qualification D'Offre" in final_event.content
    assert "Programme C2" in final_event.content
    assert factory.calls == [("bid.intake.graph.v2", "bid-intake-semantic-router")]


@pytest.mark.asyncio
async def test_bid_intake_graph_rejects_unrelated_request() -> None:
    definition = BidMgrDefinition()
    runtime = GraphRuntime(definition=definition, services=RuntimeServices())
    runtime.bind(_binding("bid-intake-unsupported"))
    executor = await runtime.get_executor()

    events = [
        event
        async for event in executor.stream(
            definition.input_model()(
                message="Quel temps fait-il a Paris aujourd'hui ?"
            ),
            ExecutionConfig(thread_id="bid-intake-unsupported"),
        )
    ]

    assert [event.kind.value for event in events] == [RuntimeEventKind.FINAL.value]
    final_event = cast(FinalRuntimeEvent, events[-1])
    assert "workflow de qualification attend un brief client" in final_event.content
