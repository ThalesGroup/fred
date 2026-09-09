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

// Outline rail — one mark per turn along the conversation's left edge.
// Full rationale: docs/swift/rfc/CONVERSATION-OUTLINE-RAIL-RFC.md

import { memo, useEffect, useRef } from "react";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import type { OutlineItem, OutlinePreview } from "./outlineItems";
import styles from "./ConversationOutlineRail.module.css";

interface ConversationOutlineRailProps {
  items: OutlineItem[];
  activeId: string | null;
  /** A turn is running: marks stay visible but dimmed and inert, so the rail
   *  can never write the conversation's scroll position while the autoscroll
   *  owns it. */
  frozen: boolean;
  onJump: (turnId: string) => void;
  getPreview: (turnId: string) => OutlinePreview;
}

/**
 * The hover tile.
 *
 * Takes the turn's id and resolves its own text, rather than being handed a
 * ready-made preview: `Tooltip`'s `content` element is built on every render of
 * the rail, but a React element is inert until something renders it, and
 * `Tooltip` only renders it while the tooltip is actually open. Passing the
 * resolved strings in would move that work back to render time — for every
 * turn, on every render, which is exactly what this design set out to avoid.
 *
 * Deliberately not memoised across hovers. Reading two sentences out of one
 * bounded slice is microseconds, and a cache keyed by turn id cannot see an
 * exchange completed by a background revalidation — it would pin the truncated
 * preview for the life of the page, to save nothing measurable.
 */
function PreviewTile({ turnId, resolve }: { turnId: string; resolve: (id: string) => OutlinePreview }) {
  const preview = resolve(turnId);
  return (
    <span className={styles.tile}>
      <span className={styles.tileRequest}>{preview.request}</span>
      {preview.answer && <span className={styles.tileAnswer}>{preview.answer}</span>}
    </span>
  );
}

// Memoized for the same reason ConversationThread is: the page above re-renders
// on every composer keystroke, and the rail must not follow it down.
export const ConversationOutlineRail = memo(function ConversationOutlineRail({
  items,
  activeId,
  frozen,
  onJump,
  getPreview,
}: ConversationOutlineRailProps) {
  // Keep the turn being read reachable in a rail that has outgrown its height.
  // Its own scrollTop, never `scrollIntoView`: that would scroll every
  // scrollable ancestor, the conversation container included — the one element
  // this component must never move.
  const railRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const rail = railRef.current;
    if (!rail || !activeId) return;
    const mark = rail.querySelector<HTMLElement>(`[data-mark-id="${CSS.escape(activeId)}"]`);
    if (!mark) return;
    const railBox = rail.getBoundingClientRect();
    const markBox = mark.getBoundingClientRect();
    if (markBox.top < railBox.top) rail.scrollTop -= railBox.top - markBox.top;
    else if (markBox.bottom > railBox.bottom) rail.scrollTop += markBox.bottom - railBox.bottom;
  }, [activeId, items]);

  if (items.length === 0) return null;

  return (
    // Hidden from assistive technology: the marks carry no text of their own,
    // and the conversation they summarise is already fully readable in the
    // thread. Reachability is a V1 omission, not a judgement that it is
    // unwanted — see the RFC's out-of-scope section.
    <div ref={railRef} className={`${styles.rail} ${frozen ? styles.railFrozen : ""}`} aria-hidden="true">
      <div className={styles.marks}>
        {items.map((item) => {
          const mark = (
            <button
              type="button"
              // Never in the tab order: a focusable control inside an
              // aria-hidden subtree is a trap — reachable by keyboard, yet
              // invisible to the screen reader that should announce it.
              tabIndex={-1}
              data-mark-id={item.id}
              className={`${styles.mark} ${styles[item.height]} ${item.id === activeId ? styles.markActive : ""}`}
              onClick={() => onJump(item.id)}
            />
          );
          // Frozen: no tooltip is mounted at all, so no extract is computed for
          // a turn the reader cannot reach anyway.
          return frozen ? (
            <span key={item.id} className={styles.markSlot}>
              {mark}
            </span>
          ) : (
            <Tooltip
              key={item.id}
              placement="left"
              gapPx={12}
              content={<PreviewTile turnId={item.id} resolve={getPreview} />}
            >
              {mark}
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
});
