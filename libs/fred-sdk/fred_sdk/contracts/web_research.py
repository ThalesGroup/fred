# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded web research wire contract; deployment and identity stay outside tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

SafeSearch = Literal["on", "moderate", "off"]
Freshness = Literal["d", "w", "m", "y"]


class WebSearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2048)
    max_results: int = Field(default=8, ge=1, le=30)
    safesearch: SafeSearch = "on"
    region: str = Field(
        default="fr-fr", min_length=2, max_length=16, pattern=r"^[a-z-]+$"
    )
    timelimit: Freshness | None = None


class FetchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=4096)
    focus: str | None = Field(default=None, max_length=2048)
    max_passages: int = Field(default=8, ge=1, le=20)
    max_chars: int = Field(default=12_000, ge=500, le=50_000)
    include_links: bool = False

    @field_validator("url")
    @classmethod
    def public_url_syntax(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme in {"http", "https"}
                and parsed.hostname is not None
                and parsed.username is None
                and parsed.password is None
                and parsed.port in {None, 80, 443}
                and not any(character.isspace() for character in value)
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("unsupported_url")
        return value


class SearchAndFetchArguments(WebSearchArguments):
    max_results: int = Field(default=3, ge=1, le=10)
    max_passages: int = Field(default=5, ge=1, le=20)
    max_chars_per_page: int = Field(default=4000, ge=500, le=50_000)


class WebSearchRequest(WebSearchArguments):
    operation: Literal["web_search"] = "web_search"


class FetchRequest(FetchArguments):
    operation: Literal["fetch_url"] = "fetch_url"


class SearchAndFetchRequest(SearchAndFetchArguments):
    operation: Literal["search_and_fetch"] = "search_and_fetch"


WebResearchRequest = Annotated[
    WebSearchRequest | FetchRequest | SearchAndFetchRequest,
    Field(discriminator="operation"),
]


class WebPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(max_length=4096)
    final_url: str | None = Field(default=None, max_length=4096)
    title: str = Field(default="", max_length=512)
    snippet: str = Field(default="", max_length=2000)
    content: str | None = Field(default=None, max_length=50_000)
    content_type: str | None = Field(default=None, max_length=128)
    status: int | None = Field(default=None, ge=100, le=599)
    truncated: bool = False
    error_code: str | None = Field(default=None, pattern=r"^[a-z_]{1,64}$")


class WebResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[WebPage] = Field(default_factory=list, max_length=30)
    safesearch: SafeSearch | None = None
    untrusted_content: Literal[True] = True


class WebResearchError(RuntimeError):
    """Only a bounded code may cross a tool/observability boundary."""

    def __init__(self, code: str) -> None:
        allowed = {
            "unavailable",
            "timed_out",
            "rejected",
            "invalid_response",
            "activity_unavailable",
            "unsafe_destination",
            "too_many_redirects",
            "unsupported_content",
            "response_too_large",
            "provider_failed",
            "busy",
            "http_error",
        }
        self.code = code if code in allowed else "unavailable"
        super().__init__(self.code)


class WebResearchPort(ABC):
    @abstractmethod
    async def check_ready(self) -> None:
        """Fail if deployment transport or the restricted activity sink is absent."""

    @abstractmethod
    async def execute(self, request: WebResearchRequest) -> WebResearchResult:
        """Identity and correlation are bound privately by the platform adapter."""


class WebResearchDeploymentConfig(BaseModel):
    """Deployment policy; never editable by an agent or sent to the model."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    egress_url: str | None = None
    token_env: str = Field(
        default="WEB_RESEARCH_EGRESS_TOKEN", pattern=r"^[A-Z][A-Z0-9_]+$"
    )
    ca_file: str | None = None
    client_certificate: str | None = None
    client_key: str | None = None
    timeout_seconds: float = Field(default=60, ge=5, le=120)
    max_concurrency: int = Field(default=4, ge=1, le=32)
    activity_retention_days: int = Field(default=30, ge=1, le=365)
    purge_interval_seconds: int = Field(default=60, ge=5, le=3600)

    @field_validator("egress_url")
    @classmethod
    def https_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Web research egress must use HTTPS without embedded credentials."
            )
        return value.rstrip("/")
