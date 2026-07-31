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

import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type PromptCategorySummary,
  useDeleteTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdDeleteMutation,
  usePostTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesPostMutation,
  usePutTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdPutMutation,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ManageCategoriesDialog.module.scss";

interface ManageCategoriesDialogProps {
  open: boolean;
  teamId: string;
  categories: PromptCategorySummary[];
  /** Category ids currently referenced by at least one prompt in the team —
   *  their delete action is disabled (matches the backend's 409 rule, but
   *  pre-empts the round trip). */
  usedCategoryIds: Set<string>;
  onClose: () => void;
  onChanged: () => void;
}

/** One row of the locally-edited draft list. `id === null` means "not yet
 * created on the backend" — Save decides create/rename/delete purely from
 * comparing this draft state back to the `categories` prop it was seeded from. */
interface DraftCategory {
  key: string;
  id: string | null;
  name: string;
  originalName: string;
}

function apiErrorDetail(error: unknown): string | undefined {
  return (error as { data?: { detail?: string }; message?: string } | undefined)?.data?.detail;
}

export default function ManageCategoriesDialog({
  open,
  teamId,
  categories,
  usedCategoryIds,
  onClose,
  onChanged,
}: ManageCategoriesDialogProps) {
  const { t } = useTranslation();
  const { showError } = useToast();

  const [newName, setNewName] = useState("");
  const [drafts, setDrafts] = useState<DraftCategory[]>([]);
  const [deletedIds, setDeletedIds] = useState<Set<string>>(new Set());
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const [createCategory] = usePostTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesPostMutation();
  const [updateCategory] = usePutTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdPutMutation();
  const [deleteCategory] =
    useDeleteTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdDeleteMutation();

  // Fresh draft from the latest server state every time the dialog opens —
  // never leaks the previous run's uncommitted edits into a new session.
  useEffect(() => {
    if (open) {
      setDrafts(categories.map((c) => ({ key: c.id, id: c.id, name: c.name, originalName: c.name })));
      setDeletedIds(new Set());
      setNewName("");
      setEditingKey(null);
      setEditingName("");
    }
  }, [open, categories]);

  const cancel = () => {
    onClose();
  };

  const handleAddDraft = () => {
    const name = newName.trim();
    if (!name) return;
    setDrafts((prev) => [...prev, { key: crypto.randomUUID(), id: null, name, originalName: "" }]);
    setNewName("");
  };

  const startEdit = (draft: DraftCategory) => {
    setEditingKey(draft.key);
    setEditingName(draft.name);
  };

  const cancelEdit = () => {
    setEditingKey(null);
    setEditingName("");
  };

  const commitEdit = () => {
    const name = editingName.trim();
    if (!editingKey || !name) return;
    setDrafts((prev) => prev.map((d) => (d.key === editingKey ? { ...d, name } : d)));
    cancelEdit();
  };

  const removeDraft = (draft: DraftCategory) => {
    if (draft.id) {
      setDeletedIds((prev) => new Set(prev).add(draft.id!));
    }
    setDrafts((prev) => prev.filter((d) => d.key !== draft.key));
    if (editingKey === draft.key) cancelEdit();
  };

  const handleSave = async () => {
    setIsSaving(true);

    const operations: Promise<unknown>[] = [];

    for (const id of deletedIds) {
      operations.push(
        deleteCategory({ teamId, categoryId: id })
          .unwrap()
          .catch((error: unknown) => {
            showError({
              summary: t("rework.promptCategories.manage.deleteError"),
              detail: apiErrorDetail(error) ?? t("rework.promptCategories.manage.genericError"),
            });
            throw error;
          }),
      );
    }
    for (const draft of drafts) {
      const name = draft.name.trim();
      if (!name) continue;
      if (draft.id) {
        if (name !== draft.originalName) {
          operations.push(
            updateCategory({ teamId, categoryId: draft.id, updatePromptCategoryRequest: { name } })
              .unwrap()
              .catch((error: unknown) => {
                showError({
                  summary: t("rework.promptCategories.manage.renameError"),
                  detail: apiErrorDetail(error) ?? t("rework.promptCategories.manage.genericError"),
                });
                throw error;
              }),
          );
        }
      } else {
        operations.push(
          createCategory({ teamId, createPromptCategoryRequest: { name } })
            .unwrap()
            .catch((error: unknown) => {
              showError({
                summary: t("rework.promptCategories.manage.createError"),
                detail: apiErrorDetail(error) ?? t("rework.promptCategories.manage.genericError"),
              });
              throw error;
            }),
        );
      }
    }

    const results = await Promise.allSettled(operations);
    setIsSaving(false);
    onChanged();
    // Only close on a fully clean save — a partial failure leaves the dialog
    // open, already-committed rows shown by their next `onChanged()` refetch,
    // so the user can see what still needs fixing and retry just that.
    if (results.every((r) => r.status === "fulfilled")) {
      onClose();
    }
  };

  return (
    <FullPageModal isOpen={open} onClose={cancel} id="manage-prompt-categories-modal" background="container">
      <div className={styles.card}>
        <div className={styles.header}>
          <span className={styles.title}>{t("rework.promptCategories.manage.title")}</span>
        </div>

        <div className={styles.createRow}>
          <TextInput
            compact
            size="small"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t("rework.promptCategories.manage.createPlaceholder")}
            maxLength={120}
            onKeyDown={(e) => e.key === "Enter" && handleAddDraft()}
          />
          <Button color="primary" variant="filled" size="medium" disabled={!newName.trim()} onClick={handleAddDraft}>
            {t("rework.promptCategories.manage.create")}
          </Button>
        </div>

        {drafts.length === 0 ? (
          <div className={styles.empty}>{t("rework.promptCategories.manage.empty")}</div>
        ) : (
          <ul className={styles.list}>
            {drafts.map((draft) => {
              const isEditing = editingKey === draft.key;
              const isInUse = !!draft.id && usedCategoryIds.has(draft.id);
              return (
                <li key={draft.key} className={styles.row}>
                  {isEditing ? (
                    <TextInput
                      compact
                      size="small"
                      value={editingName}
                      autoFocus
                      onChange={(e) => setEditingName(e.target.value)}
                      maxLength={120}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitEdit();
                        if (e.key === "Escape") cancelEdit();
                      }}
                    />
                  ) : (
                    <span className={styles.name}>{draft.name}</span>
                  )}
                  <div className={styles.actions}>
                    {isEditing ? (
                      <>
                        <Tooltip text={t("rework.promptCategories.manage.saveAria")}>
                          <IconButton
                            size="small"
                            color="primary"
                            variant="icon"
                            icon={{ category: "outlined", type: "check" }}
                            disabled={!editingName.trim()}
                            aria-label={t("rework.promptCategories.manage.saveAria")}
                            onClick={commitEdit}
                          />
                        </Tooltip>
                        <Tooltip text={t("rework.promptCategories.manage.cancelEditAria")}>
                          <IconButton
                            size="small"
                            color="on-surface-retreat"
                            variant="icon"
                            icon={{ category: "outlined", type: "close" }}
                            aria-label={t("rework.promptCategories.manage.cancelEditAria")}
                            onClick={cancelEdit}
                          />
                        </Tooltip>
                      </>
                    ) : (
                      <>
                        <Tooltip text={t("rework.promptCategories.manage.editAria", { name: draft.name })}>
                          <IconButton
                            size="small"
                            color="on-surface-retreat"
                            variant="icon"
                            icon={{ category: "outlined", type: "edit" }}
                            aria-label={t("rework.promptCategories.manage.editAria", { name: draft.name })}
                            onClick={() => startEdit(draft)}
                          />
                        </Tooltip>
                        <Tooltip
                          text={
                            isInUse
                              ? t("rework.promptCategories.manage.deleteBlocked")
                              : t("rework.promptCategories.manage.deleteAria", { name: draft.name })
                          }
                        >
                          <IconButton
                            size="small"
                            color="error"
                            variant="icon"
                            icon={{ category: "outlined", type: "delete" }}
                            disabled={isInUse}
                            aria-label={t("rework.promptCategories.manage.deleteAria", { name: draft.name })}
                            onClick={() => removeDraft(draft)}
                          />
                        </Tooltip>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <div className={styles.footer}>
          <Button color="on-surface" variant="text" size="medium" disabled={isSaving} onClick={cancel}>
            {t("rework.cancel")}
          </Button>
          <Button color="primary" variant="filled" size="medium" disabled={isSaving} onClick={handleSave}>
            {t("rework.save")}
          </Button>
        </div>
      </div>
    </FullPageModal>
  );
}
