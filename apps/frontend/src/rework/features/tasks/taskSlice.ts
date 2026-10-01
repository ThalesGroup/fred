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
import { TERMINAL_STATES, type AnyTaskEvent, type ImportStage, type TaskTarget, type TaskViewModel } from "./taskTypes";

export interface TasksState {
  byId: Record<string, TaskViewModel>;
  // Bumped when something asks the import panel to show itself
  // (see `importPanelOpenRequested`).
  importPanelOpenRequest?: number;
}

// Local root-state shape — avoids circular import with store.tsx.
// Structurally compatible with AppState after Step 3 adds tasks reducer.
interface TasksRootState {
  tasks: TasksState;
}

const initialState: TasksState = { byId: {}, importPanelOpenRequest: 0 };

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
        teamId?: string | null;
        /** Pass `null` for a document ingestion that is not an import — a
         *  relaunch of a document already in the corpus — so it does not turn
         *  up in the import panel. */
        stage?: ImportStage | null;
      }>,
    ) {
      const { taskId, kind, target, owner, localOnly, stage, teamId } = action.payload;
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
        // A document ingestion known to the server is past its transfer by
        // definition — including one rehydrated after a reload, whose bytes
        // went up in a browser session that may no longer exist.
        stage: stage !== undefined ? stage : kind === "ingestion" && target?.type === "document" ? "analysis" : null,
        conflict: null,
        teamId: teamId ?? null,
        registeredAt: Date.now(),
        terminalAt: null,
        acknowledgedAt: null,
        warnings: null,
      };
    },

    /** A file whose bytes are on their way, before the server has named a task
     *  for it.
     *
     *  Without this the file is invisible for the whole transfer — the panel
     *  only ever learns of it once the upload is over, which for a large import
     *  is most of the wait. `localId` is the browser's own handle on it; the
     *  real task id replaces it at handoff. */
    uploadStarted(state, action: PayloadAction<{ localId: string; filename: string; teamId: string | null }>) {
      const { localId, filename, teamId } = action.payload;
      const existing = state.byId[localId];
      if (existing) {
        // Sent again — a retry, or a conflict just answered. Same entry, back
        // to the transfer, with whatever it was waiting on cleared.
        existing.stage = "upload";
        existing.state = "running";
        existing.progress = null;
        existing.step = null;
        existing.error = null;
        existing.conflict = null;
        existing.terminalAt = null;
        existing.acknowledgedAt = null;
        return;
      }
      state.byId[localId] = {
        taskId: localId,
        kind: "ingestion",
        // No document uid until the server has written one. The label is what
        // the panel shows; an empty id keeps this entry out of every selector
        // that resolves a task back to a real document row.
        target: { type: "document", id: "", label: filename },
        owner: null,
        // Nothing server-side to subscribe to or acknowledge yet.
        localOnly: true,
        state: "running",
        progress: null,
        step: null,
        error: null,
        lastSeq: -1,
        stage: "upload",
        conflict: null,
        teamId,
        registeredAt: Date.now(),
        terminalAt: null,
        acknowledgedAt: null,
        warnings: null,
      };
    },

    /** The server took the file and named the ingestion task that owns it now.
     *
     *  Re-keyed rather than replaced: the entry keeps its start time, so the
     *  panel's list does not reshuffle as each file crosses over. The state
     *  goes back to `pending` because the analysis has not started — the
     *  transfer being done says nothing about the document being usable. */
    uploadHandedOff(
      state,
      action: PayloadAction<{ localId: string; taskId: string; documentUid: string | null; filename: string }>,
    ) {
      const { localId, taskId, documentUid, filename } = action.payload;
      const vm = state.byId[localId];
      delete state.byId[localId];
      if (state.byId[taskId]) return;
      state.byId[taskId] = {
        ...(vm ?? { registeredAt: Date.now() }),
        taskId,
        kind: "ingestion",
        target: documentUid ? { type: "document", id: documentUid, label: filename } : null,
        owner: vm?.owner ?? null,
        localOnly: false,
        state: "pending",
        progress: null,
        step: null,
        error: null,
        lastSeq: -1,
        stage: "analysis",
        conflict: null,
        teamId: vm?.teamId ?? null,
        terminalAt: null,
        acknowledgedAt: null,
        warnings: null,
      };
    },

    /** The transfer got there and the server refused to write: the folder
     *  gained a document of that name while the import was under way.
     *
     *  Not a failure — nothing went wrong and nothing was lost. The file is
     *  still ours to send; what is missing is the user's answer. */
    uploadConflicted(state, action: PayloadAction<{ localId: string; tagId: string | null; filename: string }>) {
      const vm = state.byId[action.payload.localId];
      if (!vm || vm.stage !== "upload") return;
      vm.stage = "decision";
      // Nothing is running and nothing has settled: the entry is waiting.
      vm.state = "pending";
      vm.progress = null;
      vm.step = null;
      vm.error = null;
      vm.conflict = { tagId: action.payload.tagId, filename: action.payload.filename };
    },

    /** The transfer ended with nothing left to wait for: upload-only mode, or a
     *  file the user chose to skip. A file that was handed off is already gone
     *  from here and its task owns the rest. */
    uploadFinished(state, action: PayloadAction<{ localId: string }>) {
      const vm = state.byId[action.payload.localId];
      if (!vm || vm.stage !== "upload") return;
      vm.state = "succeeded";
      vm.terminalAt = Date.now();
    },

    /** The transfer itself failed — the file never reached a task, so no task
     *  will ever report this. */
    uploadFailed(state, action: PayloadAction<{ localId: string; error: string }>) {
      const vm = state.byId[action.payload.localId];
      if (!vm || vm.stage !== "upload") return;
      vm.state = "failed";
      vm.error = action.payload.error;
      vm.terminalAt = Date.now();
    },

    taskEventReceived(state, action: PayloadAction<AnyTaskEvent>) {
      const event = action.payload;
      const vm = state.byId[event.task_id];
      if (!vm) return;
      if (event.seq <= vm.lastSeq) return; // sequential dedup
      if (vm.kind === "ingestion" && TERMINAL_STATES.has(vm.state)) return;
      vm.state = event.state;
      // Preserve last-known progress/step when a sparse event omits them (same
      // rule as target/owner below): a running event with no progress means
      // "unchanged", not "reset to indeterminate", so the bar never flickers back.
      // `error` is written through so a recovering retry can clear a transient one.
      if (event.progress != null) vm.progress = event.progress;
      if (event.step != null) vm.step = event.step;
      vm.error = event.error ?? null;
      vm.lastSeq = event.seq;
      if (event.target) vm.target = event.target;
      if (event.owner) vm.owner = event.owner;
      // `warnings` only ever arrives on the migration kind's final `result` — an
      // earlier `running` event with no result must not clobber it back to null.
      if (event.kind === "migration" && event.detail?.result?.warnings) {
        vm.warnings = event.detail.result.warnings;
      }
      if (TERMINAL_STATES.has(event.state) && vm.terminalAt === null) {
        vm.terminalAt = Date.now();
      }
    },

    taskEvicted(state, action: PayloadAction<string>) {
      delete state.byId[action.payload];
    },

    /** Ask the import panel to open itself.
     *
     *  For work the user has just handed off and expects to see continue
     *  somewhere — an import, once its dialog closes. Without this the work
     *  would carry on behind a closed panel, which reads as nothing happening:
     *  the very complaint that put the panel there.
     *
     *  A counter rather than a boolean, so a second import reopens a panel the
     *  user closed in between, and so no one has to reset a flag. */
    importPanelOpenRequested(state) {
      state.importPanelOpenRequest = (state.importPanelOpenRequest ?? 0) + 1;
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

    /** Mirror the server's per-task acknowledgement timestamp so task
     *  selectors update without a browser-local bulk flag. */
    taskAcknowledged(state, action: PayloadAction<{ taskId: string; acknowledgedAt: string }>) {
      const vm = state.byId[action.payload.taskId];
      if (!vm) return;
      vm.acknowledgedAt = new Date(action.payload.acknowledgedAt).getTime();
    },
  },
});

export const {
  taskRegistered,
  uploadStarted,
  uploadConflicted,
  uploadHandedOff,
  uploadFinished,
  uploadFailed,
  taskEventReceived,
  taskEvicted,
  importPanelOpenRequested,
  taskAcknowledged,
  completedTasksCleared,
} = taskSlice.actions;

// ── Selectors ─────────────────────────────────────────────────────────────────

const selectById = (state: TasksRootState) => state.tasks.byId;

/** Bumped every time something asks the import panel to open; it watches this. */
export const selectImportPanelOpenRequest = (state: TasksRootState) => state.tasks.importPanelOpenRequest ?? 0;

export const selectActiveTasks = createSelector(selectById, (byId) =>
  Object.values(byId).filter((vm) => !TERMINAL_STATES.has(vm.state)),
);

export const selectVisibleTasks = createSelector(selectById, (byId) => {
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
 * The imports this user has running or just finished in one team — what that
 * team's import panel lists.
 *
 * Scoped to the team whose page the panel is on: someone else's folder is not
 * where you follow your own import. Chat attachments are ingestions too, but
 * they belong to the conversation, not to a team's resources — `target.type`
 * is what separates those, not `localOnly`, since a file still being
 * transferred has no server task either and does belong here.
 *
 * Factory (one memoized selector per team); memoize the call with `useMemo`.
 */
export const makeSelectImportTasks = (teamId: string | null) =>
  createSelector(selectVisibleTasks, (tasks) =>
    tasks
      // A stage is what makes it an import: re-processing a document already
      // in the corpus is registered without one.
      .filter(
        (vm) => vm.kind === "ingestion" && vm.stage !== null && vm.target?.type === "document" && vm.teamId === teamId,
      )
      // Oldest first, unlike the tray: these are the files of one import, and
      // reading them in the order they were sent beats having the list reshuffle
      // under the eye as each new one registers.
      .sort((a, b) => a.registeredAt - b.registeredAt),
  );

/**
 * All tasks in the store, active first then most-recently-finished, with NO age
 * cutoff. Backs the admin Tasks page, which keeps the full session history until
 * the user clears it; `selectVisibleTasks` drops old ones.
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

/** A task that settled on an outcome which changed its entity, paired with that entity's id. */
export interface SettledTarget {
  taskId: string;
  targetId: string;
}

/**
 * All tasks of a given target type that settled on an outcome which changed the
 * entity they acted on — `succeeded` or `cancelled` — each with its target id.
 *
 * Backs `useRefetchOnTaskSettled`: a row/list derives its status from a cached
 * copy of the underlying entity, which goes stale the instant its task finishes
 * (`selectActiveTaskForTarget` drops succeeded tasks, so the row falls back to the
 * pre-completion snapshot). Consumers watch this selector to refetch the affected
 * entity on completion — the shared mechanism ingestion and erasure both use.
 *
 * `cancelled` counts because a cancelled ingestion does not merely stop: the
 * backend erases the half-built document — content, vectors, metadata row and
 * its storage quota (`delete_cancelled_document`, #2315). The entity the caller
 * cached is gone, so it needs the same refresh a success gets. `failed` is
 * deliberately excluded: the document survives, and its row keeps rendering
 * from the retained task rather than from a refetched snapshot.
 *
 * Factory (one memoized selector per `type`); memoize the call with `useMemo`.
 */
export const makeSelectSettledTargetsOfType = (type: string) =>
  createSelector(selectById, (byId): SettledTarget[] =>
    Object.values(byId)
      .filter(
        (vm) => (vm.state === "succeeded" || vm.state === "cancelled") && vm.target?.type === type && !!vm.target?.id,
      )
      .map((vm) => ({ taskId: vm.taskId, targetId: vm.target!.id })),
  );

/**
 * Every distinct target id of a given type currently in the store, in ANY
 * state (including `pending` — a task is registered with its target set from
 * creation, see `taskRegistered`). Backs `useNotifyOnNewTaskTarget`: a list page
 * (document folders today, others later) uses this to notice a target it has
 * never seen before — typically a document that was just uploaded and has no
 * row yet — and refetch, instead of waiting for that task to reach `succeeded`
 * (which `makeSelectSettledTargetsOfType` requires and a brand-new row never
 * satisfies, since it never existed pre-task to refresh in place).
 *
 * Factory (one memoized selector per `type`); memoize the call with `useMemo`.
 */
export const makeSelectTaskTargetsOfType = (type: string) =>
  createSelector(selectById, (byId): string[] => [
    ...new Set(
      Object.values(byId)
        .filter((vm) => vm.target?.type === type && !!vm.target?.id)
        .map((vm) => vm.target!.id),
    ),
  ]);
