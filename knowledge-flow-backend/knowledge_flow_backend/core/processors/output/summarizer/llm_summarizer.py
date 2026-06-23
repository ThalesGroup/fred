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

# app/core/summarization/llm_summarizer.py
import logging
from typing import List, Optional

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import ModelConfiguration
from knowledge_flow_backend.core.processors.output.summarizer.base_summarizer import BaseDocSummarizer

logger = logging.getLogger(__name__)

_ABSTRACT_SYS = "You are a precise technical summarizer for software docs."
_TOKENS_SYS = "You extract discriminative keywords and short phrases."


class LLMBasedDocSummarizer(BaseDocSummarizer):
    """
    Fred rationale:
    - Use the small 'utility' chat model to generate short, deterministic summaries.
    - Keep the interface dead simple: a private `_complete()` that takes system+user.
    - No provider branching here; utility_llm factory already handled that.
    """

    def __init__(self, model_config: Optional[ModelConfiguration]):
        # If no model configured, raise: the ApplicationContext should select the fallback summarizer instead.
        self.context = ApplicationContext.get_instance()
        self.model = self.context.get_utility_model()
        if self.model is None:
            raise RuntimeError("No utility LLM configured; use FallbackDocSummarizer instead.")

        # Reusable 2-message prompt (system + user). We keep a MessagesPlaceholder
        # so we can reuse the chain for both abstract and keywords with different system prompts.
        self.prompt = ChatPromptTemplate.from_messages([MessagesPlaceholder("messages")])

        # Build a tiny chain once: (prompt | chat_model) returns an AIMessage
        self.chain: Runnable = self.prompt | self.model

    def _complete(self, system: str, user: str) -> str:
        """
        Why this helper:
        - Central place to issue a single system+user completion.
        - Works across OpenAI/Azure/Ollama since all are LangChain ChatModels.

        Note on output length: we deliberately do NOT bind ``max_tokens`` here.
        Recent langchain-openai rewrites ``max_tokens`` to ``max_completion_tokens``
        on the wire, which some OpenAI-compatible gateways reject with HTTP 400
        (strict OpenAPI validation). Output length is instead bounded by the
        prompt (``≤max_words``) and overall latency by the model's request_timeout.
        """
        messages = [
            ("system", system),
            ("user", user),
        ]
        result = self.chain.invoke({"messages": messages})
        # `result` is an AIMessage for ChatModels; safeguard for plain strings and
        # list-shaped content (some providers return content blocks).
        content = getattr(result, "content", result)
        return content.strip() if isinstance(content, str) else str(content).strip()

    def summarize_abstract(self, text: str, *, max_words: int = 180, instruction: Optional[str] = None) -> str:
        if instruction:
            task = f"Write a summary following this instruction: {instruction}\n\nKeep it focused and within about {max_words} words."
        else:
            task = f"Write a concise abstract (≤{max_words} words) for engineers. State problem, approach, and key takeaways. Avoid marketing tone."
        user = f"{task}\n\n---\n{text}"
        return self._complete(_ABSTRACT_SYS, user)

    def summarize_tokens(self, text: str, *, top_k: int = 24, vocab_hint: Optional[str] = None) -> List[str]:
        user = (
            "Extract the most discriminative keywords/short phrases (1–4 words), "
            f"lowercase, comma-separated, up to {top_k}. Prefer domain terms and compound nouns. "
            "No duplicates, avoid stopwords.\n\n---\n"
            f"{text}"
        )
        raw = self._complete(_TOKENS_SYS, user)
        toks = [t.strip().lower() for t in raw.split(",") if t.strip()]
        seen, out = set(), []
        for t in toks:
            if t not in seen:
                seen.add(t)
                out.append(t)
            if len(out) >= top_k:
                break
        return out
