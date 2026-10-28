// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import Button from "@shared/atoms/Button/Button.tsx";
import StatusBadge, { type StatusBadgeTone } from "@shared/atoms/StatusBadge/StatusBadge.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable.tsx";
import { EntityIdentity } from "@shared/molecules/EntityIdentity/EntityIdentity.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { formatDateTime } from "@rework/utils/formatDateTime";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useOrganizationCapabilitiesQuery,
  useRefreshOrganizationCapabilitiesMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  CapabilityInventoryOffer,
  CatalogObservationState,
  PodCapabilityInventory,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { normalizeApiError } from "../../../../core/errors/normalizeApiError";
import styles from "./FeaturesPage.module.css";

const OBSERVATION_TONE: Record<CatalogObservationState, StatusBadgeTone> = {
  observed: "success",
  unavailable: "error",
  not_observed: "neutral",
};

// An offer is (pod, capability): pick a pod, then read its offers in the catalog table.
// The capability columns come from FeaturesPage so both tables keep one layout.
export function OrganizationCapabilities({
  organizationId,
  capabilityColumns,
}: {
  organizationId: string;
  capabilityColumns: DataTableColumn<CapabilityInventoryOffer>[];
}) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const {
    currentData: pods,
    isFetching,
    isError,
  } = useOrganizationCapabilitiesQuery({ organizationId }, { refetchOnMountOrArgChange: true });
  const [refreshInventory] = useRefreshOrganizationCapabilitiesMutation();
  const [refreshing, setRefreshing] = useState<string[]>([]);
  const [selectedRuntimeId, setSelectedRuntimeId] = useState<string | null>(null);
  const initialRefreshStarted = useRef(false);
  const prefix = "rework.admin.capabilities.organizationCapabilities";

  const refresh = useCallback(
    async (runtimeId: string) => {
      setRefreshing((ids) => [...ids, runtimeId]);
      try {
        await refreshInventory({ organizationId, runtimeId }).unwrap();
      } catch (error) {
        showError({
          summary: t(`${prefix}.refreshError`, { runtimeId }),
          detail: normalizeApiError(error).detail,
        });
      } finally {
        setRefreshing((ids) => ids.filter((id) => id !== runtimeId));
      }
    },
    [organizationId, refreshInventory, showError, t],
  );
  useEffect(() => {
    if (!pods || isFetching || isError || initialRefreshStarted.current) return;
    // A fresh installation has no inventory yet; later refreshes stay manual.
    initialRefreshStarted.current = true;
    pods
      .filter((pod) => pod.enabled && pod.observation === "not_observed")
      .forEach((pod) => void refresh(pod.runtime_id));
  }, [pods, isFetching, isError, refresh]);

  // Resolved on every render so the selected pod follows the refetched inventory.
  const selectedPod = pods?.find((pod) => pod.runtime_id === selectedRuntimeId) ?? null;
  const podColumns: DataTableColumn<PodCapabilityInventory>[] = [
    {
      label: t(`${prefix}.col.pod`),
      size: "2fr",
      cellRenderer: (pod) => <EntityIdentity name={pod.runtime_id} icon="hub" dimmed={!pod.enabled} />,
    },
    {
      label: t(`${prefix}.col.observation`),
      size: "1fr",
      cellRenderer: (pod) => (
        <StatusBadge label={t(`${prefix}.observation.${pod.observation}`)} tone={OBSERVATION_TONE[pod.observation]} />
      ),
    },
    {
      label: t(`${prefix}.col.checkedAt`),
      size: "1fr",
      cellRenderer: (pod) => formatDateTime(pod.checked_at),
    },
    {
      label: t(`${prefix}.col.capabilities`),
      size: "1fr",
      cellRenderer: (pod) => pod.capabilities.filter((offer) => offer.advertised).length,
    },
    {
      label: t("rework.admin.capabilities.col.actions"),
      size: "1fr",
      cellRenderer: (pod) => {
        const button = (
          <Button
            color="on-surface"
            variant="outlined"
            size="small"
            icon={{ category: "outlined", type: "refresh" }}
            disabled={!pod.enabled || refreshing.includes(pod.runtime_id)}
            onClick={() => void refresh(pod.runtime_id)}
          >
            {t("rework.admin.capabilities.discovery.refresh")}
          </Button>
        );
        return pod.enabled ? (
          button
        ) : (
          <Tooltip text={t(`${prefix}.disabledHint`)}>
            <span>{button}</span>
          </Tooltip>
        );
      },
    },
  ];

  if (isError) {
    return (
      <p className={styles.statusError} role="alert">
        {t("rework.admin.capabilities.loadError")}
      </p>
    );
  }
  if (!pods) {
    return isFetching ? <p className={styles.status}>{t("rework.admin.capabilities.loading")}</p> : null;
  }
  if (selectedPod) {
    return (
      <>
        <div className={styles.modelListToolbar}>
          <Button
            color="on-surface"
            variant="text"
            size="small"
            icon={{ category: "outlined", type: "arrow_back" }}
            onClick={() => setSelectedRuntimeId(null)}
          >
            {t(`${prefix}.backToPods`)}
          </Button>
          <span className={styles.capName}>{selectedPod.runtime_id}</span>
        </div>
        {selectedPod.observation === "unavailable" && (
          <p className={styles.statusWarning} role="status">
            {selectedPod.observed_at
              ? t(`${prefix}.unavailableHint`, { date: formatDateTime(selectedPod.observed_at) })
              : t(`${prefix}.neverAnsweredHint`)}
          </p>
        )}
        {selectedPod.capabilities.length ? (
          <DataTable
            columns={capabilityColumns}
            data={selectedPod.capabilities}
            rowKey={(offer) => offer.capability_id}
            size="medium"
          />
        ) : (
          <PageEmptyState icon="tune" message={t("rework.admin.capabilities.empty")} />
        )}
      </>
    );
  }
  return pods.length ? (
    <DataTable
      columns={podColumns}
      data={pods}
      rowKey={(pod) => pod.runtime_id}
      onRowClick={(pod) => setSelectedRuntimeId(pod.runtime_id)}
      size="medium"
    />
  ) : (
    <PageEmptyState icon="tune" message={t(`${prefix}.noPods`)} />
  );
}
