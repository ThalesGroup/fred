// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import PlatformAccessExpirationPicker from "./PlatformAccessExpirationPicker";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { useCopyConfirmation } from "@hooks/useCopyConfirmation";
import { ActionBar } from "@shared/molecules/ActionBar/ActionBar";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import Select from "@shared/molecules/Select/Select";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { platformPath } from "../../../../../common/platformAccess";
import type {
  PlatformAccessTeam,
  PlatformEnrollmentLinkInfo,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  usePlatformEnrollmentLinksQuery,
  useGeneratePlatformLinkMutation,
  useRevealPlatformLinkMutation,
  useRevokePlatformLinkMutation,
  useDeleteInactivePlatformLinksMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformAccessPage.module.css";

type LinkStatusFilter = Exclude<PlatformEnrollmentLinkInfo["status"], "suspended"> | "all";

export default function PlatformAccessLinkManager({
  team,
  onClose,
}: {
  team: PlatformAccessTeam;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState<LinkStatusFilter>("all");
  const links = usePlatformEnrollmentLinksQuery(
    { teamId: team.team_id, offset, limit: 25, status: status === "all" ? undefined : status },
    {
      refetchOnMountOrArgChange: true,
      pollingInterval: 30000,
    },
  );
  const [generate, generating] = useGeneratePlatformLinkMutation();
  const [reveal, revealing] = useRevealPlatformLinkMutation();
  const [revoke, revoking] = useRevokePlatformLinkMutation();
  const [deleteInactive, deleting] = useDeleteInactivePlatformLinksMutation();
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [deletedCount, setDeletedCount] = useState<number>();
  const [view, setView] = useState<"list" | "create" | "output">("list");
  const [copying, setCopying] = useState(false);
  const [created, setCreated] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"copied" | "failed">();
  const [copiedLinkId, setCopiedLinkId] = useState<string>();
  const { copied, confirmCopied } = useCopyConfirmation();
  const [note, setNote] = useState("");
  const [expiry, setExpiry] = useState("");
  const [choosingExpiry, setChoosingExpiry] = useState(false);
  const [url, setUrl] = useState<string>();
  const [confirmRevoke, setConfirmRevoke] = useState<string>();
  const [failed, setFailed] = useState(false);
  const busy = generating.isLoading || revealing.isLoading || revoking.isLoading || deleting.isLoading || copying;
  const history = !links.isFetching && !links.isError ? links.currentData : undefined;
  const inactiveCount = links.currentData?.inactive_count ?? 0;
  const date = (value: string | null) =>
    value ? new Date(value).toLocaleString(i18n.language) : t("rework.platformAccess.links.never");
  const run = async (action: () => Promise<void>) => {
    setFailed(false);
    try {
      await action();
    } catch {
      setFailed(true);
    }
  };
  const linkUrl = (token: string) => new URL(platformPath(`join-free/${token}`), window.location.origin).toString();
  const copyConfirmed = (linkId?: string) => copied && copyStatus === "copied" && copiedLinkId === linkId;
  const copyAnnouncement = (
    <span className={styles.screenReaderOnly} role="status">
      {copied && copyStatus === "copied" ? t("rework.platformAccess.links.copied") : ""}
    </span>
  );
  const copy = async (value: string, linkId?: string) => {
    setCopyStatus(undefined);
    setCopying(true);
    try {
      await navigator.clipboard.writeText(value);
      setCopiedLinkId(linkId);
      setCopyStatus("copied");
      confirmCopied();
    } catch {
      setCopyStatus("failed");
      setUrl(value);
      setView("output");
    } finally {
      setCopying(false);
    }
  };
  const back = () => {
    if (busy) return;
    setView("list");
    setChoosingExpiry(false);
    setUrl(undefined);
    setCopyStatus(undefined);
    setFailed(false);
  };
  const create = async () => {
    await run(async () => {
      try {
        const result = await generate({
          teamId: team.team_id,
          createPlatformEnrollmentLink: {
            note: note.trim() || null,
            expires_at: expiry ? new Date(expiry).toISOString() : null,
          },
        }).unwrap();
        setCreated(true);
        setUrl(linkUrl(result.token));
        setCopyStatus(undefined);
        setView("output");
        setOffset(0);
        setNote("");
        setExpiry("");
      } finally {
        generating.reset();
      }
    });
  };
  const expiredInput =
    expiry !== "" && (!Number.isFinite(new Date(expiry).getTime()) || new Date(expiry).getTime() <= Date.now());
  return (
    <>
      <Dialog
        open={!confirmRevoke && !confirmCleanup && view === "list"}
        title={t("rework.platformAccess.links.title", { team: team.name || team.team_id })}
        maxWidth={1100}
        hideCancel
        confirmLabel={t("common.close")}
        confirmDisabled={busy}
        onConfirm={() => {
          if (!busy) onClose();
        }}
        onCancel={() => {
          if (!busy) onClose();
        }}
      >
        <div className={styles.dialogBody}>
          {copyAnnouncement}
          <div className={styles.linkToolbar}>
            <p>{t("rework.platformAccess.links.hint")}</p>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={busy || !team.free}
              onClick={() => {
                setFailed(false);
                setCopyStatus(undefined);
                setView("create");
              }}
            >
              {t("rework.platformAccess.createLink")}
            </Button>
          </div>
          <div className={styles.linkControls}>
            <div className={styles.linkFilter}>
              <Select<LinkStatusFilter>
                compact
                size="medium"
                label={t("rework.platformAccess.links.statusLabel")}
                value={status}
                disabled={busy}
                options={(["all", "active", "revoked", "expired"] as const).map((value) => ({
                  key: value,
                  value,
                  label: t(`rework.platformAccess.links.status.${value}`),
                }))}
                onChange={(value) => {
                  setOffset(0);
                  setStatus(value);
                  setFailed(false);
                  setDeletedCount(undefined);
                }}
              />
            </div>
            <Button
              color="error"
              variant="outlined"
              size="medium"
              disabled={busy || links.isFetching || links.isError || !inactiveCount}
              onClick={() => {
                setFailed(false);
                setConfirmCleanup(true);
              }}
            >
              {t("rework.platformAccess.links.cleanup")}
            </Button>
          </div>
          {deletedCount !== undefined && (
            <p role="status">{t("rework.platformAccess.links.deleted", { count: deletedCount })}</p>
          )}
          {links.isFetching && <p role="status">{t("rework.platformAccess.links.loading")}</p>}
          {failed && <p role="alert">{t("rework.platformAccess.failed")}</p>}
          {links.isError && (
            <div role="alert">
              <p>{t("rework.platformAccess.failed")}</p>
              <Button color="primary" variant="outlined" size="small" onClick={() => void links.refetch()}>
                {t("rework.platformAccess.retry")}
              </Button>
            </div>
          )}
          <div className={styles.linkTable}>
            <DataTable
              data={history?.items ?? []}
              rowKey={(link) => link.id}
              rowClassName={(link) => (link.status === "suspended" ? styles.suspendedLink : undefined)}
              serverPagination={{
                offset,
                limit: 25,
                totalCount: links.currentData?.total ?? links.data?.total ?? 0,
                onOffsetChange: setOffset,
              }}
              columns={[
                {
                  label: t("rework.platformAccess.links.note"),
                  size: "2fr",
                  cellRenderer: (link) => (
                    <span className={styles.exampleValue}>
                      {link.note || t("rework.platformAccess.links.untitled")}
                    </span>
                  ),
                },
                {
                  label: t("rework.platformAccess.links.created"),
                  size: "1.5fr",
                  cellRenderer: (link) => date(link.created_at),
                },
                {
                  label: t("rework.platformAccess.links.expiry"),
                  size: "1.5fr",
                  cellRenderer: (link) => date(link.expires_at),
                },
                {
                  label: t("rework.platformAccess.links.statusLabel"),
                  size: "1fr",
                  cellRenderer: (link) => (
                    <span className={link.status === "suspended" ? styles.screenReaderOnly : undefined}>
                      {t(`rework.platformAccess.links.status.${link.status}`)}
                    </span>
                  ),
                },
                {
                  label: t("rework.platformAccess.links.openings"),
                  size: "1fr",
                  cellRenderer: (link) => link.opening_count,
                },
                {
                  label: t("rework.platformAccess.links.actions"),
                  size: "2fr",
                  cellRenderer: (link) => (
                    <div className={styles.row}>
                      <ActionBar
                        alwaysVisible
                        actions={[
                          {
                            id: "copy",
                            icon: copyConfirmed(link.id) ? "check" : "content_copy",
                            label: t(
                              copyConfirmed(link.id)
                                ? "rework.platformAccess.links.copied"
                                : "rework.platformAccess.links.copyUrl",
                            ),
                            disabled: busy || links.isFetching || !link.recoverable,
                            onClick: () =>
                              void run(async () => {
                                try {
                                  const result = await reveal({ teamId: team.team_id, linkId: link.id }).unwrap();
                                  setCreated(false);
                                  await copy(linkUrl(result.token), link.id);
                                } finally {
                                  revealing.reset();
                                }
                              }),
                          },
                        ]}
                      />
                      <Button
                        color="error"
                        variant="outlined"
                        size="small"
                        disabled={busy || links.isFetching || link.status === "revoked"}
                        onClick={() => setConfirmRevoke(link.id)}
                      >
                        {t("rework.platformAccess.links.revoke")}
                      </Button>
                    </div>
                  ),
                },
              ]}
            />
          </div>
        </div>
      </Dialog>
      {confirmCleanup && (
        <Dialog
          open
          title={t("rework.platformAccess.links.cleanupTitle", { team: team.name || team.team_id })}
          confirmColor="error"
          confirmLabel={t("rework.platformAccess.links.cleanupConfirm")}
          confirmDisabled={busy || links.isFetching || links.isError || !inactiveCount}
          onCancel={() => {
            if (!busy) {
              setConfirmCleanup(false);
              setFailed(false);
            }
          }}
          onConfirm={() =>
            void run(async () => {
              const result = await deleteInactive({ teamId: team.team_id }).unwrap();
              setDeletedCount(result.deleted_count);
              setOffset(0);
              setConfirmCleanup(false);
            })
          }
        >
          <div className={styles.dialogBody}>
            <p>
              {t("rework.platformAccess.links.cleanupHint", { team: team.name || team.team_id, count: inactiveCount })}
            </p>
            {failed && <p role="alert">{t("rework.platformAccess.failed")}</p>}
          </div>
        </Dialog>
      )}
      {view === "create" && (
        <Dialog
          open
          title={t("rework.platformAccess.createLink")}
          maxWidth={600}
          confirmLabel={t("rework.platformAccess.createLink")}
          confirmDisabled={busy || !team.free || expiredInput || choosingExpiry}
          onCancel={back}
          onConfirm={() => void create()}
        >
          <div className={`${styles.dialogBody} ${styles.linkCreation}`}>
            <TextInput
              label={t("rework.platformAccess.links.note")}
              value={note}
              maxLength={512}
              disabled={busy || !team.free}
              onChange={(event) => setNote(event.target.value)}
            />
            <PlatformAccessExpirationPicker
              value={expiry}
              disabled={busy || !team.free}
              onChange={setExpiry}
              onOpenChange={setChoosingExpiry}
            />
            {expiredInput && (
              <p id="link-expiry-error" role="alert">
                {t("rework.platformAccess.links.futureExpiry")}
              </p>
            )}
            {failed && <p role="alert">{t("rework.platformAccess.failed")}</p>}
          </div>
        </Dialog>
      )}
      {view === "output" && url && (
        <Dialog
          open
          title={t(created ? "rework.platformAccess.links.createdSuccess" : "rework.platformAccess.links.copyUrl")}
          maxWidth={700}
          confirmLabel={t("common.close")}
          confirmDisabled={busy}
          hideCancel
          onCancel={back}
          onConfirm={back}
        >
          <div className={styles.dialogBody}>
            <TextInput
              label={t("rework.platformAccess.copyLink")}
              value={url}
              readOnly
              onFocus={(event) => event.target.select()}
            />
            <ActionBar
              alwaysVisible
              actions={[
                {
                  id: "copy",
                  icon: copyConfirmed() ? "check" : "content_copy",
                  label: t(
                    copyConfirmed() ? "rework.platformAccess.links.copied" : "rework.platformAccess.links.copyUrl",
                  ),
                  disabled: busy,
                  onClick: () => void copy(url),
                },
              ]}
            />
            {copyStatus === "failed" && <p role="alert">{t("rework.platformAccess.links.copyFailed")}</p>}
            {copyAnnouncement}
          </div>
        </Dialog>
      )}
      {confirmRevoke && (
        <Dialog
          open
          title={t("rework.platformAccess.links.revokeTitle")}
          confirmLabel={t("rework.platformAccess.links.revoke")}
          confirmDisabled={busy}
          onCancel={() => {
            if (!busy) setConfirmRevoke(undefined);
          }}
          onConfirm={() =>
            void run(async () => {
              await revoke({ teamId: team.team_id, linkId: confirmRevoke }).unwrap();
              setUrl(undefined);
              setConfirmRevoke(undefined);
            })
          }
        >
          <div className={styles.dialogBody}>
            <p>{t("rework.platformAccess.links.revokeHint")}</p>
            {failed && <p role="alert">{t("rework.platformAccess.failed")}</p>}
          </div>
        </Dialog>
      )}
    </>
  );
}
