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

import { useEffect, useId, type ReactNode } from "react";
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete.tsx";
import { Portal } from "@shared/utils/Portal.tsx";
import { OptionModel } from "@models/Option.model.ts";
import styles from "./AddPeopleDialog.module.scss";

export interface AddPeopleDialogProps<T> {
  open: boolean;
  title: string;
  subtitle: string;
  searchPlaceholder: string;
  /** Shown in the suggestions menu when `options` is empty (searching, no match). */
  noOptionsMessage?: string;
  options: OptionModel<T>[];
  onSearchChange: (value: string) => void;
  onSelect: (item: T) => void;
  pending: T[];
  pendingKey: (item: T) => string;
  pendingLabel: (item: T) => string;
  /** Optional controls between a pending person's name and its remove button. */
  pendingAddon?: (item: T) => ReactNode;
  pendingListHeader: string;
  pendingListEmpty: string;
  removeAriaLabel: (item: T) => string;
  onRemove: (item: T) => void;
  cancelLabel: string;
  confirmLabel: string;
  confirmDisabled: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

/** Search people, collect them in a pending list, add them in one action. Callers own data and mutations. */
export default function AddPeopleDialog<T>({
  open,
  title,
  subtitle,
  searchPlaceholder,
  noOptionsMessage,
  options,
  onSearchChange,
  onSelect,
  pending,
  pendingKey,
  pendingLabel,
  pendingAddon,
  pendingListHeader,
  pendingListEmpty,
  removeAriaLabel,
  onRemove,
  cancelLabel,
  confirmLabel,
  confirmDisabled,
  onConfirm,
  onClose,
}: AddPeopleDialogProps<T>) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onClose}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.header}>
            <p id={titleId} className={styles.title}>
              {title}
            </p>
            <p className={styles.subtitle}>{subtitle}</p>
          </div>

          <div className={styles.searchRow}>
            <Autocomplete<T>
              textInput={{
                placeholder: searchPlaceholder,
                icon: { category: "outlined", type: "search" },
                autoFocus: true,
              }}
              minQueryLength={2}
              noOptionsMessage={noOptionsMessage}
              onFieldValueChange={onSearchChange}
              options={options}
              onSelect={onSelect}
            />
          </div>

          <div className={styles.pendingListContainer}>
            <div className={styles.pendingListHeader}>{pendingListHeader}</div>
            {pending.length > 0 ? (
              <ul className={styles.pendingList}>
                {pending.map((item) => (
                  <li key={pendingKey(item)} className={styles.pendingRow}>
                    <span className={styles.pendingName}>{pendingLabel(item)}</span>
                    {pendingAddon && <div className={styles.pendingAddon}>{pendingAddon(item)}</div>}
                    <IconButton
                      variant="icon"
                      size="medium"
                      icon={{ category: "outlined", type: "close" }}
                      aria-label={removeAriaLabel(item)}
                      onClick={() => onRemove(item)}
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <div className={styles.pendingListEmpty}>{pendingListEmpty}</div>
            )}
          </div>

          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="medium" onClick={onClose}>
              {cancelLabel}
            </Button>
            <Button color="primary" variant="filled" size="medium" disabled={confirmDisabled} onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
