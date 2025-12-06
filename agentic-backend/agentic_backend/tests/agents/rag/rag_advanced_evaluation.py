import argparse
import asyncio
import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

from deepeval import evaluate
from deepeval.evaluate import AsyncConfig
from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)
from deepeval.models import GPTModel, OllamaModel
from deepeval.test_case import LLMTestCase
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from agentic_backend.agents.rags.advanced_rag_expert import AdvancedRico
from agentic_backend.application_context import (
    ApplicationContext,
    get_configuration,
    get_default_model,
)
from agentic_backend.common.utils import parse_server_configuration
from agentic_backend.core.agents.runtime_context import RuntimeContext


def setup_colored_logging():
    """
    Set up colored logging for console output.
    The logging output includes timestamp, log level, and message.
    """
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }

    class ColorFormatter(logging.Formatter):
        def format(self, record):
            color = COLORS.get(record.levelname, "\033[0m")
            record.levelname = f"{color}{record.levelname}\033[0m"
            return super().format(record)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ColorFormatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    )

    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def load_config():
    """
    Load and configure the application settings for a specified model.

    Returns:
        The updated configuration object.
    """
    config_path = Path(__file__).parents[4] / "config" / "configuration.yaml"
    config = parse_server_configuration(str(config_path))
    ApplicationContext(config)
    return config


def mapping_langchain_deepeval(langchain_model):
    """
    Maps a LangChain model instance to a corresponding DeepEval model instance.

    Args:
        langchain_model: A LangChain model instance (either ChatOllama or ChatOpenAI).

    Returns:
        A DeepEval model instance (OllamaModel or GPTModel) corresponding to the input.
    """
    if isinstance(langchain_model, ChatOllama):
        return OllamaModel(
            model=langchain_model.model,
            base_url=langchain_model.base_url,
            temperature=langchain_model.temperature or 0.0,
        )
    if isinstance(langchain_model, ChatOpenAI):
        return GPTModel(
            model=langchain_model.model_name,
            temperature=langchain_model.temperature or 0.0,
        )


async def setup_agent(
    agent_id: str = "advanced-rag-expert", doc_lib_ids: list[str] | None = None
):
    """
    Initialize and configure an agent by id, optionally setting document libraries.

    Args:
        agent_id (str): The id of the agent to initialize. Defaults to Rico Senior (advanced-rag-expert).
        doc_lib_ids (list): Optional list of document library IDs to set in runtime context.

    Returns:
        The compiled graph of the initialized agent.
    """
    agents = get_configuration().ai.agents
    settings = next((a for a in agents if a.id == agent_id), None)

    if not settings:
        available = [a.id for a in agents]
        raise ValueError(f"Agent '{agent_id}' not found. Available: {available}")

    agent = AdvancedRico(settings)
    await agent.async_init()
    agent.set_runtime_context(
        context=RuntimeContext(access_token="fake_token")  # nosec B106
    )

    if doc_lib_ids:
        agent.set_runtime_context(
            RuntimeContext(selected_document_libraries_ids=doc_lib_ids)
        )

    return agent.get_compiled_graph()


def calculate_metric_averages(result):
    """
    Calculate and display average scores for each metric from evaluation results.

    Args:
        result: The evaluation result object returned by DeepEval's evaluate function.
                It should contain test_results with metrics_data for each test case.
    """

    metrics_scores = defaultdict(list)

    for test_result in result.test_results:
        for metric_data in test_result.metrics_data:
            metric_name = metric_data.name
            metrics_scores[metric_name].append(metric_data.score)

    print("\n" + "=" * 70)
    print("AVERAGES PER METRIC")
    print("=" * 70)

    results = {}
    for metric_name in sorted(metrics_scores.keys()):
        scores = metrics_scores[metric_name]
        avg = sum(scores) / len(scores) if scores else 0
        min_score = min(scores) if scores else 0
        max_score = max(scores) if scores else 0

        print(f"\n{metric_name}")
        print(f"{'─' * 70}")
        percent = round(avg * 100, 2)
        print(f"  Average:           {avg:.4f} ({percent}%)")

        results[metric_name] = {
            "scores": scores,
            "average": avg,
            "min": min_score,
            "max": max_score,
        }

    all_scores = [score for scores in metrics_scores.values() for score in scores]
    global_average = sum(all_scores) / len(all_scores) if all_scores else 0

    print("\n" + "=" * 70)
    print("OVERALL AVERAGE")
    print("=" * 70)
    global_percent = round(global_average * 100, 2)
    print(f"  Overall average:   {global_average:.4f} ({global_percent}%)")


async def run_evaluation(
    test_file: Path,
    chat_model: str,
    embedding_model: str,
    agent_id: str = "advanced-rag-expert",
    doc_lib_ids: list[str] | None = None,
):
    """
    Run evaluation of an agent using DeepEval metrics.

    This function loads test data, evaluates the agent's responses, and prints
    formatted results including various DeepEval metrics.
    """
    logger = logging.getLogger(__name__)

    if not test_file.is_file():
        raise FileNotFoundError(f"Test file not found: {test_file}")

    load_config()

    # Setup LLM for evaluation
    llm_as_judge = get_default_model()
    if isinstance(llm_as_judge, ChatOllama):
        setattr(llm_as_judge, "model", chat_model)
    if isinstance(llm_as_judge, ChatOpenAI):
        setattr(llm_as_judge, "model_name", chat_model)
    deepeval_llm = mapping_langchain_deepeval(llm_as_judge)

    logger.info(
        f"🔧 Configuration : chat_model={chat_model}, embedding_model={embedding_model}"
    )

    with open(test_file, "r", encoding="utf-8") as f:
        test_data = json.load(f)
    logger.info(f"📝 {len(test_data)} questions loaded from {test_file.name}")

    agent = await setup_agent(agent_id, doc_lib_ids)
    logger.info(f"🤖 Agent '{agent_id}' ready")

    faithfulness_metric = FaithfulnessMetric(
        model=deepeval_llm, verbose_mode=True, threshold=0.0
    )
    answer_relevancy_metric = AnswerRelevancyMetric(
        model=deepeval_llm, verbose_mode=True, threshold=0.0
    )
    contextual_precision_metric = ContextualPrecisionMetric(
        model=deepeval_llm, verbose_mode=True, threshold=0.0
    )
    contextual_recall_metric = ContextualRecallMetric(
        model=deepeval_llm, verbose_mode=True, threshold=0.0
    )
    contextual_relevancy_metric = ContextualRelevancyMetric(
        model=deepeval_llm, verbose_mode=True, threshold=0.0
    )

    test_cases = []

    logger.info("🔄 Evaluation in progress...")
    for i, item in enumerate(test_data, 1):
        result = await agent.ainvoke(
            {"question": item["question"], "retry_count": 0},
            config={"configurable": {"thread_id": f"eval_{i}"}},
        )

        messages = result.get("messages", [])
        documents = result.get("documents", [])

        actual_output = messages[-1].content if messages else ""
        retrieval_context = [doc.content for doc in documents]

        # Create DeepEval test case
        test_case = LLMTestCase(
            input=item["question"],
            actual_output=actual_output,
            expected_output=item["expected_answer"],
            retrieval_context=retrieval_context,
        )
        test_cases.append(test_case)

        logger.info(f"✓ Question {i}/{len(test_data)}")

    logger.info("📊 Calculation of DeepEval metrics...")

    # Evaluate all test cases
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

    calculate_metric_averages(results)

    return results


def parse_args():
    """
    Parse command-line arguments for the DeepEval evaluation script.

    Returns:
        argparse.Namespace: Parsed arguments including chat_model, embedding_model,
                            dataset_path, and doc_libs.
    """
    parser = argparse.ArgumentParser(description="DeepEval evaluation for RAG agents")

    parser.add_argument("--chat_model", required=True, help="Name of chat model")
    parser.add_argument(
        "--embedding_model", required=True, help="Name of the embedding model"
    )
    parser.add_argument(
        "--dataset_path",
        required=True,
        type=Path,
        help="Path to the JSON test file",
    )
    parser.add_argument(
        "--doc_libs",
        help="Document library IDs (separated by commas)",
    )

    return parser.parse_args()


async def main():
    """
    Main function to run the DeepEval evaluation.

    Parses command-line arguments, sets up logging, and executes the evaluation
    process using the specified models and dataset.
    """
    args = parse_args()
    setup_colored_logging()
    logger = logging.getLogger(__name__)

    try:
        doc_lib_ids = None
        if args.doc_libs:
            doc_lib_ids = [id.strip() for id in args.doc_libs.split(",")]
            logger.info(f"📚 Document libraries: {doc_lib_ids}")

        await run_evaluation(
            test_file=args.dataset_path,
            chat_model=args.chat_model,
            embedding_model=args.embedding_model,
            doc_lib_ids=doc_lib_ids,
        )

        return 0

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"
    os.environ["ERROR_REPORTING"] = "0"
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
