# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from datetime import datetime
from typing import List

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from fred_core import VectorSearchHit
from app.common.rags_client import VectorSearchClient
from app.common.rags_utils import (
    attach_sources_to_llm_response,
    ensure_ranks,
    format_sources_for_prompt,
    sort_hits,
)
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.agents.runtime_context import get_document_libraries_ids
from app.core.model.model_factory import get_model

logger = logging.getLogger(__name__)


def cir_preamble(now: str | None = None) -> str:
    now = now or datetime.now().strftime("%Y-%m-%d")
    return (
        "Tu es un expert du Crédit Impôt Recherche (CIR). "
        "Rédige en français, ton professionnel, concis et vérifiable. "
        "Appuie toujours l’argumentation sur les quatre piliers : "
        "nouveauté, incertitude scientifique/technique, démarche expérimentale systématique, création de connaissances. "
        "Réponds STRICTEMENT à partir des extraits fournis et cite chaque fait avec des marqueurs numériques [1], [2], etc., "
        "correspondant à la liste des sources. Si la preuve manque, dis-le.\n"
        f"Date courante : {now}.\n"
    )


def build_cir_prompt(preamble: str, question: str, sources_block: str) -> str:
    return (
        f"{preamble}\n"
        "Consignes :\n"
        "- Utilise UNIQUEMENT les sources ci-dessous.\n"
        "- Évite toute spéculation ; si une affirmation n’est pas étayée par les sources, abstiens-toi ou formule une réserve explicite.\n"
        "- Cite les faits par des marqueurs [n].\n\n"
        f"Question / objectif :\n{question}\n\n"
        f"Sources :\n{sources_block}\n"
    )


class EliccirAgent(AgentFlow):
    name: str = "EliccirAgent"
    role: str = "CIR Drafting Expert"
    nickname: str = "Eliccir"
    description: str
    icon: str = "report_agent"
    categories: List[str] = []
    tag: str = "CIR"

    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.name = agent_settings.name or "EliccirAgent"
        self.nickname = agent_settings.nickname or "Eliccir"
        self.role = agent_settings.role or "CIR Drafting Expert"
        self.description = agent_settings.description or "Generate CIR-ready drafts from internal evidence with strict citations."
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.categories = agent_settings.categories or ["Compliance", "Documentation"]
        self.knowledge_flow_url = agent_settings.settings.get(
            "knowledge_flow_url", "http://localhost:8111/knowledge-flow/v1"
        )
        self.model = None
        self.base_prompt = ""
        self._graph = None
        self.tag = agent_settings.tag or "CIR"

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        self.search_client = VectorSearchClient(self.knowledge_flow_url, timeout_s=10)
        self.base_prompt = cir_preamble(self.current_date)
        self._graph = self._build_graph()

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

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self._run_reasoning_step)
        builder.add_edge(START, "reasoner")
        builder.add_edge("reasoner", END)
        return builder

    async def _run_reasoning_step(self, state: MessagesState):
        if self.model is None:
            raise RuntimeError("Model is not initialized. Did you forget to call async_init()?")

        msg = state["messages"][-1]
        if not isinstance(msg.content, str):
            raise TypeError(f"Expected string content, got: {type(msg.content).__name__}")
        question = msg.content or "Ébaucher un brouillon de rapport CIR sur la base des documents fournis."

        try:
            # 1) Vector search (same pattern as Rico)
            top_k = 6
            tags = get_document_libraries_ids(self.get_runtime_context())
            hits: List[VectorSearchHit] = self.search_client.search(
                query=question,
                top_k=top_k,
                tags=tags,  # library scoping
                metadata_any={"tags": ["verrou", "experiment", "failure"]}, 
                boost_tags=["verrou", "experiment", "failure"],             
                boost_weight=0.15,
            )
            if not hits:
                warn = (
                    "Je n’ai pas trouvé de documents pertinents. "
                    "Ajoutez des sources (PDF, DOCX, code) ou reformulez votre demande."
                )
                return {"messages": [await self.model.ainvoke([HumanMessage(content=warn)])]}

            # 2) Deterministic ordering + ranks
            hits = sort_hits(hits)
            ensure_ranks(hits)

            # 3) Prompt build with shared utils
            sources_block = format_sources_for_prompt(hits, snippet_chars=600)
            prompt = build_cir_prompt(self.base_prompt, question, sources_block)

            # 4) Ask the model
            answer = await self.model.ainvoke([HumanMessage(content=prompt)])

            # 5) Attach rich sources metadata for the UI
            attach_sources_to_llm_response(answer, hits)

            return {"messages": [answer]}

        except Exception:
            logger.exception("Error in EliccirAgent reasoning.")
            fallback = await self.model.ainvoke(
                [HumanMessage(content="Une erreur est survenue. Veuillez réessayer plus tard.")]
            )
            return {"messages": [fallback]}
