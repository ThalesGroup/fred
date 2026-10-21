// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Button from "@shared/atoms/Button/Button";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import Select from "@shared/molecules/Select/Select";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  useImportPlatformT0Mutation,
  usePlatformAccessStateQuery,
  usePlatformAccessT0Query,
} from "../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements";
import type { RefreshPlatformT0 } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import styles from "./PlatformAccessPage.module.css";

export default function PlatformAccessT0RefreshDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const [choice, setChoice] = useState<RefreshPlatformT0["mode"]>("preserve_removals");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const status = usePlatformAccessT0Query({}, { refetchOnMountOrArgChange: true });
  const authority = usePlatformAccessStateQuery(undefined, { refetchOnMountOrArgChange: true });
  const statusKnown = !status.isFetching && !status.isError && !!status.data?.completed_at;
  const requiresFull = status.data?.removal_history_complete !== true;
  const mode = requiresFull ? "include_removed" : choice;
  const preview = usePlatformAccessT0Query(
    { refreshMode: mode },
    { skip: !statusKnown || !authority.data || authority.isError, refetchOnMountOrArgChange: true },
  );
  const [importT0] = useImportPlatformT0Mutation();
  const current = preview.currentData;
  const fresh =
    statusKnown &&
    !authority.isFetching &&
    !authority.isError &&
    !!authority.data &&
    !preview.isFetching &&
    !preview.isError &&
    !!current?.completed_at &&
    current.completed_at === status.data?.completed_at &&
    current.revision === authority.data?.revision;
  const loading = status.isFetching || authority.isFetching || preview.isFetching;
  const failed = status.isError || authority.isError || preview.isError || (!loading && !fresh);
  const retry = () => {
    setError(undefined);
    void Promise.all([status.refetch(), authority.refetch(), ...(preview.isUninitialized ? [] : [preview.refetch()])]);
  };
  const confirm = async () => {
    if (!fresh || busy || !current?.completed_at || current.revision === undefined) return;
    setBusy(true);
    setError(undefined);
    try {
      const result = await importT0({
        body: {
          mode,
          expected_revision: current.revision,
          expected_completed_at: current.completed_at,
        },
      }).unwrap();
      showSuccess({ summary: t("rework.platformAccess.t0Refresh.success", { count: result.imported_count ?? 0 }) });
      onClose();
    } catch (failure) {
      const detail = normalizeApiError(failure).detail;
      setError(
        t(
          detail === "platform_access_t0_snapshot_changed" || detail === "platform_access_t0_full_refresh_required"
            ? "rework.platformAccess.t0Refresh.conflict"
            : "rework.platformAccess.failed",
        ),
      );
      await Promise.all([status.refetch(), authority.refetch(), preview.refetch()]);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open
      title={t("rework.platformAccess.t0Refresh.title")}
      maxWidth={600}
      confirmLabel={t("rework.platformAccess.t0Refresh.confirm")}
      confirmDisabled={busy || !fresh}
      onCancel={() => {
        if (!busy) onClose();
      }}
      onConfirm={() => void confirm()}
    >
      <div className={styles.dialogBody}>
        <Select
          compact
          size="small"
          label={t("rework.platformAccess.t0Refresh.mode")}
          value={mode}
          disabled={busy || !statusKnown}
          options={(["preserve_removals", "include_removed"] as const).map((value) => ({
            key: value,
            value,
            label: t(`rework.platformAccess.t0Refresh.${value}`),
            disabled: value === "preserve_removals" && requiresFull,
          }))}
          onChange={(value) => {
            setChoice(value);
            setError(undefined);
          }}
        />
        {statusKnown && (requiresFull || mode === "include_removed") && (
          <p role="alert" className={styles.importWarning}>
            {t(
              requiresFull
                ? "rework.platformAccess.t0Refresh.missingHistory"
                : "rework.platformAccess.t0Refresh.includeWarning",
            )}
          </p>
        )}
        {loading && <Spinner statusText={t("rework.platformAccess.loading")} />}
        {fresh && current && (
          <p role="status">
            {t("rework.platformAccess.t0Refresh.preview", {
              count: current.candidates,
              skipped: current.removed_skipped ?? 0,
            })}
          </p>
        )}
        {(error || failed) && (
          <div role="alert">
            <p>{error || t("rework.platformAccess.failed")}</p>
            <Button size="small" color="primary" variant="outlined" disabled={busy || loading} onClick={retry}>
              {t("rework.platformAccess.retry")}
            </Button>
          </div>
        )}
      </div>
    </Dialog>
  );
}
