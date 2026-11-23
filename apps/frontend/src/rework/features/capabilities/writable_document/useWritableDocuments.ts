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

// One read model for the editor, launcher and conversation files: persisted
// documents merged with live snapshots by identity and newest updated_at.
// Only useWritableDocuments adds selection and debounced editing.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  writableDocumentCapabilityApi,
  useListWritableDocumentsQuery,
  useUpdateWritableDocumentMutation,
} from "./api/writableDocumentCapabilityOpenApi";
import { CAPABILITY_ID } from "./api/writableDocumentCapabilityApi";
import { useCapabilityRouted } from "../useCapabilityRouted";
import {
  documentSaveStarted,
  documentSaveFinished,
  selectDocumentSaves,
  selectWritableDocument,
  selectWritableDocumentsById,
  selectWritableDocumentSelectedId,
  selectWritableDocumentSessionId,
} from "./writableDocumentSlice";
import { tsMs } from "./writableDocumentUtils";

const AUTOSAVE_DEBOUNCE_MS = 800;
// Closing/reopening the pane must not allow an older PUT to finish after a newer one.
const saving: Record<string, Promise<void> | undefined> = {};

// A user save refreshes every reader of this conversation, including the drawer.
// Keep endpoint enhancements outside the generated client.
writableDocumentCapabilityApi.enhanceEndpoints({
  addTagTypes: ["WritableDocuments"],
  endpoints: {
    listWritableDocuments: {
      providesTags: (_result, _error, { sessionId }) => [{ type: "WritableDocuments", id: sessionId }],
    },
    updateWritableDocument: {
      invalidatesTags: (_result, _error, { sessionId }) => [{ type: "WritableDocuments", id: sessionId }],
    },
    deleteWritableDocument: {
      invalidatesTags: (_result, error, { sessionId }) => (error ? [] : [{ type: "WritableDocuments", id: sessionId }]),
    },
  },
});

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
  saveFailed: boolean;
  retrySave: () => void;
}

/** Read-only: subscribing never selects, edits or copies a document. */
export function useWritableDocumentList(sessionId: string | undefined) {
  const liveById = useSelector(selectWritableDocumentsById);
  const liveSessionId = useSelector(selectWritableDocumentSessionId);
  const routed = useCapabilityRouted(CAPABILITY_ID);
  const {
    currentData: listed,
    refetch,
    isFetching,
    error,
  } = useListWritableDocumentsQuery(
    { sessionId: sessionId || "" },
    { skip: !sessionId || !routed, refetchOnMountOrArgChange: true },
  );
  // Streamed/history parts carry content, not existence. Re-read the catalogue
  // when a part arrives so deleted documents cannot return through history replay.
  useEffect(() => {
    if (sessionId && routed && liveSessionId === sessionId) void refetch();
  }, [sessionId, routed, liveSessionId, liveById, refetch]);
  const documents = useMemo(() => {
    if (!sessionId || !routed) return [];
    const byId = new Map<string, WritableDocumentView>();
    const consider = (doc: WritableDocumentView) => {
      const current = byId.get(doc.document_id);
      if (!current || tsMs(doc.updated_at) >= tsMs(current.updated_at)) byId.set(doc.document_id, doc);
    };
    listed?.forEach(consider);
    if (liveSessionId === sessionId)
      Object.values(liveById)
        .filter((doc) => byId.has(doc.document_id))
        .forEach(consider);
    return [...byId.values()];
  }, [sessionId, routed, liveSessionId, liveById, listed]);

  return {
    documents,
    loading: !!sessionId && routed && (isFetching || (!listed && !error)),
    error,
    unavailable: !routed,
    refetch,
  };
}

export function useWritableDocuments(sessionId: string | undefined): UseWritableDocuments {
  const dispatch = useDispatch();
  const selectedId = useSelector(selectWritableDocumentSelectedId);
  const { documents: authoritative } = useWritableDocumentList(sessionId);
  const [updateDocument] = useUpdateWritableDocumentMutation();

  const saves = useSelector(selectDocumentSaves);
  const isSaving = Object.entries(saves ?? {}).some(
    ([key, save]) => key.startsWith(`${sessionId}/`) && save.status === "saving",
  );
  const saveFailed = Object.entries(saves ?? {}).some(
    ([key, save]) => key.startsWith(`${sessionId}/`) && save.status === "failed",
  );
  const activeSession = useRef(sessionId);
  activeSession.current = sessionId;
  // Keep a local edit's editor version stable across its own save acknowledgments:
  // the shared list advances, but typing must not remount MDXEditor or lose its cursor.
  const [localEdits, setLocalEdits] = useState<
    Record<
      string,
      {
        content: string;
        baseTs: number;
        editorVersion: WritableDocumentView["updated_at"];
      }
    >
  >({});
  const authoritativeRef = useRef<Record<string, WritableDocumentView>>({});
  useEffect(() => {
    authoritativeRef.current = Object.fromEntries(authoritative.map((d) => [d.document_id, d]));
  }, [authoritative]);

  const documents = useMemo(
    () =>
      authoritative.map((doc) => {
        const edit = localEdits[doc.document_id];
        const unsaved = saves?.[`${sessionId}/${doc.document_id}`];
        // A newer agent snapshot supersedes local text in the same render.
        return edit && edit.baseTs >= tsMs(doc.updated_at)
          ? { ...doc, content_md: edit.content, updated_at: edit.editorVersion }
          : unsaved
            ? { ...doc, content_md: unsaved.content }
            : doc;
      }),
    [authoritative, localEdits, saves, sessionId],
  );

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
  const pendingSaves = useRef<Record<string, () => void>>({});
  const onEditDocument = useCallback(
    (documentId: string, contentMd: string) => {
      const authoritative = authoritativeRef.current[documentId];
      setLocalEdits((previous) => {
        const previousEdit = previous[documentId];
        const current = previousEdit && previousEdit.baseTs >= tsMs(authoritative?.updated_at);
        return {
          ...previous,
          [documentId]: {
            content: contentMd,
            baseTs: Math.max(previousEdit?.baseTs ?? 0, tsMs(authoritative?.updated_at)),
            editorVersion: current ? previousEdit.editorVersion : authoritative?.updated_at,
          },
        };
      });
      if (!sessionId) return;
      const timers = saveTimers.current;
      if (timers[documentId]) clearTimeout(timers[documentId]);
      const key = `${sessionId}/${documentId}`;
      const revision = crypto.randomUUID();
      dispatch(documentSaveStarted({ key, revision, content: contentMd }));
      const persist = () => {
        delete pendingSaves.current[documentId];
        delete timers[documentId];
        // Serialize saves of one document: an older response cannot overwrite newer typing.
        const pending = (saving[key] ?? Promise.resolve()).then(async () => {
          try {
            const saved = await updateDocument({
              sessionId,
              documentId,
              writableDocumentUpdate: { content_md: contentMd },
            }).unwrap();
            dispatch(documentSaveFinished({ key, revision, failed: false }));
            if (activeSession.current !== sessionId) return;
            setLocalEdits((previous) => {
              const edit = previous[documentId];
              if (!edit) return previous;
              return { ...previous, [documentId]: { ...edit, baseTs: Math.max(edit.baseTs, tsMs(saved.updated_at)) } };
            });
          } catch {
            dispatch(documentSaveFinished({ key, revision, failed: true }));
          }
        });
        saving[key] = pending;
        void pending.finally(() => {
          if (saving[key] === pending) delete saving[key];
        });
      };
      pendingSaves.current[documentId] = persist;
      timers[documentId] = setTimeout(persist, AUTOSAVE_DEBOUNCE_MS);
    },
    [sessionId, updateDocument, dispatch],
  );

  // Reset the hook-local optimistic state when switching sessions. The live-snapshot
  // map self-heals in the slice (an upsert from a new session resets it), so we only
  // clear the per-mount edit bookkeeping here.
  useEffect(() => {
    setLocalEdits({});
    const timers = saveTimers.current;
    const pending = pendingSaves.current;
    return () => {
      Object.values(timers).forEach(clearTimeout);
      Object.values(pending).forEach((persist) => persist());
    };
  }, [sessionId]);

  const retrySave = () => {
    for (const [key, save] of Object.entries(saves ?? {})) {
      if (key.startsWith(`${sessionId}/`) && save.status === "failed") {
        onEditDocument(key.slice(`${sessionId}/`.length), save.content);
      }
    }
  };
  return { documents, selectedId, selectDocument, onEditDocument, isSaving, saveFailed, retrySave };
}
