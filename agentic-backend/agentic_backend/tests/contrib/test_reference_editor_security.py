import types

import pytest
from fred_core import OwnerFilter
from pydantic import ValidationError

from agentic_backend.agents.reference_editor.image_search_util import (
    search_image_by_name,
)
from agentic_backend.agents.reference_editor.pydantic_models import (
    InformationsProjet,
)
from agentic_backend.agents.reference_editor.validation_tools import (
    _normalize_reference_payload_for_validation,
)


def test_normalize_reference_payload_accepts_wrapped_payload():
    wrapped = {
        "data": {
            "informationsProjet": {},
            "contexte": {},
            "syntheseProjet": {},
        }
    }
    payload, err = _normalize_reference_payload_for_validation(wrapped)
    assert err is None
    assert payload == wrapped["data"]


def test_normalize_reference_payload_rejects_old_schema_shape():
    old_shape = {
        "enjeuxBesoins": {},
        "cv": {},
        "prestationFinanciere": {},
    }
    payload, err = _normalize_reference_payload_for_validation(old_shape)
    assert payload is None
    assert err is not None
    assert "Bad root key format" in err


def test_reference_schema_accepts_valid_partial_payload():
    """Pydantic models use defaults, so partial payloads are valid."""
    valid = InformationsProjet(
        nomSociete="Acme",
        nomProjet="Project X",
        dateProjet="",
        nombrePersonnes="",
        enjeuFinancier="",
    )
    assert valid.nomSociete == "Acme"
    assert valid.dateProjet == ""


def test_reference_schema_rejects_field_exceeding_max_length():
    with pytest.raises(ValidationError) as exc_info:
        InformationsProjet(
            nomSociete="A" * 51,
            nomProjet="",
            dateProjet="",
            nombrePersonnes="",
            enjeuFinancier="",
        )
    assert any(
        "max_length" in str(err) or "most" in str(err["msg"])
        for err in exc_info.value.errors()
    )


@pytest.mark.asyncio
async def test_search_image_by_name_forwards_only_allowed_scope_options():
    class DummySearchClient:
        def __init__(self):
            self.kwargs = None

        async def search(self, **kwargs):
            self.kwargs = kwargs
            return [types.SimpleNamespace(uid="doc-1", file_name="Nvidia.png")]

    client = DummySearchClient()
    result = await search_image_by_name(
        "Nvidia",
        client,
        None,
        search_options={
            "owner_filter": OwnerFilter.TEAM,
            "team_id": "team-42",
            "document_library_tags_ids": ["lib-a"],
            "include_session_scope": False,
            "include_corpus_scope": True,
            "question": "should-not-override",
            "unexpected": "should-be-ignored",
        },
    )

    assert result == "doc-1"
    assert client.kwargs is not None
    assert client.kwargs["question"] == "Nvidia"
    assert client.kwargs["top_k"] == 5
    assert client.kwargs["search_policy"] == "semantic"
    assert client.kwargs["owner_filter"] == OwnerFilter.TEAM
    assert client.kwargs["team_id"] == "team-42"
    assert client.kwargs["document_library_tags_ids"] == ["lib-a"]
    assert "unexpected" not in client.kwargs


@pytest.mark.asyncio
async def test_search_image_by_name_defaults_to_personal_scope_when_unspecified():
    class DummySearchClient:
        def __init__(self):
            self.kwargs = None

        async def search(self, **kwargs):
            self.kwargs = kwargs
            return [types.SimpleNamespace(uid="doc-1", file_name="Nvidia.png")]

    client = DummySearchClient()
    _ = await search_image_by_name(
        "Nvidia",
        client,
        None,
        search_options={},
    )

    assert client.kwargs is not None
    assert client.kwargs["owner_filter"] == OwnerFilter.PERSONAL
