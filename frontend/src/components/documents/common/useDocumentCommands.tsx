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
import { useMarkdownDocumentViewer } from "../../../common/useMarkdownDocumentViewer";
import { downloadFile } from "../../../utils/downloadUtils";
import { useLazyDownloadRawContentBlobQuery } from "../../../slices/knowledgeFlow/knowledgeFlowApi.blob";
import { usePdfDocumentViewer } from "../../../common/usePdfDocumentViewer";

type DocumentRefreshers = {
  refetchTags?: () => Promise<any>;
  refetchDocs?: () => Promise<any>;
};

export function useDocumentCommands({ refetchTags, refetchDocs }: DocumentRefreshers = {}) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const [] = useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery();

  const [updateTag] = useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation();
  const [updateRetrievable] =
    useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation();
  const [fetchAllDocuments] = useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation();
  const { openMarkdownDocument } = useMarkdownDocumentViewer();
  const { openPdfDocument } = usePdfDocumentViewer();
  const [triggerDownloadBlob] = useLazyDownloadRawContentBlobQuery();
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
        const status = e?.status ?? e?.originalStatus ?? e?.data?.status_code;
        // If the tag or document no longer exists, treat it as a no-op to keep
        // bulk operations resilient (e.g. when the backend has already cleaned up).
        if (status === 404) {
          console.warn("[useDocumentCommands] removeFromLibrary: 404 Not Found, ignoring", e);
          return;
        }
        const isForbidden = status === 403;

        showError?.({
          summary:
            (isForbidden && (t("documentLibrary.removeForbiddenSummary") || "Not allowed")) ||
            t("validation.error") ||
            "Error",
          detail:
            (isForbidden &&
              (t("documentLibrary.removeForbiddenDetail", { folder: tag.name }) ||
                "You do not have permission to remove items from this library.")) ||
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
        await refresh?.();
        showSuccess?.({
          summary: t("documentLibrary.removeSuccess") || "Removed",
          detail:
            docs.length === 1
              ? t("documentLibrary.removedOneDocument") || "Document removed from the library."
              : t("documentLibrary.removedManyDocuments", { count: docs.length }) ||
                `${docs.length} documents removed from the library.`,
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
  const preview = useCallback(
    (doc: DocumentMetadata) => {
      const name = doc.identity.title || doc.identity.document_name || doc.identity.document_uid;

      openMarkdownDocument({
        document_uid: doc.identity.document_uid,
        file_name: name,
      });
    },
    [openMarkdownDocument],
  );
  const previewPdf = useCallback(
    (doc: DocumentMetadata) => {
      const name = doc.identity.title || doc.identity.document_name || doc.identity.document_uid;

      openPdfDocument({
        document_uid: doc.identity.document_uid,
        file_name: name,
      });
    },
    [openPdfDocument],
  );
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
  return { toggleRetrievable, removeFromLibrary, bulkRemoveFromLibraryForTag, preview, previewPdf, refresh, download };
}
