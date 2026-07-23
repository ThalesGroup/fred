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

// WritableDocumentAutoOpenProbe (#1905) — "document sessions resume in the
// editor": when a conversation is OPENED and its authoritative document list
// already holds at least one document, request the editor panel once.
//
// Why a probe and not the card renderer: the card's auto-open deliberately
// covers LIVE writes only (`AUTO_OPEN_MIN_AGE_MS` suppresses history replay),
// and a replayed conversation may not even render its historical document part.
// The list API is the authoritative "this conversation has a document" signal,
// independent of which messages rendered.
//
// One evaluation per conversation-open: the FIRST list answer for the session
// decides (documents → open, none → stay closed). Later list refreshes (a live
// write mid-conversation) never re-fire — reopening on a list update would
// override a user's deliberate close; the live-write pop is the card
// renderer's job. Switching to another conversation and back re-evaluates
// (that is a new conversation-open).

import { useEffect, useRef } from "react";
import { useDispatch } from "react-redux";
import { useSearchParams } from "react-router-dom";
import { requestSidePanelOpen } from "../sidePanelOpenRequestSlice";
import { useListWritableDocumentsQuery } from "./api/writableDocumentCapabilityOpenApi";
import { CAPABILITY_ID } from "./api/writableDocumentCapabilityApi";

export function WritableDocumentAutoOpenProbe() {
  const dispatch = useDispatch();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("session") ?? "";

  const { data: listed } = useListWritableDocumentsQuery(
    { sessionId },
    { skip: !sessionId, refetchOnMountOrArgChange: true },
  );

  // Last session already evaluated — switching back re-evaluates (a re-open).
  const evaluatedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!sessionId || evaluatedRef.current === sessionId) return;
    if (listed === undefined) return; // wait for the first authoritative answer
    evaluatedRef.current = sessionId;
    if (listed.length === 0) return;
    dispatch(requestSidePanelOpen({ capabilityId: CAPABILITY_ID, widget: "writable_document_pane" }));
  }, [sessionId, listed, dispatch]);

  return null;
}
