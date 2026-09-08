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

import { useCallback, useRef, useState } from "react";
import { useLocalStorageState } from "../../../hooks/useLocalStorageState";

/** localStorage key (namespaced by `useLocalStorageState` itself). */
export const TRACE_EXPANDED_PREFERENCE_KEY = "chatTraceExpanded";

/**
 * Whether one trace block is expanded, from the three inputs that can decide it.
 *
 * Precedence:
 * 1. `override` — the user toggled THIS block, so it wins for this block.
 * 2. `preference` — the user's last explicit choice on any block, read once at
 *    mount. This is what makes "hide the whole thing for good" a one-click,
 *    durable action.
 * 3. auto — open while the turn streams, and it STAYS open once the answer
 *    lands: collapsing on `done` contracted the layout by tens of pixels at the
 *    exact moment the reader started on the answer, every turn. A trace that
 *    mounted already finished — history — still opens collapsed, so a long
 *    conversation is unchanged.
 */
export function resolveTraceExpanded(
  override: boolean | null,
  preference: boolean | null,
  done: boolean,
  streamedHere = false,
): boolean {
  if (override !== null) return override;
  if (preference !== null) return preference;
  return !done || streamedHere;
}

/**
 * Expand/collapse state for a `ThoughtTrace` block.
 *
 * The stored preference is snapshotted at mount on purpose: toggling one turn's
 * trace sets the default for turns mounted later, but must not reach back and
 * flip every other trace already on screen.
 */
export function useTraceExpansion(done: boolean): { expanded: boolean; toggle: () => void } {
  const [preference, setPreference] = useLocalStorageState<boolean | null>(TRACE_EXPANDED_PREFERENCE_KEY, null);
  const mountPreference = useRef(preference).current;
  const [override, setOverride] = useState<boolean | null>(null);
  // Captured at mount, not latched over time. `done` comes from the LAST
  // exchange's isStreaming, which briefly goes true on the previous turn during
  // the pre-flight between `waitResponse` flipping and the new user message
  // landing — a running latch would pin that history block open for good.
  const streamedHere = useRef(!done).current;

  const expanded = resolveTraceExpanded(override, mountPreference, done, streamedHere);

  const toggle = useCallback(() => {
    const next = !expanded;
    setOverride(next);
    setPreference(next);
  }, [expanded, setPreference]);

  return { expanded, toggle };
}
