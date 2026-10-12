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

// The deck the open conversation produced, or null. Scoping it keeps an old deck
// out of the pane and the launcher dark; with no list endpoint, the slice (fed by
// rendered cards) is the "this conversation produced a deck" signal.

import { useSelector } from "react-redux";
import { useOpenSessionId } from "../useOpenSessionId";
import { selectCurrentPptxPreview, selectPptxPreviewProduced, selectPptxPreviewSessionId } from "./pptxPreviewSlice";
import type { PptxGeneratedPartData } from "./types";

export function useSessionPptxPreview(): PptxGeneratedPartData | null {
  const sessionId = useOpenSessionId();
  const current = useSelector(selectCurrentPptxPreview);
  const previewSessionId = useSelector(selectPptxPreviewSessionId);
  return sessionId !== "" && previewSessionId === sessionId ? current : null;
}

/** Launcher visibility for the pptx_generator side panel - see `CapabilitySidePanelSpec`. */
export function useHasPptxPreview(): boolean {
  const sessionId = useOpenSessionId();
  const produced = useSelector(selectPptxPreviewProduced);
  const previewSessionId = useSelector(selectPptxPreviewSessionId);
  return produced && sessionId !== "" && previewSessionId === sessionId;
}
