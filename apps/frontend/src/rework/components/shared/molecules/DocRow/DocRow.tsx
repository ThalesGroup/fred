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

import { useTranslation } from "react-i18next";
import { useSelector } from "react-redux";
import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import { DocStatusBadge, type DocStatus } from "@shared/atoms/DocStatusBadge/DocStatusBadge.tsx";
import { selectActiveTaskForTarget } from "../../../../features/tasks/taskSlice";
import type { TaskViewModel } from "../../../../features/tasks/taskTypes";
import { fileTypeMeta } from "./docFileType.ts";
import styles from "./DocRow.module.css";

/** A secondary action shown in the row's "…" overflow menu. */
export interface DocRowMoreAction {
  id: string;
  label: string;
  onSelect: () => void;
}

interface DocRowProps {
  id: string;
  name: string;
  /** file extension/type, e.g. "docx" | "pdf" | "csv". */
  fileType: string;
  /** intrinsic status when no task is active; an active task overrides it. */
  status: DocStatus;
  /** 0.0–1.0 base progress when status === "processing" with no task. */
  progress?: number | null;
  selected?: boolean;
  onSelect?: () => void;
  onPreview?: () => void;
  onDownload?: () => void;
  /** shown as a direct "Traiter" action when the resolved status is "raw". */
  onProcess?: () => void;
  /** secondary actions grouped under the "…" overflow menu. */
  moreActions?: DocRowMoreAction[];
}

/**
 * One document = one row = one state. The row reads the task store for its own
 * id: an active task wins over the intrinsic `status` prop so a processing
 * document never needs a second, separate row (cf. the task system contract).
 */
export function DocRow({
  id,
  name,
  fileType,
  status,
  progress = null,
  selected = false,
  onSelect,
  onPreview,
  onDownload,
  onProcess,
  moreActions,
}: DocRowProps) {
  const { t } = useTranslation();
  const task = useSelector(selectActiveTaskForTarget("document", id));
  const resolved = resolveStatus(status, progress, task);
  const meta = fileTypeMeta(fileType);

  return (
    <div className={styles.row} data-selected={selected || undefined} onClick={onSelect}>
      <span className={styles.icon} style={{ color: meta.color }} aria-hidden>
        <Icon category="outlined" type={meta.icon} />
      </span>
      <span className={styles.name} title={name}>
        {name}
      </span>

      <span className={styles.trailing}>
        {resolved.status === "raw" && onProcess && (
          <span className={styles.processAction}>
            <Button
              color="on-surface"
              variant="outlined"
              size="xs"
              icon={{ category: "outlined", type: "auto_awesome" }}
              onClick={(e) => {
                e.stopPropagation();
                onProcess();
              }}
            >
              {t("rework.resources.action.process")}
            </Button>
          </span>
        )}

        <DocStatusBadge status={resolved.status} progress={resolved.progress} />

        <span className={styles.actions}>
          {onPreview && (
            <IconButton
              color="on-surface"
              variant="icon"
              size="xs"
              icon={{ category: "outlined", type: "visibility" }}
              aria-label={t("rework.resources.action.preview")}
              title={t("rework.resources.action.preview")}
              onClick={(e) => {
                e.stopPropagation();
                onPreview();
              }}
            />
          )}
          {onDownload && (
            <IconButton
              color="on-surface"
              variant="icon"
              size="xs"
              icon={{ category: "outlined", type: "download" }}
              aria-label={t("rework.resources.action.download")}
              title={t("rework.resources.action.download")}
              onClick={(e) => {
                e.stopPropagation();
                onDownload();
              }}
            />
          )}
          {moreActions && moreActions.length > 0 && (
            <span onClick={(e) => e.stopPropagation()}>
              <IconButtonMenu
                iconButton={{
                  color: "on-surface",
                  variant: "icon",
                  size: "xs",
                  icon: { category: "outlined", type: "more_horiz" },
                  "aria-label": t("rework.resources.action.more"),
                  title: t("rework.resources.action.more"),
                }}
                options={moreActions.map((action) => ({ key: action.id, value: action.id, label: action.label }))}
                onSelect={(id) => moreActions.find((action) => action.id === id)?.onSelect()}
              />
            </span>
          )}
        </span>
      </span>
    </div>
  );
}

/** An active task (running/pending/cancelling) wins over the intrinsic status. */
function resolveStatus(
  base: DocStatus,
  baseProgress: number | null,
  task: TaskViewModel | undefined,
): { status: DocStatus; progress: number | null } {
  if (!task) return { status: base, progress: base === "processing" ? baseProgress : null };
  if (task.state === "failed") return { status: "failed", progress: null };
  return { status: "processing", progress: task.progress };
}
