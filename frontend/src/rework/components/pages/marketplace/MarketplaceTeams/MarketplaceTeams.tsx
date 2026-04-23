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

  const renderCard = (team: Team, withDescription: boolean, canJoin: boolean) => {
    if (isAdmin)
      return (
        <Link to={`/team/${team.id}/agents`}>
          <TeamCard key={team.id} team={team} withDescription={withDescription} canJoin={canJoin} />
        </Link>
      );
    return <TeamCard key={team.id} team={team} withDescription={withDescription} canJoin={canJoin} />;
  };

  return (
    <div className={styles.marketplaceTeamsContainer}>
      <div className={styles.marketplaceTeamsHeader}>
        <h1 className={styles.marketplaceTeamsTitle}>{t("rework.marketplace.teams.title")}</h1>
      </div>
      <div className={styles.marketplaceTeamsContent}>
        <div className={styles.marketplaceTeamsListSubtitle}>{t("rework.marketplace.teams.yourTeams")}</div>
        <div className={styles.marketplaceTeamsList}>
          {yourTeams && yourTeams.map((team) => renderCard(team, false, false))}
        </div>
        <div className={styles.marketplaceTeamsListSubtitle}>{t("rework.marketplace.teams.otherTeams")}</div>
        <div className={styles.marketplaceTeamsList}>
          {otherTeams && otherTeams.map((team) => renderCard(team, true, true))}
        </div>
      </div>
    </div>
  );
}
