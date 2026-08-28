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

// Launcher visibility for the writable_document side panel — see
// `CapabilitySidePanelSpec`.
//
// "Has content" = the OPEN conversation holds at least one document. The list API
// is authoritative but lags a live agent write by one refetch, so the live
// snapshots count too — scoped to the open conversation, since the slice only
// drops a previous conversation's snapshots on its next upsert.
//
// The query is the same one the auto-open probe and the pane subscribe to: RTK
// Query dedupes it, so the launcher costs no extra request.

import { useSelector } from "react-redux";
import { useSearchParams } from "react-router-dom";
import { useListWritableDocumentsQuery } from "./api/writableDocumentCapabilityOpenApi";
import { selectWritableDocumentSessionId, selectWritableDocumentsById } from "./writableDocumentSlice";

export function useHasWritableDocuments(): boolean {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("session") ?? "";
  const { data: listed } = useListWritableDocumentsQuery({ sessionId }, { skip: !sessionId });
  const liveById = useSelector(selectWritableDocumentsById);
  const liveSessionId = useSelector(selectWritableDocumentSessionId);

  const hasLive = sessionId !== "" && liveSessionId === sessionId && Object.keys(liveById).length > 0;
  return hasLive || (listed?.length ?? 0) > 0;
}
