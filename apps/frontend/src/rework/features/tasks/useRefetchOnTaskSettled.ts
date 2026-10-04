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
import { makeSelectSettledTargetsOfType, type SettledTarget } from "./taskSlice";

/**
 * Run `onSettled(targetIds)` once for the tasks acting on entities of
 * `targetType` that just settled on an outcome that changed their entity —
 * `succeeded` or `cancelled` — or stopped being followed (untracked). Tasks that
 * settle together come in one call, so the consumer can refresh each list once.
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
 * Cancellation is included, not just success: cancelling an ingestion erases the
 * half-built document outright — content, vectors, metadata row and the storage
 * quota it had been charged (`delete_cancelled_document`, #2315). A consumer that
 * only watched `succeeded` left the deleted document's row and the team's storage
 * meter frozen until a manual reload. Cancellation is cooperative, so the erase
 * lands seconds after the cancel request returns; this hook fires on the terminal
 * state, which is when it has actually happened, not when it was asked for.
 *
 * `failed` deliberately does not fire: the document survives a failure and its
 * row keeps rendering from the retained task, so there is nothing to refetch.
 * Each task is handed out once for the lifetime of the mount, so a task
 * already settled before mount triggers a single catch-up refetch.
 *
 * That catch-up is handed out after the mount commit, never inside it — the
 * same hazard `useNotifyOnNewTaskTarget` documents: React runs a child's
 * effects before its parent's, so refetching a PARENT's query from inside the
 * mount commit reaches an instance that has not subscribed yet, and RTK Query
 * throws "Cannot refetch a query that has not been started yet".
 */
export function useRefetchOnTaskSettled(targetType: string, onSettled: (targetIds: string[]) => void): void {
  const selectSettled = useMemo(() => makeSelectSettledTargetsOfType(targetType), [targetType]);
  // Content-equality on task ids: only re-render when the settled set changes,
  // not on every progress event that mutates the task store.
  const settled = useSelector(selectSettled, sameTaskIds);

  // Keep the latest callback without making it an effect dependency, so the
  // consumer can pass a fresh closure each render (capturing current state).
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;

  const handledRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    // Queued during the effect pass, so it runs once that whole pass is over
    // and every query on the page — parents included — has started.
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      const fresh = settled.filter(({ taskId }) => !handledRef.current.has(taskId));
      if (fresh.length === 0) return;
      for (const { taskId } of fresh) handledRef.current.add(taskId);
      onSettledRef.current([...new Set(fresh.map(({ targetId }) => targetId))]);
    });
    // Nothing is marked handled until it is actually handed out, so a run
    // superseded by a newer set — or by unmounting — loses nothing.
    return () => {
      cancelled = true;
    };
  }, [settled]);
}

/** True when both lists carry the same task ids (order-sensitive is fine — the
 *  selector orders by store iteration, which is stable between recomputes). */
function sameTaskIds(a: SettledTarget[], b: SettledTarget[]): boolean {
  return a.length === b.length && a.every((item, i) => item.taskId === b[i].taskId);
}
