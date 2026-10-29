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

// One editable place's local draft: what the collaborator typed survives the
// view refreshes caused by the AI's edits, and `remoteChange` flags that the
// AI changed that same place meanwhile. The draft is dropped only once saved
// (or cancelled), so a refused save (409/422) never loses the typed text.

import { useCallback, useRef, useState } from "react";
import { changedRemotely, hasPendingChange, shownValue, typeInDraft, type PlaceDraft } from "./contentView";

export function usePlaceDraft(serverValue: string, save: (value: string) => Promise<boolean>) {
  const [draft, setDraft] = useState<PlaceDraft | null>(null);
  // Escape cancels then blurs: the blur's commit must not save the cancelled text.
  const cancelled = useRef(false);

  const onType = useCallback(
    (value: string) => {
      cancelled.current = false;
      setDraft((d) => typeInDraft(d, serverValue, value));
    },
    [serverValue],
  );

  /** Start the draft from the value shown now (an editor that keeps its own copy of the text). */
  const begin = useCallback(() => setDraft((d) => d ?? { value: serverValue, original: serverValue }), [serverValue]);

  /** Save the draft if it changed anything. Resolves false when the save was refused (the draft is kept). */
  const commit = useCallback(async (): Promise<boolean> => {
    if (cancelled.current) {
      cancelled.current = false;
      return true;
    }
    if (!hasPendingChange(draft)) {
      setDraft(null);
      return true;
    }
    const saved = await save(draft.value);
    if (saved) setDraft(null);
    return saved;
  }, [draft, save]);

  const cancel = useCallback(() => {
    cancelled.current = true;
    setDraft(null);
  }, []);

  return {
    value: shownValue(draft, serverValue),
    dirty: hasPendingChange(draft),
    remoteChange: changedRemotely(draft, serverValue),
    onType,
    begin,
    commit,
    cancel,
  };
}
