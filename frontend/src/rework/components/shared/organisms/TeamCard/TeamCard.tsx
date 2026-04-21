import styles from "./TeamCard.module.scss";
import { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { useTranslation } from "react-i18next";
import AvatarGroup from "@shared/molecules/AvatarGroup/AvatarGroup.tsx";
import { useFrontendProperties } from "src/hooks/useFrontendProperties";
import Button from "@shared/atoms/Button/Button.tsx";
import React from "react";
import { KeyCloakService } from "../../../../../security/KeycloakService.ts";

export interface TeamCardProps {
  team: Team;
  withDescription: boolean;
  canJoin: boolean;
}

export default function TeamCard({ team, withDescription, canJoin }: TeamCardProps) {
  const { defaultTeamBannerFile, defaultTeamAvatarFile, siteTitle, siteSubtitle } = useFrontendProperties();
  const { t } = useTranslation();
  const userFullName = KeyCloakService.GetUserFullName();
  const username = KeyCloakService.GetUserName();

  const handleJoinTeam = (e: React.MouseEvent<HTMLButtonElement>, team: Team): void => {
    e.preventDefault();
    if (team.owners.length === 0) return;
    const recipients = team.owners.map((o) => o.email).join(",");
    const subject = `[${siteTitle} ${siteSubtitle}] Demande pour rejoindre l'équipe ${team.name}`;
    const teamUrl = `${window.location.origin}/teams/${team.id}/agents`;
    const body = `Bonjour,\n\nJe souhaite rejoindre l’équipe ${team.name} sur ${siteTitle} ${siteSubtitle}.\n\nInformations utilisateur : ${userFullName} (${username})\n\nAller à la page de l'équipe ${team.name} : ${teamUrl}`;
    const params = new URLSearchParams({
      subject: subject,
      body: body,
    });
    window.location.href = `mailto:${recipients}?${params.toString().replace(/\+/g, "%20")}`;
  };

  return (
    <div className={styles.teamCardContainer}>
      <img
        className={styles.teamBanner}
        src={team.banner_image_url ?? `/images/${defaultTeamBannerFile}`}
        alt=""
        aria-hidden="true"
      ></img>
      <img
        className={styles.teamAvatar}
        src={team.banner_image_url ?? `/images/${defaultTeamAvatarFile}`}
        alt=""
        aria-hidden="true"
      ></img>
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
          <AvatarGroup avatars={team.owners.map((o) => ({ name: o.first_name + " " + o.last_name }))} />
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
