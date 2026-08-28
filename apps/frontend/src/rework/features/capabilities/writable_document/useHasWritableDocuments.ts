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

// Launcher visibility for the writable_document side panel - see
// `CapabilitySidePanelSpec`.
//
// "Has content" = the OPEN conversation holds at least one document. The list API
// is authoritative but lags a live agent write by one refetch, so the live
// snapshots count too - scoped to the open conversation, since the slice only
// drops a previous conversation's snapshots on its next upsert.
//
// The query is the same one the auto-open probe and the pane subscribe to: RTK
// Query dedupes it, so the launcher costs no extra request.

import { useSelector } from "react-redux";
import { useListWritableDocumentsQuery } from "./api/writableDocumentCapabilityOpenApi";
import { CAPABILITY_ID } from "./api/writableDocumentCapabilityApi";
import { useCapabilityRouted } from "../useCapabilityRouted";
import { useOpenSessionId } from "../useOpenSessionId";
import { selectWritableDocumentSessionId, selectWritableDocumentsById } from "./writableDocumentSlice";

export function useHasWritableDocuments(): boolean {
  const sessionId = useOpenSessionId();
  const routed = useCapabilityRouted(CAPABILITY_ID);
  // `currentData`, not `data`: RTK Query keeps the last resolved result across an
  // arg change, so on a switch out of a conversation WITH documents `data` would
  // keep the launcher lit on the new one until the request lands.
  const { currentData: listed } = useListWritableDocumentsQuery({ sessionId }, { skip: !sessionId || !routed });
  const liveById = useSelector(selectWritableDocumentsById);
  const liveSessionId = useSelector(selectWritableDocumentSessionId);

  const hasLive = sessionId !== "" && liveSessionId === sessionId && Object.keys(liveById).length > 0;
  return hasLive || (listed?.length ?? 0) > 0;
}
