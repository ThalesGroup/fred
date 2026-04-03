import styles from "./TeamCard.module.scss";
import { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { useTranslation } from "react-i18next";
import AvatarGroup from "@shared/molecules/AvatarGroup/AvatarGroup.tsx";

export interface TeamCardProps {
  team: Team;
  withDescription: boolean;
}

export default function TeamCard({ team, withDescription }: TeamCardProps) {
  const { t } = useTranslation();

  return (
    <div className={styles["team-card-container"]}>
      <img
        className={styles["team-banner"]}
        src={team.banner_image_url ? `url(${team.banner_image_url})` : "/images/default-team-banner.png"}
        alt=""
        aria-hidden="true"
      ></img>
      <img className={styles["team-avatar"]} src="/images/defaultTeamAvatar.png" alt="" aria-hidden="true"></img>
      <div className={styles["team-card-details"]}>
        <div className={styles["team-card-detail-name"]}>
          <div className={styles["team-information"]}>
            <div className={styles["team-name"]}>{team.name}</div>
            {team.is_private && (
              <div className={styles["team-private-state"]}>
                <Icon category={"outlined"} type={"lock"} />
              </div>
            )}
          </div>
          <div className={styles["team-member-count"]}>
            <span className={styles["team-member-count-icon"]}>
              <Icon category={"outlined"} type={"groups"} />
            </span>
            {t("rework.teamCard.memberCount", { count: team.member_count })}
          </div>
        </div>
        {withDescription && <div className={styles["team-card-description"]}>{team.description}</div>}
        <div className={styles["team-card-footer"]}>
          <AvatarGroup avatars={team.owners.map((o) => ({ name: o.first_name + " " + o.last_name }))} />
        </div>
      </div>
    </div>
  );
}
