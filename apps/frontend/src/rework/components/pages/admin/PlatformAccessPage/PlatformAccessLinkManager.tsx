// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { platformPath } from "../../../../../common/platformAccess";
import type { PlatformAccessTeam } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  usePlatformEnrollmentLinksQuery,
  useGeneratePlatformLinkMutation,
  useRevealPlatformLinkMutation,
  useRevokePlatformLinkMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformAccessPage.module.css";

export default function PlatformAccessLinkManager({
  team,
  onClose,
}: {
  team: PlatformAccessTeam;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [offset, setOffset] = useState(0);
  const links = usePlatformEnrollmentLinksQuery(
    { teamId: team.team_id, offset, limit: 25 },
    {
      refetchOnMountOrArgChange: true,
      pollingInterval: 30000,
    },
  );
  const [generate, generating] = useGeneratePlatformLinkMutation();
  const [reveal, revealing] = useRevealPlatformLinkMutation();
  const [revoke, revoking] = useRevokePlatformLinkMutation();
  const [note, setNote] = useState("");
  const [expiry, setExpiry] = useState("");
  const [url, setUrl] = useState<string>();
  const [confirmRevoke, setConfirmRevoke] = useState<string>();
  const [failed, setFailed] = useState(false);
  const busy = generating.isLoading || revealing.isLoading || revoking.isLoading;
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
  const show = (token: string) =>
    setUrl(new URL(platformPath(`join-free/${token}`), window.location.origin).toString());
  const expiredInput =
    expiry !== "" && (!Number.isFinite(new Date(expiry).getTime()) || new Date(expiry).getTime() <= Date.now());
  return (
    <>
      <Dialog
        open={!confirmRevoke}
        title={t("rework.platformAccess.links.title", { team: team.name || team.team_id })}
        maxWidth={1100}
        hideCancel
        confirmLabel={t("common.close")}
        onConfirm={onClose}
        onCancel={onClose}
      >
        <p>{t("rework.platformAccess.links.hint")}</p>
        {!team.free && <p role="status">{t("rework.platformAccess.links.suspendedHint")}</p>}
        <div className={styles.linkCreation}>
          <TextInput
            label={t("rework.platformAccess.links.note")}
            value={note}
            maxLength={512}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.preventDefault();
            }}
            disabled={busy || !team.free}
            onChange={(event) => setNote(event.target.value)}
          />
          <TextInput
            label={t("rework.platformAccess.links.expiry")}
            type="datetime-local"
            onKeyDown={(event) => {
              if (event.key === "Enter") event.preventDefault();
            }}
            value={expiry}
            disabled={busy || !team.free}
            onChange={(event) => setExpiry(event.target.value)}
            error={expiredInput ? t("rework.platformAccess.links.futureExpiry") : undefined}
          />
        </div>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          disabled={busy || !team.free || expiredInput}
          onClick={() =>
            void run(async () => {
              const result = await generate({
                teamId: team.team_id,
                createPlatformEnrollmentLink: {
                  note: note.trim() || null,
                  expires_at: expiry ? new Date(expiry).toISOString() : null,
                },
              }).unwrap();
              generating.reset();
              show(result.token);
              setOffset(0);
              setNote("");
              setExpiry("");
            })
          }
        >
          {t("rework.platformAccess.createLink")}
        </Button>
        {url && (
          <div className={styles.linkOutput}>
            <TextInput
              label={t("rework.platformAccess.copyLink")}
              value={url}
              readOnly
              onFocus={(event) => event.target.select()}
            />
            <Button
              color="primary"
              variant="outlined"
              size="small"
              onClick={() => void run(() => navigator.clipboard.writeText(url))}
            >
              {t("common.copy")}
            </Button>
          </div>
        )}
        {failed && <p role="alert">{t("rework.platformAccess.failed")}</p>}
        {links.isError && (
          <div role="alert">
            <p>{t("rework.platformAccess.failed")}</p>
            <Button color="primary" variant="outlined" size="small" onClick={() => void links.refetch()}>
              {t("rework.platformAccess.retry")}
            </Button>
          </div>
        )}
        <DataTable
          data={links.data?.items ?? []}
          rowKey={(link) => link.id}
          serverPagination={{ offset, limit: 25, totalCount: links.data?.total ?? 0, onOffsetChange: setOffset }}
          columns={[
            {
              label: t("rework.platformAccess.links.note"),
              size: "2fr",
              cellRenderer: (link) => (
                <span className={styles.exampleValue}>{link.note || t("rework.platformAccess.links.untitled")}</span>
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
              cellRenderer: (link) => t(`rework.platformAccess.links.status.${link.status}`),
            },
            {
              label: t("rework.platformAccess.links.openings"),
              size: "1fr",
              cellRenderer: (link) => (
                <span>
                  {link.opening_count}
                  <br />
                  {link.last_opened_at && date(link.last_opened_at)}
                </span>
              ),
            },
            {
              label: t("rework.platformAccess.links.actions"),
              size: "2fr",
              cellRenderer: (link) => (
                <div className={styles.row}>
                  <Button
                    color="primary"
                    variant="outlined"
                    size="small"
                    disabled={busy || links.isFetching || !link.recoverable}
                    onClick={() =>
                      void run(async () => {
                        const result = await reveal({ teamId: team.team_id, linkId: link.id }).unwrap();
                        revealing.reset();
                        show(result.token);
                      })
                    }
                  >
                    {t("rework.platformAccess.links.showUrl")}
                  </Button>
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
      </Dialog>
      {confirmRevoke && (
        <Dialog
          open
          title={t("rework.platformAccess.links.revokeTitle")}
          confirmLabel={t("rework.platformAccess.links.revoke")}
          confirmDisabled={busy}
          onCancel={() => setConfirmRevoke(undefined)}
          onConfirm={() =>
            void run(async () => {
              await revoke({ teamId: team.team_id, linkId: confirmRevoke }).unwrap();
              setUrl(undefined);
              setConfirmRevoke(undefined);
            })
          }
        >
          <p>{t("rework.platformAccess.links.revokeHint")}</p>
          {failed && <p role="alert">{t("rework.platformAccess.failed")}</p>}
        </Dialog>
      )}
    </>
  );
}
