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

import { useTranslation } from "react-i18next";
import {
  ProcessDocumentsRequest,
  // useDeleteDocumentMutation,
  useLazyGetDocumentRawContentQuery,
  useProcessDocumentsMutation,
  useScheduleDocumentsMutation,
} from "../../slices/documentApi";
import { DocumentMetadata } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { downloadFile } from "../../utils/downloadUtils";
import { useToast } from "../ToastProvider";
import {
  //createBulkDeleteAction,
  createBulkDownloadAction,
  createBulkProcessSyncAction,
  createBulkScheduleAction,
  //createDeleteAction,
  createDownloadAction,
  createPreviewAction,
  createProcessAction,
  createScheduleAction,
} from "./DocumentActions";
import { useDocumentViewer } from "./useDocumentViewer";

export const useDocumentActions = (onRefreshData?: () => void) => {
  const { t } = useTranslation();
  const { showInfo, showError } = useToast();
  const { openDocument } = useDocumentViewer();
  console.log("useDocumentActions with to review", onRefreshData)
  // API hooks
  // const [deleteDocument] = useDeleteDocumentMutation();
  const [triggerDownload] = useLazyGetDocumentRawContentQuery();
  const [processDocuments] = useProcessDocumentsMutation();
  const [scheduleDocuments] = useScheduleDocumentsMutation();

  // const handleDelete = async (file: DocumentMetadata) => {
  //   try {
  //     await deleteDocument(file.document_uid).unwrap();
  //     showInfo({
  //       summary: "Delete Success",
  //       detail: `${file.document_name} deleted`,
  //       duration: 3000,
  //     });
  //     onRefreshData?.();
  //   } catch (error) {
  //     showError({
  //       summary: "Delete Failed",
  //       detail: `Could not delete document: ${error?.data?.detail || error.message}`,
  //     });
  //     throw error;
  //   }
  // };

  // const handleBulkDelete = async (files: DocumentMetadata[]) => {
  //   let successCount = 0;
  //   let failedFiles: string[] = [];

  //   for (const file of files) {
  //     try {
  //       await deleteDocument(file.document_uid).unwrap();
  //       successCount++;
  //     } catch (error) {
  //       failedFiles.push(file.document_name);
  //     }
  //   }

  //   if (successCount > 0) {
  //     showInfo({
  //       summary: "Delete Success",
  //       detail: `${successCount} document${successCount > 1 ? "s" : ""} deleted`,
  //       duration: 3000,
  //     });
  //   }

  //   if (failedFiles.length > 0) {
  //     showError({
  //       summary: "Delete Failed",
  //       detail: `Failed to delete: ${failedFiles.join(", ")}`,
  //     });
  //   }

  //   onRefreshData?.();
  // };

  const handleDownload = async (file: DocumentMetadata) => {
    try {
      const { data: blob } = await triggerDownload({ document_uid: file.document_uid });
      if (blob) {
        downloadFile(blob, file.document_name || "document");
      }
    } catch (err) {
      showError({
        summary: "Download failed",
        detail: `Could not download document: ${err?.data?.detail || err.message}`,
      });
    }
  };

  const handleBulkDownload = async (files: DocumentMetadata[]) => {
    for (const file of files) {
      await handleDownload(file);
    }
  };

  const handleDocumentPreview = async (file: DocumentMetadata) => {
    openDocument({
      document_uid: file.document_uid,
      file_name: file.document_name,
    });
  };

  const handleSchedule = async (files: DocumentMetadata[]) => {
    try {
      const payload: ProcessDocumentsRequest = {
        files: files.map((f) => {
          const isPull = f.source_type === "pull";
          return {
            source_tag: f.source_tag,
            document_uid: isPull ? undefined : f.document_uid,
            external_path: isPull ? (f.pull_location ?? undefined) : undefined,
            tags: f.tags || [],
            display_name: f.document_name,
          };
        }),
        pipeline_name: "manual_ui_async",
      };

      const result = await scheduleDocuments(payload).unwrap();

      showInfo({
        summary: "Processing started",
        detail: `Workflow ${result.workflow_id} submitted`,
      });
    } catch (error) {
      showError({
        summary: "Processing Failed",
        detail: error?.data?.detail || error.message,
      });
    }
  };
  const handleProcess = async (files: DocumentMetadata[]) => {
    try {
      const payload: ProcessDocumentsRequest = {
        files: files.map((f) => {
          const isPull = f.source_type === "pull";
          return {
            source_tag: f.source_tag,
            document_uid: isPull ? undefined : f.document_uid,
            external_path: isPull ? (f.pull_location ?? undefined) : undefined,
            tags: f.tags || [],
            display_name: f.document_name,
          };
        }),
        pipeline_name: "manual_ui_async",
      };

      const result = await processDocuments(payload).unwrap();

      showInfo({
        summary: "Processing started",
        detail: `Workflow ${result.workflow_id} submitted`,
      });
    } catch (error) {
      showError({
        summary: "Processing Failed",
        detail: error?.data?.detail || error.message,
      });
    }
  };

  // Create default actions
  const defaultRowActions = [
    createPreviewAction(handleDocumentPreview, t),
    createDownloadAction(handleDownload, t),
    //createDeleteAction(handleDelete, t),
    createProcessAction((file) => handleProcess([file]), t),
    createScheduleAction((file) => handleSchedule([file]), t),
  ];

  const defaultBulkActions = [
    //createBulkDeleteAction(handleBulkDelete, t),
    createBulkDownloadAction(handleBulkDownload, t),
    createBulkProcessSyncAction((files) => handleProcess(files), t),
    createBulkScheduleAction((file) => handleSchedule(file), t), // Optional if your library supports bulk createScheduleAction
  ];

  return {
    // Individual handlers
    //handleDelete,
    //handleBulkDelete,
    handleDownload,
    handleBulkDownload,
    handleDocumentPreview,
    handleProcess,

    // Pre-built action arrays
    defaultRowActions,
    defaultBulkActions,
  };
};
