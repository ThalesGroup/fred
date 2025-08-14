from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional, cast

from langgraph.graph import END, StateGraph
from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, SystemMessage, BaseMessage
import requests

from app.common.document_source import DocumentSource
from app.common.mcp_utils import get_mcp_client_for_agent
from app.common.structures import AgentSettings
from app.contrib.eliccir.eliccir_agent_toolkit import EliccirToolkit
from app.contrib.eliccir.eliccir_structures import (
    CIRAssessmentOutput,
    CIROutlineOutput,
    CIRSectionDraft,
)
from app.core.agents.flow import AgentFlow
from app.core.agents.runtime_context import get_document_libraries_ids
from app.core.chatbot.chat_schema import ChatSource
from app.core.model.model_factory import get_model
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)


class Eliccir(AgentFlow):
    name: str
    role: str
    nickname: str = "Eliccir"
    description: str
    icon: str = "report_agent"
    categories: List[str]
    tag: str = "CIR"
    mcp_client: MultiServerMCPClient
    TOP_K = 6

    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.mcp_client = MultiServerMCPClient()
        self.toolkit = None
        self.name = agent_settings.name
        self.role = agent_settings.role
        self.description = agent_settings.description
        self.categories = agent_settings.categories
        self.knowledge_flow_url = agent_settings.settings.get(
            "knowledge_flow_url", "http://localhost:8111/knowledge-flow/v1"
        )
        self.template_family = agent_settings.settings.get("template_family", "reports")
        self.default_template_id = agent_settings.settings.get(
            "default_template_id", "cir-report"
        )
        self.default_template_version = agent_settings.settings.get(
            "default_template_version", "v1"
        )
        self.instantiate_template = bool(
            agent_settings.settings.get("instantiate_template", True)
        )

        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.model = None
        self.base_prompt = ""
        self._graph = None

    async def async_init(self):
        self.mcp_client = await get_mcp_client_for_agent(self.agent_settings)
        self.model = get_model(self.agent_settings.model)
        self.base_prompt = self._base_prompt()
        self._graph = self._build_graph()
        self.toolkit = EliccirToolkit(
            self.mcp_client, lambda: self.get_runtime_context()
        )

        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self._graph,
            base_prompt=self.base_prompt,
            categories=self.categories,
            tag=self.tag,
        )

    def _base_prompt(self) -> str:
        return f"""You are a French CIR reporting expert. Be concise, factual, and auditable.
Always cover the four pillars (novelty, uncertainty, systematic approach, knowledge creation).
Cite sources with [file p.page]. Date: {self.current_date}."""

    def _build_graph(self) -> StateGraph:
        g = StateGraph(dict)
        g.add_node("retrieve", self._retrieve)
        g.add_node("assess", self._assess)
        g.add_node("outline", self._outline)
        g.add_node("draft", self._draft)
        g.add_node("compose", self._compose)
        g.add_node("materialize_template", self._materialize_template)
        g.add_node("finalize_success", self._finalize_success)
        g.add_node("finalize_failure", self._finalize_failure)

        g.set_entry_point("retrieve")
        g.add_edge("retrieve", "assess")
        g.add_conditional_edges(
            "assess",
            self._after_assess,
            {
                "outline": "outline",
                "retry": "retrieve",
                "abort": "finalize_failure",
            },
        )
        g.add_edge("outline", "draft")
        g.add_edge("draft", "compose")
        # Optional last mile (DOCX). If off, jump to finalize_success.
        g.add_conditional_edges(
            "compose",
            self._maybe_materialize,
            {
                "materialize": "materialize_template",
                "skip": "finalize_success",
            },
        )
        g.add_edge("materialize_template", "finalize_success")
        g.add_edge("finalize_success", END)
        g.add_edge("finalize_failure", END)
        return g

    # ---------- Nodes ----------

    async def _retrieve(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[BaseMessage] = state.get("messages") or []
        question = state.get("question") or (messages[-1].content if messages else "")

        top_k = state.get("top_k", self.TOP_K)
        retry_count = state.get("retry_count", 0)
        if retry_count > 0:
            top_k = min(12, self.TOP_K + 3 * retry_count)

        req = {"query": question or "Rédiger un rapport CIR", "top_k": top_k}
        library_ids = get_document_libraries_ids(self.get_runtime_context())
        if library_ids:
            req["tags"] = library_ids

        try:
            r = requests.post(
                f"{self.knowledge_flow_url}/vector/search", json=req, timeout=60
            )
            r.raise_for_status()
            raw_docs = r.json()

            docs: List[DocumentSource] = []
            for d in raw_docs:
                if "uid" in d and "document_uid" not in d:
                    d["document_uid"] = d["uid"]
                docs.append(DocumentSource(**d))

            msg = SystemMessage(
                content=json.dumps([d.model_dump() for d in docs]),
                response_metadata={
                    "thought": True,
                    "fred": {"node": "retrieve", "task": "Retrieve evidence"},
                },
            )
            return {
                "messages": [msg],
                "documents": docs,
                "question": question,
                "top_k": top_k,
                "retry_count": retry_count,
            }
        except Exception as e:
            logger.exception("CIR retrieve error: %s", e)
            return {
                "messages": [
                    SystemMessage(content="Erreur de récupération des documents.")
                ]
            }

    async def _assess(self, state: Dict[str, Any]) -> Dict[str, Any]:
        docs: List[DocumentSource] = state.get("documents", [])
        q = state.get("question", "")
        context = "\n".join(f"- {d.file_name} (p.{d.page}): {d.content}" for d in docs)

        system = """Audit CIR: produce brief bullets for each pillar and set eligibility_binary to 'yes' only if evidence clearly supports a CIR claim."""
        prompt = ChatPromptTemplate.from_messages(
            [("system", system), ("human", "Question: {q}\nDocuments:\n{context}")]
        )
        assert self.model
        chain = prompt | self.model.with_structured_output(CIRAssessmentOutput)
        assessment = cast(
            CIRAssessmentOutput, await chain.ainvoke({"q": q, "context": context})
        )

        msg = SystemMessage(
            content=assessment.model_dump_json(),
            response_metadata={
                "thought": True,
                "fred": {"node": "assess", "task": "Assess CIR pillars"},
            },
        )
        return {"messages": [msg], "assessment": assessment}

    async def _outline(self, state: Dict[str, Any]) -> Dict[str, Any]:
        assessment: CIRAssessmentOutput = state["assessment"]
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Create a French CIR report outline (4–6 sections) mapping to the pillars plus intro and conclusion.",
                ),
                ("human", "Pillars summary:\n{pillars}"),
            ]
        )
        assert self.model
        chain = prompt | self.model.with_structured_output(CIROutlineOutput)
        outline = cast(
            CIROutlineOutput,
            await chain.ainvoke({"pillars": assessment.model_dump_json()}),
        )

        if len(outline.sections) < 4:
            outline.sections = [
                "Introduction",
                "Contexte & État de l'art (Nouveauté)",
                "Incertitudes scientifiques et techniques",
                "Démarche expérimentale (Approche systématique)",
                "Résultats & Création de connaissances",
                "Conclusion",
            ]

        msg = SystemMessage(
            content=outline.model_dump_json(),
            response_metadata={
                "thought": True,
                "fred": {"node": "outline", "task": "Build outline"},
            },
        )
        return {"messages": [msg], "outline": outline}

    async def _draft(self, state: Dict[str, Any]) -> Dict[str, Any]:
        assert self.model
        outline: CIROutlineOutput = state["outline"]
        docs: List[DocumentSource] = state["documents"]
        docs_str = "\n".join(
            f"Source: {d.file_name} p.{d.page}\n{d.content}\n" for d in docs
        )

        section_prompt = ChatPromptTemplate.from_template(
            """Rédige la section: "{section_title}" en français, style audit CIR (sobre, précis), 180–300 mots.
Ajoute des citations [source: file_name p.page] aux phrases pertinentes.
N'invente rien: si l'assertion n'est pas dans les documents, reformule prudemment ou omets.
Documents:\n{context}"""
        )

        drafts: List[CIRSectionDraft] = []
        msgs: List[BaseMessage] = []
        for title in outline.sections:
            chain = section_prompt | self.model
            resp: BaseMessage = await chain.ainvoke(
                {"section_title": title, "context": docs_str}
            )
            content = resp.content  # BaseMessage always has .content
            if not isinstance(content, str):
                content = str(content)
            drafts.append(
                CIRSectionDraft(section_title=title, content_markdown=content)
            )
            msgs.append(
                AIMessage(
                    content=content,
                    response_metadata={
                        "thought": True,
                        "fred": {"node": "draft", "task": f"Draft {title}"},
                    },
                )
            )
        # For UI sources
        sources: List[ChatSource] = [
            ChatSource(
                document_uid=getattr(d, "document_uid", getattr(d, "uid", "unknown")),
                file_name=d.file_name,
                title=d.title,
                author=d.author,
                content=d.content,
                created=d.created,
                modified=d.modified or "",
                type=d.type,
                score=d.score,
            )
            for d in docs
        ]
        return {
            "messages": msgs,
            "drafts": [d.model_dump() for d in drafts],
            "sources": [s.model_dump() for s in sources],
        }

    async def _compose(self, state: Dict[str, Any]) -> Dict[str, Any]:
        drafts = state.get("drafts", [])
        md = ["# Rapport CIR (brouillon)\n"]
        for d in drafts:
            md.append(f"## {d['section_title']}\n\n{d['content_markdown']}\n")
        content = "\n".join(md)
        msg = SystemMessage(
            content=content,
            response_metadata={
                "thought": True,
                "fred": {"node": "compose", "task": "Assemble markdown"},
            },
        )
        return {
            "messages": [msg],
            "report_markdown": content,
            "generation": AIMessage(
                content=content, response_metadata={"sources": state.get("sources", [])}
            ),
        }

    async def _materialize_template(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call Templates MCP to instantiate a DOCX from the composed content.
        Assumes MCP server exposes 'templates.instantiate'.
        """

        # Build a minimal inputInline matching your manifest's inputSchema.
        # Map drafted sections to the schema fields expected by your template.
        input_inline = {
            "annee": datetime.now().strftime("%Y"),
            "sections": [
                {"title": d["section_title"], "content": d["content_markdown"]}
                for d in state.get("drafts", [])
            ],
            "glossaire": {},  # you can fill later
        }

        try:
            assert self.toolkit
            tool = self.toolkit.get_tool("templates.instantiate")
            if tool is None:
                raise RuntimeError(
                    f"templates.instantiate not found. Tools available: {[t.name for t in self.toolkit.get_tools()]}"
                )
            result = await tool.invoke(
                {
                    "id": self.default_template_id,
                    "version": self.default_template_version,
                    "inputInline": input_inline,
                }
            )
            artifact_path = result.get("artifactPath", "")
            note = (
                f"Document généré: {artifact_path}"
                if artifact_path
                else "Génération DOCX échouée."
            )
            msg = SystemMessage(
                content=note,
                response_metadata={
                    "thought": True,
                    "fred": {
                        "node": "materialize_template",
                        "task": "Instantiate DOCX",
                    },
                },
            )
            return {"messages": [msg], "artifact_path": artifact_path}
        except Exception as e:
            logger.exception("Template instantiation failed: %s", e)
            return {
                "messages": [
                    SystemMessage(
                        content="Échec de la génération DOCX. Brouillon Markdown prêt."
                    )
                ],
                "artifact_path": "",
            }

    async def _finalize_success(self, state: Dict[str, Any]) -> Dict[str, Any]:
        gen: AIMessage = state["generation"]
        return {
            "messages": [SystemMessage(content="Brouillon CIR prêt."), gen],
            "documents": [],
            "sources": state.get("sources", []),
            "artifact_path": state.get("artifact_path", ""),
            "retry_count": 0,
        }

    async def _finalize_failure(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "messages": [
                SystemMessage(
                    content="Impossible de produire un brouillon CIR avec les éléments fournis."
                )
            ]
        }

    # ---------- Conditionals ----------

    async def _after_assess(self, state: Dict[str, Any]) -> str:
        assessment: Optional[CIRAssessmentOutput] = state.get("assessment")
        retry = state.get("retry_count", 0)
        if not assessment:
            return "retry" if retry < 2 else "abort"
        if assessment.eligibility_binary.strip().lower() == "yes":
            return "outline"
        if retry < 1:
            state["retry_count"] = retry + 1
            return "retry"
        return "abort"

    async def _maybe_materialize(self, state: Dict[str, Any]) -> str:
        return "materialize" if self.instantiate_template else "skip"
