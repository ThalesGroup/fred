// SPDX-License-Identifier: Apache-2.0
import { useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
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
  usePlatformEnrollmentJoinersQuery,
  useGeneratePlatformLinkMutation,
  useRevealPlatformLinkMutation,
  useRevokePlatformLinkMutation,
  useDeleteInactivePlatformLinksMutation,
  usePlatformAccessTeamsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformAccessPage.module.css";

type LinkStatusFilter = Exclude<PlatformEnrollmentLinkInfo["status"], "suspended"> | "all";

const selectUrlFromStart = (input: HTMLInputElement) => {
  input.setSelectionRange(0, input.value.length, "backward");
  input.scrollLeft = 0;
};

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
  const teams = usePlatformAccessTeamsQuery(undefined, {
    refetchOnMountOrArgChange: true,
  });
  const linkAccessEnabled = teams.data?.find((entry) => entry.team_id === team.team_id)?.free ?? team.free;
  const links = usePlatformEnrollmentLinksQuery(
    { teamId: team.team_id, offset, limit: 25, status: status === "all" ? undefined : status },
    {
      refetchOnMountOrArgChange: true,
    },
  );
  const [generate, generating] = useGeneratePlatformLinkMutation();
  const [reveal] = useRevealPlatformLinkMutation();
  const [revoke, revoking] = useRevokePlatformLinkMutation();
  const [deleteInactive, deleting] = useDeleteInactivePlatformLinksMutation();
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [joinersLink, setJoinersLink] = useState<PlatformEnrollmentLinkInfo>();
  const [joinersOffset, setJoinersOffset] = useState(0);
  const joiners = usePlatformEnrollmentJoinersQuery(
    { teamId: team.team_id, linkId: joinersLink?.id ?? "", offset: joinersOffset, limit: 25 },
    { skip: !joinersLink, refetchOnMountOrArgChange: true },
  );
  const [deletedCount, setDeletedCount] = useState<number>();
  const [view, setView] = useState<"list" | "create" | "output">("list");
  const [created, setCreated] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"copied" | "failed">();
  const [copiedLinkId, setCopiedLinkId] = useState<string>();
  const { copied, confirmCopied } = useCopyConfirmation();
  const [note, setNote] = useState("");
  const [expiry, setExpiry] = useState("");
  const [choosingExpiry, setChoosingExpiry] = useState(false);
  const [url, setUrl] = useState<string>();
  const outputInputRef = useRef<HTMLInputElement>(null);
  const copyAttemptRef = useRef(0);
  const returnFocusRef = useRef<{ trigger: HTMLElement | null; dialog: HTMLElement | null } | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<string>();
  const [failed, setFailed] = useState(false);
  const busy = generating.isLoading || revoking.isLoading || deleting.isLoading;
  const history = !links.isError ? links.currentData : undefined;
  const linksLoading = links.isFetching && !history;
  const joinersPage = !joiners.isError ? joiners.currentData : undefined;
  const joinersLoading = joiners.isFetching && !joinersPage;
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
  const linkUrl = (token: string) => new URL(platformPath(`join/${token}`), window.location.origin).toString();
  const rememberFocus = (trigger: HTMLElement) => {
    copyAttemptRef.current += 1;
    returnFocusRef.current = { trigger, dialog: trigger.closest<HTMLElement>('[role="dialog"]') };
    return copyAttemptRef.current;
  };
  const copyConfirmed = (linkId?: string) => copied && copyStatus === "copied" && copiedLinkId === linkId;
  const copyAction = (onClick: () => void, disabled: boolean, linkId?: string) => (
    <ActionBar
      alwaysVisible
      actions={[
        {
          id: "copy",
          icon: copyConfirmed(linkId) ? "check" : "content_copy",
          label: t(
            copyConfirmed(linkId) ? "rework.platformAccess.links.copied" : "rework.platformAccess.links.copyUrl",
          ),
          disabled,
          onClick,
        },
      ]}
    />
  );
  const copyAnnouncement = (
    <span className={styles.screenReaderOnly} role="status">
      {copied && copyStatus === "copied" ? t("rework.platformAccess.links.copied") : ""}
    </span>
  );
  const copy = async (value: string, linkId?: string) => {
    const attempt = ++copyAttemptRef.current;
    setCopyStatus(undefined);
    try {
      await navigator.clipboard.writeText(value);
      if (attempt !== copyAttemptRef.current) return;
      setCopiedLinkId(linkId);
      setCopyStatus("copied");
      confirmCopied();
    } catch {
      if (attempt !== copyAttemptRef.current) return;
      setCopyStatus("failed");
      setUrl(value);
      setView("output");
    }
  };
  const back = () => {
    if (busy) return;
    copyAttemptRef.current += 1;
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
        const createdUrl = linkUrl(result.token);
        setCreated(true);
        setUrl(createdUrl);
        setView("output");
        setOffset(0);
        setNote("");
        setExpiry("");
        void copy(createdUrl);
      } finally {
        generating.reset();
      }
    });
  };
  const expiredInput =
    expiry !== "" && (!Number.isFinite(new Date(expiry).getTime()) || new Date(expiry).getTime() <= Date.now());
  useLayoutEffect(() => {
    if (view !== "output") return;
    const input = outputInputRef.current;
    input?.focus();
    if (input) selectUrlFromStart(input);
  }, [view]);
  useLayoutEffect(() => {
    if (view !== "list" || confirmCleanup || confirmRevoke || joinersLink) return;
    const previous = returnFocusRef.current;
    if (!previous) return;
    returnFocusRef.current = null;
    const trigger = previous.trigger?.isConnected && !previous.trigger.matches(":disabled") ? previous.trigger : null;
    const fallback = previous.dialog?.querySelector<HTMLElement>("button:not([disabled])");
    (trigger ?? fallback)?.focus();
  }, [view, confirmCleanup, confirmRevoke, joinersLink]);
  return (
    <>
      <Dialog
        open
        inactive={view !== "list" || confirmCleanup || !!confirmRevoke || !!joinersLink}
        title={t("rework.platformAccess.links.title", { team: team.name || team.team_id })}
        maxWidth={1100}
        hideCancel
        confirmLabel={t("common.close")}
        confirmDisabled={busy}
        footerStart={
          <Button
            color="error"
            variant="outlined"
            size="small"
            disabled={busy || !history || !inactiveCount}
            onClick={(event) => {
              rememberFocus(event.currentTarget);
              setFailed(false);
              setConfirmCleanup(true);
            }}
          >
            {t("rework.platformAccess.links.cleanup")}
          </Button>
        }
        onConfirm={() => {
          if (!busy) {
            copyAttemptRef.current += 1;
            onClose();
          }
        }}
        onCancel={() => {
          if (!busy) {
            copyAttemptRef.current += 1;
            onClose();
          }
        }}
      >
        <div className={styles.dialogBody}>
          {copyAnnouncement}
          <p className={styles.hint}>{t("rework.platformAccess.links.hint")}</p>
          {!linkAccessEnabled && (
            <p className={styles.linkSuspendedNotice} role="status">
              <span className="material-symbols-outlined" aria-hidden="true">
                link_off
              </span>
              {t("rework.platformAccess.links.suspendedHint")}
            </p>
          )}
          <div className={styles.linkControls}>
            <div>
              <Select<LinkStatusFilter>
                compact
                size="small"
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
              color="primary"
              variant="filled"
              size="small"
              disabled={busy || !linkAccessEnabled}
              onClick={(event) => {
                rememberFocus(event.currentTarget);
                setFailed(false);
                setCopyStatus(undefined);
                setView("create");
              }}
            >
              {t("rework.platformAccess.createLink")}
            </Button>
          </div>
          {deletedCount !== undefined && (
            <p role="status">{t("rework.platformAccess.links.deleted", { count: deletedCount })}</p>
          )}
          {linksLoading && <Spinner statusText={t("rework.platformAccess.links.loading")} />}
          {failed && <p role="alert">{t("rework.platformAccess.failed")}</p>}
          {links.isError && (
            <div role="alert">
              <p>{t("rework.platformAccess.failed")}</p>
              <Button color="primary" variant="outlined" size="small" onClick={() => void links.refetch()}>
                {t("rework.platformAccess.retry")}
              </Button>
            </div>
          )}
          <div className={styles.boundedTable}>
            <DataTable
              size="small"
              data={history?.items ?? []}
              rowKey={(link) => link.id}
              rowClassName={(link) =>
                !linkAccessEnabled || link.status === "suspended" ? styles.suspendedLink : undefined
              }
              serverPagination={{
                offset,
                limit: 25,
                totalCount: links.currentData?.total ?? links.data?.total ?? 0,
                onOffsetChange: setOffset,
              }}
              columns={[
                {
                  label: t("rework.platformAccess.links.noteColumn"),
                  size: "2fr",
                  cellRenderer: (link) => <span className={styles.exampleValue}>{link.note}</span>,
                },
                {
                  label: t("rework.platformAccess.links.created"),
                  size: "1.5fr",
                  cellRenderer: (link) => date(link.created_at),
                },
                {
                  label: t("rework.platformAccess.links.expiryColumn"),
                  size: "1.5fr",
                  cellRenderer: (link) => date(link.expires_at),
                },
                {
                  label: t("rework.platformAccess.links.statusLabel"),
                  size: "1fr",
                  cellRenderer: (link) => t(`rework.platformAccess.links.status.${link.status}`),
                },
                {
                  label: t("rework.platformAccess.links.openings"),
                  size: "1fr",
                  cellRenderer: (link) => link.opening_count,
                },
                {
                  label: t("rework.platformAccess.links.actions"),
                  size: "8.5rem",
                  cellRenderer: (link) => (
                    <ActionBar
                      alwaysVisible
                      className={styles.linkActions}
                      actions={[
                        {
                          id: "copy",
                          icon: copyConfirmed(link.id) ? "check" : "content_copy",
                          label: t(
                            copyConfirmed(link.id)
                              ? "rework.platformAccess.links.copied"
                              : "rework.platformAccess.links.copyUrl",
                          ),
                          disabled: busy || !link.recoverable,
                          onClick: (event) => {
                            const attempt = rememberFocus(event.currentTarget);
                            void run(async () => {
                              const result = await reveal({ teamId: team.team_id, linkId: link.id }).unwrap();
                              if (attempt !== copyAttemptRef.current) return;
                              setCreated(false);
                              await copy(linkUrl(result.token), link.id);
                            });
                          },
                        },
                        {
                          id: "joiners",
                          icon: "group",
                          label: t("rework.platformAccess.links.joiners"),
                          disabled: busy,
                          onClick: (event) => {
                            rememberFocus(event.currentTarget);
                            setJoinersOffset(0);
                            setJoinersLink(link);
                          },
                        },
                        {
                          id: "revoke",
                          icon: "block",
                          label: t("rework.platformAccess.links.revoke"),
                          disabled: busy || link.status === "revoked",
                          onClick: (event) => {
                            rememberFocus(event.currentTarget);
                            setConfirmRevoke(link.id);
                          },
                        },
                      ]}
                    />
                  ),
                },
              ]}
            />
          </div>
        </div>
      </Dialog>
      {joinersLink && (
        <Dialog
          open
          title={
            joinersLink.note
              ? t("rework.platformAccess.links.joinersTitle", { note: joinersLink.note })
              : t("rework.platformAccess.links.joiners")
          }
          maxWidth={900}
          hideCancel
          confirmLabel={t("rework.back")}
          footerStart={
            <IconButton
              type="button"
              color="primary"
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "refresh" }}
              title={t("common.refresh")}
              aria-label={t("common.refresh")}
              loading={joiners.isFetching || links.isFetching}
              onClick={() => {
                void joiners.refetch();
                void links.refetch();
              }}
            />
          }
          onCancel={() => setJoinersLink(undefined)}
          onConfirm={() => setJoinersLink(undefined)}
        >
          <div className={styles.dialogBody}>
            {joinersLoading && <Spinner statusText={t("rework.platformAccess.links.loading")} />}
            {joiners.isError && (
              <div role="alert">
                <p>{t("rework.platformAccess.links.joinersFailed")}</p>
                <Button color="primary" variant="outlined" size="small" onClick={() => void joiners.refetch()}>
                  {t("rework.platformAccess.retry")}
                </Button>
              </div>
            )}
            {joinersPage?.total === 0 && <p>{t("rework.platformAccess.links.noJoiners")}</p>}
            {!!joinersPage?.total && (
              <DataTable
                size="small"
                data={joinersPage.items}
                rowKey={(person) => person.user_id}
                rowClassName={(person) => (person.deleted ? styles.deletedJoiner : undefined)}
                serverPagination={{
                  offset: joinersOffset,
                  limit: 25,
                  totalCount: joinersPage.total,
                  onOffsetChange: setJoinersOffset,
                }}
                columns={[
                  {
                    label: t("rework.platformAccess.links.username"),
                    cellRenderer: (person) => (
                      <span className={styles.joinerUsername}>
                        <span className={styles.joinerUsernameText} title={person.username || "-"}>
                          {person.username || "-"}
                        </span>
                        {person.deleted && <span>({t("rework.platformAccess.links.deletedUser")})</span>}
                      </span>
                    ),
                  },
                  {
                    label: t("rework.teamSettings.members.table.firstName"),
                    cellRenderer: (person) => person.first_name || "-",
                  },
                  {
                    label: t("rework.teamSettings.members.table.lastName"),
                    cellRenderer: (person) => person.last_name || "-",
                  },
                  {
                    label: t("rework.platformAccess.links.joinedAt"),
                    cellRenderer: (person) => date(person.joined_at),
                  },
                ]}
              />
            )}
          </div>
        </Dialog>
      )}
      {confirmCleanup && (
        <Dialog
          open
          title={t("rework.platformAccess.links.cleanupTitle", { team: team.name || team.team_id })}
          confirmColor="error"
          confirmLabel={t("rework.platformAccess.links.cleanupConfirm")}
          confirmDisabled={busy || !history || !inactiveCount}
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
      {(view === "create" || (view === "output" && url)) && (
        <Dialog
          open
          title={
            view === "create"
              ? t("rework.platformAccess.createLink")
              : t(created ? "rework.platformAccess.links.createdSuccess" : "rework.platformAccess.links.copyUrl")
          }
          maxWidth={700}
          confirmLabel={t(view === "create" ? "rework.platformAccess.createLink" : "common.close")}
          confirmDisabled={view === "create" ? busy || !linkAccessEnabled || expiredInput || choosingExpiry : busy}
          hideCancel={view === "output"}
          onCancel={back}
          onConfirm={view === "create" ? () => void create() : back}
        >
          {view === "create" ? (
            <div className={`${styles.dialogBody} ${styles.linkCreation}`}>
              <TextInput
                label={t("rework.platformAccess.links.note")}
                value={note}
                maxLength={512}
                disabled={busy || !linkAccessEnabled}
                onChange={(event) => setNote(event.target.value)}
              />
              <PlatformAccessExpirationPicker
                value={expiry}
                disabled={busy || !linkAccessEnabled}
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
          ) : url ? (
            <div className={styles.dialogBody}>
              <TextInput
                ref={outputInputRef}
                className={styles.linkUrlInput}
                label={t("rework.platformAccess.copyLink")}
                value={url}
                readOnly
                onFocus={(event) => selectUrlFromStart(event.currentTarget)}
              />
              {copyAction(() => void copy(url), busy)}
              {copyStatus === "failed" && <p role="alert">{t("rework.platformAccess.links.copyFailed")}</p>}
              {copyAnnouncement}
            </div>
          ) : null}
        </Dialog>
      )}
      {confirmRevoke && (
        <Dialog
          open
          title={t("rework.platformAccess.links.revokeTitle")}
          confirmColor="error"
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
