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
 * 3. auto — open while the turn streams (the live activity is the point),
 *    collapsed once the answer has landed.
 */
export function resolveTraceExpanded(override: boolean | null, preference: boolean | null, done: boolean): boolean {
  if (override !== null) return override;
  if (preference !== null) return preference;
  return !done;
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

  const expanded = resolveTraceExpanded(override, mountPreference, done);

  const toggle = useCallback(() => {
    const next = !expanded;
    setOverride(next);
    setPreference(next);
  }, [expanded, setPreference]);

  return { expanded, toggle };
}
