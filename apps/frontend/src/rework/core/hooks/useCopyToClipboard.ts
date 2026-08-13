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
 * Clipboard copy with in-place feedback: `copied` flips true on success and
 * reverts after `revertMs` — the copy button itself becomes the confirmation
 * (content_copy → green check), no toast. A failed copy stays silent: the
 * icon simply not changing IS the feedback, and the clipboard API only fails
 * in degraded contexts (permissions, non-secure origin) a toast wouldn't fix.
 */
export function useCopyToClipboard(text: string, revertMs = 1500) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    [],
  );

  const copy = useCallback(() => {
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopied(true);
        if (timerRef.current !== null) window.clearTimeout(timerRef.current);
        timerRef.current = window.setTimeout(() => setCopied(false), revertMs);
      })
      .catch(() => {});
  }, [text, revertMs]);

  return { copied, copy };
}
