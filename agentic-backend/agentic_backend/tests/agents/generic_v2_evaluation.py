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
Generic DeepEval evaluator for any V2 agent registered in agents_catalog.yaml.

QUICK START
-----------
    # From agentic-backend/ — recommended entry point:
    ./eval.sh
    ./eval.sh -a "SQL Agent" -d /path/to/dataset.json

    # Or directly with Python:
    python agentic_backend/tests/agents/generic_v2_evaluation.py \\
        --agent_id   "SQL Agent" \\
        --dataset    /path/to/dataset.json \\
        --config     agentic_backend/tests/agents/eval_config.yaml

CLI ARGUMENTS
-------------
    --agent_id   / -a   Catalog agent id (see agents_catalog.yaml). Required.
    --dataset           Path to the JSON scenario file. Required.
    --config            Path to the YAML eval config (judge model, app config).
                        Defaults to agentic_backend/tests/agents/eval_config.yaml.
    --configuration_file  App configuration YAML. Default: configuration.yaml.
    --chat_model        Override the LLM judge model name.

AVAILABLE AGENTS (agent_id values)
-----------------------------------
    "SQL Agent"                 — tabular data analysis via SQL + MCP tools
    "Corpus Investigator Deep"  — deep RAG over document corpus
    "DVARiskValidatorGraph"     — DVA risk validation graph
    "DVARiskValidatorQA"        — DVA risk QA
    "BankTransfer"              — bank transfer sample agent

DATASET FORMAT
--------------
    JSON file, list of objects:
    [
      { "question": "How many ports?",   "expect": "8"     },
      { "question": "List the radars.",  "expect": "RAD-"  },
      { "question": "Who are you?"       }   ← expect is optional
    ]
    "expect" is used for:
      1. A substring check logged immediately after the agent answers.
      2. A hint given to the GEval judge as expected_output.

PREREQUISITES
-------------
    - Run from agentic-backend/
    - Knowledge Flow server running on localhost:8111 (if agent uses MCP tools)
    - config/.env with KEYCLOAK_AGENTIC_CLIENT_SECRET (for bearer token)
    - Judge LLM configured: OPENAI_API_KEY in .env, or judge_model in eval_config.yaml

HOW IT WORKS
------------
    1. Agent is resolved from agents_catalog.yaml via definition_ref → Python class.
    2. Agent is instantiated in-process (no HTTP server needed).
    3. Each question is sent to the agent via astream_updates().
    4. Each answer is scored individually by the judge LLM (tqdm progress bar).
    5. A detailed report is written to output/.

METRICS
-------
    - AnswerRelevancy : does the answer address the question? (0.0 → 1.0)
    - Correctness     : does the answer contain the expected fact? (GEval, 0.0 → 1.0)

OUTPUT
------
    Terminal  : two tqdm progress bars (questioning / scoring) + summary table.
    File      : agentic_backend/tests/agents/output/eval_<agent>_<timestamp>.txt
                Contains per-question: question, expected, answer, substring check,
                per-metric scores with visual bar, then global averages.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from textwrap import fill
from typing import Any, Optional

import yaml
from deepeval.evaluate import AsyncConfig
from deepeval.metrics import AnswerRelevancyMetric, GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from tqdm import tqdm

from agentic_backend.agents.v2.definition_refs import class_path_for_definition_ref
from agentic_backend.application_context import get_configuration
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
)
from agentic_backend.core.agents.v2.legacy_bridge.agent_settings_bridge import (
    apply_profile_defaults_to_settings,
    instantiate_definition_class,
)
from agentic_backend.core.agents.v2.legacy_bridge.runtime_bootstrap import (
    build_v2_session_agent,
)
from agentic_backend.core.agents.v2.runtime_support import V2SessionAgent
from agentic_backend.integrations.v2_runtime.adapters import DefaultFredChatModelFactory
from agentic_backend.tests.agents.base_deepeval_test import BaseEvaluator

# ── Output directory (relative to this file) ────────────────────────────────
_OUTPUT_DIR = Path(__file__).parent / "output"


def _load_yaml_config(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_eval_binding(agent_id: str) -> BoundRuntimeContext:
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


def _resolve_definition_class(definition_ref: str):
    class_path = class_path_for_definition_ref(definition_ref)
    module_name, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def _silence_logging() -> None:
    """Suppress all loggers so only the Rich UI is visible in the terminal."""
    logging.root.setLevel(logging.CRITICAL + 1)
    for name in list(logging.root.manager.loggerDict):
        logging.getLogger(name).setLevel(logging.CRITICAL + 1)


def _write_report(
    output_path: Path,
    agent_id: str,
    dataset_path: Path,
    judge_model: str,
    records: list[dict],
    metric_results: dict,
    global_average: float,
) -> None:
    """Write the full evaluation report to a text file."""
    sep = "=" * 72
    thin = "─" * 72
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []
    a = lines.append

    a(sep)
    a(f"  EVALUATION REPORT  —  {agent_id}")
    a(sep)
    a(f"  Date    : {now}")
    a(f"  Dataset : {dataset_path.name}")
    a(f"  Judge   : {judge_model}")
    a(f"  Total   : {len(records)} question(s)")
    a(sep)

    for i, rec in enumerate(records, 1):
        a(f"\nQUESTION {i}/{len(records)}")
        a(thin)
        a(f"Q : {rec['question']}")
        if rec["expected"]:
            a(f"E : {rec['expected']}")
        a(f"A : {fill(rec['answer'], width=70, subsequent_indent='    ')}")
        if rec["expected"]:
            hit = rec["expected"].lower() in rec["answer"].lower()
            a(f"Substring check : {'PASS' if hit else 'FAIL'} ('{rec['expected']}')")
        a("")
        a("Scores")
        for metric_name, score in rec["scores"].items():
            bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
            a(f"  {metric_name:<30} {score:.2f}  [{bar}]  {score*100:.1f}%")

    a(f"\n{sep}")
    a("  SUMMARY")
    a(sep)
    for metric_name, stats in sorted(metric_results.items()):
        a(f"\n{metric_name}")
        a(f"  Average : {stats['average']:.4f}  ({stats['average']*100:.2f}%)")
        a(f"  Min     : {stats['min']:.4f}  —  Max : {stats['max']:.4f}")
    a(f"\n{thin}")
    a(f"  OVERALL AVERAGE : {global_average:.4f}  ({global_average*100:.2f}%)")
    a(sep)

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


class GenericV2Evaluator(BaseEvaluator):
    """
    Generic evaluator for any V2 agent declared in agents_catalog.yaml.

    Terminal output   : Rich progress bar only — no log spam.
    Detailed report   : Written to agentic_backend/tests/agents/output/.
    """

    def parse_args(self) -> argparse.Namespace:
        pre = argparse.ArgumentParser(add_help=False)
        pre.add_argument("--config", type=Path)
        pre_args, _ = pre.parse_known_args()

        cfg: dict[str, Any] = {}
        if pre_args.config:
            cfg = _load_yaml_config(pre_args.config)

        parser = argparse.ArgumentParser(
            description="Generic DeepEval evaluator for any V2 agent",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=(
                "Example:\n"
                "  ./eval.sh -a 'SQL Agent' -d /home/sylvain/output/sql_scenario.json\n"
            ),
        )
        parser.add_argument("--config", type=Path, help="YAML config file.")
        parser.add_argument(
            "--agent_id",
            default=cfg.get("agent_id", ""),
            metavar="AGENT",
        )
        parser.add_argument(
            "--dataset", "--dataset_path",
            dest="dataset_path",
            type=Path,
            default=Path(cfg["dataset_path"]) if "dataset_path" in cfg else None,
            metavar="FILE",
        )
        parser.add_argument(
            "--configuration_file",
            default=cfg.get("configuration_file", "configuration.yaml"),
            metavar="FILE",
        )
        parser.add_argument(
            "--chat_model",
            default=cfg.get("judge_model", ""),
            metavar="MODEL",
        )
        parser.add_argument("--embedding_model", default="", metavar="MODEL")

        args = parser.parse_args()

        if not args.agent_id:
            parser.error("--agent_id is required.")
        if not args.dataset_path:
            parser.error("--dataset / --dataset_path is required.")

        return args

    async def _build_session_agent(self, catalog_agent_id: str) -> V2SessionAgent:
        agents = get_configuration().ai.agents
        settings = next((a for a in agents if a.id == catalog_agent_id), None)
        if not settings:
            available = [a.id for a in agents]
            raise ValueError(
                f"Agent '{catalog_agent_id}' not found in catalog.\n"
                f"Available: {available}"
            )
        if not settings.definition_ref:
            raise ValueError(
                f"Agent '{catalog_agent_id}' has no definition_ref — "
                f"only V2 agents are supported."
            )
        definition_cls = _resolve_definition_class(settings.definition_ref)
        definition = instantiate_definition_class(definition_cls)
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

    async def run_evaluation(
        self,
        agent_id: str,
        doc_lib_ids: Optional[list[str]] = None,
    ):
        # ── Phase 1 : ask the agent ───────────────────────────────────────────
        records: list[dict] = []
        test_cases: list[LLMTestCase] = []

        session_agent = await self._build_session_agent(agent_id)
        try:
            with tqdm(self.dataset, desc="Questioning agent", unit="q", leave=True) as bar:
                for item in bar:
                    question: str = item["question"]
                    expected: str = item.get("expect", item.get("expected_answer", ""))
                    old_out, old_err = sys.stdout, sys.stderr
                    sys.stdout = sys.stderr = open(os.devnull, "w")
                    try:
                        answer = await self._ask(
                            session_agent, question, thread_id=f"eval_{len(records) + 1}"
                        )
                    except Exception as exc:
                        answer = f"[ERROR: {exc}]"
                    finally:
                        sys.stdout.close()
                        sys.stdout, sys.stderr = old_out, old_err

                    records.append(
                        {"question": question, "expected": expected, "answer": answer, "scores": {}}
                    )
                    test_cases.append(
                        LLMTestCase(
                            input=question,
                            actual_output=answer,
                            expected_output=expected if expected else None,
                        )
                    )
        finally:
            await session_agent.aclose()

        # ── Phase 2 : LLM-as-judge scoring ───────────────────────────────────
        answer_relevancy = AnswerRelevancyMetric(
            model=self.deepeval_llm, verbose_mode=False, threshold=0.0
        )
        correctness = GEval(
            name="Correctness",
            criteria=(
                "The actual output must correctly answer the user's question. "
                "If an expected answer is provided, the actual output must contain "
                "or clearly convey that expected value or concept."
            ),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            model=self.deepeval_llm,
            verbose_mode=False,
            threshold=0.0,
        )

        # Score each test case individually so tqdm can advance per question
        import io
        metrics = [answer_relevancy, correctness]
        with tqdm(test_cases, desc="Scoring (LLM judge) ", unit="q", leave=True) as bar:
            for i, tc in enumerate(bar):
                for metric in metrics:
                    old_out, old_err = sys.stdout, sys.stderr
                    sys.stdout = sys.stderr = open(os.devnull, "w")
                    try:
                        metric.measure(tc)
                    finally:
                        sys.stdout.close()
                        sys.stdout, sys.stderr = old_out, old_err
                    metric_name = metric.__name__
                    records[i]["scores"][metric_name] = getattr(metric, "score", 0.0) or 0.0

        # Build a lightweight result-like structure for calculate_metric_averages
        class _FakeMetricData:
            def __init__(self, name, score):
                self.name = name
                self.score = score

        class _FakeTestResult:
            def __init__(self, metrics_data):
                self.metrics_data = metrics_data

        class _FakeResult:
            def __init__(self, test_results):
                self.test_results = test_results

        fake_test_results = [
            _FakeTestResult([
                _FakeMetricData(name, score)
                for name, score in rec["scores"].items()
            ])
            for rec in records
        ]
        result = _FakeResult(fake_test_results)

        return result, records

    async def main_with_report(self, agent_id: str) -> int:
        """Override of the base main() that handles the rich UI and report writing."""
        os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"
        os.environ["ERROR_REPORTING"] = "0"
        os.environ["DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"] = "600"

        args = self.parse_args()
        self.chat_model = args.chat_model
        self.embedding_model = args.embedding_model
        self.dataset_path = args.dataset_path

        _silence_logging()

        print(f"\nEvaluation — {agent_id}")
        print(f"Dataset : {self.dataset_path}")

        try:
            self.load_config(configuration_file=args.configuration_file)
            self.load_deepeval_llm()
            self.load_dataset()

            print(f"Judge   : {self.chat_model}  |  Questions : {len(self.dataset)}\n")

            result, records = await self.run_evaluation(agent_id=agent_id)

            # ── Build metric summary ──────────────────────────────────────────
            from collections import defaultdict
            metrics_scores: dict = defaultdict(list)
            for test_result in result.test_results:
                for md in test_result.metrics_data:
                    metrics_scores[md.name].append(md.score or 0.0)

            metric_results = {}
            for name, scores in metrics_scores.items():
                metric_results[name] = {
                    "scores": scores,
                    "average": sum(scores) / len(scores),
                    "min": min(scores),
                    "max": max(scores),
                }

            all_scores = [s for v in metrics_scores.values() for s in v]
            global_average = sum(all_scores) / len(all_scores) if all_scores else 0.0

            # ── Write report ─────────────────────────────────────────────────
            slug = agent_id.replace(" ", "_").lower()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = _OUTPUT_DIR / f"eval_{slug}_{ts}.txt"

            _write_report(
                output_path=output_path,
                agent_id=agent_id,
                dataset_path=self.dataset_path,
                judge_model=self.chat_model or "unknown",
                records=records,
                metric_results=metric_results,
                global_average=global_average,
            )

            # ── Summary ───────────────────────────────────────────────────────
            sep = "=" * 50
            print(f"\n{sep}")
            print(f"  Results — {agent_id}")
            print(sep)
            for name, stats in sorted(metric_results.items()):
                print(f"  {name:<30} {stats['average']*100:.1f}%"
                      f"  (min {stats['min']*100:.1f}%  max {stats['max']*100:.1f}%)")
            print(f"{'─'*50}")
            print(f"  {'OVERALL':<30} {global_average*100:.1f}%")
            print(sep)
            print(f"\nReport saved → {output_path}\n")

            return 0

        except Exception as e:
            print(f"\nError: {e}")
            return 1


def main() -> None:
    evaluator = GenericV2Evaluator()

    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--agent_id", default="")
    pre.add_argument("--config", type=Path)
    pre_args, _ = pre.parse_known_args()

    agent_id = pre_args.agent_id
    if not agent_id and pre_args.config and pre_args.config.exists():
        cfg = _load_yaml_config(pre_args.config)
        agent_id = cfg.get("agent_id", "")

    exit_code = asyncio.run(evaluator.main_with_report(agent_id=agent_id))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
