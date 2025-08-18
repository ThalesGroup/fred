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
import {
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
  useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation,
  TagWithItemsId,
  DocumentMetadata,
  useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../../ToastProvider";
import { useTranslation } from "react-i18next";

type DocumentRefreshers = {
  refetchTags?: () => Promise<any>;
  refetchDocs?: () => Promise<any>;
};

export function useDocumentCommands({ refetchTags, refetchDocs }: DocumentRefreshers = {}) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const [] = useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery();

  const [updateTag] = useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation();
  const [updateRetrievable] = useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation();
  const [fetchAllDocuments] = useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation();

  const refresh = useCallback(async () => {
    await Promise.all([refetchTags?.(), refetchDocs ? refetchDocs() : fetchAllDocuments({ filters: {} })]);
  }, [refetchTags, refetchDocs, fetchAllDocuments]);

  const toggleRetrievable = useCallback(
    async (doc: DocumentMetadata) => {
      try {
        await updateRetrievable({
          documentUid: doc.identity.document_uid,
          retrievable: !doc.source.retrievable,
        }).unwrap();
        await refresh();
        showSuccess?.({
          summary: t("validation.updated") || "Updated",
          detail: !doc.source.retrievable
            ? t("documentTable.nowSearchable") || "Document is now searchable."
            : t("documentTable.nowExcluded") || "Document is now excluded from search.",
        });
      } catch (e: any) {
        showError?.({
          summary: t("validation.error") || "Error",
          detail: e?.data?.detail || e?.message || "Failed to update retrievable flag.",
        });
      }
    },
    [updateRetrievable, refresh, showSuccess, showError, t],
  );

  const removeFromLibrary = useCallback(
    async (doc: DocumentMetadata, tag: TagWithItemsId) => {
      try {
        const newItemIds = (tag.item_ids || []).filter((id) => id !== doc.identity.document_uid);
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
          summary: t("validation.error") || "Error",
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

