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

// The deck the OPEN conversation produced, or null.
//
// The slice keeps the last registered deck globally; scoping it to the open
// conversation is what keeps a deck from a previous conversation out of the pane -
// and, more visibly, keeps the panel's launcher dark on a conversation that never
// produced one.
//
// Unlike writable_document, ppt_filler has no list endpoint to ask: the slice, fed
// by every rendered `ppt_preview` card, IS the "this conversation produced a deck"
// signal, so the launcher appears once the cards have rendered.

import { useSelector } from "react-redux";
import { useOpenSessionId } from "../useOpenSessionId";
import { selectCurrentPreview, selectPptPreviewSessionId } from "./pptPreviewSlice";
import type { PptPreviewPartData } from "./types";

export function useSessionPptPreview(): PptPreviewPartData | null {
  const sessionId = useOpenSessionId();
  const current = useSelector(selectCurrentPreview);
  const previewSessionId = useSelector(selectPptPreviewSessionId);
  return sessionId !== "" && previewSessionId === sessionId ? current : null;
}

/** Launcher visibility for the ppt_filler side panel - see `CapabilitySidePanelSpec`. */
export function useHasPptPreview(): boolean {
  return useSessionPptPreview() !== null;
}
