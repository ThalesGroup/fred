import styles from "./MarketplaceTeams.module.scss";
import { useTranslation } from "react-i18next";
import TeamCard from "@shared/organisms/TeamCard/TeamCard.tsx";
import { useListTeamsQuery } from "../../../../../slices/controlPlane/controlPlaneApi.ts";

export default function () {
  const { t } = useTranslation();
  const { data: teams } = useListTeamsQuery();

  const yourTeams = teams && teams.filter((t) => t.is_member);
  const otherTeams = teams && teams.filter((t) => !t.is_member);

  return (
    <div className={styles["marketplace-teams-container"]}>
      <div className={styles["marketplace-teams-header"]}>
        <h1 className={styles["marketplace-teams-title"]}>{t("rework.marketplace.teams.title")}</h1>
      </div>
      <div className={styles["marketplace-teams-content"]}>
        <div className={styles["marketplace-teams-list-subtitle"]}>{t("rework.marketplace.teams.yourTeams")}</div>
        <div className={styles["marketplace-teams-list"]}>
          {yourTeams && yourTeams.map((team) => <TeamCard key={team.id} team={team} withDescription={false} />)}
        </div>
        <div className={styles["marketplace-teams-list-subtitle"]}>{t("rework.marketplace.teams.otherTeams")}</div>
        <div className={styles["marketplace-teams-list"]}>
          {otherTeams && otherTeams.map((team) => <TeamCard key={team.id} team={team} withDescription={true} />)}
        </div>
      </div>
    </div>
  );
}
