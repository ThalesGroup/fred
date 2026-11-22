// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useRef, useState, type ReactNode } from "react";
import Button from "@shared/atoms/Button/Button";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextInput from "@shared/atoms/TextInput/TextInput";
import styles from "./WordTemplateLibraryForm.module.css";

export interface LibraryItem {
  key: string;
  name: string;
  detail?: string;
  error?: string;
  readOnly?: boolean;
}

interface LibraryEditorLabels {
  title: string;
  empty: string;
  edit: (name: string) => string;
  editHint: string;
  upload: string;
  uploadAria: string;
  remove: (name: string) => string;
  count: string;
  save: string;
  cancel: string;
  nameField: string;
}

interface Props {
  items: LibraryItem[];
  labels: LibraryEditorLabels;
  canEdit: boolean;
  disabled: boolean;
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
  onRename: (index: number, name: string) => void;
  onStartRename?: () => void;
  onSave?: () => void;
  onCancel?: () => void;
  saveDisabled?: boolean;
  dirty?: boolean;
  description?: ReactNode;
  status?: ReactNode;
  errors?: ReactNode;
}

export function WordTemplateLibraryEditor({
  items,
  labels,
  canEdit,
  disabled,
  onAdd,
  onRemove,
  onRename,
  onStartRename,
  onSave,
  onCancel,
  saveDisabled,
  dirty,
  description,
  status,
  errors,
}: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [renamingKey, setRenamingKey] = useState<string | null>(null);
  const [pendingName, setPendingName] = useState("");
  const [initialName, setInitialName] = useState("");
  const editableCount = items.filter((item) => !item.readOnly).length;
  const finishRename = (index: number) => {
    onRename(index, pendingName.trim());
    setRenamingKey(null);
  };
  const cancelRename = (index: number) => {
    onRename(index, initialName);
    setRenamingKey(null);
  };

  return (
    <div className={styles.settingCard}>
      <div className={styles.sectionHeader}>
        <span className={styles.sectionTitle}>{labels.title}</span>
        <span className={styles.countBadge}>{items.length}</span>
      </div>
      {description && <p className={styles.description}>{description}</p>}
      {items.length ? (
        <ul className={styles.libraryList} aria-label={labels.title}>
          {items.map((item, index) => (
            <li className={`${styles.libraryRow} ${item.error ? styles.libraryRowInvalid : ""}`} key={item.key}>
              <Icon category="outlined" type="description" />
              <div className={styles.libraryName}>
                {renamingKey === item.key ? (
                  <TextInput
                    compact
                    size="xs"
                    value={pendingName}
                    disabled={disabled}
                    aria-label={labels.nameField}
                    onChange={(event) => {
                      setPendingName(event.target.value);
                      onRename(index, event.target.value);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        event.stopPropagation();
                        finishRename(index);
                      }
                      if (event.key === "Escape") {
                        event.preventDefault();
                        event.stopPropagation();
                        cancelRename(index);
                      }
                    }}
                  />
                ) : (
                  <span className={styles.libraryLabel} title={item.name}>
                    {item.name}
                  </span>
                )}
                {renamingKey !== item.key && item.detail && (
                  <span className={styles.libraryFile} title={item.detail}>
                    {item.detail}
                  </span>
                )}
                {item.error && <span className={styles.error}>{item.error}</span>}
              </div>
              {canEdit &&
                !item.readOnly &&
                (renamingKey === item.key ? (
                  <>
                    <IconButton
                      variant="icon"
                      size="small"
                      icon={{ category: "outlined", type: "check" }}
                      aria-label={labels.save}
                      disabled={disabled}
                      onClick={() => finishRename(index)}
                    />
                    <IconButton
                      variant="icon"
                      size="small"
                      icon={{ category: "outlined", type: "close" }}
                      aria-label={labels.cancel}
                      disabled={disabled}
                      onClick={() => cancelRename(index)}
                    />
                  </>
                ) : (
                  <>
                    <IconButton
                      variant="icon"
                      size="small"
                      icon={{ category: "outlined", type: "edit" }}
                      aria-label={labels.edit(item.name)}
                      disabled={disabled}
                      onClick={() => {
                        onStartRename?.();
                        setInitialName(item.name);
                        setPendingName(item.name);
                        setRenamingKey(item.key);
                      }}
                    />
                    <DeleteIconButton
                      size="small"
                      disabled={disabled}
                      aria-label={labels.remove(item.name)}
                      onClick={() => onRemove(index)}
                    />
                  </>
                ))}
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.description}>{labels.empty}</p>
      )}
      {canEdit && (
        <div className={styles.uploadRow}>
          <input
            ref={input}
            className={styles.fileInput}
            type="file"
            accept=".docx"
            multiple
            aria-label={labels.uploadAria}
            disabled={disabled || editableCount >= 8}
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
            disabled={disabled || editableCount >= 8}
            icon={{ category: "outlined", type: "upload" }}
            onClick={() => input.current?.click()}
          >
            {labels.upload}
          </Button>
          <span className={styles.description}>{labels.count}</span>
          {onSave && dirty && (
            <>
              <Button
                type="button"
                color="primary"
                variant="filled"
                size="small"
                disabled={disabled || saveDisabled}
                onClick={onSave}
              >
                {labels.save}
              </Button>
              <Button
                type="button"
                color="on-surface"
                variant="text"
                size="small"
                disabled={disabled}
                onClick={onCancel}
              >
                {labels.cancel}
              </Button>
            </>
          )}
        </div>
      )}
      {errors}
      {status}
      {canEdit && labels.editHint && <p className={styles.description}>{labels.editHint}</p>}
    </div>
  );
}
