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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { Portal } from "@shared/utils/Portal.tsx";
import { MAX_FOLDER_DEPTH, folderPathDepth } from "@shared/organisms/DocumentUploadDrawer/droppedPaths";
import styles from "./CreateFolderModal.module.css";

interface FolderNameDialogProps {
  open: boolean;
  onClose: () => void;
  parentPath?: string;
  onSubmit: (name: string) => Promise<void>;
  onCreated: () => void;
  maxDepth?: number | null;
  maxNameLength?: number;
  canSubmit?: boolean;
}

// Shared presentation for manager folders and legacy corpus/fs callers.
export default function FolderNameDialog({
  open,
  onClose,
  parentPath,
  onSubmit,
  onCreated,
  maxDepth = MAX_FOLDER_DEPTH,
  maxNameLength,
  canSubmit = true,
}: FolderNameDialogProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [isLoading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const pending = useRef(false);
  const active = useRef(false);
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    active.current = open;
    if (!open) return;
    setName("");
    setError(undefined);
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        if (!pending.current) close.current();
      } else if (e.key === "Tab") {
        const controls = [
          ...(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)") ?? []),
        ];
        const first = controls[0],
          last = controls[controls.length - 1];
        if (
          first &&
          (!dialog.current?.contains(document.activeElement) || document.activeElement === (e.shiftKey ? first : last))
        ) {
          e.preventDefault();
          (e.shiftKey ? last : first).focus();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      active.current = false;
      window.removeEventListener("keydown", handleKeyDown);
      if (opener?.isConnected) opener.focus();
    };
  }, [open]);

  if (!open) return null;

  const trimmed = name.trim();
  const parentLeaf = parentPath?.split("/").filter(Boolean).pop();

  const nameHasSlash = trimmed.includes("/") || trimmed.includes("\\");
  const tooDeep = maxDepth != null && folderPathDepth(parentPath) + 1 > maxDepth;
  const invalidName = maxNameLength != null && (Array.from(trimmed).length > maxNameLength || /\p{Cc}/u.test(trimmed));
  const blocked = !canSubmit || !trimmed || nameHasSlash || tooDeep || invalidName;
  const inlineError = tooDeep
    ? t("rework.resources.folderModal.tooDeep", { max: maxDepth })
    : nameHasSlash
      ? t("rework.resources.folderModal.nameNoSlash")
      : invalidName
        ? t("rework.resources.folderModal.invalidName", { max: maxNameLength })
        : error;
  const dismiss = () => {
    if (!pending.current) onClose();
  };
  const submit = async () => {
    if (blocked || pending.current) return;
    pending.current = true;
    setLoading(true);
    setError(undefined);
    try {
      await onSubmit(trimmed);
      if (active.current) {
        onCreated();
        onClose();
      }
    } catch (e: unknown) {
      if (active.current)
        setError(
          e instanceof Error
            ? e.message
            : ((e as { data?: { detail?: string } })?.data?.detail ?? t("rework.resources.folderModal.error")),
        );
    } finally {
      pending.current = false;
      if (active.current) setLoading(false);
    }
  };

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={dismiss}>
        <div
          className={styles.dialog}
          ref={dialog}
          aria-busy={isLoading}
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-folder-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.body}>
            <div className={styles.header}>
              <div>
                <p id="create-folder-title" className={styles.title}>
                  {t("rework.resources.folderModal.title")}
                </p>
                <p className={styles.context}>
                  {parentLeaf ? (
                    <>
                      {t("rework.resources.folderModal.inFolder")} <code className={styles.path}>{parentLeaf}</code> /
                    </>
                  ) : (
                    t("rework.resources.folderModal.atRoot")
                  )}
                </p>
              </div>
              <IconButton
                variant="icon"
                size="small"
                icon={{ category: "outlined", type: "close" }}
                aria-label={t("common.close")}
                onClick={dismiss}
                disabled={isLoading}
              />
            </div>

            <TextInput
              autoFocus
              readOnly={isLoading}
              aria-invalid={!!inlineError}
              aria-describedby={inlineError ? "folder-name-error" : undefined}
              label={t("rework.resources.folderModal.nameLabel")}
              placeholder={t("rework.resources.folderModal.namePlaceholder")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void submit();
              }}
            />
            {inlineError && (
              <p id="folder-name-error" className={styles.inlineError} role="alert">
                {inlineError}
              </p>
            )}
          </div>

          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="medium" onClick={dismiss} disabled={isLoading}>
              {t("rework.resources.folderModal.cancel")}
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={blocked || isLoading}
              onClick={() => void submit()}
            >
              {t("rework.resources.folderModal.create")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
