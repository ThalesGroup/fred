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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { Portal } from "@shared/utils/Portal.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useCreateTagKnowledgeFlowV1TagsPostMutation } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import styles from "./CreateFolderModal.module.css";

interface CreateFolderModalProps {
  open: boolean;
  onClose: () => void;
  /** Parent folder full path, e.g. "CIR" or "CIR/Sub". `undefined` => top level. */
  parentPath?: string;
  /** Team id for a collaborative team; omit/undefined for the personal space. */
  teamId?: string;
  onCreated: () => void;
}

/**
 * Small centred modal for the single "folder name" field. Replaces the old MUI
 * `LibraryCreateDrawer`. The header makes the destination explicit ("In CIR /"
 * or "At the top level") so top-level vs subfolder is never ambiguous.
 */
export default function CreateFolderModal({ open, onClose, parentPath, teamId, onCreated }: CreateFolderModalProps) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [createTag, { isLoading }] = useCreateTagKnowledgeFlowV1TagsPostMutation();
  const [name, setName] = useState("");

  // Reset the field each time the modal opens (it mounts fresh, so the input's
  // autoFocus handles focus).
  useEffect(() => {
    if (open) setName("");
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const trimmed = name.trim();
  const parentLeaf = parentPath?.split("/").filter(Boolean).pop();

  const submit = async () => {
    if (!trimmed || isLoading) return;
    try {
      await createTag({
        tagCreate: {
          name: trimmed,
          path: parentPath ?? null,
          type: "document",
          team_id: teamId ?? null,
        },
      }).unwrap();
      onCreated();
      onClose();
    } catch (e: unknown) {
      showError?.({
        summary: t("validation.error"),
        detail: (e as { data?: { detail?: string } })?.data?.detail ?? t("rework.resources.folderModal.error"),
      });
    }
  };

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onClose}>
        <div
          className={styles.dialog}
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
                color="on-surface"
                variant="icon"
                size="xs"
                icon={{ category: "outlined", type: "close" }}
                aria-label={t("common.close")}
                onClick={onClose}
              />
            </div>

            <TextInput
              autoFocus
              label={t("rework.resources.folderModal.nameLabel")}
              placeholder={t("rework.resources.folderModal.namePlaceholder")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void submit();
              }}
            />
          </div>

          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="medium" onClick={onClose}>
              {t("rework.resources.folderModal.cancel")}
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={!trimmed || isLoading}
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
