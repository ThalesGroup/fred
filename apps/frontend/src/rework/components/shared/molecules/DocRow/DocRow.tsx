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

import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useSelector } from "react-redux";
import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import { DocStatusBadge, type DocStatus } from "@shared/atoms/DocStatusBadge/DocStatusBadge.tsx";
import { formatBytes } from "@shared/utils/formatBytes";
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
  /** intrinsic status when no task is active; an active task overrides it. Omit for a plain
   * file with no indexing status (e.g. a workspace file), which renders no status badge. */
  status?: DocStatus;
  /** 0.0–1.0 base progress when status === "processing" with no task. */
  progress?: number | null;
  /** Original file size in bytes; rendered as a localized "1.5 MB"/"1,5 Mo" label. Omit to hide. */
  sizeBytes?: number | null;
  /** Upload/ingest date (ISO string); revealed on row hover, just left of the size. Omit to hide. */
  uploadedAt?: string | null;
  selected?: boolean;
  onSelect?: () => void;
  onPreview?: () => void;
  onDownload?: () => void;
  /** shown as a direct "Traiter" action when the resolved status is "raw". */
  onProcess?: () => void;
  /** secondary actions grouped under the "…" overflow menu. */
  moreActions?: DocRowMoreAction[];
  /** optional provenance chip (e.g. OriginBadge) rendered in the trailing area. */
  provenanceBadge?: ReactNode;
  /** current search-inclusion state (retrievable flag). Omit when the concept doesn't
   * apply to this row (e.g. a plain filesystem file) — the toggle then renders nothing. */
  searchable?: boolean;
  /** flips `searchable`; rendered as an eye/crossed-eye button just left of download,
   * reflecting the current state and toggling it on click. */
  onToggleSearchable?: () => void;
  /** direct delete action, rendered as a trash icon among the row's actions. */
  onDelete?: () => void;
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
  sizeBytes = null,
  uploadedAt = null,
  selected = false,
  onSelect,
  onPreview,
  onDownload,
  onProcess,
  moreActions,
  provenanceBadge,
  searchable,
  onToggleSearchable,
  onDelete,
}: DocRowProps) {
  const { t, i18n } = useTranslation();
  const task = useSelector(selectActiveTaskForTarget("document", id));
  const resolved = resolveStatus(status, progress, task);
  const meta = fileTypeMeta(fileType);
  const sizeLabel = sizeBytes && sizeBytes > 0 ? formatBytes(sizeBytes, i18n.language) : null;
  const dateLabel = formatUploadDate(uploadedAt, i18n.language);

  // The whole row is the document's "open" target: the icon, the metadata (date,
  // size) and the empty space between them read as one clickable line, so any of
  // them selects AND previews — not just the name. The action buttons inside the
  // row stop propagation, so they keep their own behaviour. Rows given no
  // `onPreview` (e.g. a plain filesystem file) still just select.
  const openRow = () => {
    onSelect?.();
    onPreview?.();
  };

  return (
    <div className={styles.row} data-selected={selected || undefined} onClick={openRow}>
      <span className={styles.icon} style={{ color: meta.color }} aria-hidden>
        <Icon category="outlined" type={meta.icon} />
      </span>
      {/* No `title` on the name: the row already shows it, and the native tooltip
          only covered the neighbouring rows on hover. */}
      {onPreview ? (
        <button
          type="button"
          className={styles.nameButton}
          onClick={(e) => {
            // Keeps the row's handler from firing a second time: with a toggling
            // host (re-clicking the open document closes its preview) a bubbled
            // duplicate would open and immediately re-close it.
            e.stopPropagation();
            openRow();
          }}
        >
          {name}
        </button>
      ) : (
        <span className={styles.name}>{name}</span>
      )}

      <span className={styles.trailing}>
        {/* Date: collapsed at rest, slides in on the LEFT of the size on hover. */}
        {dateLabel && (
          <span className={styles.revealLeft}>
            <span className={styles.date} title={dateLabel}>
              {dateLabel}
            </span>
          </span>
        )}

        {sizeLabel && <span className={styles.size}>{sizeLabel}</span>}

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

        {provenanceBadge}

        {/* "ready" is the silent, happy path — users only want to see the states
            that need attention (processing / failed) or action (raw). */}
        {resolved.status && resolved.status !== "ready" && (
          <DocStatusBadge status={resolved.status} progress={resolved.progress} />
        )}

        {/* Searchable toggle / download / delete / menu: collapsed at rest, slide
            in on the RIGHT of the size on hover. */}
        {(onDownload ||
          onDelete ||
          (typeof searchable === "boolean" && onToggleSearchable) ||
          (moreActions && moreActions.length > 0)) && (
          <span className={styles.revealRight}>
            <span className={styles.actions}>
              {typeof searchable === "boolean" && onToggleSearchable && (
                // Keying on the state forces a remount on toggle, so the pop-in
                // animation below plays every time the icon swaps.
                <span key={searchable ? "searchable" : "excluded"} className={styles.searchableToggle}>
                  <IconButton
                    color="on-surface"
                    variant="icon"
                    size="xs"
                    icon={{ category: "outlined", type: searchable ? "visibility" : "visibility_off" }}
                    aria-label={searchable ? t("documentLibrary.makeExcluded") : t("documentLibrary.makeSearchable")}
                    title={searchable ? t("documentLibrary.makeExcluded") : t("documentLibrary.makeSearchable")}
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleSearchable();
                    }}
                  />
                </span>
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
              {onDelete && (
                <IconButton
                  color="on-surface"
                  variant="icon"
                  size="xs"
                  icon={{ category: "outlined", type: "delete" }}
                  aria-label={t("rework.resources.action.delete")}
                  title={t("rework.resources.action.delete")}
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete();
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
        )}
      </span>
    </div>
  );
}

/** Localized short date for the upload timestamp; null for missing/unparseable values. */
function formatUploadDate(value: string | null | undefined, locale: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" });
}

/** An active task (running/pending/cancelling) wins over the intrinsic status. */
function resolveStatus(
  base: DocStatus | undefined,
  baseProgress: number | null,
  task: TaskViewModel | undefined,
): { status: DocStatus | undefined; progress: number | null } {
  if (!task) return { status: base, progress: base === "processing" ? baseProgress : null };
  if (task.state === "failed") return { status: "failed", progress: null };
  return { status: "processing", progress: task.progress };
}
