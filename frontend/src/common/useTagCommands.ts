// Copyright Thales 2025
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

import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useConfirmationDialog } from "../components/ConfirmationDialogProvider";
import { useToast } from "../components/ToastProvider";
import {
  TagWithItemsId,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

type Refresher = {
  refetchTags?: () => Promise<any> | void;
  refetchResources?: () => Promise<any> | void;
  refetchDocs?: () => Promise<any> | void; // ← NEW (for documents view)
};

export function useTagCommands({ refetchTags, refetchResources, refetchDocs }: Refresher = {}) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();

  const [deleteTagMutation] = useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation();

  const refresh = useCallback(async () => {
    await Promise.all([refetchTags?.(), refetchResources?.(), refetchDocs?.()]);
  }, [refetchTags, refetchResources, refetchDocs]);

  /** Core action: delete a folder tag. Caller ensures it's empty. */
  const deleteFolder = useCallback(
    async (tag: TagWithItemsId) => {
      try {
        await deleteTagMutation({ tagId: tag.id }).unwrap();
        await refresh();
        showSuccess?.({
          summary: t("resourceLibrary.folderDeleteSuccess") || "Folder deleted",
          detail: t("resourceLibrary.folderDeleteDetail", { name: tag.name }) || "The folder was removed.",
        });
        // 💡 CRUCIAL CHANGE: Return a value or use a signal if needed
        return true;
      } catch (e: any) {
        showError?.({
          summary: t("validation.error") || "Error",
          detail: e?.data?.detail || e?.message || "Failed to delete folder.",
        });
        throw e;
      }
    },
    [deleteTagMutation, refresh, showSuccess, showError, t],
  );

  /** UI wrapper: confirm, then delete. */
  const confirmDeleteFolder = useCallback(
    (tag: TagWithItemsId, onSuccess?: () => void) => {
      showConfirmationDialog({
        title: t("documentLibrary.confirmDeleteFolderTitle") || "Delete folder?",
        message:
          t("documentLibrary.confirmDeleteFolderMessage", { name: tag.name }) ||
          `Delete the empty folder “${tag.name}”?`,
        onConfirm: () => {
          void deleteFolder(tag)
            .then(() => {
              // 👈 EXECUTE onSuccess CALLBACK AFTER successful deletion
              onSuccess?.();
            })
            .catch(() => {
              // Handle error case if needed, but usually the catch in deleteFolder handles the UI feedback (Toast)
            });
        },
      });
    },
    [showConfirmationDialog, deleteFolder, t],
  );

  return { deleteFolder, confirmDeleteFolder };
}
