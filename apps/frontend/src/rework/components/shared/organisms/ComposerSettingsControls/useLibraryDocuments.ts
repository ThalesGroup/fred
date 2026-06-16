// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useEffect, useState } from "react";
import {
  type DocumentMetadata,
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { buildLibrarySelectionKey, parseLibrarySelectionKey } from "./documentSelection";

const DOCUMENT_PAGE_SIZE = 100;

type UseLibraryDocumentsResult = {
  documents: DocumentMetadata[];
  isLoading: boolean;
  error: string | null;
};

/**
 * Fetch the first metadata page for each selected library and merge the visible documents.
 *
 * Why this exists:
 * - the composer only needs lightweight document metadata for selection
 * - keeping the fetch logic in one hook avoids duplicating loading/error/reconcile behavior
 *
 * How to use:
 * - pass the effective library ids (selected or bound)
 * - render from `documents`, `isLoading`, and `error`
 */
export function useLibraryDocuments(libraryIds: string[]): UseLibraryDocumentsResult {
  const [browseDocumentsByTag] = useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation();
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const libraryKey = buildLibrarySelectionKey(libraryIds);

  useEffect(() => {
    const normalizedLibraryIds = parseLibrarySelectionKey(libraryKey);

    if (normalizedLibraryIds.length === 0) {
      setDocuments([]);
      setIsLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;

    async function load(): Promise<void> {
      setIsLoading(true);
      setError(null);

      try {
        const responses = await Promise.all(
          normalizedLibraryIds.map((libraryId) =>
            browseDocumentsByTag({
              browseDocumentsByTagRequest: {
                tag_id: libraryId,
                offset: 0,
                limit: DOCUMENT_PAGE_SIZE,
              },
            }).unwrap(),
          ),
        );

        if (cancelled) return;

        const merged = new Map<string, DocumentMetadata>();
        for (const response of responses) {
          for (const document of response.documents ?? []) {
            merged.set(document.identity.document_uid, document);
          }
        }

        const sortedDocuments = Array.from(merged.values()).sort((left, right) => {
          const leftLabel = left.identity.title || left.identity.document_name;
          const rightLabel = right.identity.title || right.identity.document_name;
          return leftLabel.localeCompare(rightLabel);
        });

        setDocuments(sortedDocuments);
      } catch {
        if (cancelled) return;
        setDocuments([]);
        setError("load_failed");
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [browseDocumentsByTag, libraryKey]);

  return { documents, isLoading, error };
}
