import styles from "./MarketplaceTeams.module.scss";
import { useTranslation } from "react-i18next";
import TeamCard from "@shared/organisms/TeamCard/TeamCard.tsx";
import { useListTeamsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { KeyCloakService } from "../../../../../security/KeycloakService.ts";
import { Link, Navigate } from "react-router-dom";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";

/**
 * Render the collaborative team marketplace only when collaborative teams exist.
 *
 * Why this component exists:
 * - the no-security personal-only baseline should not expose collaborative-team
 *   discovery as a primary supported path
 *
 * How to use it:
 * - mount it on the marketplace team route; it redirects back to the personal
 *   agent page when the user only has the reserved personal team
 *
 * Example:
 * - `<MarketplaceTeams />`
 */
export default function MarketplaceTeams() {
  const { t } = useTranslation();
  const { activeTeam, availableTeams } = useFrontendBootstrap();
  const isAdmin = KeyCloakService.GetUserRoles().includes("admin");
  const personalTeamId = activeTeam?.id ?? "personal";
  const collaborativeTeams = availableTeams.filter((team) => team.id !== personalTeamId);
  const { data: teams } = useListTeamsQuery(undefined, {
    skip: collaborativeTeams.length === 0,
  });

  const yourTeams = teams && teams.filter((t) => t.is_member);
  const otherTeams = teams && teams.filter((t) => !t.is_member);

  if (collaborativeTeams.length === 0) {
    return <Navigate to={`/team/${personalTeamId}/agents`} replace />;
  }

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
