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

/** Parse an ISO timestamp to epoch ms; 0 when missing/invalid (treated as oldest). */
const tsMs = (updatedAt?: string | null): number => {
  if (!updatedAt) return 0;
  const t = Date.parse(updatedAt);
  return Number.isNaN(t) ? 0 : t;
};

export function useWritableDocuments(sessionId: string | undefined, messages: ChatMessage[]): UseWritableDocuments {
  const { data: listed, refetch } = useListWritableDocumentsAgenticV1WritableDocumentsSessionIdGetQuery(
    { sessionId: sessionId || "" },
    { skip: !sessionId, refetchOnMountOrArgChange: true },
  );
  const [updateDocument] = useUpdateWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdPutMutation();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isPaneOpen, setIsPaneOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  // Local optimistic content overrides so the editor reflects edits immediately.
  const [localContent, setLocalContent] = useState<Record<string, string>>({});
  // The authoritative updated_at each local edit was based on, so we can tell a
  // still-current optimistic edit from one an agent write has since superseded.
  const localBaseTs = useRef<Record<string, number>>({});
  // Latest authoritative updated_at per document (stream + API, ignoring local edits),
  // kept in a ref so onEditDocument can stamp localBaseTs without extra re-renders.
  const authTsRef = useRef<Record<string, number>>({});

  const liveDocs = useMemo(() => documentsFromMessages(messages), [messages]);

  // Track the newest authoritative updated_at per document (stream + API, no local edits).
  useEffect(() => {
    const next: Record<string, number> = {};
    for (const d of liveDocs) next[d.document_id] = Math.max(next[d.document_id] ?? 0, tsMs(d.updated_at));
    for (const r of listed ?? []) next[r.document_id] = Math.max(next[r.document_id] ?? 0, tsMs(r.updated_at));
    authTsRef.current = next;
  }, [liveDocs, listed]);

  const documents = useMemo(() => {
    const byId = new Map<string, WritableDocument>();
    // Keep the most recently updated snapshot per id, regardless of source: a live
    // chat-stream snapshot (an agent just wrote) or the authoritative API list (a
    // prior edit rehydrated on load). Comparing updated_at means a live agent write
    // is no longer masked by the stale API snapshot fetched at mount, while a
    // refreshed session still shows the latest persisted text. On a tie the API
    // entry wins (considered last) so the backend stays authoritative.
    const consider = (d: WritableDocument) => {
      const existing = byId.get(d.document_id);
      if (!existing || tsMs(d.updated_at) >= tsMs(existing.updated_at)) byId.set(d.document_id, d);
    };
    for (const d of liveDocs) consider(d);
    for (const r of listed ?? []) consider(toDoc(r));
    // Apply a local optimistic edit only while it is still based on the current
    // authoritative version. Once an agent writes a newer version (greater updated_at),
    // the stale local edit is ignored so the editor shows the agent's content — atomically,
    // in the same render the new updated_at (the editor key) appears. This avoids a remount
    // that would otherwise capture the stale local text one render before it is dropped.
    return [...byId.values()].map((d) => {
      const local = localContent[d.document_id];
      const stillCurrent = (localBaseTs.current[d.document_id] ?? 0) >= tsMs(d.updated_at);
      return local !== undefined && stillCurrent ? { ...d, content_md: local } : d;
    });
  }, [liveDocs, listed, localContent]);

  // Detect an agent write and refresh the editor live (no page reload needed).
  // A chat-stream snapshot newer than what the list API last returned means the agent
  // just wrote: re-pull the authoritative content and drop any stale local optimistic
  // edit so the editor shows the new text. Comparing live-vs-API (rather than two
  // consecutive stream snapshots) also covers the first time a document appears in the
  // stream this session. User edits never produce a stream snapshot (they persist via
  // PUT) and the refetch makes the API catch up, so in-progress typing is not clobbered.
  useEffect(() => {
    const apiTsById = new Map((listed ?? []).map((r) => [r.document_id, tsMs(r.updated_at)]));
    const stale = liveDocs.filter((d) => tsMs(d.updated_at) > (apiTsById.get(d.document_id) ?? 0));
    if (stale.length === 0) return;
    for (const d of stale) delete localBaseTs.current[d.document_id];
    setLocalContent((prev) => {
      if (!stale.some((d) => d.document_id in prev)) return prev;
      const next = { ...prev };
      for (const d of stale) delete next[d.document_id];
      return next;
    });
    if (sessionId) refetch();
  }, [liveDocs, listed, sessionId, refetch]);

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
      // Stamp the authoritative version this edit is based on, so a later agent write
      // (with a newer updated_at) supersedes it instead of being masked by it.
      localBaseTs.current[documentId] = authTsRef.current[documentId] ?? 0;
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
    localBaseTs.current = {};
    authTsRef.current = {};
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
