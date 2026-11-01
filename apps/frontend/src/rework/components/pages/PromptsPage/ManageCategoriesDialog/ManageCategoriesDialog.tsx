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
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { PromptCategory } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useDeletePromptCategoryMutation,
  useCreatePromptCategoryMutation,
  useRenamePromptCategoryMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { agentErrorText } from "../../TeamAgentsPage/weaverAgents";
import styles from "./ManageCategoriesDialog.module.scss";

interface ManageCategoriesDialogProps {
  open: boolean;
  spaceId: string;
  categories: PromptCategory[];
  /** Category ids currently referenced by at least one prompt in the space —
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

export default function ManageCategoriesDialog({
  open,
  spaceId,
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

  const [createCategory] = useCreatePromptCategoryMutation();
  const [updateCategory] = useRenamePromptCategoryMutation();
  const [deleteCategory] = useDeletePromptCategoryMutation();

  const wasOpen = useRef(false);
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);

  // Fresh draft from the latest server state every time the dialog opens —
  // never leaks the previous run's uncommitted edits into a new session.
  useEffect(() => {
    if (open && !wasOpen.current) {
      setDrafts(categories.map((c) => ({ key: c.id, id: c.id, name: c.name, originalName: c.name })));
      setDeletedIds(new Set());
      setNewName("");
      setEditingKey(null);
      setEditingName("");
    }
    wasOpen.current = open;
  }, [open, categories]);

  const cancel = () => {
    if (!isSaving) onClose();
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
    if (isSaving || editingKey) return;
    setIsSaving(true);
    let failed = false;
    // Deletions free names before renames/creates. Successful writes are removed
    // from the draft, so a partial failure can be retried without replaying them.
    const apply = async (operation: () => Promise<void>, errorKey: string) => {
      try {
        await operation();
      } catch (error) {
        failed = true;
        const code = (error as { data?: { code?: string } })?.data?.code;
        const detail =
          code === "prompt_category_name_conflict"
            ? t("rework.promptCategories.nameConflict")
            : code === "prompt_category_conflict"
              ? t("rework.promptCategories.categoryConflict")
              : agentErrorText(error, t);
        if (live.current) showError({ summary: t(errorKey), detail });
      }
    };
    for (const id of deletedIds) {
      if (!live.current) break;
      await apply(async () => {
        await deleteCategory({ spaceId, categoryId: id }).unwrap();
        setDeletedIds((ids) => new Set([...ids].filter((value) => value !== id)));
      }, "rework.promptCategories.manage.deleteError");
    }
    for (const draft of drafts) {
      if (!live.current) break;
      const name = draft.name.trim();
      if (!name || (draft.id && name === draft.originalName)) continue;
      await apply(
        async () => {
          const saved = await (
            draft.id
              ? updateCategory({ spaceId, categoryId: draft.id, promptCategoryRequest: { name } })
              : createCategory({ spaceId, promptCategoryRequest: { name } })
          ).unwrap();
          setDrafts((rows) =>
            rows.map((row) =>
              row.key === draft.key ? { ...row, id: saved.id, name: saved.name, originalName: saved.name } : row,
            ),
          );
        },
        draft.id ? "rework.promptCategories.manage.renameError" : "rework.promptCategories.manage.createError",
      );
    }
    if (!live.current) return;
    setIsSaving(false);
    onChanged();
    if (!failed) onClose();
  };

  return (
    <FullPageModal isOpen={open} onClose={cancel} id="manage-prompt-categories-modal" background="container">
      <div className={styles.card}>
        <div className={styles.header}>
          <span className={styles.title}>{t("rework.promptCategories.manage.title")}</span>
        </div>

        <div className={styles.createRow}>
          <TextInput
            disabled={isSaving}
            compact
            size="small"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t("rework.promptCategories.manage.createPlaceholder")}
            maxLength={120}
            onKeyDown={(e) => e.key === "Enter" && handleAddDraft()}
          />
          <Button
            color="primary"
            variant="filled"
            size="medium"
            disabled={isSaving || !newName.trim()}
            onClick={handleAddDraft}
          >
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
                      disabled={isSaving}
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
                    <span className={styles.name} title={draft.name}>
                      {draft.name}
                    </span>
                  )}
                  <div className={styles.actions}>
                    {isEditing ? (
                      <>
                        <Tooltip text={t("rework.promptCategories.manage.saveAria")}>
                          <IconButton
                            size="small"
                            color="primary"
                            variant="filled"
                            icon={{ category: "outlined", type: "check" }}
                            disabled={isSaving || !editingName.trim()}
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
                            disabled={isSaving}
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
                            disabled={isSaving}
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
                            disabled={isSaving || isInUse}
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
          <Button
            color="primary"
            variant="filled"
            size="medium"
            disabled={isSaving || editingKey !== null}
            onClick={handleSave}
          >
            {t("rework.save")}
          </Button>
        </div>
      </div>
    </FullPageModal>
  );
}
