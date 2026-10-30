# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from uuid import uuid4

import pytest
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DocumentAccessContext
from pydantic import ValidationError


def test_corpus_context_defaults_do_not_admit_attachments() -> None:
    context = DocumentAccessContext(space_id=uuid4(), document_scope=DocumentScope())
    assert context.conversation_id is None and context.attachment_ids == ()
    assert (
        DocumentAccessContext.model_validate_json(context.model_dump_json()) == context
    )


def test_attachment_ids_need_a_conversation_but_have_no_fixed_count_limit() -> None:
    ids = tuple(uuid4() for _ in range(125))
    with pytest.raises(ValidationError, match="requires conversation_id"):
        DocumentAccessContext(
            space_id=uuid4(), document_scope=DocumentScope(), attachment_ids=ids
        )
    context = DocumentAccessContext(
        space_id=uuid4(),
        document_scope=DocumentScope(),
        conversation_id=uuid4(),
        attachment_ids=ids,
    )
    assert (
        DocumentAccessContext.model_validate_json(
            context.model_dump_json()
        ).attachment_ids
        == ids
    )
