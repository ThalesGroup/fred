# Copyright Thales 2026
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

"""
Direct evaluation of the V2 SQL analyst graph agent.

QUICK START
-----------
    # From agentic-backend/:
    make eval-sql-agent

HOW IT WORKS
------------
The agent is invoked in-process using the same V2 runtime that the server uses.
No WebSocket, no session management, no Agentic API token needed.

The only external dependency is the Knowledge Flow server (for the MCP tools
`knowledge.tabular.list_tabular_datasets` and `knowledge.tabular.read_query`).
Set AGENTIC_TOKEN in config/.env if your KF server requires a Bearer token.

MANUAL USAGE
------------
    python agentic_backend/tests/agents/sql/sql_analyst_evaluation.py \\
        --config agentic_backend/tests/agents/sql/eval_config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

import yaml
from deepeval import evaluate
from deepeval.evaluate import AsyncConfig
from deepeval.metrics import AnswerRelevancyMetric, GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from agentic_backend.agents.v2.production.sql_analyst_graph import SqlAgentDefinition
from agentic_backend.application_context import get_configuration, get_default_model
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
)
from agentic_backend.core.agents.v2.legacy_bridge.agent_settings_bridge import (
    apply_profile_defaults_to_settings,
)
from agentic_backend.core.agents.v2.legacy_bridge.runtime_bootstrap import (
    build_v2_session_agent,
)
from agentic_backend.core.agents.v2.runtime_support import V2SessionAgent
from agentic_backend.integrations.v2_runtime.adapters import DefaultFredChatModelFactory
from agentic_backend.tests.agents.base_deepeval_test import BaseEvaluator

logger = logging.getLogger(__name__)

# The catalog id for the SQL agent (agents_catalog.yaml → id field).
_DEFAULT_CATALOG_AGENT_ID = "SQL Agent"


def _load_yaml_config(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_eval_binding(agent_id: str) -> BoundRuntimeContext:
    """
    Build a minimal BoundRuntimeContext for in-process evaluation.
    AGENTIC_TOKEN is forwarded to the KF server for MCP tool auth.
    """
    token = os.getenv("AGENTIC_TOKEN", "")
    session_id = f"eval-{agent_id}"
    return BoundRuntimeContext.model_construct(
        portable_context=PortableContext.model_construct(
            request_id=f"eval-req-{agent_id}",
            correlation_id=f"eval-corr-{agent_id}",
            actor="eval-user",
            tenant="eval-tenant",
            environment=PortableEnvironment.DEV,
            agent_id=agent_id,
            session_id=session_id,
        ),
        runtime_context=RuntimeContext(
            access_token=token,
            session_id=session_id,
        ),
    )


class SqlAgentEvaluator(BaseEvaluator):
    """
    Evaluator for the V2 SQL analyst graph agent.

    Extends BaseEvaluator to reuse metric averaging and colored logging.

    Overrides:
      - parse_args()      : reads --config YAML; judge model is optional (auto-detected)
      - load_deepeval_llm : auto-detects judge model from environment or config
      - run_evaluation()  : direct in-process V2 agent invocation
    """

    # ── CLI ──────────────────────────────────────────────────────────────────

    def parse_args(self) -> argparse.Namespace:
        # Pre-scan for --config so YAML values can serve as argument defaults.
        pre = argparse.ArgumentParser(add_help=False)
        pre.add_argument("--config", type=Path)
        pre_args, _ = pre.parse_known_args()

        cfg: dict[str, Any] = {}
        if pre_args.config:
            cfg = _load_yaml_config(pre_args.config)
            self.logger.info("Loaded eval config: %s", pre_args.config)

        parser = argparse.ArgumentParser(
            description="DeepEval evaluation for the V2 SQL analyst agent",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="Tip: put all settings in eval_config.yaml and run: make eval-sql-agent",
        )
        parser.add_argument("--config", type=Path, help="YAML config file.")
        parser.add_argument(
            "--chat_model",
            default=cfg.get("judge_model", ""),
            metavar="MODEL",
            help="LLM-as-judge model name. Auto-detected when omitted.",
        )
        parser.add_argument(
            "--embedding_model",
            default=cfg.get("embedding_model", ""),
            metavar="MODEL",
        )
        parser.add_argument(
            "--dataset_path",
            type=Path,
            default=Path(cfg["dataset_path"]) if "dataset_path" in cfg else None,
            metavar="FILE",
            help="JSON scenario file [{question, expect}].",
        )
        parser.add_argument(
            "--configuration_file",
            default=cfg.get("configuration_file"),
            metavar="FILE",
            help="App configuration YAML (default: configuration.yaml).",
        )
        parser.add_argument("--doc_libs", help=argparse.SUPPRESS)

        args = parser.parse_args()
        if not args.dataset_path:
            parser.error(
                "dataset_path is required — set it in eval_config.yaml or pass --dataset_path."
            )
        return args

    # ── Judge model ───────────────────────────────────────────────────────────

    def load_deepeval_llm(self) -> None:
        """
        Build the LLM judge with automatic provider detection.

        Priority (first match wins):
          1. OPENAI_API_KEY in environment → ChatOpenAI (default: gpt-4o-mini)
          2. Default model in configuration.yaml → reused as judge
        """
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            judge_model = self.chat_model or "gpt-4o-mini"
            llm = ChatOpenAI(model=judge_model, temperature=0.0)
            self.chat_model = judge_model
            self.deepeval_llm = self.mapping_langchain_deepeval(llm)
            self.logger.info(
                "Judge model: OpenAI %s (from OPENAI_API_KEY)", judge_model
            )
            return

        try:
            default_llm = get_default_model()
        except Exception:
            default_llm = None

        if default_llm is None:
            raise RuntimeError(
                "Cannot configure judge model. Set one of:\n"
                "  • OPENAI_API_KEY in config/.env\n"
                "  • judge_model in eval_config.yaml"
            )

        if not self.chat_model:
            if isinstance(default_llm, ChatOllama):
                self.chat_model = default_llm.model
            elif isinstance(default_llm, ChatOpenAI):
                self.chat_model = default_llm.model_name
            self.logger.info(
                "Judge model: auto-detected from configuration.yaml: %s",
                self.chat_model,
            )

        super().load_deepeval_llm()

    # ── Agent setup ───────────────────────────────────────────────────────────

    async def _build_session_agent(self, catalog_agent_id: str) -> V2SessionAgent:
        """
        Build a ready-to-use V2SessionAgent from the catalog settings.
        No server needed — the agent runs in-process.
        """
        agents = get_configuration().ai.agents
        settings = next((a for a in agents if a.id == catalog_agent_id), None)
        if not settings:
            available = [a.id for a in agents]
            raise ValueError(
                f"Agent '{catalog_agent_id}' not found in catalog. Available: {available}"
            )

        definition = SqlAgentDefinition()
        effective_settings = apply_profile_defaults_to_settings(
            definition=definition,
            settings=settings,
        )
        binding = _build_eval_binding(catalog_agent_id)
        factory = DefaultFredChatModelFactory()
        return build_v2_session_agent(
            definition=definition,
            effective_settings=effective_settings,
            binding=binding,
            chat_model_factory=factory,
            checkpointer=None,
        )

    async def _ask(
        self, session_agent: V2SessionAgent, question: str, thread_id: str
    ) -> str:
        """Send one question and return the final answer from the graph."""
        state = {"messages": [HumanMessage(content=question)]}
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        answer = ""
        async for update in session_agent.astream_updates(
            state, config=config, stream_mode="updates"
        ):
            if isinstance(update, dict) and "agent" in update:
                for msg in update["agent"].get("messages", []):
                    if (
                        isinstance(msg, AIMessage)
                        and isinstance(msg.content, str)
                        and msg.content
                    ):
                        answer = msg.content
        return answer

    # ── Evaluation ───────────────────────────────────────────────────────────

    async def run_evaluation(
        self,
        agent_id: str,
        doc_lib_ids: Optional[list[str]] = None,
    ):
        """
        Evaluation flow:
          1. Build V2SessionAgent in-process.
          2. Ask each question; collect the final answer.
          3. Log an immediate substring check for fast feedback.
          4. Run LLM-as-judge metrics via deepeval.
        """
        self.logger.info("Agent: %s", agent_id)
        self.logger.info(
            "%d question(s) from %s",
            len(self.dataset),
            getattr(self.dataset_path, "name", str(self.dataset_path)),
        )

        session_agent = await self._build_session_agent(agent_id)
        self.logger.info("Agent ready")

        answer_relevancy = AnswerRelevancyMetric(
            model=self.deepeval_llm,
            verbose_mode=True,
            threshold=0.0,
        )
        sql_correctness = GEval(
            name="SQL Correctness",
            criteria=(
                "The actual output must correctly answer the user's data question. "
                "If an expected answer is provided, the actual output must contain "
                "or clearly convey that expected value or concept. "
                "A response that says 'no data found' when data exists is incorrect."
            ),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            model=self.deepeval_llm,
            verbose_mode=True,
            threshold=0.0,
        )

        test_cases: list[LLMTestCase] = []
        self.logger.info("Evaluation in progress...")
        try:
            for i, item in enumerate(self.dataset, 1):
                question: str = item["question"]
                expected: str = item.get("expect", "")

                self.logger.info("[%d/%d] %s", i, len(self.dataset), question)
                try:
                    answer = await self._ask(
                        session_agent, question, thread_id=f"eval_{i}"
                    )
                    self.logger.info("Answer (%d chars)", len(answer))
                except Exception as exc:
                    self.logger.warning("[%d/%d] Error: %s", i, len(self.dataset), exc)
                    answer = ""

                if expected:
                    hit = expected.lower() in answer.lower()
                    tag = "[PASS]" if hit else "[FAIL]"
                    level = logging.INFO if hit else logging.WARNING
                    self.logger.log(level, "%s substring '%s'", tag, expected)

                test_cases.append(
                    LLMTestCase(
                        input=question,
                        actual_output=answer,
                        expected_output=expected if expected else None,
                    )
                )
        finally:
            await session_agent.aclose()

        self.logger.info(
            "Running DeepEval metrics on %d test case(s)...", len(test_cases)
        )
        return evaluate(
            test_cases=test_cases,
            metrics=[answer_relevancy, sql_correctness],
            async_config=AsyncConfig(run_async=False),
        )


def main() -> None:
    evaluator = SqlAgentEvaluator()
    exit_code = asyncio.run(evaluator.main(agent_id=_DEFAULT_CATALOG_AGENT_ID))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
