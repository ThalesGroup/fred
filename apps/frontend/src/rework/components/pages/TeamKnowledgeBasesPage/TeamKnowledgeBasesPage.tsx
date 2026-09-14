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
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import KnowledgeBaseCard from "@shared/organisms/KnowledgeBaseCard/KnowledgeBaseCard.tsx";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  useDeleteKnowledgeBaseMutation,
  useKnowledgeBasesQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import { KnowledgeBaseInstanceSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import KnowledgeBaseFormModal from "./KnowledgeBaseFormModal/KnowledgeBaseFormModal.tsx";
import styles from "./TeamKnowledgeBasesPage.module.css";

/** Where a team's documents come from, one card per base.
 *
 * Deliberately its own screen rather than a level inside the folder tree: a
 * team's own deposits and a contributor's mirror are different acts, and only
 * this list answers "which sources are we drawing on at all".
 */
export default function TeamKnowledgeBasesPage() {
  const { teamId } = useParams<{ teamId: string }>();
  const { t } = useTranslation();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { showError, showSuccess } = useToast();

  const { data: instances, isLoading, isError } = useKnowledgeBasesQuery({ teamId: teamId ?? "" }, { skip: !teamId });
  const [deleteKnowledgeBase] = useDeleteKnowledgeBaseMutation();
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const handleDelete = (instance: KnowledgeBaseInstanceSummary) => {
    showConfirmationDialog({
      // Deleting a base takes its documents with it — the tag's own cascade.
      criticalAction: true,
      title: t("rework.knowledgeBases.deleteDialog.title"),
      message: t("rework.knowledgeBases.deleteDialog.message", { name: instance.library_name }),
      confirmButtonLabel: t("rework.knowledgeBases.deleteDialog.confirm"),
      cancelButtonLabel: t("rework.knowledgeBases.deleteDialog.cancel"),
      onConfirm: async () => {
        try {
          await deleteKnowledgeBase({ instanceId: instance.id }).unwrap();
          showSuccess({ summary: t("rework.knowledgeBases.deleted", { name: instance.library_name }) });
        } catch {
          showError({ summary: t("rework.knowledgeBases.deleteFailed", { name: instance.library_name }) });
        }
      },
    });
  };

  return (
    <div className={styles.page}>
      <div className={styles.title}>
        <PageHeader
          title={t("rework.knowledgeBases.title")}
          actions={
            <Button
              color={"primary"}
              variant={"filled"}
              size={"medium"}
              icon={{ category: "outlined", type: "add" }}
              onClick={() => setIsCreateOpen(true)}
            >
              {t("rework.knowledgeBases.create")}
            </Button>
          }
        />
      </div>

      {isLoading ? (
        <div className={styles.loadingState}>
          <Spinner size={20} />
          {t("rework.knowledgeBases.loading")}
        </div>
      ) : isError ? (
        <ServiceNotice
          icon="cloud_off"
          title={t("rework.knowledgeBases.unavailable.title")}
          description={t("rework.knowledgeBases.unavailable.description")}
          centered
        />
      ) : !instances?.length ? (
        <ServiceNotice icon="database" title={t("rework.knowledgeBases.empty")} centered />
      ) : (
        <div className={styles.list}>
          {instances.map((instance) => (
            <KnowledgeBaseCard
              key={instance.id}
              instance={instance}
              teamId={teamId ?? ""}
              canManage
              onDelete={() => handleDelete(instance)}
            />
          ))}
        </div>
      )}

      <KnowledgeBaseFormModal open={isCreateOpen} teamId={teamId ?? ""} onClose={() => setIsCreateOpen(false)} />
    </div>
  );
}
