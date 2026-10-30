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

// The "Rédaction" view's data: the content query, the collaborator's batches
// and undo. The query cache is the one source of truth: an edit writes the
// returned view into it (no second GET); an AI edit changes the session's
// version key, the view is refetched and the fields keep their drafts.

import type { ThunkDispatch, UnknownAction } from "@reduxjs/toolkit";
import { useCallback, useEffect, useRef, useState } from "react";
import { useDispatch } from "react-redux";
import {
  useEditWordTemplateContentMutation,
  useGetWordTemplateContentQuery,
  useUndoWordTemplateEditMutation,
  wordTemplateCapabilityApi,
  type ContentOperation,
  type WordTemplateContentResponse,
} from "./api/wordTemplateCapabilityOpenApi";
import { classifyEditError, editRequest, type EditFailure } from "./contentView";

export interface UseWordTemplateContentResult {
  view: WordTemplateContentResponse | undefined;
  isLoading: boolean;
  loadError: unknown;
  isSaving: boolean;
  /** Send one batch made on the current view. Resolves true when applied. */
  apply: (operations: ContentOperation[]) => Promise<boolean>;
  /** Cancel the last edit (whoever made it), as seen in the current view. */
  undo: () => Promise<boolean>;
  /** The last failed batch's problems (422), until dismissed or the next success. */
  rejection: Extract<EditFailure, { kind: "rejected" }> | null;
  dismissRejection: () => void;
}

export function useWordTemplateContent(params: {
  sessionId: string;
  /** The session poll's version key (null = no document): a change means the document changed. */
  versionKey: string | null;
  /** Re-read the session state (refreshes the preview). */
  onChanged: () => void;
  /** 409: the document changed under the collaborator - tell them, the view is reloaded. */
  onStale: () => void;
  /** Network / unexpected failure. */
  onFailure: (message: string) => void;
}): UseWordTemplateContentResult {
  const { sessionId, versionKey, onChanged, onStale, onFailure } = params;
  const dispatch = useDispatch<ThunkDispatch<unknown, unknown, UnknownAction>>();
  const skip = !sessionId || versionKey === null;
  const query = useGetWordTemplateContentQuery({ sessionId }, { skip, refetchOnMountOrArgChange: true });
  const [editContent, editState] = useEditWordTemplateContentMutation();
  const [undoEdit, undoState] = useUndoWordTemplateEditMutation();
  const [rejection, setRejection] = useState<UseWordTemplateContentResult["rejection"]>(null);

  // Refetch when the session's document changed (an AI edit, or our own
  // edit echoed by the poll - the view is cheap next to the PDF conversion).
  const lastKey = useRef(versionKey);
  const { refetch } = query;
  useEffect(() => {
    const previous = lastKey.current;
    lastKey.current = versionKey;
    // From "no document" to a document, the un-skipped query fetches by itself.
    if (skip || previous === null || previous === versionKey) return;
    void refetch();
  }, [skip, versionKey, refetch]);

  const view = query.data;

  const settle = useCallback(
    (result: { data: WordTemplateContentResponse } | { error: unknown }): boolean => {
      if ("data" in result) {
        dispatch(wordTemplateCapabilityApi.util.upsertQueryData("getWordTemplateContent", { sessionId }, result.data));
        setRejection(null);
        onChanged();
        return true;
      }
      const failure = classifyEditError(result.error);
      if (failure.kind === "stale") {
        onStale();
        void refetch();
      } else if (failure.kind === "rejected") {
        setRejection(failure);
      } else {
        onFailure(failure.message);
      }
      return false;
    },
    [dispatch, sessionId, onChanged, onStale, onFailure, refetch],
  );

  const apply = useCallback(
    async (operations: ContentOperation[]) => {
      if (!view || operations.length === 0) return false;
      const result = await editContent({ sessionId, wordTemplateEditRequest: editRequest(view.seq, operations) });
      return settle(result);
    },
    [view, editContent, sessionId, settle],
  );

  const undo = useCallback(async () => {
    if (!view) return false;
    const result = await undoEdit({ sessionId, body: { base_seq: view.seq } });
    return settle(result);
  }, [view, undoEdit, sessionId, settle]);

  return {
    view,
    isLoading: query.isLoading || query.isFetching,
    loadError: query.error,
    isSaving: editState.isLoading || undoState.isLoading,
    apply,
    undo,
    rejection,
    dismissRejection: () => setRejection(null),
  };
}
