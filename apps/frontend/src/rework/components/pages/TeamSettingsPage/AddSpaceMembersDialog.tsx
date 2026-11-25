// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { useGrantMutation } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Role } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import SpaceMemberPicker, { SPACE_ROLES, type PendingMember } from "./SpaceMemberPicker";
import styles from "./AddSpaceMembersDialog.module.scss";

/** Picks people the server lists as eligible and grants their roles in one explicit step. */
export default function AddSpaceMembersDialog({
  spaceId,
  kind,
  roles = SPACE_ROLES,
  onClose,
}: {
  spaceId: string;
  kind: "team" | "project" | "organization";
  /** The roles offered; an organization only adds observers here. */
  roles?: Role[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<PendingMember[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<"conflict" | "forbidden" | "failed">();
  const [grant] = useGrantMutation();

  const confirm = async () => {
    if (submitting || pending.length === 0 || pending.some((item) => item.roles.length === 0)) return;
    setSubmitting(true);
    setError(undefined);
    let failure: unknown;
    const remaining: PendingMember[] = [];
    for (const item of pending) {
      const failed: Role[] = [];
      for (const role of item.roles) {
        try {
          await grant({ id: spaceId, user: item.user.id, role }).unwrap();
        } catch (caught) {
          failure ??= caught;
          failed.push(role);
        }
      }
      if (failed.length) remaining.push({ ...item, roles: failed });
    }
    setSubmitting(false);
    // Granting refreshes the roster through the SpaceMembers tag; only what failed stays selected.
    if (!remaining.length) return onClose();
    const { status } = normalizeApiError(failure);
    setPending(remaining);
    setError(status === 409 ? "conflict" : status === 403 ? "forbidden" : "failed");
  };

  return (
    <Dialog
      open
      maxWidth={640}
      title={t("rework.teamSettings.members.addMembersDialog.title")}
      confirmLabel={t("rework.teamSettings.members.addMembersDialog.confirm")}
      confirmDisabled={submitting || pending.length === 0 || pending.some((item) => item.roles.length === 0)}
      dismissible={!submitting}
      onConfirm={() => void confirm()}
      onCancel={() => {
        if (!submitting) onClose();
      }}
    >
      <div className={styles.body}>
        <SpaceMemberPicker
          spaceId={spaceId}
          source="candidates"
          eligibility={t(`rework.spaceMembers.add.eligibility.${kind}`)}
          roles={roles}
          pending={pending}
          onPendingChange={setPending}
          disabled={submitting}
        />
        {pending.some((item) => item.roles.length === 0) && (
          <span className={styles.hint}>{t("rework.spaceMembers.add.roleRequired")}</span>
        )}
        {error && (
          <span role="alert" className={styles.error}>
            {t(`rework.spaceMembers.${error}`)}
          </span>
        )}
      </div>
    </Dialog>
  );
}
