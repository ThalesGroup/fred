// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import Button from "@shared/atoms/Button/Button";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { EntityIdentity } from "@shared/molecules/EntityIdentity/EntityIdentity";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useModelAccessMatrixQuery,
  useSetModelAccessMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  ModelScopeChoice,
  ModelTeamAccess,
  StoredModelOffer,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { normalizeApiError } from "../../../../core/errors/normalizeApiError";
import styles from "./ModelCatalog.module.css";

type AccessRow = Omit<ModelTeamAccess, "team_id"> & { team_id: string | null };
const choices: ModelScopeChoice[] = ["disabled", "default", "enabled"];

export function ModelAccessDialog({
  organizationId,
  offer,
  onClose,
}: {
  organizationId: string;
  offer: StoredModelOffer;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const key = "rework.admin.capabilities.organizationModels.access";
  const [filter, setFilter] = useState("");
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const query = useModelAccessMatrixQuery(
    {
      organizationId,
      sourceId: offer.source_id,
      upstreamModelId: offer.upstream_model_id,
      name: filter.trim(),
      after: cursors[cursors.length - 1],
    },
    { refetchOnMountOrArgChange: true },
  );
  const [setAccess, saving] = useSetModelAccessMutation();
  const [pending, setPending] = useState<AccessRow | null>(null);
  const [changing, setChanging] = useState<string | null>(null);
  const data = query.currentData;
  const busy = saving.isLoading || query.isFetching || query.isError || changing !== null;
  const change = async (row: AccessRow, choice: ModelScopeChoice) => {
    if (!data || busy || row.choice === choice) return;
    setChanging(row.team_id ?? "personal");
    try {
      await setAccess({
        organizationId,
        sourceId: offer.source_id,
        setModelAccess: {
          expected_revision: data.revision,
          upstream_model_id: offer.upstream_model_id,
          team_id: row.team_id,
          choice,
        },
      }).unwrap();
      await query.refetch().unwrap();
      showSuccess({ summary: t(`${key}.saved`) });
    } catch (error) {
      showError({ summary: t(`${key}.saveFailed`), detail: normalizeApiError(error).detail });
      await query.refetch();
    } finally {
      setChanging(null);
    }
  };
  const rows: AccessRow[] = data
    ? [
        ...(!filter.trim()
          ? [
              {
                team_id: null,
                name: t(`${key}.personal`),
                choice: data.personal,
                effective: data.personal_effective,
                locally_disabled: false,
              },
            ]
          : []),
        ...data.teams,
      ]
    : [];
  return (
    <>
      <Dialog
        open
        dense
        maxWidth={1000}
        title={`${t(`${key}.manage`)} - ${offer.metadata.display_name ?? offer.upstream_model_id}`}
        hideConfirm
        confirmLabel={t("common.close")}
        cancelLabel={t("common.close")}
        onCancel={onClose}
        onConfirm={onClose}
      >
        <p className={styles.metadataHint}>{t(`${key}.hint`)}</p>
        {data && !data.organization_permitted && <p role="note">{t(`${key}.organizationDenied`)}</p>}
        <div className={styles.filter}>
          <SearchInput
            size="xs"
            value={filter}
            ariaLabel={t(`${key}.filter`)}
            placeholder={t(`${key}.filter`)}
            clearAriaLabel={t("rework.admin.capabilities.discovery.clearFilter")}
            onChange={(value) => {
              setFilter(value);
              setCursors([undefined]);
            }}
          />
        </div>
        {query.isError ? (
          <p role="alert">
            {t("rework.manager.unavailable")}{" "}
            <Button variant="text" color="on-surface" size="small" onClick={() => void query.refetch()}>
              {t("common.retry")}
            </Button>
          </p>
        ) : !data ? (
          <p role="status">{t("common.loading")}</p>
        ) : (
          <>
            <DataTable
              data={rows}
              rowKey={(row) => row.team_id ?? "personal"}
              size="small"
              columns={[
                {
                  label: t(`${key}.scope`),
                  size: "2fr",
                  cellRenderer: (row) => (
                    <div className={styles.metadataField}>
                      <EntityIdentity name={row.name} />
                      {row.locally_disabled && <span className={styles.hint}>{t(`${key}.localRestriction`)}</span>}
                    </div>
                  ),
                },
                {
                  label: t(`${key}.choice`),
                  size: "2fr",
                  cellRenderer: (row) => (
                    <ButtonGroup
                      size="small"
                      color="primary"
                      variant="radio"
                      aria-label={row.name}
                      selectedIndex={choices.indexOf(row.choice)}
                      items={choices.map((choice) => ({
                        label: t(`${key}.${choice}`),
                        disabled:
                          (busy && changing !== (row.team_id ?? "personal")) ||
                          (choice === "enabled" && (!data.organization_permitted || !offer.selectable)),
                      }))}
                      onSelectedIndexChange={(index) => {
                        if (busy || row.choice === choices[index]) return;
                        if (choices[index] === "disabled") setPending(row);
                        else void change(row, choices[index]);
                      }}
                    />
                  ),
                },
                {
                  label: t(`${key}.effective`),
                  size: "1fr",
                  cellRenderer: (row) => t(`rework.toolGovernance.${row.effective ? "allowed" : "denied"}`),
                },
              ]}
            />
            {rows.length === 0 && <p role="status">{t("rework.admin.capabilities.matrix.searchEmpty")}</p>}
            {(cursors.length > 1 || data.next_cursor) && (
              <div className={styles.toolbar}>
                <Button
                  variant="text"
                  color="on-surface"
                  size="small"
                  disabled={busy || cursors.length < 2}
                  onClick={() => setCursors((previous) => previous.slice(0, -1))}
                >
                  {t("dataTable.pagination.prev")}
                </Button>
                <Button
                  variant="text"
                  color="on-surface"
                  size="small"
                  disabled={busy || !data.next_cursor}
                  onClick={() => setCursors((previous) => [...previous, data.next_cursor ?? undefined])}
                >
                  {t("dataTable.pagination.next")}
                </Button>
              </div>
            )}
          </>
        )}
      </Dialog>
      <ConfirmationDialog
        open={pending !== null}
        criticalAction
        title={t(`${key}.disableTitle`)}
        message={t(`${key}.disableWarning`, { name: pending?.name })}
        confirmLabel={t("common.confirm")}
        cancelLabel={t("common.cancel")}
        confirmDisabled={busy}
        onCancel={() => setPending(null)}
        onConfirm={() => {
          if (pending) void change(pending, "disabled");
          setPending(null);
        }}
      />
    </>
  );
}
