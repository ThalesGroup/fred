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
from typing import Any, Dict, List, Literal, Optional, Sequence, cast

from fred_core import VectorSearchHit
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph

from agentic_backend.agents.rags.prompt import (
    generate_answer_prompt,
    grade_answer_prompt,
    grade_documents_prompt,
    rephrase_query_prompt,
)
from agentic_backend.agents.rags.structures import (
    GradeAnswerOutput,
    GradeDocumentsOutput,
    RagGraphState,
    RephraseQueryOutput,
)
from agentic_backend.application_context import (
    get_default_chat_model,
)
from agentic_backend.common.conversation_exporter import (
    export_conversation_to_asset,
    format_conversation_from_messages,
)
from agentic_backend.common.kf_vectorsearch_client import VectorSearchClient
from agentic_backend.common.rags_utils import attach_sources_to_llm_response
from agentic_backend.common.structures import AgentChatOptions, AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import (
    RuntimeContext,
    get_document_library_tags_ids,
    get_document_uids,
    get_search_policy,
    get_vector_search_scopes,
)
from agentic_backend.core.chatbot.chat_schema import (
    LinkKind,
    LinkPart,
    MessagePart,
    TextPart,
)
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


def mk_thought(*, label: str, node: str, task: str, content: str) -> AIMessage:
    """
    Emits an assistant-side 'thought' trace.
    - UI shows this under the Thoughts accordion (channel=thought).
    - The actual text to show must be in response_metadata['thought'].
    - Any routing/context tags go under response_metadata['extras'].
    """
    return AIMessage(
        content="",  # content is unused for thought; we put text in metadata
        response_metadata={
            "thought": content,  # <-- text the UI will render in Thoughts
            "extras": {"task": task, "node": node, "label": label},
        },
    )


def mk_tool_call(*, call_id: str, name: str, args: Dict[str, Any]) -> AIMessage:
    """
    Emits an OpenAI-style tool_call on the assistant role.
    Your SessionManager will convert it to ChatMessage(role=assistant, channel=tool_call).
    """
    return AIMessage(
        content="",
        tool_calls=[
            {
                "id": call_id,
                "name": name,
                "args": args,
            }
        ],
        response_metadata={"extras": {"task": "retrieval", "node": name}},
    )


def mk_tool_result(
    *,
    call_id: str,
    content: str,
    ok: Optional[bool] = None,
    latency_ms: Optional[int] = None,
    extras: Optional[Dict[str, Any]] = None,
    sources: Optional[list] = None,
) -> ToolMessage:
    md: Dict[str, Any] = {}
    if extras:
        md["extras"] = extras
    if latency_ms is not None:
        md["latency_ms"] = latency_ms
    if ok is not None:
        md["ok"] = ok
    if sources:
        md["sources"] = [
            s.model_dump() if hasattr(s, "model_dump") else s for s in sources
        ]
    return ToolMessage(content=content, tool_call_id=call_id, response_metadata=md)


def _chunk_key(d: VectorSearchHit) -> str:
    """
    Build a stable, collision-resistant key for a chunk based on its document ID + locators.
    Works even if some fields are missing; keeps agent grading/dedup deterministic.
    """
    uid = getattr(d, "document_uid", None) or getattr(d, "uid", "") or ""
    page = getattr(d, "page", "")
    start = getattr(d, "char_start", "")
    end = getattr(d, "char_end", "")
    # Fallbacks to reduce accidental collisions for stores without char spans
    heading = getattr(d, "heading_slug", "") or getattr(d, "heading", "") or ""
    return f"{uid}|p={page}|cs={start}|ce={end}|h={heading}"


@expose_runtime_source("agent.Rico Senior")
class AdvancedRico(AgentFlow):
    """
    AdvancedRico is a sophisticated retrieval-augmented generation (RAG) agent designed to
    handle complex query processing and document retrieval tasks. It leverages vector
    search capabilities and integrates with LangChain for natural language understanding
    and response generation. The agent supports multi-step reasoning, document grading,
    and query rephrasing to enhance the accuracy and relevance of retrieved information.
    It is built using a state machine approach for managing agent workflows and ensures
    traceability through detailed metadata and tool call handling.
    """

    MIN_DOCS = 3
    tuning = AgentTuning(
        role="Advanced Document Retrieval Expert",
        description="An advanced expert in retrieving and processing documents using enhanced retrieval-augmented generation techniques. Rico Senior is capable of handling more complex document-related tasks with improved accuracy.",
        tags=["document"],
        fields=[
            FieldSpec(
                key="prompts.grade_documents",
                type="prompt",
                title="Grade documents prompt",
                description="Prompt that evaluates whether a document is relevant or not to answer the user's question",
                required=True,
                default=grade_documents_prompt(),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.generate_answer",
                type="prompt",
                title="Generate answer prompt",
                description="Prompt that generates answers based on retrieved documents",
                required=True,
                default=generate_answer_prompt(),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.grade_answer",
                type="prompt",
                title="Grade answer prompt",
                description="Prompt that evaluates whether an answer adequately addresses a given question.",
                required=True,
                default=grade_answer_prompt(),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.rephrase_query",
                type="prompt",
                title="Rephrase query prompt",
                description="Prompt for rephrasing an input question to improve vector retrieval performance.",
                required=True,
                default=rephrase_query_prompt(),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="search.top_k",
                type="integer",
                title="TOP_K documents",
                description="Number of top chunks to retrieve during vector search",
                required=False,
                default=50,
                ui=UIHints(group="Retrieval"),
            ),
            FieldSpec(
                key="rerankink.top_r",
                type="integer",
                title="TOP_R documents",
                description="Number of top-reranked chunks to consider before grading",
                required=False,
                default=6,
                ui=UIHints(group="Reranking"),
            ),
            FieldSpec(
                key="chat_options.attach_files",
                type="boolean",
                title="Allow file attachments",
                description="Show file upload/attachment controls for this agent.",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.libraries_selection",
                type="boolean",
                title="Document libraries picker",
                description="Let users select document libraries/knowledge sources for this agent.",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.search_policy_selection",
                type="boolean",
                title="Search policy selector",
                description="Expose the search policy toggle (hybrid/semantic/strict).",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.search_rag_scoping",
                type="boolean",
                title="RAG scope selector",
                description="Expose the RAG scope control (documents-only vs hybrid vs general knowledge).",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.deep_search_delegate",
                type="boolean",
                title="Deep search delegate toggle",
                description="Allow delegation to a senior agent for deep search.",
                required=False,
                default=False,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.include_corpus_in_search",
                type="boolean",
                title="Include corpus in search",
                description="Allow corpus retrieval alongside attachments/session scope.",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="export.enable_conversation_download",
                type="boolean",
                title="Enable Conversation Download",
                description="Allow users to download the conversation history as a file.",
                required=False,
                default=True,
                ui=UIHints(group="Export"),
            ),
            FieldSpec(
                key="export.filename",
                type="text",
                title="Conversation Export Filename",
                description="The filename for exported conversations (e.g., 'conversation.txt').",
                required=False,
                default="conversation.txt",
                ui=UIHints(group="Export"),
            ),
        ],
    )

    default_chat_options = AgentChatOptions(
        search_policy_selection=True,
        libraries_selection=True,
    )

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)  # ← Important !
        self.model = get_default_chat_model()
        self.search_client = VectorSearchClient(agent=self)
        self.base_prompt = self._generate_prompt()
        self._graph = self._build_graph()

    def _generate_prompt(self) -> str:
        return (
            "You analyze retrieved document parts and answer the user's question. "
            "Always include citations when you use documents. "
            f"Current date: {self.current_date}."
        )

    def _build_graph(self) -> StateGraph:
        """
        Builds the state graph for the AdvancedRico agent workflow.

        This method defines the sequence of operations in the agent's execution flow,
        including retrieval, reranking, document grading, response generation, and
        conditional branching based on the quality of retrieved documents and generated
        responses. It sets up the entry point and all possible transitions between nodes.

        Returns:
            StateGraph: A configured StateGraph representing the agent's workflow.
        """
        builder = StateGraph(RagGraphState)

        builder.add_node("retrieve", self._retrieve)
        builder.add_node("rerank", self._rerank)
        builder.add_node("grade_documents", self._grade_documents)
        builder.add_node("generate", self._generate)
        builder.add_node("rephrase_query", self._rephrase_query)
        builder.add_node("grade_response", self._grade_response)
        builder.add_node("finalize_success", self._finalize_success)
        builder.add_node("finalize_failure", self._finalize_failure)

        builder.set_entry_point("retrieve")
        builder.add_edge("retrieve", "rerank")
        builder.add_edge("rerank", "grade_documents")
        builder.add_conditional_edges(
            "grade_documents",
            self._decide_to_generate,
            {
                "rephrase_query": "rephrase_query",
                "generate": "generate",
                "abort": "finalize_failure",
            },
        )
        builder.add_edge("rephrase_query", "retrieve")
        builder.add_edge("generate", "grade_response")
        builder.add_conditional_edges(
            "grade_response",
            self._decide_to_answer,
            {
                "useful": "finalize_success",
                "not useful": "rephrase_query",
                "abort": "finalize_failure",
            },
        )
        builder.add_edge("finalize_success", END)
        builder.add_edge("finalize_failure", END)

        return builder

    def _extract_question_from_messages(self, messages: Sequence[Any]) -> Optional[str]:
        """
        Return the most recent human question (or the last message content) from history.
        """
        if not messages:
            return None

        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = getattr(msg, "content", "")
                if isinstance(content, str) and content.strip():
                    return content.strip()

        for msg in reversed(messages):
            content = getattr(msg, "content", None)
            if isinstance(content, str) and content.strip():
                return content

        return None

    async def _retrieve(self, state: RagGraphState) -> RagGraphState:
        """
        Retrieves relevant document chunks based on the user's question using vector search.

        Args:
            state (RagGraphState): The current state of the agent, containing the question and retry count.

        Returns:
            RagGraphState: The updated state with retrieved documents, sources, and messages.
        """
        # Extract parameters from state
        question: Optional[str] = state.get("question")
        message_history = state.get("messages") or []
        if question is None or question == "":
            question = self._extract_question_from_messages(message_history)
            if not question:
                raise RuntimeError(
                    "Cannot perform retrieval: question missing from state and message history."
                )

        retry_count = int(state.get("retry_count", 0) or 0)
        top_k = self.get_tuned_int("search.top_k", default=50)

        # Prepare search context
        runtime_context = self.get_runtime_context()
        if not runtime_context or not runtime_context.session_id:
            raise RuntimeError(
                "Runtime context missing session_id; required for scoped retrieval."
            )
        document_library_tags_ids = get_document_library_tags_ids(runtime_context)
        document_uids = get_document_uids(runtime_context)
        search_policy = get_search_policy(runtime_context)
        include_session_scope, include_corpus_scope = get_vector_search_scopes(
            runtime_context
        )

        try:
            # Perform search
            with self.kpi_timer(
                "agent.step_latency_ms",
                dims={"step": "vector_search", "policy": search_policy},
            ):
                hits: List[VectorSearchHit] = await self.search_client.search(
                    question=question or "",
                    top_k=top_k,
                    document_library_tags_ids=document_library_tags_ids,
                    document_uids=document_uids,
                    search_policy=search_policy,
                    session_id=runtime_context.session_id,
                    include_session_scope=include_session_scope,
                    include_corpus_scope=include_corpus_scope,
                )

            if not hits:
                warning = f"I couldn't find any relevant documents for “{question}”. Try rephrasing?"
                state["messages"] = [
                    mk_thought(
                        label="retrieve_none",
                        node="retrieve",
                        task="retrieval",
                        content=warning,
                    )
                ]
                state["question"] = question
                state["documents"] = []
                state["sources"] = []
                state["retry_count"] = retry_count
                return state

            # Build success response
            call_id = "tc_retrieve_1"
            summary = f"Retrieved {len(hits)} candidates."
            call_args = {
                "query": question,
                **(
                    {"tags": document_library_tags_ids}
                    if document_library_tags_ids
                    else {}
                ),
            }
            call_args = {
                "query": question,
                "top_k": top_k,
            }
            if document_library_tags_ids:
                call_args["tags"] = document_library_tags_ids
            if document_uids:
                call_args["document_uids"] = document_uids

            messages = [
                mk_tool_call(call_id=call_id, name="retrieve", args=call_args),
                mk_tool_result(
                    call_id=call_id,
                    content=summary,
                    ok=True,
                    extras={"task": "retrieval", "node": "retrieve"},
                    sources=hits,
                ),
                mk_thought(
                    label="retrieve",
                    node="retrieve",
                    task="retrieval",
                    content=summary,
                ),
            ]
            state["messages"] = messages
            state["documents"] = hits
            state["sources"] = hits
            state["question"] = question
            state["retry_count"] = retry_count
            return state
        except Exception as e:
            logger.exception(f"Failed to retrieve documents: {e}")
            state["messages"] = [
                mk_thought(
                    label="retrieve_error",
                    node="retrieve",
                    task="retrieval",
                    content="Error during retrieval.",
                )
            ]
            return state

    async def _rerank(self, state: RagGraphState) -> RagGraphState:
        """
        Reranks retrieved documents using a cross-encoder model to improve relevance.

        Args:
            state: Current state containing the question and documents.

        Returns:
            Updated state with reranked documents and a thought message.
        """
        # Extract parameters from state
        question = cast(str, state.get("question"))
        documents = cast(List[VectorSearchHit], state["documents"])
        top_r = self.get_tuned_int("rerankink.top_r", default=6)

        with self.kpi_timer("agent.step_latency_ms", dims={"step": "rerank"}):
            reranked_documents = await self.search_client.rerank(
                question=question, documents=documents, top_r=top_r
            )

        seen = set()
        keep_documents = []
        for d in reranked_documents + documents[:top_r]:
            key = d.content
            if key not in seen:
                seen.add(key)
                keep_documents.append(d)

        # Build response
        summary = f"Reranked {len(documents)} documents, keeping top reranked and vector-search results : {len(keep_documents)}"

        state["messages"] = [
            mk_thought(
                label="rerank",
                node="rerank",
                task="reranking",
                content=summary,
            )
        ]
        state["documents"] = keep_documents
        state["sources"] = keep_documents
        return state

    async def _grade_documents(self, state: RagGraphState) -> RagGraphState:
        """
        Grade documents for relevance using a permissive LLM-based grader.

        Args:
            state: Current state containing question and documents.

        Returns:
            Updated state with filtered relevant documents.
        """
        # Extract inputs
        question = cast(str, state["question"])
        documents = cast(List[VectorSearchHit], state.get("documents"))
        irrelevant_documents = cast(
            List[VectorSearchHit], state.get("irrelevant_documents", [])
        )

        # Define grading system prompt
        template = (
            self.get_tuned_text("prompts.grade_documents") or grade_documents_prompt()
        )

        # Prepare grading chain
        grade_prompt = ChatPromptTemplate.from_template(template)
        chain = grade_prompt | self.model.with_structured_output(GradeDocumentsOutput)

        # Avoid false dedup across retries by using a stable chunk key.
        irrelevant_keys = {_chunk_key(doc) for doc in irrelevant_documents}
        grade_documents: List[VectorSearchHit] = [
            d for d in (documents or []) if _chunk_key(d) not in irrelevant_keys
        ]

        # Grade each document
        filtered_docs: List[VectorSearchHit] = []
        with self.kpi_timer("agent.step_latency_ms", dims={"step": "grade_documents"}):
            for document in grade_documents:
                # Format document with metadata for grader
                doc_context = (
                    f"Title: {document.title or document.file_name}\n"
                    f"Page: {getattr(document, 'page', 'n/a')}\n"
                    f"Content:\n{document.content}"
                )

                llm_response = await chain.ainvoke(
                    {
                        "question": question,
                        "document": doc_context,
                    }
                )
                score = cast(GradeDocumentsOutput, llm_response)

                logger.debug(
                    f"Grade for {(document.file_name or document.title,)} (p={getattr(document, 'page', None)}): {getattr(score, 'binary_score', None)}",
                )

                # Categorize document
                if str(score.binary_score).lower() == "yes":
                    filtered_docs.append(document)
                else:
                    irrelevant_documents.append(document)

        # Apply failsafe: ensure minimum number of documents
        if not filtered_docs and documents:
            kept_docs = documents[: self.MIN_DOCS]
        elif 0 < len(filtered_docs) < self.MIN_DOCS and documents:
            # Top-up with additional documents not already kept
            kept_docs = filtered_docs.copy()
            seen_keys = {_chunk_key(doc) for doc in kept_docs}

            for doc in documents:
                if len(kept_docs) >= self.MIN_DOCS:
                    break
                if _chunk_key(doc) not in seen_keys:
                    kept_docs.append(doc)
                    seen_keys.add(_chunk_key(doc))
        else:
            kept_docs = filtered_docs

        logger.info(
            f"[AGENTS][RAG] {len(kept_docs)} documents are relevant (of {len(documents or [])})"
        )

        # Build response message
        content = (
            f"Kept {len(kept_docs)} of {len(documents or [])} documents for answering."
        )
        message = mk_thought(
            label="grade_documents",
            node="grade_documents",
            task="retrieval",
            content=content,
        )

        # Attach sources to message metadata
        metadata = getattr(message, "response_metadata", {}) or {}
        metadata["sources"] = [doc.model_dump() for doc in kept_docs]
        setattr(message, "response_metadata", metadata)

        state["messages"] = [message]
        state["documents"] = kept_docs
        state["irrelevant_documents"] = irrelevant_documents
        state["sources"] = kept_docs
        return state

    async def _generate(self, state: RagGraphState) -> RagGraphState:
        """
        Generate an answer based on retrieved documents.

        Args:
            state: Current state containing question and documents.

        Returns:
            Updated state with generated answer and progress message.
        """
        # Extract inputs
        question = cast(str, state["question"])
        documents = cast(List[VectorSearchHit], state["documents"])

        # Build context from documents with metadata
        context = "\n".join(
            f"Source file: {doc.file_name or doc.title}\n"
            f"Page: {getattr(doc, 'page', 'n/a')}\n"
            f"Content: {doc.content}\n"
            for doc in documents
        )

        # Get optional chat context instructions
        chat_context_instructions = await self.chat_context_text()
        programmatic_context = state.get("context", None)

        # Build prompt template and variables
        base_prompt = (
            self.get_tuned_text("prompts.generate_answer") or generate_answer_prompt()
        )

        variables = {
            "context": context,
            "question": question,
        }

        # Add chat context instructions if available
        if programmatic_context:
            base_prompt += f"\n\n{programmatic_context}"
        if chat_context_instructions:
            base_prompt += f"\n\n{chat_context_instructions}"

        prompt = ChatPromptTemplate.from_template(base_prompt)

        # Generate response
        with self.kpi_timer("agent.step_latency_ms", dims={"step": "generate"}):
            response = await (prompt | self.model).ainvoke(variables)
        response = cast(AIMessage, response)
        # Attach sources metadata to response
        attach_sources_to_llm_response(response, documents)

        progress = mk_thought(
            label="generate",
            node="generate",
            task="answering",
            content="Drafting an answer from selected documents…",
        )

        state["messages"] = [progress]
        state["generation"] = response
        state["sources"] = documents
        return state

    async def _rephrase_query(self, state: RagGraphState) -> RagGraphState:
        """
        Rephrase the user's question

        Args:
            state: Current state containing the question and retry count.

        Returns:
            Updated state with rephrased question and incremented retry count.
        """
        # Extract inputs
        question: str = cast(str, state["question"])
        retry_count = int(state.get("retry_count", 0) or 0) + 1

        # Define rephrasing prompt
        template = (
            self.get_tuned_text("prompts.rephrase_query") or rephrase_query_prompt()
        )
        rewrite_prompt = ChatPromptTemplate.from_template(template)

        # Generate rephrased query
        chain = rewrite_prompt | self.model.with_structured_output(RephraseQueryOutput)
        with self.kpi_timer("agent.step_latency_ms", dims={"step": "rephrase_query"}):
            llm_response = await chain.ainvoke({"question": question})
        rephrased = cast(RephraseQueryOutput, llm_response)

        logger.info(
            f"Rephrased question: {question} -> {rephrased.rephrase_query} (retry=f{retry_count})",
        )

        message = mk_thought(
            label="rephrase_query",
            node="rephrase_query",
            task="query rewriting",
            content=rephrased.rephrase_query,
        )

        state["messages"] = [message]
        state["question"] = rephrased.rephrase_query
        state["retry_count"] = retry_count
        return state

    async def _grade_response(self, state: RagGraphState) -> RagGraphState:
        """
        Grade the generated response to assess if it resolves the question.

        Args:
            state: Current state containing question, generation, and retry count.

        Returns:
            Updated state with generation message and reset fields.
        """
        # Extract inputs
        question = cast(str, state["question"])
        generation = cast(AIMessage, state["generation"])

        # Define grading prompt
        template = self.get_tuned_text("prompts.grade_answer") or grade_answer_prompt()
        grade_prompt = ChatPromptTemplate.from_template(template)

        # Grade the response
        grader = grade_prompt | self.model.with_structured_output(GradeAnswerOutput)
        with self.kpi_timer("agent.step_latency_ms", dims={"step": "grade_response"}):
            llm_response = await grader.ainvoke(
                {
                    "question": question,
                    "generation": generation.content,
                }
            )
        grade = cast(GradeAnswerOutput, llm_response)

        message = mk_thought(
            label="grade_response",
            node="grade_response",
            task="grade response",
            content=f"Response assessment : {grade.binary_score}",
        )

        state["messages"] = [message]
        state["response_grade"] = grade.binary_score
        return state

    async def _finalize_success(self, state: RagGraphState) -> RagGraphState:
        """
        Finalize the workflow upon successful completion.

        Args:
            state: The current workflow state, which should contain the generated answer.
        Returns:
            A dictionary containing the final message (the generated answer) and
            cleared intermediate fields to prevent carryover in subsequent runs.
        """
        generation = cast(AIMessage, state["generation"])

        # Try to export conversation if enabled
        try:
            enable_export = (
                self.get_tuned_text("export.enable_conversation_download") != "false"
            )
            if enable_export:
                # Get the full conversation history from runtime context
                runtime_context = self.get_runtime_context()
                full_messages = []

                # Try to get messages from runtime context
                if runtime_context:
                    for attr in [
                        "messages",
                        "chat_history",
                        "history",
                        "conversation_history",
                    ]:
                        if hasattr(runtime_context, attr):
                            history = getattr(runtime_context, attr, None)
                            if history and isinstance(history, list):
                                full_messages = history
                                logger.info(
                                    f"Found {len(full_messages)} messages in runtime_context.{attr}"
                                )
                                break

                # Format conversation using the generic function
                conversation_text = format_conversation_from_messages(
                    messages=full_messages,
                    question=state.get("question"),
                    generation=generation,
                    sources=state.get("sources", []),
                )

                # Export using the generic function
                download_url, _ = await export_conversation_to_asset(
                    agent=self,
                    conversation_text=conversation_text,
                    filename=self.get_tuned_text("export.filename")
                    or "conversation.txt",
                    asset_key_prefix="rico_conversation",
                )

                # Add structured content + download link to response
                answer_text = self._get_text_content(generation)
                link_parts = cast(
                    List[MessagePart],
                    [
                        TextPart(text=answer_text),
                        LinkPart(
                            href=download_url,
                            title="Download conversation.txt",
                            kind=LinkKind.download,
                            mime="text/plain",
                            file_name="conversation.txt",
                        ),
                    ],
                )
                generation = AIMessage(
                    content=answer_text,
                    additional_kwargs=getattr(generation, "additional_kwargs", {}),
                    response_metadata=generation.response_metadata,
                    parts=link_parts,
                )

        except Exception as e:
            logger.warning(f"Failed to export conversation: {e}")
            # Don't fail the workflow, just skip export

        state["messages"] = [generation]
        state["question"] = ""
        state["sources"] = []
        state["retry_count"] = 0
        state["generation"] = None
        state["irrelevant_documents"] = []
        return state

    async def _finalize_failure(self, state: RagGraphState) -> RagGraphState:
        """
        Finalize the workflow upon failure to generate a satisfactory response.

        Args:
            state: The current workflow state.

        Returns:
            A dictionary containing a failure message and cleared intermediate fields.
        """
        explanation = "The agent was unable to generate a satisfactory response. I can rephrase the question and try again."
        message = AIMessage(
            content=explanation,
            response_metadata={
                "extras": {"task": "answering", "node": "finalize_failure"},
                "sources": [],
            },
        )

        state["messages"] = [message]
        state["question"] = ""
        state["sources"] = []
        state["retry_count"] = 0
        state["generation"] = None
        state["irrelevant_documents"] = []
        return state

    # ---------- edges ----------

    async def _decide_to_generate(self, state: RagGraphState) -> str:
        """
        Decide whether to rephrase the query or proceed to generation based on document availability and retry count.

        Args:
            state: The current workflow state, which includes documents and retry count.

        Returns:
            A string indicating the next step: "abort", "rephrase_query", or "generate".
        """
        documents: Optional[List[VectorSearchHit]] = state.get("documents")
        retry_count = int(state.get("retry_count", 0) or 0)

        if retry_count > 2:
            return "abort"
        elif not documents:
            return "rephrase_query"
        else:
            return "generate"

    GradeRoute = Literal["useful", "not useful", "abort"]

    async def _decide_to_answer(self, state: RagGraphState) -> str:
        """
        Decide whether to accept the answer, retry, or abort based on grading.

        Args:
            state: Current state containing response_grade and retry_count.

        Returns:
            Routing decision: "useful", "not useful", or "abort".
        """
        # Extract inputs
        response_grade = cast(str, state["response_grade"])
        retry_count = int(state.get("retry_count", 0) or 0)

        if response_grade.lower() == "yes":
            return "useful"
        elif retry_count >= 2:
            return "abort"
        else:
            return "not useful"
