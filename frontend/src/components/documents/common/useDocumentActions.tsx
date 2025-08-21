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
  useProcessDocumentsMutation,
  useScheduleDocumentsMutation,
} from "../../../slices/documentApi";
import { DocumentMetadata } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../../ToastProvider";
import {
  createBulkProcessSyncAction,
  createBulkScheduleAction,
  createProcessAction,
  createScheduleAction,
} from "../operations/DocumentOperationsActions";

export const useDocumentActions = (onRefreshData?: () => void) => {
  const { t } = useTranslation();
  const { showInfo, showError } = useToast();
  console.log("useDocumentActions with to review", onRefreshData)
  // API hooks
  // const [deleteDocument] = useDeleteDocumentMutation();
  const [processDocuments] = useProcessDocumentsMutation();
  const [scheduleDocuments] = useScheduleDocumentsMutation();

  const handleSchedule = async (files: DocumentMetadata[]) => {
    try {
      const payload: ProcessDocumentsRequest = {
        files: files.map((f) => {
          const isPull = f.source.source_type === "pull";
          return {
            source_tag: f.source.source_tag,
            document_uid: isPull ? undefined : f.identity.document_uid,
            external_path: isPull ? (f.source.pull_location ?? undefined) : undefined,
            tags: f.tags.tag_ids || [],
            display_name: f.identity.document_name,
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
          const isPull = f.source.source_type === "pull";
          return {
            source_tag: f.source.source_tag,
            document_uid: isPull ? undefined : f.identity.document_uid,
            external_path: isPull ? (f.source.pull_location ?? undefined) : undefined,
            tags: f.tags.tag_ids || [],
            display_name: f.identity.document_name,
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
    createProcessAction((file) => handleProcess([file]), t),
    createScheduleAction((file) => handleSchedule([file]), t),
  ];

  const defaultBulkActions = [
    createBulkProcessSyncAction((files) => handleProcess(files), t),
    createBulkScheduleAction((file) => handleSchedule(file), t), // Optional if your library supports bulk createScheduleAction
  ];

  return {
    defaultRowActions,
    defaultBulkActions,
  };
};
