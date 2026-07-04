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
import { makeSelectSucceededTargetsOfType, type SucceededTarget } from "./taskSlice";

/**
 * Run `onSuccess(targetId)` exactly once when a task acting on an entity of
 * `targetType` reaches `succeeded`.
 *
 * Why this exists — a list/row derives its status from a cached copy of the
 * entity (e.g. a document's browse snapshot, an erasure schedule query result).
 * That copy captures the pre-completion state and never refreshes on its own: the
 * moment the task finishes it drops out of `selectActiveTaskForTarget`, so the row
 * silently falls back to the stale snapshot (a finished ingestion shows "Raw"
 * until a manual page refresh). This hook is the shared fix — the owning consumer
 * refetches just the affected entity when its task completes, so ingestion today
 * and conversation erasure tomorrow both stay live with identical logic.
 *
 * Fires only on `succeeded` (failed/cancelled still render from the retained
 * task). Each task fires its callback once for the lifetime of the mount, so a
 * task already succeeded before mount triggers a single catch-up refetch.
 */
export function useRefetchOnTaskSuccess(targetType: string, onSuccess: (targetId: string) => void): void {
  const selectSucceeded = useMemo(() => makeSelectSucceededTargetsOfType(targetType), [targetType]);
  // Content-equality on task ids: only re-render when the succeeded set changes,
  // not on every progress event that mutates the task store.
  const succeeded = useSelector(selectSucceeded, sameTaskIds);

  // Keep the latest callback without making it an effect dependency, so the
  // consumer can pass a fresh closure each render (capturing current state).
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;

  const handledRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const { taskId, targetId } of succeeded) {
      if (handledRef.current.has(taskId)) continue;
      handledRef.current.add(taskId);
      onSuccessRef.current(targetId);
    }
  }, [succeeded]);
}

/** True when both lists carry the same task ids (order-sensitive is fine — the
 *  selector orders by store iteration, which is stable between recomputes). */
function sameTaskIds(a: SucceededTarget[], b: SucceededTarget[]): boolean {
  return a.length === b.length && a.every((item, i) => item.taskId === b[i].taskId);
}
