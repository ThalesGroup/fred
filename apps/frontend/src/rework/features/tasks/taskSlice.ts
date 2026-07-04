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

import { createSelector, createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { TERMINAL_STATES, type AnyTaskEvent, type TaskTarget, type TaskViewModel } from "./taskTypes";

export interface TasksState {
  byId: Record<string, TaskViewModel>;
  // Monotonic counter bumped by the tray clock (see `trayClockTicked`). Terminal
  // tasks age out of the tray purely by elapsed wall-clock, which `byId` does not
  // reflect; this gives `selectVisibleTasks` an input to recompute on.
  tick?: number;
}

// Local root-state shape — avoids circular import with store.tsx.
// Structurally compatible with AppState after Step 3 adds tasks reducer.
interface TasksRootState {
  tasks: TasksState;
}

const initialState: TasksState = { byId: {}, tick: 0 };

export const EVICTION_DELAY_MS = 5 * 60 * 1000;

export const taskSlice = createSlice({
  name: "tasks",
  initialState,
  reducers: {
    taskRegistered(
      state,
      action: PayloadAction<{
        taskId: string;
        kind?: string;
        target?: TaskTarget | null;
        owner?: string;
        localOnly?: boolean;
      }>,
    ) {
      const { taskId, kind, target, owner, localOnly } = action.payload;
      if (state.byId[taskId]) return;
      state.byId[taskId] = {
        taskId,
        kind: kind ?? null,
        target: target ?? null,
        owner: owner ?? null,
        localOnly: localOnly ?? false,
        state: "pending",
        progress: null,
        step: null,
        error: null,
        lastSeq: -1,
        registeredAt: Date.now(),
        terminalAt: null,
        acknowledgedAt: null,
      };
    },

    taskEventReceived(state, action: PayloadAction<AnyTaskEvent>) {
      const event = action.payload;
      const vm = state.byId[event.task_id];
      if (!vm) return;
      if (event.seq <= vm.lastSeq) return; // sequential dedup
      vm.state = event.state;
      vm.progress = event.progress ?? null;
      vm.step = event.step ?? null;
      vm.error = event.error ?? null;
      vm.lastSeq = event.seq;
      if (event.target) vm.target = event.target;
      if (event.owner) vm.owner = event.owner;
      if (TERMINAL_STATES.has(event.state) && vm.terminalAt === null) {
        vm.terminalAt = Date.now();
      }
    },

    taskEvicted(state, action: PayloadAction<string>) {
      delete state.byId[action.payload];
    },

    /** Advance the tray clock so time-based selectors (`selectVisibleTasks`)
     *  recompute. Dispatched by a timer when a succeeded task crosses its
     *  eviction window — it must drop out of the floating tray without being
     *  removed from the store (admin history keeps it for the session). */
    trayClockTicked(state) {
      state.tick = (state.tick ?? 0) + 1;
    },

    /** Manually drop every terminal task (succeeded/failed/cancelled). Backs the
     *  admin "Clear completed" button — done tasks are kept for the whole session
     *  (useful after big ingestions) and only removed when the user asks. */
    completedTasksCleared(state) {
      for (const id of Object.keys(state.byId)) {
        if (TERMINAL_STATES.has(state.byId[id].state)) {
          delete state.byId[id];
        }
      }
    },

    failuresAcknowledged(state) {
      const now = Date.now();
      for (const vm of Object.values(state.byId)) {
        if ((vm.state === "failed" || vm.state === "cancelled") && vm.acknowledgedAt === null) {
          vm.acknowledgedAt = now;
        }
      }
    },
  },
});

export const {
  taskRegistered,
  taskEventReceived,
  taskEvicted,
  trayClockTicked,
  failuresAcknowledged,
  completedTasksCleared,
} = taskSlice.actions;

// ── Selectors ─────────────────────────────────────────────────────────────────

const selectById = (state: TasksRootState) => state.tasks.byId;
const selectTick = (state: TasksRootState) => state.tasks.tick;

export const selectActiveTasks = createSelector(selectById, (byId) =>
  Object.values(byId).filter((vm) => !TERMINAL_STATES.has(vm.state)),
);

// `selectTick` is a memoization input only: it carries no data into the result but
// forces a recompute when the tray clock advances, so terminal tasks age out on time.
export const selectVisibleTasks = createSelector([selectById, selectTick], (byId) => {
  const now = Date.now();
  return Object.values(byId)
    .filter((vm) => {
      if (!TERMINAL_STATES.has(vm.state)) return true;
      if (vm.state === "succeeded") {
        return vm.terminalAt !== null && now - vm.terminalAt < EVICTION_DELAY_MS;
      }
      // failed/cancelled: show until acknowledgedAt + 5min, or until acknowledged
      if (vm.acknowledgedAt !== null) {
        return now - vm.acknowledgedAt < EVICTION_DELAY_MS;
      }
      return true;
    })
    .sort((a, b) => {
      const aActive = !TERMINAL_STATES.has(a.state);
      const bActive = !TERMINAL_STATES.has(b.state);
      if (aActive !== bActive) return aActive ? -1 : 1;
      return b.registeredAt - a.registeredAt;
    });
});

/**
 * All tasks in the store, active first then most-recently-finished, with NO age
 * cutoff. Backs the admin Tasks page, which keeps the full session history until
 * the user clears it — unlike `selectVisibleTasks` (tray) which drops old ones.
 */
export const selectAllTasks = createSelector(selectById, (byId) =>
  Object.values(byId).sort((a, b) => {
    const aActive = !TERMINAL_STATES.has(a.state);
    const bActive = !TERMINAL_STATES.has(b.state);
    if (aActive !== bActive) return aActive ? -1 : 1;
    return b.registeredAt - a.registeredAt;
  }),
);

export const selectActiveCount = createSelector(
  selectById,
  (byId) => Object.values(byId).filter((vm) => !TERMINAL_STATES.has(vm.state)).length,
);

export const selectUnacknowledgedFailures = createSelector(
  selectById,
  (byId) =>
    Object.values(byId).filter(
      (vm) => (vm.state === "failed" || vm.state === "cancelled") && vm.acknowledgedAt === null,
    ).length,
);

/** Returns the TaskViewModel for a specific taskId, or undefined. */
export const selectTask = (taskId: string) => (state: TasksRootState) => state.tasks.byId[taskId];

/**
 * Returns the first non-succeeded task whose target matches (type, id).
 * Used by document rows and other object rows to show inline TaskIndicator.
 */
export const selectActiveTaskForTarget =
  (type: string, id: string) =>
  (state: TasksRootState): TaskViewModel | undefined =>
    Object.values(state.tasks.byId).find(
      (vm) => vm.state !== "succeeded" && vm.target?.type === type && vm.target?.id === id,
    );

/** A task that reached `succeeded`, paired with the id of the entity it acted on. */
export interface SucceededTarget {
  taskId: string;
  targetId: string;
}

/**
 * All succeeded tasks of a given target type, each with its target id.
 *
 * Backs `useRefetchOnTaskSuccess`: a row/list derives its status from a cached
 * copy of the underlying entity, which goes stale the instant its task finishes
 * (`selectActiveTaskForTarget` drops succeeded tasks, so the row falls back to the
 * pre-completion snapshot). Consumers watch this selector to refetch the affected
 * entity on completion — the shared mechanism ingestion and erasure both use.
 *
 * Factory (one memoized selector per `type`); memoize the call with `useMemo`.
 */
export const makeSelectSucceededTargetsOfType = (type: string) =>
  createSelector(selectById, (byId): SucceededTarget[] =>
    Object.values(byId)
      .filter((vm) => vm.state === "succeeded" && vm.target?.type === type && !!vm.target?.id)
      .map((vm) => ({ taskId: vm.taskId, targetId: vm.target!.id })),
  );
