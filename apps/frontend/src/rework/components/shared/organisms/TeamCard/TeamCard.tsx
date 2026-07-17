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

export interface TeamCardProps {
  team: Team;
  withDescription: boolean;
  canJoin: boolean;
}

export default function TeamCard({ team, withDescription, canJoin }: TeamCardProps) {
  const {
    siteTitle,
    siteSubtitle,
    defaultTeamBannerFile,
    defaultTeamAvatarFile,
    defaultPersonalBannerFile,
    defaultPersonalAvatarFile,
  } = useFrontendProperties();
  const { activeTeam } = useFrontendBootstrap();
  const { t } = useTranslation();
  const userFullName = KeyCloakService.GetUserFullName();
  const username = KeyCloakService.GetUserName();

  // Configured assets replace initials/solid colour. Without configured assets,
  // the card keeps the name-derived solid colour treatment.
  const isPersonal = team.id === activeTeam?.id;
  const bannerFile = isPersonal ? defaultPersonalBannerFile : defaultTeamBannerFile;
  const avatarFile = isPersonal ? defaultPersonalAvatarFile : defaultTeamAvatarFile;
  const color = isPersonal ? PERSONAL_TEAM_COLOR : teamColor(team.name);
  const avatarName = isPersonal ? userFullName : team.name;

  const handleJoinTeam = (e: React.MouseEvent<HTMLButtonElement>, team: Team): void => {
    e.preventDefault();
    if (!team.admins || team.admins.length === 0) return;
    const recipients = team.admins.map((o) => o.email).join(";");
    const subject = `[${siteTitle} ${siteSubtitle}] Demande pour rejoindre l'équipe ${team.name}`;
    const teamUrl = `${window.location.origin}/team/${team.id}/agents`;
    const body = `Bonjour,\n\nJe souhaite rejoindre l'équipe ${team.name} sur ${siteTitle} ${siteSubtitle}.\n\nInformations utilisateur : ${userFullName} (${username})\n\nAller à la page de l'équipe ${team.name} : ${teamUrl}`;
    const params = new URLSearchParams({
      subject: subject,
      body: body,
    });
    window.location.href = `mailto:${recipients}?${params.toString().replace(/\+/g, "%20")}`;
  };

  return (
    <div className={styles.teamCardContainer}>
      {team.banner_image_url || bannerFile ? (
        <img
          className={styles.teamBanner}
          src={team.banner_image_url ?? `/images/${bannerFile}`}
          alt=""
          aria-hidden="true"
        />
      ) : (
        <div className={styles.teamBanner} style={{ background: color.banner }} aria-hidden="true" />
      )}
      {team.banner_image_url ? (
        <img className={styles.teamAvatar} src={team.banner_image_url} alt="" aria-hidden="true" />
      ) : avatarFile ? (
        <img
          className={styles.teamAvatar}
          style={isPersonal ? { borderRadius: "50%" } : undefined}
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
      <div className={styles.teamCardDetails}>
        <div className={styles.teamCardDetailName}>
          <div className={styles.teamInformation}>
            <div className={styles.teamName}>{team.name}</div>
            {team.is_private && (
              <div className={styles.teamPrivateState}>
                <Icon category={"outlined"} type={"lock"} />
              </div>
            )}
          </div>
          <div className={styles.teamMemberCount}>
            <span className={styles.teamMemberCountIcon}>
              <Icon category={"outlined"} type={"groups"} />
            </span>
            {t("rework.teamCard.memberCount", { count: team.member_count })}
          </div>
        </div>
        {withDescription && <div className={styles.teamCardDescription}>{team.description}</div>}
        <div className={styles.teamCardFooter}>
          <AvatarGroup avatars={(team.admins ?? []).map((o) => ({ name: o.first_name + " " + o.last_name }))} />
          {canJoin && (
            <Button
              color={"primary"}
              variant={"text"}
              size={"medium"}
              icon={{ category: "outlined", type: "mail" }}
              onClick={(e) => handleJoinTeam(e, team)}
            >
              {t("rework.teamCard.join")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
