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

import { useEffect, useMemo, useRef } from "react";
import { useSelector } from "react-redux";
import { makeSelectTaskTargetsOfType } from "./taskSlice";

/**
 * Run `onNewTarget(targetId)` exactly once, the first time a task of `targetType`
 * appears in the store for a target this hook instance has not seen before.
 *
 * Why this exists — sibling to `useRefetchOnTaskSuccess`, but for the opposite
 * edge of a task's lifecycle. That hook lets a row already on screen refresh
 * itself once its task *succeeds*. This hook is for the entity that does not
 * exist on screen *yet*: a document just registered by the upload drawer has no
 * row anywhere until its owning list refetches — and `useRefetchOnTaskSuccess`
 * can never trigger that first refetch, because its `succeeded`-only check
 * requires the target to already be in the loaded page. Firing on first
 * sighting (any state, including `pending`) instead of on success means the
 * consumer can refetch as soon as the task is registered — the document's
 * metadata is already persisted server-side by then — and the newly-appeared
 * row's own live status comes from the existing `DocRow`/`selectActiveTaskForTarget`
 * wiring, unchanged.
 *
 * Fires at most once per target id for the lifetime of the mount, including
 * for a target already known when the component mounts (a catch-up call), so
 * the consumer's refetch is idempotent-safe to call eagerly.
 */
export function useNotifyOnNewTaskTarget(targetType: string, onNewTarget: (targetId: string) => void): void {
  const selectTargets = useMemo(() => makeSelectTaskTargetsOfType(targetType), [targetType]);
  // Content-equality: only re-render when the actual set of target ids changes,
  // not on every progress event that mutates the task store.
  const targetIds = useSelector(selectTargets, sameIds);

  const onNewTargetRef = useRef(onNewTarget);
  onNewTargetRef.current = onNewTarget;

  const seenRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const targetId of targetIds) {
      if (seenRef.current.has(targetId)) continue;
      seenRef.current.add(targetId);
      onNewTargetRef.current(targetId);
    }
  }, [targetIds]);
}

/** True when both lists carry the same ids, order-insensitive. */
function sameIds(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((id) => b.includes(id));
}
