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

// Where an import is followed once its dialog has closed.
//
// One element with two widths, not a rail plus a drawer: collapsed it is a
// narrow rail beside the documents card, expanded it is the panel itself. The
// button that opens it stays exactly where it was, and closes it again — so
// there is one thing on screen that grows and shrinks, rather than two that
// appear and disappear.
//
// It adds to the document rows, it does not replace them. A row stays the
// permanent home of its document's status; this is the same state gathered in
// one place, and later where actions on it are offered.

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import { usePaneResize } from "@rework/core/hooks/usePaneResize";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { TaskCard } from "@shared/molecules/TaskCard/TaskCard";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { makeSelectImportTasks, selectImportPanelOpenRequest, taskEvicted } from "../../../../features/tasks/taskSlice";
import { useTaskAcknowledgement } from "../../../../features/tasks/useTaskAcknowledgement";
import { importFailure } from "../../../../features/imports/importFailure";
import { importPhaseLabel } from "../../../../features/imports/importPhases";
import {
  cancelImport,
  canCancelImport,
  heldImport,
  releaseHeldImport,
  resolveConflict,
  resumeUnfinishedImports,
  retryImport,
} from "../../../../features/imports/importRun";
import {
  forgetUnfinishedImports,
  noteImportSettled,
  unfinishedImports,
  type UnfinishedFile,
} from "../../../../features/imports/unfinishedImports";
import { TERMINAL_STATES, type TaskViewModel } from "../../../../features/tasks/taskTypes";
import type { ConflictDecision } from "../DocumentUploadDrawer/importConflicts";
import { ImportStepper } from "./ImportStepper";
import styles from "./ImportPanel.module.css";

/** Long enough to read that a file made it, short enough that the panel empties
 *  itself instead of becoming a list of things already done. */
const SETTLED_CARD_LINGER_MS = 3000;

/** @param teamId whose resources the page beside this panel shows. */
export function ImportPanel({ teamId }: { teamId: string | null }) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const { showError } = useToast();
  const selectImports = useMemo(() => makeSelectImportTasks(teamId), [teamId]);
  const allImports = useSelector(selectImports);
  const runningCount = allImports.filter((vm) => !TERMINAL_STATES.has(vm.state)).length;
  const { acknowledge, isAcknowledging } = useTaskAcknowledgement();
  const [expanded, setExpanded] = useState(false);

  // An import that has just handed off opens the panel itself. Otherwise the
  // work carries on behind a closed rail, which reads as nothing happening —
  // the complaint the panel exists to answer. The counter starts where it
  // stands, so mounting the page does not reopen it for an import already under
  // way.
  // A file that arrived has nothing left to say, and a panel that keeps every
  // success is a panel nobody reads. It stays long enough to be seen finishing,
  // then leaves — this list only. The task itself stays in the store for its
  // own five-minute window, which the documents table reads to mark a row as
  // just completed and the tray reads to show it at all.
  const [settled, setSettled] = useState<ReadonlySet<string>>(() => new Set());
  // What the panel still has to show: everything it follows, minus the
  // successes it has already let go of.
  const imports = useMemo(() => allImports.filter((vm) => !settled.has(vm.taskId)), [allImports, settled]);
  const settling = useRef(new Map<string, number>());
  useEffect(() => {
    const timers = settling.current;
    for (const task of allImports) {
      // `settled` is part of the guard, not just `timers`: the timer removes
      // itself when it fires, and this effect re-runs on every task event, so
      // without it each event would schedule the same card's exit again.
      if (task.state !== "succeeded" || timers.has(task.taskId) || settled.has(task.taskId)) continue;
      timers.set(
        task.taskId,
        window.setTimeout(() => {
          timers.delete(task.taskId);
          setSettled((ids) => new Set(ids).add(task.taskId));
        }, SETTLED_CARD_LINGER_MS),
      );
    }
  }, [allImports, settled]);

  // Ids of tasks the store has since dropped: keeping them would grow for the
  // life of the tab. Only rebuilt when it has actually drifted.
  useEffect(() => {
    setSettled((ids) => {
      if (ids.size <= allImports.length) return ids;
      const live = new Set(allImports.map((vm) => vm.taskId));
      return new Set([...ids].filter((id) => live.has(id)));
    });
  }, [allImports]);
  useEffect(
    () => () => {
      for (const timer of settling.current.values()) window.clearTimeout(timer);
      settling.current.clear();
    },
    [],
  );

  const openRequest = useSelector(selectImportPanelOpenRequest);
  const lastHandledRequest = useRef(openRequest);
  useEffect(() => {
    if (openRequest === lastHandledRequest.current) return;
    lastHandledRequest.current = openRequest;
    setExpanded(true);
  }, [openRequest]);

  // What a previous visit left in the air. Read once: anything that happens
  // from here on is in the store, where the panel can follow it properly.
  const [interrupted, setInterrupted] = useState<UnfinishedFile[]>(() => unfinishedImports());
  // Except for whatever is already listed below — coming back to this page
  // re-reads the record, and a file the panel is still following is not a file
  // that failed to arrive.
  const listed = new Set(imports.map((task) => task.target?.label));
  const missing = interrupted.filter((entry) => entry.teamId === teamId && !listed.has(entry.filename));

  const resumeInput = useRef<HTMLInputElement>(null);
  const onFilesPicked = (picked: File[]) => {
    void resumeUnfinishedImports(picked, missing, {
      dispatch,
      onError: (detail) => showError({ summary: t("rework.imports.panel.title"), detail }),
    }).then(({ resumed }) => {
      // Only what was actually picked leaves the block. Clearing it outright
      // would drop the rest of the prompt after a partial selection — the
      // remaining files would never be offered again.
      if (resumed.length === 0) return;
      const done = new Set(resumed);
      setInterrupted((entries) => entries.filter((entry) => !done.has(entry.entryId)));
    });
  };

  const giveUpOnMissing = () => {
    forgetUnfinishedImports(missing.map((entry) => entry.entryId));
    setInterrupted((entries) => entries.filter((entry) => !missing.includes(entry)));
  };

  // Hoisted out of the list and keyed by task id: an arrow function built per
  // card per render is what kept every card re-rendering on every task event,
  // and an import dispatches a great many of those.
  const failFast = (detail: string) => showError({ summary: t("rework.imports.panel.title"), detail });
  const onRetry = useCallback(
    (taskId: string) => void retryImport(taskId, { dispatch, onError: failFast }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- failFast closes
    // over showError and t, both stable for the life of the provider.
    [dispatch],
  );
  const onDecide = useCallback(
    (taskId: string, decision: ConflictDecision) =>
      void resolveConflict(taskId, decision, { dispatch, onError: failFast }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see above.
    [dispatch],
  );
  const onCancel = useCallback(
    (taskId: string) => {
      if (!cancelImport(taskId, dispatch)) {
        showError({ summary: t("rework.imports.panel.title"), detail: t("rework.imports.cancel.tooLate") });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see above.
    [dispatch],
  );
  const onDismiss = useCallback(
    (task: TaskViewModel) => {
      // Dismissed for good: stop holding the file open for a retry that is no
      // longer on offer, and stop expecting it — or it would be offered again
      // as "did not arrive" on every visit.
      releaseHeldImport(task.taskId);
      noteImportSettled(task.taskId);
      // The server still gets its acknowledgement, but the entry goes now
      // rather than lingering for the tray's eviction window: dismissing it
      // here means being done with it.
      void acknowledge(task.taskId, task.kind, task.localOnly);
      dispatch(taskEvicted(task.taskId));
    },
    [dispatch, acknowledge],
  );

  const toggleLabel = expanded ? t("rework.imports.panel.collapse") : t("rework.imports.panel.expand");

  // Drag the open panel wider or narrower from its left edge, exactly as the
  // chat's viewers do — same hook, same clamping, same per-key persistence, so
  // the width survives closing the panel and reloading the page.
  const panelRef = useRef<HTMLElement>(null);
  const resize = usePaneResize({
    storageKey: "import-panel:width",
    initialWidth: 360,
    minWidth: 280,
    maxWidth: 720,
    paneRef: panelRef,
  });

  return (
    <aside
      ref={panelRef}
      className={styles.panel}
      data-expanded={expanded}
      data-dragging={expanded && resize.dragging ? "true" : undefined}
      // The collapsed rail is the button's own width; only the open panel
      // carries a chosen one.
      style={expanded ? ({ "--import-panel-width": `${resize.width}px` } as React.CSSProperties) : undefined}
      aria-label={t("rework.imports.panel.title")}
      // Collapsed it is a launcher, not a region: nothing inside it is
      // reachable, and announcing an empty landmark would be noise.
      role={expanded ? "region" : undefined}
    >
      {expanded && (
        <div
          className={styles.resizeHandle}
          role="separator"
          aria-orientation="vertical"
          aria-label={t("rework.imports.panel.resize")}
          {...resize.handleProps}
        />
      )}

      {/* The toggle hugs the right edge, which is the edge that does not move
          when the panel widens — so the button stays exactly where it was and
          everything else grows away from it. */}
      <div className={styles.head}>
        {expanded && <span className={styles.title}>{t("rework.imports.panel.title")}</span>}
        <Tooltip text={toggleLabel} placement="left">
          <IconButton
            variant={expanded ? "tonal" : "icon"}
            size="small"
            // Open, the arrow points back the way the panel folds.
            icon={{ category: "outlined", type: expanded ? "keyboard_arrow_right" : "download" }}
            aria-label={toggleLabel}
            aria-expanded={expanded}
            badgeCount={runningCount}
            onClick={() => setExpanded((open) => !open)}
          />
        </Tooltip>
      </div>

      {expanded && (
        <div className={styles.body}>
          {missing.length > 0 && (
            <div className={styles.interrupted}>
              <p className={styles.interruptedTitle}>{t("rework.imports.interrupted.title")}</p>
              {/* Named, because "some files did not arrive" is not something
                  anyone can act on. */}
              <p className={styles.interruptedNames}>{missing.map((entry) => entry.filename).join(", ")}</p>
              <div className={styles.decision}>
                <Button variant="text" size="small" color="primary" onClick={() => resumeInput.current?.click()}>
                  {t("rework.imports.interrupted.resume")}
                </Button>
                <Button variant="text" size="small" color="on-surface-retreat" onClick={giveUpOnMissing}>
                  {t("rework.imports.interrupted.forget")}
                </Button>
              </div>
              {/* The browser cannot reopen a file it no longer holds, so the
                  user picks them again; only the missing ones are sent, to
                  where they were headed. */}
              <input
                ref={resumeInput}
                type="file"
                multiple
                hidden
                onChange={(event) => {
                  onFilesPicked([...(event.target.files ?? [])]);
                  event.target.value = "";
                }}
              />
            </div>
          )}
          {imports.length === 0 && missing.length === 0 ? (
            <p className={styles.empty}>{t("rework.imports.panel.empty")}</p>
          ) : (
            imports.map((task) => (
              <ImportItem
                key={task.taskId}
                task={task}
                onRetry={onRetry}
                onDecide={onDecide}
                onCancel={onCancel}
                onDismiss={onDismiss}
                dismissing={isAcknowledging(task.taskId)}
              />
            ))
          )}
        </div>
      )}
    </aside>
  );
}

/** One file of an import.
 *
 *  The card itself is the shared one; what it cannot know is what a failure
 *  means for this file and whether anything can still be done about it. That
 *  is this component's whole job. */
const ImportItem = memo(function ImportItem({
  task,
  onRetry,
  onDecide,
  onCancel,
  onDismiss,
  dismissing,
}: {
  task: TaskViewModel;
  onRetry: (taskId: string) => void;
  onDecide: (taskId: string, decision: ConflictDecision) => void;
  onCancel: (taskId: string) => void;
  onDismiss: (task: TaskViewModel) => void;
  dismissing: boolean;
}) {
  const { t } = useTranslation();
  const failed = task.state === "failed";
  const failure = failed ? importFailure(task, t) : null;
  const awaitingDecision = task.stage === "decision";
  // Sending the file again is the only way to replace or retry, and only the
  // browser has the file. After a reload it does not, and offering an action
  // that cannot work would be worse than saying so.
  const stillHeld = heldImport(task.taskId) !== undefined;

  // The single line the markers opposite are about: the phase in flight, or —
  // when something interrupted it — why it stopped, or the question holding it.
  const statusText =
    failure?.summary ?? (awaitingDecision ? t("rework.imports.conflict.question") : importPhaseLabel(task, t));
  // Sending it again cannot change what the folder holds, and the transfer is
  // not what went wrong — only clearing the duplicate name will do.
  const retryable = failed && stillHeld && !failure?.hopeless;

  return (
    <div className={styles.item}>
      <TaskCard
        task={task}
        // A failure gets its cause named rather than the sentence the backend
        // wrote for a log.
        statusText={statusText}
        statusDetail={failure?.detail}
        // No row of its own: the markers go in the footer, facing the name of
        // the phase they are on, and give the card back the height a bar took.
        progressSlot={null}
        // Only while something is moving — once the file is settled the footer
        // goes back to saying when.
        trailingSlot={TERMINAL_STATES.has(task.state) ? undefined : <ImportStepper task={task} />}
        actions={
          retryable ? (
            <Tooltip text={t("rework.imports.retry.action")}>
              <IconButton
                variant="icon"
                size="small"
                icon={{ category: "outlined", type: "refresh" }}
                aria-label={t("rework.imports.retry.action")}
                onClick={() => onRetry(task.taskId)}
              />
            </Tooltip>
          ) : canCancelImport(task.taskId) ? (
            // Only while its request has not left. A file already on the wire
            // is the server's, and offering to call it back would leave a
            // document behind that the panel said was cancelled.
            <Tooltip text={t("rework.imports.cancel.action")}>
              <IconButton
                variant="icon"
                size="small"
                icon={{ category: "outlined", type: "close" }}
                aria-label={t("rework.imports.cancel.action")}
                onClick={() => onCancel(task.taskId)}
              />
            </Tooltip>
          ) : undefined
        }
        onAcknowledge={() => onDismiss(task)}
        acknowledging={dismissing}
      />

      {/* Replace or skip, as a file explorer asks it — never in the document
          table, which is no place to be answering a question. */}
      {awaitingDecision && stillHeld && (
        <div className={styles.decision}>
          <Button variant="text" size="small" color="primary" onClick={() => onDecide(task.taskId, "overwrite")}>
            {t("rework.imports.conflict.replace")}
          </Button>
          <Button variant="text" size="small" color="on-surface-retreat" onClick={() => onDecide(task.taskId, "skip")}>
            {t("rework.imports.conflict.skip")}
          </Button>
        </div>
      )}

      {/* Only for a file the browser was still carrying: once the server has
          it, re-selecting it would import a second copy. A failure after the
          hand-off is relaunched from the document's own row. */}
      {(failed || awaitingDecision) && !stillHeld && task.localOnly && (
        <p className={styles.reselect}>{t("rework.imports.retry.unavailable")}</p>
      )}
      {failed && !stillHeld && !task.localOnly && !failure?.hopeless && (
        <p className={styles.reselect}>{t("rework.imports.retry.relaunchFromRow")}</p>
      )}
    </div>
  );
});
