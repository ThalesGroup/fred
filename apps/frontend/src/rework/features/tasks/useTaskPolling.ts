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

// Following the user's tasks by polling: one short batched read per owning
// backend, never a connection held open per task. Held-open connections filled
// the browser's six per origin during an import and stalled the whole page.

import { useEffect } from "react";
import { useDispatch, useSelector, useStore } from "react-redux";
import type { ThunkDispatch, UnknownAction } from "@reduxjs/toolkit";
import { controlPlaneApi } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { knowledgeFlowApi, type TaskSummary } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { selectActiveTasks, taskSnapshotsReceived } from "./taskSlice";
import { taskBackendFor, type TaskBackend } from "./taskKinds";

export const POLL_INTERVAL_MS = 5_000;
/** A read still unanswered after this is given up, like any failed read. */
export const READ_TIMEOUT_MS = 15_000;
/** The backends' own limit on one read (`MAX_TASK_IDS_PER_READ` in fred-core). */
export const MAX_IDS_PER_READ = 50;

type TasksRoot = Parameters<typeof selectActiveTasks>[0];
type PollDispatch = ThunkDispatch<TasksRoot, unknown, UnknownAction>;

const selectFollowsAnyTask = (state: TasksRoot) => selectActiveTasks(state).some((task) => !task.localOnly);

interface Loop {
  stopped: boolean;
  /** Ends the pause between rounds early. */
  wake: () => void;
  /** Cancels the read in flight, if any. */
  abort: () => void;
}

// Module state, not a ref: MainLayout can unmount and mount again (a route
// outside it), and the new loop must still wait for the old one to end.
let previousLoop: Promise<void> = Promise.resolve();

/** Mounted once, in MainLayout: reads while the store follows a task, stops when it follows none. */
export function useTaskPolling(): void {
  const dispatch = useDispatch<PollDispatch>();
  const store = useStore<TasksRoot>();
  const followsAnyTask = useSelector(selectFollowsAnyTask);

  useEffect(() => {
    if (!followsAnyTask) return;
    const loop: Loop = { stopped: false, wake: () => {}, abort: () => {} };
    // Background tabs have their timers throttled: catch up on return.
    const onVisible = () => {
      if (document.visibilityState === "visible") loop.wake();
    };
    document.addEventListener("visibilitychange", onVisible);
    previousLoop = previousLoop.then(() => pollUntilStopped(loop, store.getState, dispatch));
    return () => {
      loop.stopped = true;
      loop.abort();
      loop.wake();
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [followsAnyTask, store, dispatch]);
}

async function pollUntilStopped(loop: Loop, getState: () => TasksRoot, dispatch: PollDispatch): Promise<void> {
  while (!loop.stopped) {
    await readFollowedTasks(loop, getState, dispatch);
    if (loop.stopped) return;
    await new Promise<void>((resolve) => {
      const timer = setTimeout(resolve, POLL_INTERVAL_MS);
      loop.wake = () => {
        clearTimeout(timer);
        resolve();
      };
    });
  }
}

/** One round: every followed task, grouped by the backend that owns it, read
 *  in batches one after another. A stopped loop reads no further batch. */
async function readFollowedTasks(loop: Loop, getState: () => TasksRoot, dispatch: PollDispatch): Promise<void> {
  const idsByBackend = new Map<TaskBackend, string[]>();
  for (const task of selectActiveTasks(getState())) {
    if (task.localOnly) continue;
    const backend = taskBackendFor(task.kind);
    idsByBackend.set(backend, [...(idsByBackend.get(backend) ?? []), task.taskId]);
  }
  for (const [backend, ids] of idsByBackend) {
    for (let start = 0; start < ids.length; start += MAX_IDS_PER_READ) {
      if (loop.stopped) return;
      const requestedIds = ids.slice(start, start + MAX_IDS_PER_READ);
      const tasks = await readBatch(loop, backend, requestedIds, dispatch);
      // A failed read says nothing about any task: they stay as they were.
      if (tasks && !loop.stopped) dispatch(taskSnapshotsReceived({ requestedIds, tasks }));
    }
  }
}

async function readBatch(
  loop: Loop,
  backend: TaskBackend,
  taskId: string[],
  dispatch: PollDispatch,
): Promise<TaskSummary[] | null> {
  const args = { scope: "user", taskId };
  const options = { subscribe: false, forceRefetch: true };
  const request =
    backend === "control-plane"
      ? dispatch(controlPlaneApi.endpoints.listTasksControlPlaneV1TasksGet.initiate(args, options))
      : dispatch(knowledgeFlowApi.endpoints.listTasksKnowledgeFlowV1TasksGet.initiate(args, options));
  loop.abort = () => request.abort();
  // Without a limit, one hung request would hold up every later round.
  const timer = setTimeout(() => request.abort(), READ_TIMEOUT_MS);
  try {
    const result = await request;
    return result.isSuccess ? result.data.tasks : null;
  } finally {
    clearTimeout(timer);
    loop.abort = () => {};
  }
}
