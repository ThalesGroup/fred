import styles from "./MarketplaceTeams.module.scss";
import { useTranslation } from "react-i18next";
import TeamCard from "@shared/organisms/TeamCard/TeamCard.tsx";
import { useListTeamsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { KeyCloakService } from "../../../../../security/KeycloakService.ts";
import { Link } from "react-router-dom";

export default function () {
  const { t } = useTranslation();
  const { data: teams } = useListTeamsQuery();
  const isAdmin = KeyCloakService.GetUserRoles().includes("admin");

  const yourTeams = teams && teams.filter((t) => t.is_member);
  const otherTeams = teams && teams.filter((t) => !t.is_member);

  const renderCard = (team: Team, withDescription: boolean) => {
    if (isAdmin)
      return (
        <Link to={`/team/${team.id}/agents`}>
          <TeamCard key={team.id} team={team} withDescription={withDescription} />
        </Link>
      );
    return <TeamCard key={team.id} team={team} withDescription={withDescription} />;
  };

  return (
    <div className={styles["marketplace-teams-container"]}>
      <div className={styles["marketplace-teams-header"]}>
        <h1 className={styles["marketplace-teams-title"]}>{t("rework.marketplace.teams.title")}</h1>
      </div>
      <div className={styles["marketplace-teams-content"]}>
        <div className={styles["marketplace-teams-list-subtitle"]}>{t("rework.marketplace.teams.yourTeams")}</div>
        <div className={styles["marketplace-teams-list"]}>
          {yourTeams && yourTeams.map((team) => renderCard(team, false))}
        </div>
        <div className={styles["marketplace-teams-list-subtitle"]}>{t("rework.marketplace.teams.otherTeams")}</div>
        <div className={styles["marketplace-teams-list"]}>
          {otherTeams && otherTeams.map((team) => renderCard(team, true))}
        </div>
      </div>
    </div>
  );
}
