# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from fred_core.documents.tree import DocumentTreeResult


class DocumentTreeResponse(DocumentTreeResult):
    """Bounded corpus navigation; folder/document records count towards limit."""
