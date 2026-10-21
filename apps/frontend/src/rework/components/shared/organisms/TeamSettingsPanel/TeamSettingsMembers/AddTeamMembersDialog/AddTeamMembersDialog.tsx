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
import TeamRoleChips from "@shared/molecules/TeamRoleChips/TeamRoleChips.tsx";
import AddPeopleDialog from "@shared/organisms/AddPeopleDialog/AddPeopleDialog.tsx";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { canAdministerTeamRole } from "@hooks/teamCapabilities.ts";
import {
  TeamWithPermissions,
  UserSummary,
  UserTeamRelation,
} from "../../../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import {
  useAddTeamMemberMutation,
  useGrantTeamMemberRoleMutation,
  useSearchCandidateTeamMembersQuery,
} from "../../../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements";

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
      // Always add on the team_member baseline, then grant every selected
      // elevated role as its own tuple on top — never add directly on an
      // elevated relation. A member added straight onto e.g. team_editor
      // with no separate team_member tuple has no floor to fall back to:
      // revoking their only elevated role would leave them with zero
      // relations at all, which the backend correctly refuses ("would
      // silently remove them from the team"). Every held role must stay
      // revocable down to plain membership, never to nothing. Errors
      // surface via toast (below) but don't block the rest of the batch or
      // keep the dialog open — the table reflects whatever actually
      // succeeded.
      const addResult = await runMutationAction({
        action: () =>
          addTeamMember({
            teamId: team.id,
            addTeamMemberRequest: { user_id: member.user.id, relation: "team_member" },
          }).unwrap(),
        onError: (error) =>
          notifyApiError(error, {
            summary: t("rework.teamSettings.members.addMembersDialog.errors.addSummary"),
            fallbackDetail: t("rework.teamSettings.members.addMembersDialog.errors.addDetail"),
            forbiddenDetail: t("rework.teamSettings.members.errors.forbiddenDetail"),
          }),
      });
      // addTeamMember resolves 204 No Content -> `data` is `null` on
      // success. Branch on `.ok`, never on the resolved value itself —
      // `T | null` can't tell "failed" apart from "succeeded with a
      // falsy/empty result", which every add/grant call here actually
      // returns. Checking `=== null` silently skipped every grant below
      // for every member, on every add, always.
      if (!addResult.ok) continue;

      for (const role of member.roles) {
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
    <AddPeopleDialog<UserSummary>
      open={open}
      title={t("rework.teamSettings.members.addMembersDialog.title")}
      subtitle={t("rework.teamSettings.members.addMembersDialog.subtitle")}
      searchPlaceholder={t("rework.teamSettings.members.addMembersDialog.searchPlaceholder")}
      onSearchChange={setSearchQuery}
      options={suggestions.map((user) => ({ label: candidateLabel(user), value: user, key: user.id }))}
      onSelect={handleSelectCandidate}
      pending={pendingMembers.map((member) => member.user)}
      pendingKey={(user) => user.id}
      pendingLabel={candidateLabel}
      pendingAddon={(user) => (
        <TeamRoleChips
          heldRoles={pendingMembers.find((member) => member.user.id === user.id)?.roles ?? []}
          canAdminister={(role) => canAdministerTeamRole(capabilities, role)}
          onToggle={(role, held) => handleToggleRole(user.id, role, held)}
        />
      )}
      pendingListHeader={t("rework.teamSettings.members.addMembersDialog.pendingListHeader")}
      pendingListEmpty={t("rework.teamSettings.members.addMembersDialog.pendingListEmpty")}
      removeAriaLabel={(user) =>
        t("rework.teamSettings.members.addMembersDialog.removeAria", { name: candidateLabel(user) })
      }
      onRemove={(user) => handleRemovePending(user.id)}
      cancelLabel={t("rework.teamSettings.members.addMembersDialog.cancel")}
      confirmLabel={t("rework.teamSettings.members.addMembersDialog.confirm")}
      confirmDisabled={pendingMembers.length === 0 || isSubmitting}
      onConfirm={handleConfirm}
      onClose={onClose}
    />
  );
}
