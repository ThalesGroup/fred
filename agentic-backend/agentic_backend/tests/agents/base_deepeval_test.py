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

import argparse
import json
import logging
import os
import sys
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path
from typing import List, Optional, Type, Union

from deepeval.models import GPTModel, OllamaModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from agentic_backend.application_context import (
    ApplicationContext,
    get_configuration,
    get_default_model,
)
from agentic_backend.common.structures import Configuration
from agentic_backend.common.utils import parse_server_configuration
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.runtime_context import RuntimeContext


class BaseEvaluator(ABC):
    def __init__(self):
        self.config: Optional[Configuration] = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self.deepeval_llm: Optional[Union[GPTModel, OllamaModel]] = None
        self.chat_model: Optional[str] = None
        self.embedding_model: Optional[str] = None
        self.dataset: List = []
        self.dataset_path: Optional[Path] = None
        self.configuration_file: Optional[str] = None

    def setup_colored_logging(self):
        """
        Setup a colored logging configuration to make logs more readable in the terminal.
        It applies different colors to different log levels.
        """
        COLORS = {
            "DEBUG": "\033[36m",
            "INFO": "\033[32m",
            "WARNING": "\033[33m",
            "ERROR": "\033[31m",
            "CRITICAL": "\033[35m",
        }

        class ColorFormatter(logging.Formatter):
            """
            Custom Formatter to add colors to the log messages based on the log level.
            """

            def format(self, record):
                color = COLORS.get(record.levelname, "\033[0m")
                record.levelname = f"{color}{record.levelname}\033[0m"
                return super().format(record)

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            ColorFormatter(
                "%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S"
            )
        )

        logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
        self.logger = logging.getLogger(self.__class__.__name__)

    def load_config(self, configuration_file: str = "configuration.yaml"):
        """
        Load configuration from a YAML file.

        This method reads the configuration file from the specified path,
        parses it using the parse_server_configuration function, and sets it
        as the configuration for the ApplicationContext.

        Args:
            configuration_file (str): The path to the configuration file. Default is "configuration.yaml".

        Returns:
            dict: The parsed configuration.
        """
        config_path = Path(__file__).parents[3] / "config" / configuration_file

        if not config_path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        config = parse_server_configuration(str(config_path))
        ApplicationContext(config)
        self.config = config
        return config

    def load_deepeval_llm(self):
        """
        Load the deepeval large language model (LLM) for evaluation.

        This method retrieves the default model and sets it up for use with deepeval,
        configuring the appropriate model names based on the type of the LLM (Ollama or OpenAI).
        It then maps the LangChain model to the deepeval model and logs the configuration.

        The method ensures that the appropriate model names are set for different LLM types
        and updates the deepeval_llm attribute to hold the configured model.
        """
        llm_as_judge = get_default_model()
        if isinstance(llm_as_judge, ChatOllama):
            setattr(llm_as_judge, "model", self.chat_model)
        if isinstance(llm_as_judge, ChatOpenAI):
            setattr(llm_as_judge, "model_name", self.chat_model)
        self.deepeval_llm = self.mapping_langchain_deepeval(llm_as_judge)

        self.logger.info(
            f"🔧 Configuration : chat_model={self.chat_model}, embedding_model={self.embedding_model}"
        )

    def mapping_langchain_deepeval(self, langchain_model):
        """
        Maps a LangChain model to the corresponding deepeval model.

        Args:
            langchain_model: An instance of a LangChain model (ChatOllama or ChatOpenAI).

        Returns:
            Union[GPTModel, OllamaModel]: The corresponding deepeval model instance.
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

    def load_dataset(self):
        """
        Load the dataset from a JSON file.

        Raises:
            ValueError: If the dataset_path is not set.
            FileNotFoundError: If the specified dataset file does not exist.
        """
        if self.dataset_path is None:
            raise ValueError("dataset_path is not set")

        if not self.dataset_path.is_file():
            raise FileNotFoundError(f"Test file not found: {self.dataset_path}")

        with open(self.dataset_path, "r", encoding="utf-8") as f:
            self.dataset = json.load(f)

    async def setup_agent(
        self,
        agent_type: Type[AgentFlow],
        agent_id: str,
        doc_lib_ids: list[str] | None = None,
    ):
        """
        Setup the agent for evaluation.

        Args:
            agent_type (Type[AgentFlow]): The type of agent to initialize.
            agent_id (str): The id of the agent to retrieve settings for.
            doc_lib_ids (list[str] | None, optional): List of document library IDs to set in the runtime context. Default is None.

        Returns:
            Any: The compiled graph of the initialized agent.
        """
        agents = get_configuration().ai.agents
        settings = next((a for a in agents if a.id == agent_id), None)

        if not settings:
            available = [a.id for a in agents]
            raise ValueError(f"Agent '{agent_id}' not found. Available: {available}")

        agent = agent_type(settings)
        await agent.async_init(runtime_context=RuntimeContext())
        agent.set_runtime_context(
            context=RuntimeContext(access_token="fake_token")  # nosec B106
        )

        if doc_lib_ids:
            agent.set_runtime_context(
                RuntimeContext(selected_document_libraries_ids=doc_lib_ids)
            )

        return agent.get_compiled_graph()

    def calculate_metric_averages(self, result):
        """
        Calculate average scores for each metric and overall average score from test results.

        Args:
            result: The test result object containing metrics data.

        Returns:
            dict: A dictionary with metric names as keys and a dictionary of metric details as values.
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

    def parse_args(self):
        """
        Parse command line arguments for the script.

        Returns:
            argparse.Namespace: Parsed command line arguments.
        """
        parser = argparse.ArgumentParser(description="DeepEval evaluation for agents")

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
            "--configuration_file",
            help="Name to the configuration file",
        )
        parser.add_argument(
            "--doc_libs",
            help="Document library IDs (separated by commas)",
        )

        return parser.parse_args()

    @abstractmethod
    async def run_evaluation(
        self,
        agent_id: str,
        doc_lib_ids: list[str] | None = None,
    ):
        pass

    async def main(self, agent_id: str):
        """
        Main function to run the evaluation process for a specified agent.

        Args:
            agent_id (str): The id of the agent to evaluate.

        Returns:
            int: Exit status code (0 for success, 1 for error).
        """
        os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"
        os.environ["ERROR_REPORTING"] = "0"
        os.environ["DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"] = "600"

        self.setup_colored_logging()
        args = self.parse_args()

        self.chat_model = args.chat_model
        self.embedding_model = args.embedding_model
        self.dataset_path = args.dataset_path

        try:
            doc_lib_ids = None
            if args.doc_libs:
                doc_lib_ids = [id.strip() for id in args.doc_libs.split(",")]
                self.logger.info(f"📚 Document libraries: {doc_lib_ids}")
            if args.configuration_file:
                config_file: str = args.configuration_file
                self.configuration_file = config_file
                self.logger.info(f"📖 Configuration file: {config_file}")
                self.load_config(configuration_file=config_file)
            else:
                self.load_config()
            self.load_deepeval_llm()
            self.load_dataset()

            results = await self.run_evaluation(
                agent_id=agent_id,
                doc_lib_ids=doc_lib_ids,
            )

            self.calculate_metric_averages(results)

            return 0

        except Exception as e:
            if self.logger:
                self.logger.error(f"❌ Error: {e}")
            else:
                print(f"❌ Error: {e}", file=sys.stderr)
            return 1
