// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useDispatch } from "react-redux";
import type { TaskViewModel } from "../tasks/taskTypes";
import {
  managerActor,
  managerImportsSnapshot,
  subscribeManagerImports,
  refreshManagerImports,
  type ManagerDispatch,
} from "./managerImportRun";

/** The existing import panel renders durable receipts and locally queued files. */
export function useManagerImports(spaceId?: string) {
  const dispatch = useDispatch<ManagerDispatch>();
  const actor = managerActor();
  const entries = useSyncExternalStore(subscribeManagerImports, managerImportsSnapshot);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!spaceId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        await refreshManagerImports(dispatch, spaceId);
        if (!stopped) setError(false);
      } catch {
        if (!stopped) setError(true);
      }
      if (!stopped) timer = setTimeout(refresh, 3000);
    };
    void refresh();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [spaceId, actor, dispatch]);
  const tasks = useMemo<TaskViewModel[]>(
    () =>
      entries
        .filter((e) => e.spaceId === spaceId)
        .map((e) => ({
          taskId: e.key,
          kind: "document_upload",
          target: { type: "document", id: e.receipt?.document_id ?? e.key, label: e.name },
          owner: actor,
          localOnly: true,
          state:
            e.phase === "stored"
              ? "succeeded"
              : e.phase === "uploading"
                ? "running"
                : e.phase === "queued"
                  ? "pending"
                  : "failed",
          progress: null,
          step: e.phase,
          error: e.error ?? null,
          lastSeq: -1,
          stage: "upload",
          teamId: e.spaceId,
          conflict: null,
          registeredAt: e.createdAt,
          terminalAt: e.receipt?.completed_at ? new Date(e.receipt.completed_at).getTime() : null,
          acknowledgedAt: null,
          warnings: null,
          untracked: false,
        })),
    [entries, spaceId, actor],
  );
  return { tasks, error };
}
