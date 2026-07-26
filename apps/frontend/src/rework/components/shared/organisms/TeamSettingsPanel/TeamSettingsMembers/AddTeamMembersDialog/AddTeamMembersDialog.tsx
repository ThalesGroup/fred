// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Autocomplete from "@shared/molecules/Autocomplete/Autocomplete.tsx";
import TeamRoleChips, { ELEVATED_TEAM_ROLES } from "@shared/molecules/TeamRoleChips/TeamRoleChips.tsx";
import { Portal } from "@shared/utils/Portal.tsx";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { canAdministerTeamRole } from "@hooks/teamCapabilities.ts";
import {
  TeamWithPermissions,
  UserSummary,
  UserTeamRelation,
} from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useAddTeamMemberMutation,
  useGrantTeamMemberRoleMutation,
  useSearchCandidateTeamMembersQuery,
} from "../../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./AddTeamMembersDialog.module.scss";

interface PendingMember {
  user: UserSummary;
  roles: UserTeamRelation[];
}

interface AddTeamMembersDialogProps {
  open: boolean;
  team: TeamWithPermissions;
  onClose: () => void;
}

function candidateLabel(user: UserSummary): string {
  return `${user.first_name ?? ""} ${user.last_name ?? ""} (${user.username ?? user.id})`;
}

export default function AddTeamMembersDialog({ open, team, onClose }: AddTeamMembersDialogProps) {
  const { t } = useTranslation();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();
  const capabilities = useTeamCapabilities(team);

  const [searchQuery, setSearchQuery] = useState("");
  const [pendingMembers, setPendingMembers] = useState<PendingMember[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const trimmedQuery = searchQuery.trim();
  const { data: candidates = [] } = useSearchCandidateTeamMembersQuery(
    { teamId: team.id, query: trimmedQuery },
    { skip: !open || trimmedQuery.length < 2 },
  );
  const pendingIds = new Set(pendingMembers.map((m) => m.user.id));
  const suggestions = candidates.filter((user) => !pendingIds.has(user.id));

  const [addTeamMember] = useAddTeamMemberMutation();
  const [grantTeamMemberRole] = useGrantTeamMemberRoleMutation();

  // Fresh slate on every open — a cancelled or completed run shouldn't leak
  // into the next one.
  useEffect(() => {
    if (open) {
      setPendingMembers([]);
      setSearchQuery("");
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const handleSelectCandidate = (user: UserSummary) => {
    setPendingMembers((prev) => (prev.some((m) => m.user.id === user.id) ? prev : [...prev, { user, roles: [] }]));
  };

  const handleToggleRole = (userId: string, role: UserTeamRelation, held: boolean) => {
    setPendingMembers((prev) =>
      prev.map((m) =>
        m.user.id === userId ? { ...m, roles: held ? m.roles.filter((r) => r !== role) : [...m.roles, role] } : m,
      ),
    );
  };

  const handleRemovePending = (userId: string) => {
    setPendingMembers((prev) => prev.filter((m) => m.user.id !== userId));
  };

  const handleConfirm = async () => {
    if (pendingMembers.length === 0 || isSubmitting) return;
    setIsSubmitting(true);

    for (const member of pendingMembers) {
      // AddTeamMemberRequest only carries one relation — add with the
      // highest-priority selected role (falling back to the implicit
      // `team_member` baseline), then grant any other selected elevated
      // role one at a time, exactly like the members table already does
      // for role changes on existing members. Errors surface via toast
      // (below) but don't block the rest of the batch or keep the dialog
      // open — the table reflects whatever actually succeeded.
      const initialRole = ELEVATED_TEAM_ROLES.find((role) => member.roles.includes(role)) ?? "team_member";
      const additionalRoles = member.roles.filter((role) => role !== initialRole);

      const added = await runMutationAction({
        action: () =>
          addTeamMember({
            teamId: team.id,
            addTeamMemberRequest: { user_id: member.user.id, relation: initialRole },
          }).unwrap(),
        onError: (error) =>
          notifyApiError(error, {
            summary: t("rework.teamSettings.members.addMembersDialog.errors.addSummary"),
            fallbackDetail: t("rework.teamSettings.members.addMembersDialog.errors.addDetail"),
            forbiddenDetail: t("rework.teamSettings.members.errors.forbiddenDetail"),
          }),
      });
      if (added === null) continue;

      for (const role of additionalRoles) {
        await runMutationAction({
          action: () =>
            grantTeamMemberRole({
              teamId: team.id,
              userId: member.user.id,
              grantTeamMemberRoleRequest: { relation: role },
            }).unwrap(),
          // Names the user and role explicitly (rather than the table's
          // generic "failed to update role" toast) — a dropped grant here
          // is otherwise silent: the member still gets added, just missing
          // one of the roles picked for them.
          onError: (error) =>
            notifyApiError(error, {
              summary: t("rework.teamSettings.members.errors.grantSummary"),
              fallbackDetail: t("rework.teamSettings.members.errors.grantDetail", {
                name: candidateLabel(member.user),
                role: t(`rework.teamRoles.${role}`),
              }),
              forbiddenDetail: t("rework.teamSettings.members.errors.forbiddenDetail"),
            }),
        });
      }
    }

    setIsSubmitting(false);
    onClose();
  };

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onClose}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby="add-team-members-dialog-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.header}>
            <p id="add-team-members-dialog-title" className={styles.title}>
              {t("rework.teamSettings.members.addMembersDialog.title")}
            </p>
            <p className={styles.subtitle}>{t("rework.teamSettings.members.addMembersDialog.subtitle")}</p>
          </div>

          <div className={styles.searchRow}>
            <Autocomplete<UserSummary>
              textInput={{
                placeholder: t("rework.teamSettings.members.addMembersDialog.searchPlaceholder"),
                icon: { category: "outlined", type: "search" },
              }}
              minQueryLength={2}
              onFieldValueChange={setSearchQuery}
              options={suggestions.map((user) => ({ label: candidateLabel(user), value: user, key: user.id }))}
              onSelect={handleSelectCandidate}
            />
          </div>

          <div className={styles.pendingListContainer}>
            <div className={styles.pendingListHeader}>
              {t("rework.teamSettings.members.addMembersDialog.pendingListHeader")}
            </div>
            {pendingMembers.length > 0 ? (
              <ul className={styles.pendingList}>
                {pendingMembers.map((member) => (
                  <li key={member.user.id} className={styles.pendingRow}>
                    <span className={styles.pendingName}>{candidateLabel(member.user)}</span>
                    <div className={styles.pendingRoleChips}>
                      <TeamRoleChips
                        heldRoles={member.roles}
                        canAdminister={(role) => canAdministerTeamRole(capabilities, role)}
                        onToggle={(role, held) => handleToggleRole(member.user.id, role, held)}
                      />
                    </div>
                    <IconButton
                      variant="icon"
                      size="medium"
                      icon={{ category: "outlined", type: "close" }}
                      aria-label={t("rework.teamSettings.members.addMembersDialog.removeAria", {
                        name: candidateLabel(member.user),
                      })}
                      onClick={() => handleRemovePending(member.user.id)}
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <div className={styles.pendingListEmpty}>
                {t("rework.teamSettings.members.addMembersDialog.pendingListEmpty")}
              </div>
            )}
          </div>

          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="medium" onClick={onClose}>
              {t("rework.teamSettings.members.addMembersDialog.cancel")}
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={pendingMembers.length === 0 || isSubmitting}
              onClick={handleConfirm}
            >
              {t("rework.teamSettings.members.addMembersDialog.confirm")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
