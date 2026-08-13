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

import { useEffect, type RefObject } from "react";
import { toEmailHtml, toPlainText } from "@rework/utils/clipboardUtils";

const COPYABLE_SELECTOR = "[data-copyable-content]";

function closestCopyable(node: Node | null): Element | null {
  if (!node) return null;
  const el = node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement;
  return el ? el.closest(COPYABLE_SELECTOR) : null;
}

/**
 * Intercepts the native `copy` event so a manual selection over assistant
 * message content is written as email-safe HTML instead of the browser's
 * default serialisation, which inlines computed styles — including the
 * message surface's background-color — into the pasted `text/html` (#2336).
 *
 * Delegated at the scrollable message-list container rather than per message,
 * since a single listener there covers every turn including ones added by
 * streaming without re-attaching.
 */
export function useAssistantCopyInterception(containerRef: RefObject<HTMLElement>) {
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    function onCopy(e: ClipboardEvent) {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || sel.rangeCount === 0 || !e.clipboardData) return;

      try {
        const range = sel.getRangeAt(0);
        const start = closestCopyable(range.startContainer);
        const end = closestCopyable(range.endContainer);
        // Selection must land wholly inside a single copyable region — one
        // that starts or ends outside it (chrome, another turn's region) is
        // left to the browser's default copy rather than half-transformed.
        if (!start || !end || start !== end) return;

        const clone = range.cloneContents();
        const plain = toPlainText(clone);
        if (!plain.trim()) return;
        const html = toEmailHtml(clone);

        e.clipboardData.setData("text/plain", plain);
        if (html) e.clipboardData.setData("text/html", html);
        e.preventDefault();
      } catch {
        // A serialiser bug must never break native Ctrl+C.
      }
    }

    container.addEventListener("copy", onCopy);
    return () => container.removeEventListener("copy", onCopy);
  }, [containerRef]);
}
