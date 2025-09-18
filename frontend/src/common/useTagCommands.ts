// components/prompts/useTagCommands.ts
// Copyright Thales 2025

import { useCallback } from "react";
import {
  TagWithItemsId,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../components/ToastProvider";
import { useTranslation } from "react-i18next";
import { useConfirmationDialog } from "../components/ConfirmationDialogProvider";

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
          detail:
            t("resourceLibrary.folderDeleteDetail", { name: tag.name }) ||
            "The folder was removed.",
        });
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
    (tag: TagWithItemsId) => {
      showConfirmationDialog({
        title: t("documentLibrary.confirmDeleteFolderTitle") || "Delete folder?",
        message:
          t("documentLibrary.confirmDeleteFolderMessage", { name: tag.name }) ||
          `Delete the empty folder “${tag.name}”?`,
        onConfirm: () => {
          void deleteFolder(tag);
        },
      });
    },
    [showConfirmationDialog, deleteFolder, t],
  );

  return { deleteFolder, confirmDeleteFolder };
}
