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

import { useCallback, useState } from "react";
import {
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
  useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation,
  TagWithItemsId,
  DocumentMetadata,
  useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useTranslation } from "react-i18next";
import { downloadFile } from "../../../utils/downloadUtils";
import { useLazyDownloadRawContentBlobQuery } from "../../../slices/knowledgeFlow/knowledgeFlowApi.blob";

type DocumentRefreshers = {
  refetchTags?: () => Promise<any>;
  refetchDocs?: (tagId?: string) => Promise<any>;
};

export interface DocumentPreviewTarget {
  documentUid: string;
  fileName?: string;
}

export function useDocumentCommands({ refetchTags, refetchDocs }: DocumentRefreshers = {}) {
  const { t } = useTranslation();
  const { showSuccess, showError, showInfo } = useToast();
  const [] = useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery();

  const [updateTag] = useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation();
  const [updateRetrievable] =
    useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation();
  const [fetchAllDocuments] = useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation();
  const [triggerDownloadBlob] = useLazyDownloadRawContentBlobQuery();
  const [previewTarget, setPreviewTarget] = useState<DocumentPreviewTarget | null>(null);
  const refresh = useCallback(
    async (tagId?: string) => {
      await Promise.all([refetchTags?.(), refetchDocs ? refetchDocs(tagId) : fetchAllDocuments({ filters: {} })]);
    },
    [refetchTags, refetchDocs, fetchAllDocuments],
  );

  const toggleRetrievable = useCallback(
    async (doc: DocumentMetadata) => {
      try {
        await updateRetrievable({
          documentUid: doc.identity.document_uid,
          retrievable: !doc.source.retrievable,
        }).unwrap();
        await refresh();
        showSuccess?.({
          summary: t("validation.updated"),
          detail: !doc.source.retrievable ? t("documentTable.nowSearchable") : t("documentTable.nowExcluded"),
        });
      } catch (e: any) {
        showError?.({
          summary: t("validation.error"),
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
        await refresh(tag.id);
        showSuccess?.({
          summary: t("documentLibrary.removeSuccess"),
          detail: t("documentLibrary.removedOneDocument"),
        });
      } catch (e: any) {
        const status = e?.status ?? e?.originalStatus ?? e?.data?.status_code;
        // If the tag or document no longer exists, treat it as a no-op to keep
        // bulk operations resilient (e.g. when the backend has already cleaned up).
        if (status === 404) {
          console.warn("[useDocumentCommands] removeFromLibrary: 404 Not Found, ignoring", e);
          return;
        }
        const isForbidden = status === 403;

        showError?.({
          summary: (isForbidden && t("documentLibrary.removeForbiddenSummary")) || t("validation.error"),
          detail:
            (isForbidden && t("documentLibrary.removeForbiddenDetail", { folder: tag.name })) ||
            e?.data?.detail ||
            e?.message ||
            "Failed to remove from library.",
        });
      }
    },
    [updateTag, refresh, showSuccess, showError, t],
  );

  const bulkRemoveFromLibraryForTag = useCallback(
    async (docs: DocumentMetadata[], tag: TagWithItemsId) => {
      if (!docs.length) return;
      try {
        const idsToRemove = new Set(docs.map((d) => d.identity.document_uid));
        const newItemIds = (tag.item_ids || []).filter((id) => !idsToRemove.has(id));
        await updateTag({
          tagId: tag.id,
          tagUpdate: {
            name: tag.name,
            description: tag.description,
            type: tag.type,
            item_ids: newItemIds,
          },
        }).unwrap();
        await refresh(tag.id);
        showSuccess?.({
          summary: t("documentLibrary.removeSuccess"),
          detail:
            docs.length === 1
              ? t("documentLibrary.removedOneDocument")
              : t("documentLibrary.removedManyDocuments", { count: docs.length }),
        });
      } catch (e: any) {
        showError?.({
          summary: t("validation.error"),
          detail: e?.data?.detail || e?.message || "Failed to remove from library.",
        });
      }
    },
    [updateTag, refresh, showSuccess, showError, t],
  );
  const preview = useCallback(
    (doc: DocumentMetadata) => {
      const previewReady = doc.processing?.stages?.preview === "done";

      if (!previewReady) {
        showInfo?.({
          summary: t("documentLibrary.previewNotReadySummary"),
          detail: t("documentLibrary.previewNotReadyDetail"),
        });
        return;
      }

      // fileName carries the real extension (identity.document_name), not the
      // display title — DocumentViewer needs it to pick the PDF vs. markdown
      // render strategy (FRONT-13).
      setPreviewTarget({
        documentUid: doc.identity.document_uid,
        fileName: doc.identity.document_name,
      });
    },
    [showInfo, t],
  );
  const closePreview = useCallback(() => setPreviewTarget(null), []);
  const download = useCallback(
    async (doc: DocumentMetadata) => {
      try {
        console.log("Downloading document:", doc.identity.document_name);
        // IMPORTANT: unwrap to get the Blob
        const blob = await triggerDownloadBlob({
          documentUid: doc.identity.document_uid,
        }).unwrap();

        console.log("Blob received?", blob instanceof Blob, blob.type, blob.size);

        downloadFile(blob, doc.identity.document_name || doc.identity.document_uid);
      } catch (err: any) {
        showError({
          summary: "Download failed",
          detail: `Could not download document: ${err?.data?.detail || err.message}`,
        });
        throw err;
      }
    },
    [triggerDownloadBlob, showError],
  );
  return {
    toggleRetrievable,
    removeFromLibrary,
    bulkRemoveFromLibraryForTag,
    preview,
    previewTarget,
    closePreview,
    refresh,
    download,
  };
}
