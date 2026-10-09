// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Button from "@shared/atoms/Button/Button";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import {
  usePlatformAccessActivationPreviewQuery,
  usePlatformAccessStateQuery,
  usePlatformAccessT0Query,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformAccessPage.module.css";

export default function PlatformAccessActivationDialog({
  enabling,
  revision,
  busy,
  configured,
  onClose,
  onImportUsers,
  onConfirm,
}: {
  enabling: boolean;
  revision: number;
  busy: boolean;
  configured: boolean;
  onClose: () => void;
  onImportUsers: () => void;
  onConfirm: (revision: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const [group, setGroup] = useState<number>();
  const preview = usePlatformAccessActivationPreviewQuery(undefined, {
    skip: !enabling,
    refetchOnMountOrArgChange: true,
  });
  const authority = usePlatformAccessStateQuery(undefined, { skip: !enabling });
  const initialImport = usePlatformAccessT0Query(undefined, {
    skip: !enabling,
    refetchOnMountOrArgChange: true,
  });
  const refresh = () => void Promise.all([preview.refetch(), authority.refetch(), initialImport.refetch()]);
  const importKnown = !initialImport.isFetching && !initialImport.isError && !!initialImport.data;
  const missingImport = enabling && importKnown && !initialImport.data?.completed_at;
  const refreshing = preview.isFetching || authority.isFetching || initialImport.isFetching;
  const fresh =
    !preview.isFetching &&
    !preview.isError &&
    !authority.isFetching &&
    !authority.isError &&
    preview.data?.revision === revision;
  const outcomes = ["blocked", "allowed"] as const;
  const selectedGroup = group ?? (preview.data?.blocked ? 0 : 1);
  const renderUsers = (outcome: "allowed" | "blocked" | "unknown") => (
    <div className={styles.reviewUserTable}>
      <DataTable
        data={(preview.data?.users ?? []).filter((user) => user.outcome === outcome)}
        rowKey={(user) => user.user_id}
        pageSize={25}
        columns={[
          {
            label: t("rework.teamSettings.members.table.identifiant"),
            cellRenderer: (user) => user.username || user.user_id,
          },
          { label: t("rework.teamSettings.members.table.firstName"), cellRenderer: (user) => user.first_name || "-" },
          { label: t("rework.teamSettings.members.table.lastName"), cellRenderer: (user) => user.last_name || "-" },
          { label: t("rework.platformAccess.activation.email"), cellRenderer: (user) => user.email || "-" },
        ]}
      />
    </div>
  );
  return (
    <Dialog
      open
      title={t(`rework.platformAccess.activation.${enabling ? "enableTitle" : "disableTitle"}`)}
      maxWidth={1000}
      confirmLabel={t(
        `rework.platformAccess.activation.${missingImport ? "continueWithoutImport" : enabling ? "enable" : "disable"}`,
      )}
      cancelLabel={missingImport ? t("rework.platformAccess.activation.goToWhitelist") : undefined}
      confirmDisabled={busy || (enabling && (!fresh || !configured || !importKnown))}
      onCancel={() => {
        if (!busy) {
          if (missingImport) onImportUsers();
          else onClose();
        }
      }}
      onConfirm={() => onConfirm(enabling ? preview.data!.revision : revision)}
    >
      <div className={`${styles.dialogBody} ${styles.activationBody}`}>
        <p>{t(`rework.platformAccess.activation.${enabling ? "savedOnly" : "disableHint"}`)}</p>
        {enabling && (
          <>
            {missingImport && (
              <div role="alert" className={styles.section}>
                <strong>{t("rework.platformAccess.activation.importWarning")}</strong>
                <p>{t("rework.platformAccess.activation.importWarningHint")}</p>
              </div>
            )}
            {initialImport.isFetching && <p role="status">{t("rework.platformAccess.loading")}</p>}
            {(initialImport.isError || (!initialImport.isFetching && !initialImport.data)) && (
              <div role="alert">
                <p>{t("rework.platformAccess.activation.importStatusFailed")}</p>
                <Button color="primary" variant="outlined" size="small" onClick={() => void initialImport.refetch()}>
                  {t("rework.platformAccess.retry")}
                </Button>
              </div>
            )}
            {(preview.isFetching || authority.isFetching) && <p role="status">{t("rework.platformAccess.loading")}</p>}
            {(preview.isError || authority.isError || (!refreshing && preview.data && !fresh)) && (
              <div role="alert">
                <p>{t("rework.platformAccess.activation.previewFailed")}</p>
                <Button color="primary" variant="outlined" size="small" disabled={busy || refreshing} onClick={refresh}>
                  {t("rework.platformAccess.retry")}
                </Button>
              </div>
            )}
            {preview.data && (
              <>
                <h3 className={styles.reviewHeading}>{t("rework.platformAccess.activation.groups")}</h3>
                <div className={styles.reviewHeader}>
                  <p className={styles.hint}>
                    {t("rework.platformAccess.activation.checkedAt", {
                      date: new Date(preview.data.checked_at).toLocaleString(i18n.language),
                    })}
                  </p>
                  <IconButton
                    color="primary"
                    variant="icon"
                    size="small"
                    icon={{ category: "outlined", type: "refresh" }}
                    title={t("rework.platformAccess.activation.update")}
                    aria-label={t("rework.platformAccess.activation.update")}
                    loading={!!refreshing}
                    disabled={busy}
                    onClick={refresh}
                  />
                </div>
                {fresh && (
                  <>
                    <div className={styles.reviewTable}>
                      <ButtonGroup
                        size="medium"
                        color="secondary"
                        variant="tabs"
                        selectedIndex={selectedGroup}
                        onSelectedIndexChange={setGroup}
                        aria-label={t("rework.platformAccess.activation.groups")}
                        items={outcomes.map((outcome) => ({
                          label: `${t(`rework.platformAccess.activation.${outcome}`)} (${preview.data![outcome]})`,
                        }))}
                      />
                      {preview.data[outcomes[selectedGroup]] ? (
                        renderUsers(outcomes[selectedGroup])
                      ) : (
                        <p>
                          {t(
                            `rework.platformAccess.activation.${selectedGroup === 0 ? "emptyBlocked" : "emptyAllowed"}`,
                          )}
                        </p>
                      )}
                    </div>
                    {!!preview.data.unknown && (
                      <details className={styles.unverifiedUsers}>
                        <summary role="button" tabIndex={0}>
                          {t("rework.platformAccess.activation.unverified", { count: preview.data.unknown })}
                        </summary>
                        <p>{t("rework.platformAccess.activation.unknownHint")}</p>
                        {renderUsers("unknown")}
                      </details>
                    )}
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
