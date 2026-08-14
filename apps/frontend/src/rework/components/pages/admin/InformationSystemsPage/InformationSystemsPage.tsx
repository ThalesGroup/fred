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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import DataTable, { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import {
  useDeleteInformationSystemMutation,
  useGetInformationSystemsSummaryQuery,
  type InformationSystemSummary,
} from "../../../../../slices/rags/ragsOpenApi.ts";
import CreateInformationSystemDialog from "./CreateInformationSystemDialog/CreateInformationSystemDialog.tsx";
import DocumentAssignmentModal from "./DocumentAssignmentModal/DocumentAssignmentModal.tsx";
import styles from "./InformationSystemsPage.module.css";

function countDocuments(system: InformationSystemSummary): number {
  return Object.values(system.documents ?? {}).reduce((total, docs) => total + (docs?.length ?? 0), 0);
}

/**
 * Information Systems (SI) admin page (#2307): create an SI from a
 * knowledge-flow library tag and assign that library's documents a role
 * (DAT/MEX/CMDB) — the setup the rags agents (Eva, Iris, Gap...) need before
 * they can run an assessment. Ported from the standalone fred-rags frontend
 * (MUI, old backend); rebuilt from scratch against rework's design system and
 * against `rags-services`, the now-independent CRUD backend for this data.
 *
 * `rags-services` has no team scoping at all (no `team_id` anywhere in its
 * data model — confirmed against `information_system/controller.py`), so this
 * lives under `/admin`, not under a `/team/:teamId/...` route: a team-scoped
 * URL would show the exact same global list for every team, which reads as
 * broken rather than scoped.
 */
export default function InformationSystemsPage() {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();
  const { showConfirmationDialog } = useConfirmationDialog();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [assigningSystem, setAssigningSystem] = useState<InformationSystemSummary | null>(null);

  const { data: systems, isLoading, isError, refetch } = useGetInformationSystemsSummaryQuery();
  const [deleteSystem] = useDeleteInformationSystemMutation();

  const handleDelete = (system: InformationSystemSummary) => {
    showConfirmationDialog({
      criticalAction: true,
      title: t("rework.informationSystems.deleteDialog.title"),
      message: t("rework.informationSystems.deleteDialog.message", { name: system.information_system }),
      confirmButtonLabel: t("rework.informationSystems.deleteDialog.confirm"),
      cancelButtonLabel: t("rework.informationSystems.deleteDialog.cancel"),
      onConfirm: async () => {
        await runMutationAction({
          action: () => deleteSystem({ informationSystemUid: system.information_system_uid }).unwrap(),
          onSuccess: () => {
            showSuccess({ summary: t("rework.informationSystems.deleteDialog.success") });
            refetch();
          },
          onError: (error) =>
            notifyApiError(error, {
              summary: t("rework.informationSystems.deleteDialog.errorSummary"),
              fallbackDetail: t("rework.informationSystems.deleteDialog.errorFallback"),
            }),
        });
      },
    });
  };

  const columns: DataTableColumn<InformationSystemSummary>[] = [
    {
      label: t("rework.informationSystems.table.name"),
      size: "2fr",
      sortable: true,
      sortValue: (system) => system.information_system,
      cellRenderer: (system) => system.information_system,
    },
    {
      label: t("rework.informationSystems.table.documents"),
      size: "8rem",
      cellRenderer: (system) => (
        <button type="button" className={styles.docCountButton} onClick={() => setAssigningSystem(system)}>
          {countDocuments(system)}
        </button>
      ),
    },
    {
      label: t("rework.informationSystems.table.similarities"),
      size: "8rem",
      cellRenderer: (system) => system.assessment?.similarities ?? 0,
    },
    {
      label: t("rework.informationSystems.table.contradictions"),
      size: "9rem",
      cellRenderer: (system) => system.assessment?.contradictions ?? 0,
    },
    {
      label: t("rework.informationSystems.table.actions"),
      size: "6rem",
      cellRenderer: (system) => (
        <div className={styles.rowActions}>
          <IconButton
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "description" }}
            title={t("rework.informationSystems.table.manageDocuments")}
            aria-label={t("rework.informationSystems.table.manageDocuments")}
            onClick={() => setAssigningSystem(system)}
          />
          <IconButton
            variant="icon"
            size="small"
            color="error"
            icon={{ category: "outlined", type: "delete" }}
            title={t("rework.informationSystems.table.delete")}
            aria-label={t("rework.informationSystems.table.delete")}
            onClick={() => handleDelete(system)}
          />
        </div>
      ),
    },
  ];

  if (isError) {
    return (
      <ServiceNotice
        icon="cloud_off"
        title={t("rework.serviceNotice.ragsServices.title")}
        description={t("rework.serviceNotice.ragsServices.description")}
        centered
      />
    );
  }

  const showEmptyState = !isLoading && (systems?.length ?? 0) === 0;

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("rework.informationSystems.title")}
        subtitle={t("rework.informationSystems.subtitle")}
        actions={
          !showEmptyState && (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              icon={{ category: "outlined", type: "add" }}
              onClick={() => setIsCreateOpen(true)}
            >
              {t("rework.informationSystems.create.action")}
            </Button>
          )
        }
      />

      {isLoading ? (
        <div className={styles.loadingState}>
          <Spinner size={20} />
          {t("rework.informationSystems.loading")}
        </div>
      ) : showEmptyState ? (
        <PageEmptyState
          icon="hub"
          message={t("rework.informationSystems.empty")}
          action={{ label: t("rework.informationSystems.create.action"), onClick: () => setIsCreateOpen(true) }}
        />
      ) : (
        <div className={styles.tableWrapper}>
          <DataTable
            columns={columns}
            data={systems ?? []}
            rowKey={(system) => system.information_system_uid}
            pageSize={20}
          />
        </div>
      )}

      <CreateInformationSystemDialog
        open={isCreateOpen}
        existingSystems={systems ?? []}
        onClose={() => setIsCreateOpen(false)}
        onCreated={() => {
          setIsCreateOpen(false);
          refetch();
        }}
      />

      {assigningSystem && (
        <DocumentAssignmentModal
          open
          system={assigningSystem}
          onClose={() => setAssigningSystem(null)}
          onUpdated={() => {
            setAssigningSystem(null);
            refetch();
          }}
        />
      )}
    </div>
  );
}
