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

import asyncio
import sys

from deepeval import evaluate
from deepeval.evaluate import AsyncConfig
from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)
from deepeval.test_case import LLMTestCase
from langchain_core.messages import HumanMessage

from agentic_backend.agents.rags.rag_expert import Rico
from agentic_backend.tests.agents.base_deepeval_test import BaseEvaluator


class RAGEvaluator(BaseEvaluator):
    async def run_evaluation(
        self,
        agent_id: str,
        doc_lib_ids: list[str] | None = None,
    ):
        """
        This method runs the evaluation of an agent by generating test cases from the dataset
        and evaluating them using the defined metrics.

        Args:
            agent_id (str): The id of the agent to be evaluated.
            doc_lib_ids (list[str] | None, optional): List of document library IDs. Defaults to None.

        Returns:
            dict: A dictionary containing the results of the evaluation.
        """
        agent = await self.setup_agent(
            agent_type=Rico, agent_id=agent_id, doc_lib_ids=doc_lib_ids
        )
        self.logger.info(f"🤖 Agent '{agent_id}' ready")

        self.logger.info(
            f"📝 {len(self.dataset)} questions loaded from {self.dataset_path.name if self.dataset_path else 'unknown'}"
        )

        faithfulness_metric = FaithfulnessMetric(
            model=self.deepeval_llm, verbose_mode=True, threshold=0.0
        )
        answer_relevancy_metric = AnswerRelevancyMetric(
            model=self.deepeval_llm, verbose_mode=True, threshold=0.0
        )
        contextual_precision_metric = ContextualPrecisionMetric(
            model=self.deepeval_llm, verbose_mode=True, threshold=0.0
        )
        contextual_recall_metric = ContextualRecallMetric(
            model=self.deepeval_llm, verbose_mode=True, threshold=0.0
        )
        contextual_relevancy_metric = ContextualRelevancyMetric(
            model=self.deepeval_llm, verbose_mode=True, threshold=0.0
        )

        test_cases = []

        self.logger.info("🔄 Evaluation in progress...")
        for i, item in enumerate(self.dataset, 1):
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=item["question"])]},
                config={"configurable": {"thread_id": f"eval_{i}"}},
            )

            messages = result.get("messages", [])

            actual_output = messages[-1].content if messages else ""
            retrieval_context_list = (
                messages[-1].additional_kwargs.get("sources", []) if messages else []
            )
            retrieval_context = [doc["content"] for doc in retrieval_context_list]

            # Create DeepEval test case
            test_case = LLMTestCase(
                input=item["question"],
                actual_output=actual_output,
                expected_output=item["expected_answer"],
                retrieval_context=retrieval_context,
            )
            test_cases.append(test_case)

            self.logger.info(f"✓ Question {i}/{len(self.dataset)}")

        self.logger.info("📊 Calculation of DeepEval metrics...")

        results = evaluate(
            test_cases=test_cases,
            metrics=[
                faithfulness_metric,
                answer_relevancy_metric,
                contextual_precision_metric,
                contextual_recall_metric,
                contextual_relevancy_metric,
            ],
            async_config=AsyncConfig(run_async=False),
        )

        return results


def main():
    evaluator = RAGEvaluator()
    exit_code = asyncio.run(evaluator.main(agent_id="Rico"))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
