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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  DocumentMetadata,
  ProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostApiArg,
  ProcessDocumentsProgressKnowledgeFlowV1ProcessDocumentsProgressPostApiArg,
  ProcessDocumentsRequest,
  ProcessDocumentsProgressRequest,
  ProcessDocumentsProgressResponse,
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation,
  useProcessDocumentsProgressKnowledgeFlowV1ProcessDocumentsProgressPostMutation,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../../ToastProvider";
import {
  createBulkProcessSyncAction,
  createProcessAction,
} from "../operations/DocumentOperationsActions";

export const useDocumentActions = (onRefreshData?: () => void) => {
  const { t } = useTranslation();
  const { showInfo, showError } = useToast();

  // API hooks

  const [processDocuments] = useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation();
  const [fetchProgress] = useProcessDocumentsProgressKnowledgeFlowV1ProcessDocumentsProgressPostMutation();

  const [progress, setProgress] = useState<ProcessDocumentsProgressResponse | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [workflowId, setWorkflowId] = useState<string | undefined>(undefined);
  const PROCESS_POLL_INTERVAL_MS = 2000;
  const PROCESS_POLL_TIMEOUT_MS = 30 * 60 * 1000;

  const isProcessingDone = (res: ProcessDocumentsProgressResponse) => {
    if (res.total_documents <= 0) return false;
    const completed = res.documents_fully_processed + res.documents_failed + res.documents_missing;
    return completed >= res.total_documents;
  };

  const clearProgress = () => {
    // Debug: user cleared progress manually
    console.log("[useDocumentActions] clearProgress called, clearing progress and stopping polling");
    setIsProcessing(false);
    setProgress(null);
    setWorkflowId(undefined);
  };

  const refreshProgress = async () => {
    console.log("[useDocumentActions] refreshProgress triggered");
    try {
      const req: ProcessDocumentsProgressRequest = { workflow_id: workflowId };
      const args: ProcessDocumentsProgressKnowledgeFlowV1ProcessDocumentsProgressPostApiArg = {
        processDocumentsProgressRequest: req,
      };
      console.log("[useDocumentActions] Calling /process-documents/progress (manual refresh) with:", req);
      const res = await fetchProgress(args).unwrap();
      console.log("[useDocumentActions] Manual progress response:", res);
      setProgress(res);

      const done = isProcessingDone(res);
      setIsProcessing(!done && res.total_documents > 0);
    } catch (error: any) {
      console.error("[useDocumentActions] refreshProgress error:", error);
      showError({
        summary: "Progress tracking failed",
        detail: error?.data?.detail ?? error.message ?? "Unknown error while refreshing progress.",
      });
    }
  };

  useEffect(() => {
    if (!isProcessing) {
      console.log("[useDocumentActions] Not processing, polling is idle");
      return;
    }

    console.log("[useDocumentActions] Starting polling for processing progress");

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    const startedAt = Date.now();

    const poll = async () => {
      if (cancelled) return;
      try {
        if (Date.now() - startedAt >= PROCESS_POLL_TIMEOUT_MS) {
          showError({
            summary: "Progress tracking timeout",
            detail: "Polling stopped after timeout.",
          });
          setIsProcessing(false);
          return;
        }

        const req: ProcessDocumentsProgressRequest = { workflow_id: workflowId };
        const args: ProcessDocumentsProgressKnowledgeFlowV1ProcessDocumentsProgressPostApiArg = {
          processDocumentsProgressRequest: req,
        };
        console.log("[useDocumentActions] Calling /process-documents/progress (poll) with:", req);
        const res = await fetchProgress(args).unwrap();
        if (cancelled) return;

        console.log("[useDocumentActions] Poll progress response:", res);
        setProgress(res);

        const done = isProcessingDone(res);

        if (done) {
          console.log("[useDocumentActions] Poll detected DONE for all documents, stopping polling");
          onRefreshData?.();
          setIsProcessing(false);
          return;
        }

        timeoutId = setTimeout(poll, PROCESS_POLL_INTERVAL_MS);
      } catch (error: any) {
        if (!cancelled) {
          console.error("[useDocumentActions] Poll error:", error);
          showError({
            summary: "Progress tracking failed",
            detail: error?.data?.detail ?? error.message ?? "Unknown error while polling progress.",
          });
          setIsProcessing(false);
        }
      }
    };

    poll();

    return () => {
      console.log("[useDocumentActions] Cleaning up polling effect (component unmount or deps change)");
      cancelled = true;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [isProcessing, fetchProgress, onRefreshData, showError, workflowId]);

  const handleProcess = async (files: DocumentMetadata[]) => {
    try {
      console.log("[useDocumentActions] handleProcess called for files:", files.map((f) => f.identity.document_uid));
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

      const args: ProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostApiArg = {
        processDocumentsRequest: payload,
      };

      console.log("[useDocumentActions] Calling /process-documents with payload:", payload);
      const result = await processDocuments(args).unwrap();
      console.log("[useDocumentActions] /process-documents response:", result);
      console.log("[useDocumentActions] Started processing workflow", result.workflow_id);
      setProgress(null);
      setWorkflowId(result.workflow_id);
      setIsProcessing(true);

      showInfo({
        summary: "Processing started",
        detail: `Queued ${result.total_files} document(s) for local processing`,
      });
    } catch (error: any) {
      console.error("[useDocumentActions] handleProcess error:", error);
      showError({
        summary: "Processing Failed",
        detail: error?.data?.detail ?? error.message,
      });
    }
  };

  // Create default actions
  const defaultRowActions = [createProcessAction((file) => handleProcess([file]), t)];

  const defaultBulkActions = [createBulkProcessSyncAction((files) => handleProcess(files), t)];

  return {
    defaultRowActions,
    defaultBulkActions,
    progress,
    clearProgress,
    refreshProgress,
    processDocuments: handleProcess,
    isProcessing,
  };
};
