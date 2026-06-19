// Copyright Thales 2025
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

/**
 * useWritableDocuments
 * --------------------
 * Owns the state for the collaborative "writable documents" editor pane:
 * - the list of documents for the active session (authoritative, from the API),
 *   merged with documents that just arrived live in the chat stream;
 * - the currently selected document tab and whether the pane is open;
 * - editing (debounced PUT) and local optimistic content.
 *
 * The backend store is the source of truth: on session load/refresh the list query
 * rehydrates content, so a user who edited then refreshed sees their latest text.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChatMessage,
  useListWritableDocumentsAgenticV1WritableDocumentsSessionIdGetQuery,
  useUpdateWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdPutMutation,
  WritableDocumentResponse,
} from "../../slices/agentic/agenticOpenApi";

const AUTOSAVE_DEBOUNCE_MS = 800;

export type WritableDocument = {
  document_id: string;
  title: string;
  content_md: string;
  updated_at?: string | null;
};

export type UseWritableDocuments = {
  documents: WritableDocument[];
  selectedId: string | null;
  selectDocument: (documentId: string) => void;
  isPaneOpen: boolean;
  openPane: (documentId?: string) => void;
  closePane: () => void;
  /** Called by the editor on change; debounced PUT persists the user edit. */
  onEditDocument: (documentId: string, contentMd: string) => void;
  isSaving: boolean;
};

/** Extract WritableDocumentParts that arrived live in the chat stream (latest per id). */
function documentsFromMessages(messages: ChatMessage[]): WritableDocument[] {
  const ordered = [...messages].sort((a, b) => a.rank - b.rank);
  const byId = new Map<string, WritableDocument>();
  for (const msg of ordered) {
    for (const part of msg.parts ?? []) {
      if ((part as { type?: string }).type !== "writable_document") continue;
      const p = part as {
        document_id: string;
        title: string;
        content_md: string;
        updated_at?: string;
      };
      byId.set(p.document_id, {
        document_id: p.document_id,
        title: p.title,
        content_md: p.content_md,
        updated_at: p.updated_at,
      });
    }
  }
  return [...byId.values()];
}

const toDoc = (r: WritableDocumentResponse): WritableDocument => ({
  document_id: r.document_id,
  title: r.title,
  content_md: r.content_md,
  updated_at: r.updated_at,
});

export function useWritableDocuments(sessionId: string | undefined, messages: ChatMessage[]): UseWritableDocuments {
  const { data: listed } = useListWritableDocumentsAgenticV1WritableDocumentsSessionIdGetQuery(
    { sessionId: sessionId || "" },
    { skip: !sessionId, refetchOnMountOrArgChange: true },
  );
  const [updateDocument] = useUpdateWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdPutMutation();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isPaneOpen, setIsPaneOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  // Local optimistic content overrides so the editor reflects edits immediately.
  const [localContent, setLocalContent] = useState<Record<string, string>>({});

  const liveDocs = useMemo(() => documentsFromMessages(messages), [messages]);

  const documents = useMemo(() => {
    const byId = new Map<string, WritableDocument>();
    // 1) live (chat stream) snapshots
    for (const d of liveDocs) byId.set(d.document_id, d);
    // 2) authoritative API content overrides snapshots
    for (const r of listed ?? []) byId.set(r.document_id, toDoc(r));
    // 3) local unsaved edits override content
    return [...byId.values()].map((d) =>
      localContent[d.document_id] !== undefined ? { ...d, content_md: localContent[d.document_id] } : d,
    );
  }, [liveDocs, listed, localContent]);

  const selectDocument = useCallback((documentId: string) => setSelectedId(documentId), []);

  const openPane = useCallback((documentId?: string) => {
    setIsPaneOpen(true);
    if (documentId) setSelectedId(documentId);
  }, []);

  const closePane = useCallback(() => setIsPaneOpen(false), []);

  // Auto-open the pane (and select) the first time a document appears for this session.
  const autoOpenedRef = useRef(false);
  useEffect(() => {
    if (!autoOpenedRef.current && documents.length > 0) {
      autoOpenedRef.current = true;
      setIsPaneOpen(true);
      setSelectedId((prev) => prev ?? documents[documents.length - 1].document_id);
    }
  }, [documents]);

  // Keep a valid selection when documents change.
  useEffect(() => {
    if (documents.length === 0) {
      setSelectedId(null);
      return;
    }
    setSelectedId((prev) => (prev && documents.some((d) => d.document_id === prev) ? prev : documents[0].document_id));
  }, [documents]);

  // Debounced autosave per document.
  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const onEditDocument = useCallback(
    (documentId: string, contentMd: string) => {
      setLocalContent((prev) => ({ ...prev, [documentId]: contentMd }));
      if (!sessionId) return;
      if (saveTimers.current[documentId]) clearTimeout(saveTimers.current[documentId]);
      saveTimers.current[documentId] = setTimeout(async () => {
        setIsSaving(true);
        try {
          await updateDocument({
            sessionId,
            documentId,
            writableDocumentUpdate: { content_md: contentMd },
          }).unwrap();
        } catch (err) {
          console.error("[WRITABLE_DOC] autosave failed", err);
        } finally {
          setIsSaving(false);
        }
      }, AUTOSAVE_DEBOUNCE_MS);
    },
    [sessionId, updateDocument],
  );

  // Reset everything when switching sessions.
  useEffect(() => {
    setSelectedId(null);
    setIsPaneOpen(false);
    setLocalContent({});
    autoOpenedRef.current = false;
  }, [sessionId]);

  return {
    documents,
    selectedId,
    selectDocument,
    isPaneOpen,
    openPane,
    closePane,
    onEditDocument,
    isSaving,
  };
}
