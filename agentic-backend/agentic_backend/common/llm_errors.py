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

"""
Utilities to normalize LLM/model exceptions and produce consistent log + user-facing messages.

This keeps guardrail/refusal detection centralized so agents do not each hand-roll
slightly different error handling logic.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

# Best-effort detection of OpenAI guardrail errors without a hard dependency on openai symbols.
_UNPROCESSABLE_NAMES = {"UnprocessableEntityError"}
# Azure/OpenAI content-filter specifics we want to treat as guardrail/refusal:
# - HTTP 400 with error.code == "content_filter"
# - innererror.code == "ResponsibleAIPolicyViolation"


def _is_guardrail(status: Optional[int], exc: Exception, body: Any) -> bool:
    if status == 422 or type(exc).__name__ in _UNPROCESSABLE_NAMES:
        return True
    if status == 400 and isinstance(body, dict):
        err = body.get("error") or {}
        code = err.get("code") or err.get("type")
        inner_code = (err.get("innererror") or {}).get("code")
        if code == "content_filter" or inner_code == "ResponsibleAIPolicyViolation":
            return True
    # Fallback pattern match on the exception text in case body/status are not populated
    exc_text = str(exc).lower()
    if "content_filter" in exc_text or "responsibleaipolicyviolation" in exc_text:
        return True
    if "content management policy" in exc_text:
        return True
    return False


logger = logging.getLogger(__name__)


@dataclass
class LlmErrorInfo:
    """
    Normalized view of an LLM/model exception that callers can log or surface to UIs.
    """

    type_name: str
    status: Optional[int]
    request_id: Optional[str]
    headers: Optional[Dict[str, Any]]
    body: Any
    is_guardrail: bool
    detail: Optional[str]


def _extract_body(response: Any) -> Any:
    if response is None:
        return None
    # httpx Response exposes json()/text; keep this defensive.
    try:
        return response.json()
    except Exception:
        logger.warning("Failed to extract JSON body from response", exc_info=True)
        pass
    return response.text if hasattr(response, "text") else None


def normalize_llm_exception(exc: Exception) -> LlmErrorInfo:
    """
    Pulls out common error attributes from a model exception so downstream handling can be uniform.
    """
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    response = getattr(exc, "response", None)
    body = getattr(exc, "body", None)
    if body is None and response is not None:
        body = _extract_body(response)

    request_id = getattr(exc, "request_id", None) or getattr(
        response, "request_id", None
    )
    headers = getattr(response, "headers", None)
    headers_dict = dict(headers) if headers else None

    detail = None
    if isinstance(body, dict):
        detail = body.get("error", {}).get("message") or body.get("message")

    is_guardrail = _is_guardrail(status, exc, body)

    return LlmErrorInfo(
        type_name=type(exc).__name__,
        status=status,
        request_id=request_id,
        headers=headers_dict,
        body=body,
        is_guardrail=is_guardrail,
        detail=detail,
    )


def guardrail_fallback_message(
    info: LlmErrorInfo,
    *,
    language: Optional[str] = None,
    default_message: str = "An unexpected error occurred while searching documents. Please try again.",
) -> str:
    """
    Returns a user-facing fallback string that highlights guardrail/refusal cases when detected.
    """
    if info.is_guardrail:
        lang = (language or "").lower()
        if lang.startswith("fr"):
            base = (
                "Le modèle a refusé de répondre car les filtres de sécurité du fournisseur ont bloqué la requête ou son contenu. "
                "Merci de reformuler, retirer toute donnée sensible, ou simplifier la demande puis réessayer."
            )
        else:
            base = (
                "The model refused to answer because the provider's safety filters blocked the prompt or content. "
                "Please rephrase, remove sensitive data, or simplify the request and try again."
            )
        if info.detail:
            return f"{base} Details: {info.detail}"
        return base
    return default_message


def error_log_context(
    info: LlmErrorInfo, *, extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Builds a dict that can be unpacked into logger calls for consistent telemetry.
    """
    payload = {
        "err_type": info.type_name,
        "status": info.status,
        "request_id": info.request_id,
        "body": info.body,
        "headers": info.headers,
        "is_guardrail": info.is_guardrail,
        "detail": info.detail,
    }
    if extra:
        payload.update(extra)
    return payload


__all__ = [
    "LlmErrorInfo",
    "normalize_llm_exception",
    "guardrail_fallback_message",
    "error_log_context",
]
