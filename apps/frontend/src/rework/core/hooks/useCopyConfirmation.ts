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

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * The copy receipt shared by `UserTurn` and `AssistantTurn` (#2359): `copied`
 * flips true on `confirmCopied()` and reverts after `revertMs`. The button
 * itself is the confirmation — content_copy → check, no toast.
 *
 * Deliberately knows nothing about the clipboard. The predecessor hook
 * (`useCopyToClipboard`, deleted in #2359) bundled the write with the flag and
 * so hardcoded `writeText` — which the assistant turn cannot use, since it
 * writes email-safe HTML. Unshareable by construction, it got reimplemented
 * per turn instead, and the two implementations promptly drifted. Keeping the
 * write out is what lets this one actually be shared.
 */
export function useCopyConfirmation(revertMs = 2000) {
  const [copied, setCopied] = useState(false);
  // `clearTimeout(undefined)` is a documented no-op, so neither call below
  // needs a null guard.
  const revertTimer = useRef<number | undefined>(undefined);

  // Switching conversations tears the turn down mid-window.
  useEffect(() => () => window.clearTimeout(revertTimer.current), []);

  const confirmCopied = useCallback(() => {
    setCopied(true);
    // Cancel before re-arming: a second click inside the window would
    // otherwise be cut short by the first click's timer.
    window.clearTimeout(revertTimer.current);
    revertTimer.current = window.setTimeout(() => setCopied(false), revertMs);
  }, [revertMs]);

  return { copied, confirmCopied };
}
