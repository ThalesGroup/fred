// SPDX-License-Identifier: Apache-2.0
// A team link grants Member only within its organization. Disabling revokes it.
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Switch from "@shared/atoms/Switch/Switch";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { useCopyConfirmation } from "@hooks/useCopyConfirmation";
import { platformPath } from "../../../../../../../common/platformAccess";
import {
  useCreateTeamJoinLinkMutation,
  useRevokeTeamJoinLinkMutation,
  useTeamJoinLinkQuery,
} from "../../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./TeamInviteLinkDialog.module.scss";

interface TeamInviteLinkDialogProps {
  teamId: string;
  onClose: () => void;
}

export default function TeamInviteLinkDialog({ teamId, onClose }: TeamInviteLinkDialogProps) {
  const { t } = useTranslation();
  const link = useTeamJoinLinkQuery({ id: teamId }, { refetchOnMountOrArgChange: true });
  const [revoke, setting] = useRevokeTeamJoinLinkMutation();
  const [regenerate, regenerating] = useCreateTeamJoinLinkMutation();
  const { copied, confirmCopied } = useCopyConfirmation();
  const [failed, setFailed] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const urlRef = useRef<HTMLInputElement>(null);
  const labelId = useId();
  const busy = link.isFetching || setting.isLoading || regenerating.isLoading;
  const enabled =
    !link.isError && !!link.currentData?.token && new Date(link.currentData.expires_at).getTime() > Date.now();
  const { refetch } = link;
  useEffect(() => {
    if (!link.currentData) return;
    const delay = new Date(link.currentData.expires_at).getTime() - Date.now();
    if (delay <= 0) return;
    const timer = setTimeout(() => void refetch(), Math.min(delay + 100, 2_147_483_647));
    return () => clearTimeout(timer);
  }, [link.currentData, refetch]);
  const url =
    enabled && link.currentData?.token
      ? new URL(platformPath(`join/${link.currentData.token}`), window.location.origin).toString()
      : "";

  const run = async (action: () => Promise<unknown>) => {
    setFailed(false);
    setCopyFailed(false);
    try {
      await action();
    } catch {
      setFailed(true);
    }
  };
  const toggleDisabled = busy || link.isError;
  const toggle = (next: boolean) => {
    if (!toggleDisabled) void run(() => (next ? regenerate({ id: teamId }) : revoke({ id: teamId })).unwrap());
  };
  const copy = async () => {
    setCopyFailed(false);
    try {
      await navigator.clipboard.writeText(url);
      confirmCopied();
    } catch {
      // Leave the URL selected so the person can copy it by hand.
      setCopyFailed(true);
      urlRef.current?.focus();
      urlRef.current?.select();
    }
  };

  return (
    <Dialog
      open
      title={t("rework.teamSettings.members.inviteLink.title")}
      maxWidth={560}
      dense
      hideCancel
      confirmLabel={t("common.close")}
      onConfirm={onClose}
      onCancel={onClose}
    >
      <div className={styles.body}>
        {/* The whole card toggles; the switch stays the single focusable control. */}
        <div
          className={styles.toggle}
          data-enabled={enabled}
          data-disabled={toggleDisabled}
          onClick={() => toggle(!enabled)}
        >
          <span className={styles.toggleText}>
            <span id={labelId}>{t("rework.teamSettings.members.inviteLink.enable")}</span>
            <span className={styles.hint}>{t("rework.teamSettings.members.inviteLink.hint")}</span>
          </span>
          <span onClick={(event) => event.stopPropagation()}>
            <Switch
              size="small"
              checked={enabled}
              disabled={toggleDisabled}
              aria-labelledby={labelId}
              onChange={(event) => toggle(event.target.checked)}
            />
          </span>
        </div>
        {enabled && link.currentData && (
          <p className={styles.hint}>
            {t("rework.teamSettings.members.inviteLink.expires", {
              date: new Date(link.currentData.expires_at).toLocaleString(),
            })}
          </p>
        )}
        <div className={styles.link} data-disabled={!enabled}>
          {url && (
            <div className={styles.urlRow}>
              <div className={styles.url}>
                <TextInput
                  ref={urlRef}
                  className={styles.urlInput}
                  size="xs"
                  compact
                  aria-label={t("rework.teamSettings.members.inviteLink.urlLabel")}
                  value={url}
                  readOnly
                  disabled={!enabled}
                />
              </div>
              <Button
                color="primary"
                variant="outlined"
                size="small"
                disabled={!enabled || busy}
                icon={{ category: "outlined", type: copied ? "check" : "content_copy" }}
                onClick={() => void copy()}
              >
                {t(
                  copied
                    ? "rework.teamSettings.members.inviteLink.copied"
                    : "rework.teamSettings.members.inviteLink.copy",
                )}
              </Button>
            </div>
          )}
          {url && (
            <div>
              <Button
                color="primary"
                variant="text"
                size="small"
                disabled={!enabled || busy}
                icon={{ category: "outlined", type: "refresh" }}
                onClick={() => void run(() => regenerate({ id: teamId }).unwrap())}
              >
                {t("rework.teamSettings.members.inviteLink.regenerate")}
              </Button>
            </div>
          )}
          <span className={styles.screenReaderOnly} role="status">
            {copied ? t("rework.teamSettings.members.inviteLink.copied") : ""}
          </span>
          {copyFailed && (
            <p className={styles.message} role="alert">
              {t("rework.teamSettings.members.inviteLink.copyFailed")}
            </p>
          )}
        </div>
        {(failed || link.isError) && (
          <p className={styles.message} role="alert">
            {t("rework.teamSettings.members.inviteLink.failed")}
          </p>
        )}
      </div>
    </Dialog>
  );
}
