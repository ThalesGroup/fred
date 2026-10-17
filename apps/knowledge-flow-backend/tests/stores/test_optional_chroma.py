"""Optional storage must fail clearly without affecting other vector backends."""

import builtins
import importlib.util

import pytest
from langchain_community.embeddings import FakeEmbeddings

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import ChromaVectorStorageConfig

CHROMA_ADAPTER = "knowledge_flow_backend.core.stores.vector.chromadb_vector_store"


def test_missing_chroma_is_rejected_before_startup(app_context, monkeypatch, tmp_path):
    config = app_context.configuration
    config.storage.vector_store = ChromaVectorStorageConfig(type="chroma", local_path=str(tmp_path / "vectors"))
    original_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None if name == "chromadb" else original_find_spec(name))
    ApplicationContext.reset_instance()
    with pytest.raises(ImportError, match="uv sync --extra chroma") as raised:
        ApplicationContext(config)
    assert "INSTALL_CHROMA=true" in str(raised.value)
    assert ApplicationContext._instance is None
    assert not (tmp_path / "vectors").exists()


def test_chroma_preserves_unrelated_import_errors(app_context, monkeypatch, tmp_path):
    app_context.configuration.storage.vector_store = ChromaVectorStorageConfig(type="chroma", local_path=str(tmp_path / "vectors"))
    original_import = builtins.__import__
    failure = ModuleNotFoundError("No module named 'unrelated_dependency'", name="unrelated_dependency")

    def import_without_dependency(name, *args, **kwargs):
        if name == CHROMA_ADAPTER:
            raise failure
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_dependency)
    with pytest.raises(ModuleNotFoundError) as raised:
        app_context.get_create_vector_store(FakeEmbeddings(size=8))
    assert raised.value is failure


def test_in_memory_vector_store_does_not_import_chroma(app_context, monkeypatch):
    original_import = builtins.__import__

    def import_without_chroma(name, *args, **kwargs):
        assert name != CHROMA_ADAPTER and not name.startswith("chromadb"), name
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_chroma)
    original_find_spec = importlib.util.find_spec

    def find_spec_without_chroma(name):
        assert name != "chromadb"
        return original_find_spec(name)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec_without_chroma)
    ApplicationContext.reset_instance()
    context = ApplicationContext(app_context.configuration)
    store = context.get_create_vector_store(FakeEmbeddings(size=8))
    assert store is not None
