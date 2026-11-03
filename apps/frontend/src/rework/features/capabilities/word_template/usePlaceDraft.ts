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
// view refreshes caused by the AI's edits, and is saved against the document
// as it was when typing began, so an AI edit meanwhile is a conflict (409),
// never text written over the AI's change or into a place that moved.

import { useCallback, useRef, useState } from "react";
import { changedRemotely, hasPendingChange, shownValue, typeInDraft, type PlaceDraft } from "./contentView";

type Save = (value: string) => Promise<boolean>;

export function usePlaceDraft(serverValue: string, save: Save) {
  const [draft, setDraft] = useState<PlaceDraft | null>(null);
  // Escape cancels then blurs: the blur's commit must not save the cancelled text.
  const cancelled = useRef(false);
  // The save as of the draft's start: its address and the view's version.
  const startSave = useRef<Save | null>(null);

  const onType = useCallback(
    (value: string) => {
      cancelled.current = false;
      startSave.current ??= save;
      setDraft((d) => typeInDraft(d, serverValue, value));
    },
    [serverValue, save],
  );

  /** Start the draft from the value shown now (an editor that keeps its own copy of the text). */
  const begin = useCallback(() => {
    startSave.current ??= save;
    setDraft((d) => d ?? { value: serverValue, original: serverValue });
  }, [serverValue, save]);

  /** Save the draft if it changed anything. Resolves false when the save was refused (the draft is kept). */
  const commit = useCallback(async (): Promise<boolean> => {
    if (cancelled.current) {
      cancelled.current = false;
      return true;
    }
    if (!hasPendingChange(draft)) {
      startSave.current = null;
      setDraft(null);
      return true;
    }
    // The AI changed this place: the notice offers its version, nothing is written over it.
    if (changedRemotely(draft, serverValue)) return false;
    const saved = await (startSave.current ?? save)(draft.value);
    // Refused: the collaborator was told and the view reloads; a retry saves on it.
    startSave.current = null;
    if (saved) setDraft(null);
    return saved;
  }, [draft, save, serverValue]);

  const cancel = useCallback(() => {
    cancelled.current = true;
    startSave.current = null;
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
