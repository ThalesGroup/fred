import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from datasets import Dataset
from fred_core import ModelConfiguration, get_embeddings
from ragas import RunConfig, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    answer_relevancy,
    answer_similarity,
    context_precision,
    context_recall,
    faithfulness,
)

from app.agents.rags.advanced_rag_expert import AdvancedRico
from app.application_context import (
    ApplicationContext,
    get_configuration,
    get_default_model,
)
from app.common.utils import parse_server_configuration
from app.core.agents.runtime_context import RuntimeContext


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

    Args:
        model_name (str): The name of the model to be used for chat operations.

    Returns:
        The updated configuration object.
    """
    config_path = Path(__file__).parents[4] / "config" / "configuration.yaml"
    config = parse_server_configuration(str(config_path))
    ApplicationContext(config)
    return config


def setup_embedding_model(embedding_name: str, config):
    """
    Set up and configure an embedding model for use with Ragas.

    Args:
        embedding_name (str): The name of the embedding model to be used.
        config: The application configuration object containing model settings.

    Returns:
        LangchainEmbeddingsWrapper: A wrapped embedding model instance ready for use.
    """
    default_config = config.ai.default_chat_model.model_dump(exclude_unset=True)
    # Create a new ModelConfiguration including the desired embedding model name
    embedding_config = ModelConfiguration(**{**default_config, "model": embedding_name})
    embedding = get_embeddings(embedding_config)
    return LangchainEmbeddingsWrapper(embedding)


async def setup_agent(
    agent_name: str = "Rico Senior", doc_lib_ids: list[str] | None = None
):
    """
    Initialize and configure an agent by name, optionally setting document libraries.

    Args:
        agent_name (str): The name of the agent to initialize. Defaults to "Rico Senior".
        doc_lib_ids (list): Optional list of document library IDs to set in runtime context.

    Returns:
        The compiled graph of the initialized agent.
    """
    agents = get_configuration().ai.agents
    settings = next((a for a in agents if a.name == agent_name), None)

    if not settings:
        available = [a.name for a in agents]
        raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

    agent = AdvancedRico(settings)
    await agent.async_init()

    if doc_lib_ids:
        agent.set_runtime_context(
            RuntimeContext(selected_document_libraries_ids=doc_lib_ids)
        )

    return agent.get_compiled_graph()


def print_results(results):
    """
    Print evaluation results in a formatted and visual way.
    Displays scores for each metric with a progress bar representation.
    """
    print("\n" + "=" * 70)
    print("📈 RAGAS EVALUATION RESULTS")
    print("=" * 70)

    scores = results.scores[0]
    metrics = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "answer_similarity",
    ]

    for metric in metrics:
        if metric in scores:
            score = scores[metric]
            bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
            print(f"  {metric:20s} : {bar} {score:.3f}")

    print("=" * 70 + "\n")


async def run_evaluation(
    test_file: Path,
    chat_model: str,
    embedding_model: str,
    agent_name: str = "Rico Senior",
    doc_lib_ids: list[str] | None = None,
):
    """
    Run evaluation of an agent using RAGAS metrics.

    This function loads test data, evaluates the agent's responses, and prints
    formatted results including various RAGAS metrics.
    """
    logger = logging.getLogger(__name__)

    if not test_file.is_file():
        raise FileNotFoundError(f"Test file not found: {test_file}")
    config = load_config()

    llm_as_judge = get_default_model()
    # Avoid assigning unknown attributes on BaseLanguageModel; set the model name dynamically
    setattr(llm_as_judge, "model", chat_model)
    llm = LangchainLLMWrapper(llm_as_judge)
    embeddings = setup_embedding_model(embedding_model, config)

    logger.info(
        f"🔧 Configuration : chat_model={chat_model}, embedding_model={embedding_model}"
    )

    with open(test_file, "r", encoding="utf-8") as f:
        test_data = json.load(f)
    logger.info(f"📝 {len(test_data)} questions loaded from {test_file.name}")

    agent = await setup_agent(agent_name, doc_lib_ids)
    logger.info(f"🤖 Agent '{agent_name}' ready")

    evaluation_data = {"question": [], "answer": [], "contexts": [], "ground_truth": []}

    logger.info("🔄 Evaluation in progress...")
    for i, item in enumerate(test_data, 1):
        result = await agent.ainvoke(
            {"question": item["question"], "retry_count": 0},
            config={"configurable": {"thread_id": f"eval_{i}"}},
        )

        messages = result.get("messages", [])
        documents = result.get("documents", [])

        evaluation_data["question"].append(item["question"])
        evaluation_data["answer"].append(messages[-1].content if messages else "")
        evaluation_data["ground_truth"].append(item["expected_answer"])
        evaluation_data["contexts"].append([doc.content for doc in documents])

        logger.info(f"✓ Question {i}/{len(test_data)}")

    logger.info("📊 Calculation of RAGAS metrics...")
    dataset = Dataset.from_dict(evaluation_data)

    results = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
            answer_similarity,
        ],
        llm=llm,
        embeddings=embeddings,
        run_config=RunConfig(timeout=3600),
    )

    print_results(results)

    return results


def parse_args():
    """
    Parse command-line arguments for the RAGAS evaluation script.

    Returns:
        argparse.Namespace: Parsed arguments including chat_model, embedding_model,
                            dataset_path, and doc_libs.
    """
    parser = argparse.ArgumentParser(description="RAGAS evaluation for RAG agents")

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
    Main function to run the RAGAS evaluation.

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
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
