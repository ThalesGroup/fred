from fred_sdk.contracts.context import RuntimeContext

from fred_runtime.runtime_support import (
    get_document_library_tags_ids,
    get_search_policy,
    get_vector_search_scopes,
    set_attachments_markdown,
)


def test_runtime_context_helpers_defaults():
    context = RuntimeContext()

    assert get_document_library_tags_ids(None) is None
    assert get_search_policy(None) == "semantic"
    assert get_vector_search_scopes(None) == (True, True)

    set_attachments_markdown(context, "# Notes")
    assert context.attachments_markdown == "# Notes"
