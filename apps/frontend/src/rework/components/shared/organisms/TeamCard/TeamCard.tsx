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

import styles from "./TeamCard.module.scss";
import { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useJoinTeamMutation } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials.tsx";
import { PERSONAL_TEAM_COLOR, teamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import { useTranslation } from "react-i18next";
import AvatarGroup from "@shared/molecules/AvatarGroup/AvatarGroup.tsx";
import { useFrontendProperties } from "src/hooks/useFrontendProperties";
import { useFrontendBootstrap } from "src/hooks/useFrontendBootstrap";
import Button from "@shared/atoms/Button/Button.tsx";
import React from "react";
import { KeyCloakService } from "../../../../../security/KeycloakService.ts";
import { getConfig } from "src/common/config";
import { normalizeBasename } from "../../../../utils/documentViewerUtils";

export interface TeamCardProps {
  team: Team;
  withDescription: boolean;
  /** Called after a successful self-service join (JoiningMode.OPEN) — lets the
   * page refresh anything derived outside this card's own team-list cache
   * (e.g. the bootstrap-driven team navbar). */
  onJoined?: () => void;
}

export default function TeamCard({ team, withDescription, onJoined }: TeamCardProps) {
  const { defaultTeamAvatarFile, defaultPersonalAvatarFile, siteTitle, siteSubtitle } = useFrontendProperties();
  const { activeTeam } = useFrontendBootstrap();
  const { t } = useTranslation();
  const [joinTeam, { isLoading: isJoining }] = useJoinTeamMutation();
  const userFullName = KeyCloakService.GetUserFullName();
  const username = KeyCloakService.GetUserName();

  // A configured default avatar replaces initials; without one, the card keeps
  // the name-derived coloured initials. The personal space renders round, teams
  // square (#2300 — the team image is now a square avatar, not a wide banner).
  const isPersonal = team.id === activeTeam?.id;
  const avatarFile = isPersonal ? defaultPersonalAvatarFile : defaultTeamAvatarFile;
  const color = isPersonal ? PERSONAL_TEAM_COLOR : teamColor(team.name);
  const avatarName = isPersonal ? userFullName : team.name;
  const roundAvatar = isPersonal ? { borderRadius: "50%" } : undefined;

  const handleJoinTeam = async (e: React.MouseEvent<HTMLButtonElement>): Promise<void> => {
    e.preventDefault();
    try {
      await joinTeam({ teamId: team.id }).unwrap();
      onJoined?.();
    } catch (error) {
      console.error("Join team error:", error);
    }
  };

  // A public invite-only team gets a prefilled mail to its admins
  // instead of a dead-end label. Public only (never hand a non-member a
  // private team's addresses), and only when one resolved - nobody to write
  // to otherwise. Full rationale: COMPONENT-UX.md `TeamCard`.
  const canJoinDirectly = !team.is_member && team.joining_mode === "open";
  const isInviteOnlyOutsider = !team.is_member && team.joining_mode === "invite_only";
  const adminEmails = (team.admins ?? [])
    .map((admin) => admin.email)
    .filter((email): email is string => Boolean(email));
  const canRequestInvitation = isInviteOnlyOutsider && team.visibility === "public" && adminEmails.length > 0;

  const handleRequestInvitation = (e: React.MouseEvent<HTMLButtonElement>): void => {
    e.preventDefault();
    const site = [siteTitle, siteSubtitle].filter(Boolean).join(" ");
    // Keycloak omits `name` / `preferred_username` on some accounts.
    const user = [userFullName, username && `(${username})`].filter(Boolean).join(" ");
    // Two links: the team page for context, and the members page where the
    // recipients - its admins - actually add the sender. A mailed link
    // inherits no router basename.
    const teamPath = `${window.location.origin}${normalizeBasename(getConfig().frontend_basename)}/team/${team.id}`;
    // Comma-separated and encoded per RFC 6068 - the addresses come from a
    // directory sync, so nothing guarantees they are URL-safe.
    const recipients = adminEmails.map(encodeURIComponent).join(",");
    const params = new URLSearchParams({
      subject: t("rework.teamCard.invitationMail.subject", { site, team: team.name }),
      body: t("rework.teamCard.invitationMail.body", {
        site,
        team: team.name,
        user,
        agentsUrl: `${teamPath}/agents`,
        membersUrl: `${teamPath}/settings/members`,
      }),
    });
    // `+` back to %20 or mail clients render it literally in the subject.
    const href = `mailto:${recipients}?${params.toString().replace(/\+/g, "%20")}`;
    // A new tab: a webmail registered for mailto: would otherwise replace the
    // app. `noopener` makes window.open return null, so no fallback to test.
    window.open(href, "_blank", "noopener,noreferrer");
  };

  return (
    <div className={styles.teamCardContainer}>
      <div className={styles.teamCardDetails}>
        <div className={styles.teamCardHeader}>
          {team.avatar_image_url ? (
            <img
              className={styles.teamAvatar}
              style={roundAvatar}
              src={team.avatar_image_url}
              alt=""
              aria-hidden="true"
            />
          ) : avatarFile ? (
            <img
              className={styles.teamAvatar}
              style={roundAvatar}
              src={`/images/${avatarFile}`}
              alt=""
              aria-hidden="true"
            />
          ) : (
            <TeamInitials
              className={styles.teamAvatar}
              name={avatarName}
              size="medium"
              shape={isPersonal ? "round" : "square"}
              color={color}
            />
          )}
          <div className={styles.teamCardHeaderText}>
            <div className={styles.teamName}>{team.name}</div>
            <div className={styles.teamMemberCount}>
              <span className={styles.teamMemberCountIcon}>
                <Icon category={"outlined"} type={"groups"} />
              </span>
              {t("rework.teamCard.memberCount", { count: team.member_count })}
            </div>
          </div>
        </div>
        {withDescription && <div className={styles.teamCardDescription}>{team.description}</div>}
        <div className={styles.teamCardFooter}>
          <div className={styles.teamCardAdmins}>
            <AvatarGroup
              avatars={(team.admins ?? []).map((o) => ({ name: o.first_name + " " + o.last_name }))}
              max={canJoinDirectly || canRequestInvitation ? 2 : 4}
            />
          </div>
          {canJoinDirectly && (
            <Button
              className={styles.teamCardJoinAction}
              color={"primary"}
              variant={"outlined"}
              size={"medium"}
              icon={{ category: "outlined", type: "person_add" }}
              disabled={isJoining}
              onClick={handleJoinTeam}
            >
              {t("rework.teamCard.join")}
            </Button>
          )}
          {canRequestInvitation && (
            <Button
              className={styles.teamCardJoinAction}
              color={"primary"}
              variant={"outlined"}
              size={"medium"}
              icon={{ category: "outlined", type: "mail" }}
              onClick={handleRequestInvitation}
            >
              {t("rework.teamCard.join")}
            </Button>
          )}
          {isInviteOnlyOutsider && !canRequestInvitation && (
            <span className={styles.teamJoiningLabel}>{t("rework.teamCard.inviteOnly")}</span>
          )}
        </div>
      </div>
    </div>
  );
}
