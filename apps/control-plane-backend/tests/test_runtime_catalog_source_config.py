import pytest
from pydantic import ValidationError

from control_plane_backend.config.models import RuntimeCatalogSourceConfig


@pytest.mark.parametrize("prefix", [None, "/runtime/agents-v2", "/samples/agents/v1"])
def test_runtime_ingress_prefix_accepts_canonical_paths(prefix: str | None) -> None:
    source = RuntimeCatalogSourceConfig(
        runtime_id="agents",
        base_url="http://internal-runtime",
        ingress_prefix=prefix,
    )

    assert source.ingress_prefix == prefix


@pytest.mark.parametrize(
    "prefix",
    [
        "https://outside.example/runtime",
        "//outside.example/runtime",
        "runtime/agents",
        "/runtime/../outside",
        "/runtime/./agents",
        "/runtime/%2foutside",
        "/runtime/%2e%2e/outside",
        "/runtime\\outside",
        "/runtime/agents?next=outside",
        "/runtime/agents#outside",
        "/runtime//agents",
        "/runtime/agents/",
        "/runtime/ agents",
    ],
)
def test_runtime_ingress_prefix_rejects_unsafe_or_ambiguous_paths(prefix: str) -> None:
    with pytest.raises(ValidationError):
        RuntimeCatalogSourceConfig(
            runtime_id="agents",
            base_url="http://internal-runtime",
            ingress_prefix=prefix,
        )
