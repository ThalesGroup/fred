// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useRef, type ReactNode } from "react";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import styles from "./WordTemplateLibraryForm.module.css";

export interface LibraryItem {
  key: string;
  name: string;
  detail?: string;
  error?: string;
}

interface LibraryEditorLabels {
  title: string;
  empty: string;
  edit: string;
  editTitle: string;
  editHint: string;
  upload: string;
  uploadAria: string;
  remove: (name: string) => string;
  count: string;
  save: string;
  cancel: string;
  nameField?: string;
}

interface Props {
  items: LibraryItem[];
  draftItems: LibraryItem[];
  labels: LibraryEditorLabels;
  editing: boolean;
  canEdit: boolean;
  disabled: boolean;
  confirmDisabled: boolean;
  onOpen: () => void;
  onCancel: () => void;
  onConfirm: () => void;
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
  onRename?: (index: number, name: string) => void;
  description?: ReactNode;
  status?: ReactNode;
  errors?: ReactNode;
}

export function WordTemplateLibraryEditor({
  items,
  draftItems,
  labels,
  editing,
  canEdit,
  disabled,
  confirmDisabled,
  onOpen,
  onCancel,
  onConfirm,
  onAdd,
  onRemove,
  onRename,
  description,
  status,
  errors,
}: Props) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className={styles.settingCard}>
      <div className={styles.sectionHeader}>
        <span className={styles.sectionTitle}>{labels.title}</span>
        {items.length > 0 && <span className={styles.countBadge}>{items.length}</span>}
      </div>
      {description && <p className={styles.description}>{description}</p>}
      <div className={styles.uploadRow} role="group" aria-label={labels.title}>
        {items.length ? (
          items.map((item) => (
            <Chip key={item.key} label={item.name} leading={<Icon category="outlined" type="description" />} />
          ))
        ) : (
          <Chip label={labels.empty} leading={<Icon category="outlined" type="description" />} />
        )}
        {canEdit &&
          (items.length ? (
            <IconButton
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "edit" }}
              aria-label={labels.edit}
              disabled={disabled}
              onClick={onOpen}
            />
          ) : (
            <Button
              type="button"
              color="primary"
              variant="outlined"
              size="small"
              disabled={disabled}
              icon={{ category: "outlined", type: "upload" }}
              onClick={onOpen}
            >
              {labels.upload}
            </Button>
          ))}
      </div>
      {status}
      <Dialog
        open={editing}
        title={labels.editTitle}
        confirmLabel={labels.save}
        cancelLabel={labels.cancel}
        confirmDisabled={disabled || confirmDisabled}
        onConfirm={onConfirm}
        onCancel={onCancel}
        maxWidth={600}
      >
        <div className={styles.root}>
          <p className={styles.description}>{labels.editHint}</p>
          {draftItems.length ? (
            <ul className={styles.libraryList}>
              {draftItems.map((item, index) => (
                <li className={styles.libraryRow} key={item.key}>
                  <Icon category="outlined" type="description" />
                  <div className={styles.libraryName}>
                    {onRename ? (
                      <TextInput
                        compact
                        value={item.name}
                        disabled={disabled}
                        aria-label={labels.nameField}
                        error={item.error}
                        onChange={(event) => onRename(index, event.target.value)}
                      />
                    ) : (
                      item.name
                    )}
                  </div>
                  {item.detail && (
                    <span className={styles.libraryFile} title={item.detail}>
                      {item.detail}
                    </span>
                  )}
                  <DeleteIconButton
                    size="small"
                    disabled={disabled}
                    aria-label={labels.remove(item.name)}
                    onClick={() => onRemove(index)}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.description}>{labels.empty}</p>
          )}
          <div className={styles.uploadRow}>
            <input
              ref={input}
              className={styles.fileInput}
              type="file"
              accept=".docx"
              multiple
              aria-label={labels.uploadAria}
              disabled={disabled || draftItems.length >= 8}
              onChange={(event) => {
                onAdd(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
            <Button
              type="button"
              color="primary"
              variant="outlined"
              size="small"
              disabled={disabled || draftItems.length >= 8}
              icon={{ category: "outlined", type: "upload" }}
              onClick={() => input.current?.click()}
            >
              {labels.upload}
            </Button>
            <span className={styles.description}>{labels.count}</span>
          </div>
          {errors}
        </div>
      </Dialog>
    </div>
  );
}
