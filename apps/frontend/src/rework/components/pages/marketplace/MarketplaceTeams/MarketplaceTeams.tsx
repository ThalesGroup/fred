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
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import { useListTeamsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { Link, Navigate } from "react-router-dom";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import { isPersonalTeamId } from "@shared/utils/teamId";
import { useMemo, useState } from "react";

// Free-text query matched against name and description — a team must match
// every whitespace-separated token in at least one of those two fields.
// Same tokenized-match approach as TeamSettingsMembersTable. Applied
// client-side: both team lists are already fetched in full by useListTeamsQuery.
const MIN_SEARCH_LENGTH = 2;

function matchesSearch(team: Team, tokens: string[]): boolean {
  const haystacks = [team.name, team.description]
    .filter((value): value is string => Boolean(value))
    .map((value) => value.toLowerCase());
  return tokens.every((token) => haystacks.some((haystack) => haystack.includes(token)));
}

function filterTeams(teams: Team[] | undefined, search: string): Team[] {
  if (!teams) return [];
  const trimmed = search.trim().toLowerCase();
  if (trimmed.length < MIN_SEARCH_LENGTH) return teams;
  const tokens = trimmed.split(/\s+/).filter(Boolean);
  return teams.filter((team) => matchesSearch(team, tokens));
}

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
  const { activeTeam, availableTeams, isLoading, refetch } = useFrontendBootstrap();
  const [search, setSearch] = useState("");
  const personalTeamId = activeTeam?.id ?? "personal";
  const collaborativeTeams = availableTeams.filter((team) => team.id !== personalTeamId);
  const { data: teams } = useListTeamsQuery(undefined, {
    skip: collaborativeTeams.length === 0,
  });

  // `GET /teams` intentionally includes personal spaces (it also feeds the
  // bootstrap-driven sidebar/team switcher), but the marketplace must never
  // list one, including the caller's own — see #2068.
  //
  // Same stance for private teams (#2398): the server already withholds the
  // ReBAC `public` relation from them, but that filter is skipped entirely
  // when authorization is disabled, and discoverability is this page's own
  // product rule — so never offer a private team to a non-member here,
  // whatever the endpoint returned. A member keeps seeing their own private
  // teams under "your teams": they need them to navigate.
  //
  // #2433: require `=== "public"` rather than `!== "private"` — private is
  // now the platform default, so a payload missing the field (version-skew
  // backend) must err on non-disclosure, matching the `?? "private"`
  // fallback in TeamSettingsParameters.
  const yourTeams = teams && teams.filter((t) => t.is_member && !isPersonalTeamId(t.id));
  const otherTeams = teams && teams.filter((t) => !t.is_member && !isPersonalTeamId(t.id) && t.visibility === "public");

  const filteredYourTeams = useMemo(() => filterTeams(yourTeams, search), [yourTeams, search]);
  const filteredOtherTeams = useMemo(() => filterTeams(otherTeams, search), [otherTeams, search]);

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
    // Only a team the caller is a member of is navigable — non-member cards
    // (the "discover" section) offer join/invite-only affordances, not entry.
    if (team.is_member)
      return (
        <Link key={team.id} className={styles.marketplaceTeamsCardLink} to={`/team/${team.id}/agents`}>
          <TeamCard team={team} withDescription={withDescription} onJoined={refetch} />
        </Link>
      );
    return <TeamCard key={team.id} team={team} withDescription={withDescription} onJoined={refetch} />;
  };

  return (
    <div className={styles.marketplaceTeamsContainer}>
      <div className={styles.marketplaceTeamsHeader}>
        <h1 className={styles.marketplaceTeamsTitle}>{t("rework.marketplace.teams.title")}</h1>
        <div className={styles.marketplaceTeamsSearch}>
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder={t("rework.marketplace.teams.search.placeholder")}
            ariaLabel={t("rework.marketplace.teams.search.ariaLabel")}
            clearAriaLabel={t("rework.marketplace.teams.search.clearAriaLabel")}
            size="small"
          />
        </div>
      </div>
      <div className={styles.marketplaceTeamsContent}>
        <div className={styles.marketplaceTeamsListSubtitle}>{t("rework.marketplace.teams.yourTeams")}</div>
        <div className={styles.marketplaceTeamsList}>{filteredYourTeams.map((team) => renderCard(team, false))}</div>
        <div className={styles.marketplaceTeamsListSubtitle}>{t("rework.marketplace.teams.otherTeams")}</div>
        <div className={styles.marketplaceTeamsList}>{filteredOtherTeams.map((team) => renderCard(team, true))}</div>
      </div>
    </div>
  );
}
