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

import { useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import { usePaneResize } from "@rework/core/hooks/usePaneResize";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { TaskCard } from "@shared/molecules/TaskCard/TaskCard";
import {
  selectImportPanelOpenRequest,
  selectImportTasks,
  selectRunningImportCount,
} from "../../../../features/tasks/taskSlice";
import { useTaskAcknowledgement } from "../../../../features/tasks/useTaskAcknowledgement";
import styles from "./ImportPanel.module.css";

export function ImportPanel() {
  const { t } = useTranslation();
  const imports = useSelector(selectImportTasks);
  const runningCount = useSelector(selectRunningImportCount);
  const { acknowledge, isAcknowledging } = useTaskAcknowledgement();
  const [expanded, setExpanded] = useState(false);

  // An import that has just handed off opens the panel itself. Otherwise the
  // work carries on behind a closed rail, which reads as nothing happening —
  // the complaint the panel exists to answer. The counter starts where it
  // stands, so mounting the page does not reopen it for an import already under
  // way.
  const openRequest = useSelector(selectImportPanelOpenRequest);
  const lastHandledRequest = useRef(openRequest);
  useEffect(() => {
    if (openRequest === lastHandledRequest.current) return;
    lastHandledRequest.current = openRequest;
    setExpanded(true);
  }, [openRequest]);

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
          {imports.length === 0 ? (
            <p className={styles.empty}>{t("rework.imports.panel.empty")}</p>
          ) : (
            imports.map((task) => (
              <TaskCard
                key={task.taskId}
                task={task}
                onAcknowledge={() => acknowledge(task.taskId, task.kind, task.localOnly)}
                acknowledging={isAcknowledging(task.taskId)}
              />
            ))
          )}
        </div>
      )}
    </aside>
  );
}
