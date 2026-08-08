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

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { KeyCloakService } from "../../../../../../../security/KeycloakService";
import { TeamWithPermissions } from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useListTeamMembersQuery,
  useRemoveTeamMemberMutation,
} from "../../../../../../../slices/controlPlane/controlPlaneApiEnhancements";

interface TeamSettingsMembersMenuProps {
  team: TeamWithPermissions;
}

type MembersMenuAction = "leave";

/**
 * Page-level "more" menu for the team members page, rendered next to the
 * title via `PageHeader`'s `titleAction` slot. Currently holds the AUTHZ-09
 * self-service "leave team" action; disabled for the last remaining
 * team_admin (the "at least one admin" invariant, shared with #1985).
 */
export default function TeamSettingsMembersMenu({ team }: TeamSettingsMembersMenuProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();
  const { canAdministerAdmins } = useTeamCapabilities(team);
  const [removeTeamMember] = useRemoveTeamMemberMutation();

  // Only an admin can ever be blocked from leaving — skip the lookup for
  // everyone else.
  const { data: teamMembers } = useListTeamMembersQuery({ teamId: team.id }, { skip: !canAdministerAdmins });
  const adminCount = teamMembers?.filter((member) => member.relations.includes("team_admin")).length ?? 0;
  const isLastAdmin = canAdministerAdmins && adminCount <= 1;

  const handleLeaveTeam = () => {
    if (isLastAdmin) return;
    showConfirmationDialog({
      title: t("rework.teamSettings.leaveTeam.title"),
      message: t("rework.teamSettings.leaveTeam.message", { teamName: team.name ?? "" }),
      confirmButtonLabel: t("rework.teamSettings.leaveTeam.confirmLabel"),
      criticalAction: true,
      onConfirm: async () => {
        const userId = KeyCloakService.GetUserId();
        if (!userId) return;
        await runMutationAction({
          action: () => removeTeamMember({ teamId: team.id, userId }).unwrap(),
          onError: (error) =>
            notifyApiError(error, {
              summary: t("rework.teamSettings.leaveTeam.errors.summary"),
              fallbackDetail: t("rework.teamSettings.leaveTeam.errors.fallbackDetail"),
              forbiddenDetail: t("rework.teamSettings.members.errors.forbiddenDetail"),
              conflictDetail: t("rework.teamSettings.members.errors.lastOwnerDetail"),
            }),
          onSuccess: () => navigate("/team/personal/agents"),
        });
      },
    });
  };

  return (
    <IconButtonMenu<MembersMenuAction>
      iconButton={{
        color: "on-surface-retreat",
        variant: "icon",
        size: "medium",
        icon: { category: "outlined", type: "more_vert" },
        "aria-label": t("rework.teamSettings.members.moreActions"),
        title: t("rework.teamSettings.members.moreActions"),
      }}
      options={[
        {
          key: "leave",
          value: "leave",
          label: t("rework.teamSettings.navigation.leaveTeam"),
          icon: { category: "outlined", type: "logout" },
          destructive: true,
          disabled: isLastAdmin,
          description: isLastAdmin ? t("rework.teamSettings.leaveTeam.lastAdminTooltip") : undefined,
        },
      ]}
      onSelect={() => handleLeaveTeam()}
    />
  );
}
