import logging
import sys
from pathlib import Path

from app.common.utils import parse_server_configuration
from app.application_context import ApplicationContext

from fred_core import ModelConfiguration, get_embeddings

from ragas.embeddings import LangchainEmbeddingsWrapper

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
    embedding_config = ModelConfiguration(**default_config)
    embedding = get_embeddings(embedding_config)
    embedding.model = embedding_name
    return LangchainEmbeddingsWrapper(embedding)