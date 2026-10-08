// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { usePlatformAccessActivationPreviewQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformAccessPage.module.css";

export default function PlatformAccessActivationDialog({
  enabling,
  revision,
  busy,
  configured,
  onClose,
  onConfirm,
}: {
  enabling: boolean;
  revision: number;
  busy: boolean;
  configured: boolean;
  onClose: () => void;
  onConfirm: (revision: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const [group, setGroup] = useState(0);
  const preview = usePlatformAccessActivationPreviewQuery(undefined, {
    skip: !enabling,
    refetchOnMountOrArgChange: true,
  });
  const fresh = !preview.isFetching && !preview.isError && preview.data?.revision === revision;
  const outcomes = ["blocked", "unknown", "allowed"] as const;
  return (
    <Dialog
      open
      title={t(`rework.platformAccess.activation.${enabling ? "enableTitle" : "disableTitle"}`)}
      maxWidth={1000}
      confirmLabel={t(`rework.platformAccess.activation.${enabling ? "enable" : "disable"}`)}
      confirmDisabled={busy || (enabling && (!fresh || !configured))}
      onCancel={() => {
        if (!busy) onClose();
      }}
      onConfirm={() => onConfirm(enabling ? preview.data!.revision : revision)}
    >
      <div className={styles.dialogBody}>
        <p>{t(`rework.platformAccess.activation.${enabling ? "savedOnly" : "disableHint"}`)}</p>
        {enabling && (
          <>
            {preview.isFetching && <p role="status">{t("rework.platformAccess.loading")}</p>}
            {(preview.isError || (!preview.isFetching && preview.data && !fresh)) && (
              <div role="alert">
                <p>{t("rework.platformAccess.activation.previewFailed")}</p>
                <Button color="primary" variant="outlined" size="small" onClick={() => void preview.refetch()}>
                  {t("rework.platformAccess.retry")}
                </Button>
              </div>
            )}
            {fresh && preview.data && (
              <>
                <p>{t("rework.platformAccess.activation.summary", preview.data)}</p>
                <p className={styles.hint}>
                  {t("rework.platformAccess.activation.checkedAt", {
                    date: new Date(preview.data.checked_at).toLocaleString(i18n.language),
                  })}
                </p>
                {!!preview.data.unknown && <p role="status">{t("rework.platformAccess.activation.unknownHint")}</p>}
                <ButtonGroup
                  size="small"
                  color="secondary"
                  variant="tabs"
                  selectedIndex={group}
                  onSelectedIndexChange={setGroup}
                  aria-label={t("rework.platformAccess.activation.groups")}
                  items={outcomes.map((outcome) => ({ label: t(`rework.platformAccess.activation.${outcome}`) }))}
                />
                <DataTable
                  data={preview.data.users.filter((user) => user.outcome === outcomes[group])}
                  rowKey={(user) => user.user_id}
                  pageSize={25}
                  columns={[
                    {
                      label: t("rework.teamSettings.members.table.identifiant"),
                      cellRenderer: (user) => user.username || user.user_id,
                    },
                    {
                      label: t("rework.teamSettings.members.table.firstName"),
                      cellRenderer: (user) => user.first_name || "-",
                    },
                    {
                      label: t("rework.teamSettings.members.table.lastName"),
                      cellRenderer: (user) => user.last_name || "-",
                    },
                    { label: t("rework.platformAccess.activation.email"), cellRenderer: (user) => user.email || "-" },
                  ]}
                />
              </>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
