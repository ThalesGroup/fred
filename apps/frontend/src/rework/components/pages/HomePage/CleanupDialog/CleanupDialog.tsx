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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Checkbox from "@shared/atoms/Checkbox/Checkbox.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import styles from "./CleanupDialog.module.scss";

export interface CleanupItem {
  id: string;
  title: string;
  /** Secondary line, e.g. the conversation's agent or the file's size. */
  meta?: string;
}

export interface CleanupGroup {
  key: string;
  label: string;
  items: CleanupItem[];
}

interface CleanupDialogProps {
  open: boolean;
  title: string;
  subtitle: string;
  groups: CleanupGroup[];
  emptyLabel: string;
  /** Called with the ids the user kept selected. */
  onConfirm: (selectedIds: string[]) => void;
  onClose: () => void;
}

/** Reusable "cleanup tool": a grouped, selectable list where everything starts
 * selected — the user just confirms, or unticks what they want to keep. Used by
 * the home page's inactive-conversations and unused-files cleanup. */
export default function CleanupDialog({
  open,
  title,
  subtitle,
  groups,
  emptyLabel,
  onConfirm,
  onClose,
}: CleanupDialogProps) {
  const { t } = useTranslation();
  const allIds = useMemo(() => groups.flatMap((g) => g.items.map((i) => i.id)), [groups]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  // Everything is preselected and every group expanded each time it opens.
  useEffect(() => {
    if (open) {
      setSelected(new Set(allIds));
      setCollapsed(new Set());
    }
  }, [open, allIds]);

  const toggleCollapsed = (key: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const setGroup = (group: CleanupGroup, checked: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      group.items.forEach((i) => (checked ? next.add(i.id) : next.delete(i.id)));
      return next;
    });

  const count = selected.size;
  const total = allIds.length;
  const confirmLabel =
    count === total
      ? t("rework.home.responsible.cleanupTool.confirmAll")
      : t("rework.home.responsible.cleanupTool.confirm", { count });

  return (
    <Dialog
      open={open}
      title={title}
      maxWidth={600}
      confirmLabel={confirmLabel}
      confirmColor="error"
      confirmDisabled={count === 0}
      cancelLabel={t("rework.home.responsible.cleanupTool.cancel")}
      onConfirm={() => onConfirm([...selected])}
      onCancel={onClose}
    >
      <div className={styles.container}>
        {total === 0 ? (
          <p className={styles.empty}>{emptyLabel}</p>
        ) : (
          <>
            <p className={styles.subtitle}>{subtitle}</p>
            <div className={styles.list}>
              {groups.map((group) => {
                const ids = group.items.map((i) => i.id);
                const allChecked = ids.every((id) => selected.has(id));
                const someChecked = ids.some((id) => selected.has(id));
                const expanded = !collapsed.has(group.key);
                return (
                  <div key={group.key} className={styles.group}>
                    {/* The whole header (padding included) toggles the group; the
                        checkbox stops propagation so it only (de)selects. */}
                    <div
                      className={styles.groupHeader}
                      role="button"
                      tabIndex={0}
                      aria-expanded={expanded}
                      onClick={() => toggleCollapsed(group.key)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggleCollapsed(group.key);
                        }
                      }}
                    >
                      <span
                        className={styles.groupCheckbox}
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => e.stopPropagation()}
                      >
                        <Checkbox
                          checked={allChecked}
                          indeterminate={!allChecked && someChecked}
                          onChange={() => setGroup(group, !allChecked)}
                        />
                      </span>
                      <span className={styles.groupLabel}>{group.label}</span>
                      <span className={styles.groupCount}>{group.items.length}</span>
                      <span className={styles.chevron}>
                        <Icon category="outlined" type={expanded ? "expand_less" : "expand_more"} />
                      </span>
                    </div>
                    <div className={styles.items} data-expanded={expanded} aria-hidden={!expanded}>
                      <div className={styles.itemsInner}>
                        {group.items.map((item) => (
                          <label key={item.id} className={styles.row}>
                            <Checkbox checked={selected.has(item.id)} onChange={() => toggle(item.id)} />
                            <span className={styles.rowText}>
                              <span className={styles.rowTitle}>{item.title}</span>
                              {item.meta && <span className={styles.rowMeta}>{item.meta}</span>}
                            </span>
                          </label>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
}
