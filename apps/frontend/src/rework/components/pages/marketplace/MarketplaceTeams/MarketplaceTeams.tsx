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

import styles from "./MarketplaceTeams.module.scss";
import { useTranslation } from "react-i18next";
import TeamCard from "@shared/organisms/TeamCard/TeamCard.tsx";
import { useListTeamsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { Link, Navigate } from "react-router-dom";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import { isPersonalTeamId } from "@shared/utils/teamId";

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
  const { activeTeam, availableTeams, bootstrap, isLoading, refetch } = useFrontendBootstrap();
  // AUTHZ-05 review item 4: platform-admin gating is OpenFGA-derived
  // (`PermissionSummary.is_platform_admin`), not a raw Keycloak role check.
  const isAdmin = bootstrap?.permissions?.is_platform_admin ?? false;
  const personalTeamId = activeTeam?.id ?? "personal";
  const collaborativeTeams = availableTeams.filter((team) => team.id !== personalTeamId);
  const { data: teams } = useListTeamsQuery(undefined, {
    skip: collaborativeTeams.length === 0,
  });

  // `GET /teams` intentionally includes personal spaces (it also feeds the
  // bootstrap-driven sidebar/team switcher), but the marketplace must never
  // list one, including the caller's own — see #2068.
  const yourTeams = teams && teams.filter((t) => t.is_member && !isPersonalTeamId(t.id));
  const otherTeams = teams && teams.filter((t) => !t.is_member && !isPersonalTeamId(t.id));

  // Wait for bootstrap before redirecting away: redirecting on the first,
  // pre-bootstrap render sends the user to the bare "personal" alias, then a
  // second redirect fires once activeTeam.id resolves — the same URL/navbar
  // desync as the CTRLP-10 index-route residual (router.tsx).
  if (isLoading) return null;

  if (collaborativeTeams.length === 0) {
    return <Navigate to={`/team/${personalTeamId}/agents`} replace />;
  }

  const renderCard = (team: Team, withDescription: boolean) => {
    // TEAM-09: a successful self-service join changes team.is_member, which
    // moves the card between the yourTeams/otherTeams buckets via the
    // ControlPlaneTeam:LIST tag invalidation baked into useJoinTeamMutation —
    // bootstrap's own team list (the navbar/team switcher) is a separate
    // cache, so it needs its own refetch.
    if (isAdmin)
      return (
        <Link to={`/team/${team.id}/agents`}>
          <TeamCard key={team.id} team={team} withDescription={withDescription} onJoined={refetch} />
        </Link>
      );
    return <TeamCard key={team.id} team={team} withDescription={withDescription} onJoined={refetch} />;
  };

  return (
    <div className={styles.marketplaceTeamsContainer}>
      <div className={styles.marketplaceTeamsHeader}>
        <h1 className={styles.marketplaceTeamsTitle}>{t("rework.marketplace.teams.title")}</h1>
      </div>
      <div className={styles.marketplaceTeamsContent}>
        <div className={styles.marketplaceTeamsListSubtitle}>{t("rework.marketplace.teams.yourTeams")}</div>
        <div className={styles.marketplaceTeamsList}>
          {yourTeams && yourTeams.map((team) => renderCard(team, false))}
        </div>
        <div className={styles.marketplaceTeamsListSubtitle}>{t("rework.marketplace.teams.otherTeams")}</div>
        <div className={styles.marketplaceTeamsList}>
          {otherTeams && otherTeams.map((team) => renderCard(team, true))}
        </div>
      </div>
    </div>
  );
}
