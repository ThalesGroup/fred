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

// useWritableDocuments — the editor pane's state, ported from Kea's hook of the
// same name (the merge, optimistic-edit, and autosave logic is identical; only
// the source of the live snapshots changed).
//
// Kea derived the live set from the chat `messages` prop each render. On Swift the
// chat-part renderer feeds each streamed part into `writableDocumentSlice`, so here
// the live set is a slice selector (`selectWritableDocumentsById`). Everything else
// is a faithful port:
//   - documents = live snapshots merged with the authoritative API list, newest
//     `updated_at` winning (a live agent write is not masked by the stale API copy
//     fetched at mount; a refreshed session still shows the latest persisted text;
//     on a tie the API entry wins because it is considered last).
//   - a local optimistic edit is applied ONLY while still based on the current
//     authoritative version (`localBaseTs` >= authoritative ts); once an agent
//     writes a newer version the stale local edit is dropped, atomically in the
//     same render the new `updated_at` (the editor key) appears.
//   - when a live snapshot is newer than the API copy, refetch and drop the stale
//     local edit (covers the first time a document appears in the stream).
//   - edits autosave via a debounced PUT (800 ms) per document.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  useListWritableDocumentsQuery,
  useUpdateWritableDocumentMutation,
  type WritableDocumentResponse,
} from "./api/writableDocumentCapabilityOpenApi";
import type { WritableDocumentPartData } from "./types";
import {
  selectWritableDocument,
  selectWritableDocumentsById,
  selectWritableDocumentSelectedId,
} from "./writableDocumentSlice";
import { tsMs } from "./writableDocumentUtils";

const AUTOSAVE_DEBOUNCE_MS = 800;

/** Merge view model (a UI concept, not a backend model): one editable document. */
export interface WritableDocumentView {
  document_id: string;
  title: string;
  content_md: string;
  updated_at?: string | null;
  updated_by?: "agent" | "user";
}

export interface UseWritableDocuments {
  documents: WritableDocumentView[];
  selectedId: string | null;
  selectDocument: (documentId: string) => void;
  /** Called by the editor on change; debounced PUT persists the user edit. */
  onEditDocument: (documentId: string, contentMd: string) => void;
  isSaving: boolean;
}

const partToView = (p: WritableDocumentPartData): WritableDocumentView => ({
  document_id: p.document_id,
  title: p.title,
  content_md: p.content_md,
  updated_at: p.updated_at,
  updated_by: p.updated_by,
});

const responseToView = (r: WritableDocumentResponse): WritableDocumentView => ({
  document_id: r.document_id,
  title: r.title,
  content_md: r.content_md,
  updated_at: r.updated_at,
  updated_by: r.updated_by,
});

export function useWritableDocuments(sessionId: string | undefined): UseWritableDocuments {
  const dispatch = useDispatch();
  const liveById = useSelector(selectWritableDocumentsById);
  const selectedId = useSelector(selectWritableDocumentSelectedId);

  const { data: listed, refetch } = useListWritableDocumentsQuery(
    { sessionId: sessionId || "" },
    { skip: !sessionId, refetchOnMountOrArgChange: true },
  );
  const [updateDocument] = useUpdateWritableDocumentMutation();

  const [isSaving, setIsSaving] = useState(false);
  // Local optimistic content overrides so the editor reflects edits immediately.
  const [localContent, setLocalContent] = useState<Record<string, string>>({});
  // The authoritative updated_at each local edit was based on, so we can tell a
  // still-current optimistic edit from one an agent write has since superseded.
  const localBaseTs = useRef<Record<string, number>>({});
  // Latest authoritative updated_at per document (stream + API, ignoring local edits),
  // kept in a ref so onEditDocument can stamp localBaseTs without extra re-renders.
  const authTsRef = useRef<Record<string, number>>({});

  const liveDocs = useMemo(() => Object.values(liveById).map(partToView), [liveById]);

  // Track the newest authoritative updated_at per document (stream + API, no local edits).
  useEffect(() => {
    const next: Record<string, number> = {};
    for (const d of liveDocs) next[d.document_id] = Math.max(next[d.document_id] ?? 0, tsMs(d.updated_at));
    for (const r of listed ?? []) next[r.document_id] = Math.max(next[r.document_id] ?? 0, tsMs(r.updated_at));
    authTsRef.current = next;
  }, [liveDocs, listed]);

  const documents = useMemo(() => {
    const byId = new Map<string, WritableDocumentView>();
    // Keep the most recently updated snapshot per id, regardless of source: a live
    // chat-stream snapshot (an agent just wrote) or the authoritative API list (a
    // prior edit rehydrated on load). On a tie the API entry wins (considered last).
    const consider = (d: WritableDocumentView) => {
      const existing = byId.get(d.document_id);
      if (!existing || tsMs(d.updated_at) >= tsMs(existing.updated_at)) byId.set(d.document_id, d);
    };
    for (const d of liveDocs) consider(d);
    for (const r of listed ?? []) consider(responseToView(r));
    // Apply a local optimistic edit only while it is still based on the current
    // authoritative version. Once an agent writes a newer version (greater updated_at),
    // the stale local edit is ignored so the editor shows the agent's content — in the
    // same render the new updated_at (the editor key) appears, avoiding a remount that
    // would capture the stale local text one render before it is dropped.
    return [...byId.values()].map((d) => {
      const local = localContent[d.document_id];
      const stillCurrent = (localBaseTs.current[d.document_id] ?? 0) >= tsMs(d.updated_at);
      return local !== undefined && stillCurrent ? { ...d, content_md: local } : d;
    });
  }, [liveDocs, listed, localContent]);

  // Detect an agent write and refresh the editor live (no page reload needed). A
  // chat-stream snapshot newer than what the list API last returned means the agent
  // just wrote: re-pull the authoritative content and drop any stale local optimistic
  // edit so the editor shows the new text. User edits never produce a stream snapshot
  // (they persist via PUT), so in-progress typing is not clobbered.
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

  const selectDocument = useCallback((documentId: string) => dispatch(selectWritableDocument(documentId)), [dispatch]);

  // Keep a valid selection when documents change (the pane always shows exactly one).
  useEffect(() => {
    if (documents.length === 0) {
      if (selectedId !== null) dispatch(selectWritableDocument(null));
      return;
    }
    const valid = selectedId && documents.some((d) => d.document_id === selectedId);
    if (!valid) dispatch(selectWritableDocument(documents[documents.length - 1].document_id));
  }, [documents, selectedId, dispatch]);

  // Debounced autosave per document.
  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const onEditDocument = useCallback(
    (documentId: string, contentMd: string) => {
      setLocalContent((prev) => ({ ...prev, [documentId]: contentMd }));
      // Stamp the authoritative version this edit is based on, so a later agent write
      // (with a newer updated_at) supersedes it instead of being masked by it.
      localBaseTs.current[documentId] = authTsRef.current[documentId] ?? 0;
      if (!sessionId) return;
      const timers = saveTimers.current;
      if (timers[documentId]) clearTimeout(timers[documentId]);
      timers[documentId] = setTimeout(() => {
        void (async () => {
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
        })();
      }, AUTOSAVE_DEBOUNCE_MS);
    },
    [sessionId, updateDocument],
  );

  // Reset the hook-local optimistic state when switching sessions. The live-snapshot
  // map self-heals in the slice (an upsert from a new session resets it), so we only
  // clear the per-mount edit bookkeeping here.
  useEffect(() => {
    setLocalContent({});
    localBaseTs.current = {};
    authTsRef.current = {};
  }, [sessionId]);

  return { documents, selectedId, selectDocument, onEditDocument, isSaving };
}
