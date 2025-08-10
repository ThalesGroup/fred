import { useCallback } from "react";
import {
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
  useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation,
  TagWithItemsId,
  DocumentMetadata,
  useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useUpdateDocumentRetrievableMutation } from "../../../slices/documentApi";
import { useToast } from "../../ToastProvider";
import { useTranslation } from "react-i18next";

type Refreshers = {
  refetchTags?: () => Promise<any>;
  refetchDocs?: () => Promise<any>;
};

export function useDocumentCommands({ refetchTags, refetchDocs }: Refreshers = {}) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const [] = useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery();

  const [updateTag] = useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation();
  const [updateRetrievable] = useUpdateDocumentRetrievableMutation();
  const [fetchAllDocuments] = useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation();

  const refresh = useCallback(async () => {
    await Promise.all([refetchTags?.(), refetchDocs ? refetchDocs() : fetchAllDocuments({ filters: {} })]);
  }, [refetchTags, refetchDocs, fetchAllDocuments]);

  const toggleRetrievable = useCallback(
    async (doc: DocumentMetadata) => {
      try {
        await updateRetrievable({
          document_uid: doc.document_uid,
          retrievable: !doc.retrievable,
        }).unwrap();
        await refresh();
        showSuccess?.({
          summary: t("common.updated") || "Updated",
          detail: !doc.retrievable
            ? t("documentTable.nowSearchable") || "Document is now searchable."
            : t("documentTable.nowExcluded") || "Document is now excluded from search.",
        });
      } catch (e: any) {
        showError?.({
          summary: t("common.error") || "Error",
          detail: e?.data?.detail || e?.message || "Failed to update retrievable flag.",
        });
      }
    },
    [updateRetrievable, refresh, showSuccess, showError, t],
  );

  const removeFromLibrary = useCallback(
    async (doc: DocumentMetadata, tag: TagWithItemsId) => {
      try {
        const newItemIds = (tag.item_ids || []).filter((id) => id !== doc.document_uid);
        await updateTag({
          tagId: tag.id,
          tagUpdate: {
            name: tag.name,
            description: tag.description,
            type: tag.type,
            item_ids: newItemIds,
          },
        }).unwrap();
        await refresh?.();
        showSuccess?.({
          summary: t("documentLibrary.removeSuccess") || "Removed",
          detail: t("documentLibrary.removedOneDocument") || "Document removed from the library.",
        });
      } catch (e: any) {
        showError?.({
          summary: t("common.error") || "Error",
          detail: e?.data?.detail || e?.message || "Failed to remove from library.",
        });
      }
    },
    [updateTag, refresh, showSuccess, showError, t],
  );
  // Keep preview as a “protocol”: the hook exposes an intent; the app decides how to show it.
  const preview = useCallback((doc: DocumentMetadata) => {
    // no-op default; consumers can replace with a drawer/modal or navigate
    console.debug("preview(doc)", doc);
  }, []);

  return { toggleRetrievable, removeFromLibrary, preview, refresh };
}
