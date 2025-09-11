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

from datetime import datetime, timezone
import logging
import traceback
from pydantic import ValidationError
from pydantic_settings import BaseSettings
import tiktoken
import yaml
import re
from typing import Dict, Optional, TypeVar

from app.common.structures import Configuration

logger = logging.getLogger(__name__)


def parse_server_configuration(configuration_path: str) -> Configuration:
    """
    Parses the server configuration from a YAML file.

    Args:
        configuration_path (str): The path to the configuration YAML file.

    Returns:
        Configuration: The parsed configuration object.
    """
    with open(configuration_path, "r") as f:
        try:
            config: Dict = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Error while parsing configuration file {configuration_path}: {e}")
            exit(1)
    return Configuration(**config)


def get_embedding_model_name(embedding_model: object) -> str:
    """
    Returns a clean string name for the embedding model, even if wrapped inside a custom class.
    """
    if hasattr(embedding_model, "model"):
        inner = getattr(embedding_model, "model")
        return getattr(inner, "model", type(inner).__name__)
    return getattr(embedding_model, "model", type(embedding_model).__name__)


B = TypeVar("B", bound=BaseSettings)


def validate_settings_or_exit(cls: type[B], name: str = "Settings") -> B:
    try:
        return cls()
    except ValidationError as e:
        logger.critical(f"❌ Invalid {name}:")
        for error in e.errors():
            field = error.get("loc", ["?"])[0]
            msg = error.get("msg", "")
            logger.critical(f"   - Missing or invalid: {field} → {msg}")
        logger.critical("📌 Tip: Check your .env file or environment variables.")
        raise SystemExit(1)


def log_exception(e: Exception, context_message: Optional[str] = None) -> str:
    """
    Logs an exception with full details (preserving caller's location)
    and returns a short, user-friendly summary string for UI display.

    Args:
        e (Exception): The exception to log.
        context_message (Optional[str]): Additional context for the logs.

    Returns:
        str: A human-readable summary of the exception.
    """
    error_type = type(e).__name__
    error_message = str(e)
    stack_trace = traceback.format_exc()

    # Detect root cause if chained exception
    cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
    root_cause = repr(cause) if cause else error_message

    # Short, user-friendly summary
    user_hint = ""
    if "Connection refused" in error_message:
        user_hint = "A service might be down or unreachable."
    elif "timeout" in error_message.lower():
        user_hint = "The system took too long to respond."
    elif "not found" in error_message.lower():
        user_hint = "Something you're trying to access doesn't exist."
    elif "authentication" in error_message.lower():
        user_hint = "There might be a credentials or permissions issue."
    else:
        user_hint = "An unexpected error occurred."

    # ✅ Compose final summary string
    summary = f"{error_type}: {error_message} — {user_hint}"

    # Log full details
    logger.error("Exception occurred: %s", error_type, stacklevel=2)
    if context_message:
        logger.error("🔍 Context: %s", context_message, stacklevel=2)
    logger.error("🧩 Error message: %s", error_message, stacklevel=2)
    logger.error("📦 Root cause: %s", root_cause, stacklevel=2)
    logger.debug("🧵 Stack trace:\n%s", stack_trace, stacklevel=2)

    return summary


def utc_now_iso() -> str:
    """
    Returns the current UTC timestamp as an ISO 8601 formatted string.

    This utility is useful for ensuring consistent and timezone-aware
    timestamps across metadata (e.g., `created_at`, `updated_at`).

    Example:
        >>> utc_now_iso()
        '2025-06-21T14:32:05.123456+00:00'

    Returns:
        str: The current UTC time in ISO 8601 format with timezone info.
    """
    return datetime.now(timezone.utc).isoformat()


def count_tokens(text: str) -> int:
    """
    Count the number of tokens in a given text using the best available method.

    ⚠️ BACKGROUND & CONTEXT:
    ------------------------
    This function is used to measure the "size" of a document in terms of tokens,
    which is the billing and processing unit for Large Language Models (LLMs).

    However, tokenization is *not* standardized across models or providers:
    - OpenAI (via `tiktoken`) uses a specific BPE tokenizer (e.g., cl100k_base)
    - Mistral and other open models may use different tokenizers (e.g., HuggingFace BPE, SentencePiece)
    - Some providers (e.g., Anthropic) use *undocumented* or custom schemes

    ❗Why does it matter?
    - If we overestimate tokens: we may reject files that are actually OK
    - If we underestimate tokens: we risk crashing or exceeding model limits
    - If we hardcode token logic: we tie ourselves to OpenAI assumptions

    🧩 STRATEGY:
    -----------
    1. If the configured embedder exposes a `count_tokens(text)` method, use it.
       ✅ This gives accurate results for the currently selected embedding model.

    2. Otherwise, fallback to `tiktoken` using the embedder's model name
       ⚠️ WARNING: Only works for OpenAI-compatible models
       ⚠️ May be inaccurate for others (e.g., Mistral, Cohere)

    🔒 This logic should eventually be moved to a TokenCounterService abstraction
       if/when the embedding logic becomes more diverse.

    A final not: this method assumes the application context is initialized.

    Args:
        text (str): The plain text to tokenize.

    Returns:
        int: Estimated token count.
    """
    from app.application_context import ApplicationContext

    embedder = ApplicationContext.get_instance().get_embedder()

    # Preferred path: embedder provides its own token counting logic
    if hasattr(embedder, "count_tokens"):
        try:
            return embedder.count_tokens(text)
        except Exception as e:
            logger.warning(f"Embedder-specific token count failed: {e}")

    # Fallback path: use tiktoken based on the embedder's model name
    try:
        model_name = getattr(embedder.embedding, "model_name", "cl100k_base")
        encoding = tiktoken.encoding_for_model(model_name)
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Fallback to cl100k_base tokenizer due to error: {e}")
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))


def sanitize_sql_name(name: str) -> str:
    """
    Sanitize a table or column name to be SQL-friendly:
    - Lowercase
    - Replace spaces and invalid characters with underscores
    - Remove leading/trailing underscores
    """
    name = name.lower()
    name = re.sub(r"[^a-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    return name
