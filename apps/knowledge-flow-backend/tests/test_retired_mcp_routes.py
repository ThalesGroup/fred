"""Retired MCP transports are no longer mounted in Knowledge Flow."""

from knowledge_flow_backend import main as main_module
from knowledge_flow_backend.application_context import ApplicationContext


def test_corpus_and_filesystem_mcp_mounts_are_absent(app_context, monkeypatch) -> None:
    configuration = app_context.configuration
    monkeypatch.setattr(main_module, "load_configuration", lambda: configuration)
    monkeypatch.setattr(main_module, "start_http_server", lambda *args, **kwargs: None)
    for name in (
        "MonitoringController",
        "TasksController",
        "MetadataController",
        "ContentController",
        "IngestionController",
        "LibrarySyncController",
        "TagController",
        "VectorSearchController",
        "CorpusTreeController",
        "SummarizeController",
        "ExtractController",
        "ResourceController",
        "McpFilesystemController",
        "CorpusManagerController",
        "TabularController",
        "OpenSearchOpsController",
        "SchedulerController",
    ):
        monkeypatch.setattr(main_module, name, lambda *args, **kwargs: None)

    ApplicationContext.reset_instance()
    try:
        app = main_module.create_app()
        paths = {getattr(route, "path", "") for route in app.routes}
    finally:
        ApplicationContext.reset_instance()

    base = configuration.app.base_url

    assert not any(path.startswith(f"{base}/mcp-fs") for path in paths)
    assert not any(path.startswith(f"{base}/mcp-corpus") for path in paths)
