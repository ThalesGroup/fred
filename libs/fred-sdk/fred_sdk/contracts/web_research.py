# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded web research contract; deployment and identity stay outside tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SafeSearch = Literal["on", "moderate", "off"]
SearchProviderName = Literal["duckduckgo", "fixture", "brave"]
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
    focus: str | None = Field(
        default=None,
        max_length=2048,
        description=(
            "Key terms of what you are looking for. Selects the matching passages "
            "anywhere in the page; without it the page is read from the start or from offset. "
            "Never combine with offset."
        ),
    )
    max_passages: int = Field(default=8, ge=1, le=20)
    max_chars: int = Field(default=12_000, ge=500, le=50_000)
    offset: int = Field(
        default=0,
        ge=0,
        le=10_000_000,
        description=(
            "Continue reading the full page from this character: pass the previous "
            "result's next_offset, without focus."
        ),
    )
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

    @model_validator(mode="after")
    def offset_reads_the_full_page(self) -> FetchArguments:
        # next_offset is a position in the full page, meaningless inside focused passages.
        if self.offset and self.focus:
            raise ValueError(
                "focus and offset cannot be combined; omit focus to continue a page"
            )
        return self


class WebSearchRequest(WebSearchArguments):
    operation: Literal["web_search"] = "web_search"


class FetchRequest(FetchArguments):
    operation: Literal["fetch_url"] = "fetch_url"


WebResearchRequest = Annotated[
    WebSearchRequest | FetchRequest,
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
    # Offset of the text that follows, when the page continues past this result.
    next_offset: int | None = Field(default=None, ge=0)
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
    # duckduckgo: keyless (local); fixture: offline results; brave: keyed API with SLA.
    provider: SearchProviderName = "duckduckgo"
    provider_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]+$")
    fixture_file: str | None = None
    # Contract price used only for the admin cost estimate; 0 for keyless providers.
    cost_per_1000_searches: float = Field(default=0.0, ge=0, le=1000)
    proxy_url: str | None = None
    proxy_auth_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]+$")
    proxy_ca_file: str | None = None
    max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    retries: int = Field(default=1, ge=0, le=2)
    safesearch: SafeSearch = "on"
    # Ceilings on what reaches the model, whatever the tool arguments ask for.
    max_results: int = Field(default=5, ge=1, le=30)
    max_chars_per_page: int = Field(default=6000, ge=500, le=50_000)
    timeout_seconds: float = Field(default=60, ge=5, le=120)
    max_concurrency: int = Field(default=4, ge=1, le=32)
    activity_retention_days: int = Field(default=30, ge=1, le=365)
    purge_interval_seconds: int = Field(default=60, ge=5, le=3600)

    @field_validator("proxy_url")
    @classmethod
    def proxy_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
                and parsed.path in {"", "/"}
                and not any(char.isspace() for char in value)
                and (parsed.port is None or 1 <= parsed.port <= 65535)
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(
                "Invalid forward proxy endpoint; credentials belong in the secret environment."
            )
        return value.rstrip("/")

    @model_validator(mode="after")
    def provider_material(self) -> WebResearchDeploymentConfig:
        if self.provider == "brave" and not self.provider_key_env:
            raise ValueError("The brave provider requires provider_key_env.")
        if self.fixture_file and self.provider != "fixture":
            raise ValueError("fixture_file requires the fixture provider.")
        return self

    @model_validator(mode="after")
    def proxy_material(self) -> WebResearchDeploymentConfig:
        if (self.proxy_auth_env or self.proxy_ca_file) and not self.proxy_url:
            raise ValueError("Proxy credentials and CA require a proxy endpoint.")
        if self.proxy_ca_file and not (self.proxy_url or "").startswith("https://"):
            raise ValueError("A proxy CA requires an HTTPS proxy.")
        return self
