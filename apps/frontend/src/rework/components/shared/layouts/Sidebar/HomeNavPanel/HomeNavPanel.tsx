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

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./HomeNavPanel.module.scss";
import SpaceHeader from "@shared/molecules/SpaceHeader/SpaceHeader.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import TeamSelectionListItem from "@shared/molecules/TeamSelectionListItem/TeamSelectionListItem.tsx";
import { useNavigate } from "react-router-dom";
import {
  useMySpacesQuery,
  useMeQuery,
  useCreatePersonalSpaceMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { PERSONAL_TEAM_COLOR } from "@shared/atoms/TeamInitials/teamColor.ts";
import TeamSortSelect, { type TeamSortOption } from "./TeamSortSelect.tsx";
import { getTeamRecency, setTeamSortMode, type TeamSortMode } from "@shared/utils/teamRecency.ts";
import { useCurrentUserPreference } from "../../../../../../app/userPreferences.ts";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { useFrontendBootstrap } from "../../../../../../hooks/useFrontendBootstrap.ts";
import { KeyCloakService } from "../../../../../../security/KeycloakService.ts";

/**
 * Home view of the main nav panel (mainNavPanel): the app's team switcher,
 * moved off the former far-left avatar rail. Lists the personal space and every
 * team the user belongs to; each row navigates into that space. The search box
 * filters the "Vos équipes" list only — the personal space is a fixed home
 * anchor, not one of the user's teams.
 *
 * Reached via the mainNavBar Home icon (`/home`). Team/roles come from
 * `useFrontendBootstrap` (`available_teams[].my_relations`, #2298) — no per-team
 * fetch.
 */
export default function HomeNavPanel() {
  const { t } = useTranslation();
  const { defaultTeamAvatarFile } = useFrontendProperties();
  const { bootstrap } = useFrontendBootstrap();
  const [search, setSearch] = useState("");
  const spaces = useMySpacesQuery();
  const me = useMeQuery();
  const navigate = useNavigate();
  const [openPersonal] = useCreatePersonalSpaceMutation();
  const [opening, setOpening] = useState(false);
  const [failed, setFailed] = useState(false);
  const active = useRef<string | undefined>(me.data?.user_id);
  const pending = useRef(false);
  useEffect(() => {
    active.current = me.data?.user_id;
    setFailed(false);
    setOpening(false);
    return () => {
      active.current = undefined;
    };
  }, [me.data?.user_id]);
  const org = spaces.data?.find((space) => space.kind === "organization");
  const canOpen =
    !spaces.isError &&
    !me.isError &&
    org &&
    me.data &&
    org.roles.some((role) => ["member", "editor", "admin", "analyst"].includes(role));
  const activatePersonal = async () => {
    if (!canOpen || pending.current) return;
    const user = me.data.user_id;
    pending.current = true;
    setOpening(true);
    setFailed(false);
    try {
      const space = await openPersonal({ createPersonalSpace: { organization_id: org.id } }).unwrap();
      if (active.current !== user) return;
      const memberships = await spaces.refetch().unwrap();
      if (!memberships.some((membership) => membership.id === space.id)) {
        throw new Error("Opened space is not in current memberships");
      }
      if (active.current === user) navigate(`/team/${space.id}/agents`);
    } catch {
      if (active.current === user) setFailed(true);
    } finally {
      pending.current = false;
      if (active.current === user) setOpening(false);
    }
  };

  // The search field is hidden behind a magnifier button and only mounts (as an
  // overlay over the list header) once opened; it collapses again when it loses
  // focus, but only while empty — a live filter keeps it open (chosen #2298).
  const [searchOpen, setSearchOpen] = useState(false);
  const sortMode = useCurrentUserPreference("team_sort_mode", "recent") as TeamSortMode;
  // Read once on mount — recency only changes while the user is inside a team,
  // and this panel remounts when they return to Home.
  const recency = useMemo(() => getTeamRecency(), []);

  const changeSortMode = (mode: TeamSortMode) => {
    setTeamSortMode(mode);
  };

  const collaborativeTeams = spaces.isError
    ? []
    : (spaces.currentData ?? []).filter((space) => space.kind === "team" || space.kind === "project");
  const query = search.trim().toLowerCase();
  const visibleTeams = query
    ? collaborativeTeams.filter((team) => team.name.toLowerCase().includes(query))
    : collaborativeTeams;

  const sortedTeams = useMemo(() => {
    const list = [...visibleTeams];
    if (sortMode === "alpha") {
      list.sort((a, b) => a.name.localeCompare(b.name));
    } else {
      // Most recently visited first; never-visited teams fall to the bottom,
      // tie-broken alphabetically.
      list.sort((a, b) => {
        const diff = (recency[b.id] ?? 0) - (recency[a.id] ?? 0);
        return diff !== 0 ? diff : a.name.localeCompare(b.name);
      });
    }
    return list;
  }, [visibleTeams, sortMode, recency]);

  const organization = spaces.currentData?.find((space) => space.kind === "organization");
  const sortOptions: TeamSortOption<TeamSortMode>[] = [
    { value: "recent", label: t("rework.home.sort.recent") },
    { value: "alpha", label: t("rework.home.sort.alpha") },
  ];

  return (
    <div className={styles.panel}>
      {/* Home of the person's organization; without one, just the section. */}
      <SpaceHeader eyebrow={organization?.name} title={t("rework.home.title")} />

      {canOpen && (
        <div className={styles.personalSpace}>
          <TeamSelectionListItem
            onActivate={() => void activatePersonal()}
            pending={opening}
            name={t("rework.sidebar.team.userTeam")}
            personal
            imgUrl={bootstrap?.current_user?.avatar_image_url ?? undefined}
            avatarName={KeyCloakService.GetUserFullName()}
            avatarColor={PERSONAL_TEAM_COLOR}
          />
          {opening && <p role="status">{t("common.loading")}</p>}
          {failed && <p role="alert">{t("rework.manager.unavailable")}</p>}
        </div>
      )}

      <div className={styles.teamList}>
        <div className={styles.teamListHeader}>
          <span className={styles.teamListHeaderLabel}>{t("rework.home.yourTeams")}</span>
          <IconButton
            size="small"
            variant="icon"
            icon={{ category: "outlined", type: "search" }}
            aria-label={t("rework.home.searchPlaceholder")}
            onClick={() => setSearchOpen(true)}
          />
          {searchOpen && (
            <div className={styles.searchOverlay}>
              <SearchInput
                size="xs"
                value={search}
                onChange={setSearch}
                autoFocus
                // Collapse when focus leaves, but only if the field is empty —
                // an active filter stays open so the list keeps its context.
                onBlur={() => {
                  if (!search.trim()) setSearchOpen(false);
                }}
                placeholder={t("rework.home.searchPlaceholder")}
                ariaLabel={t("rework.home.searchPlaceholder")}
                clearAriaLabel={t("rework.home.searchClear")}
              />
            </div>
          )}
        </div>
        <div className={styles.teamSort}>
          <TeamSortSelect<TeamSortMode>
            value={sortMode}
            options={sortOptions}
            onChange={changeSortMode}
            ariaLabel={t("rework.home.sort.aria")}
          />
        </div>
        <div className={styles.scroll}>
          {sortedTeams.map((team) => (
            <TeamSelectionListItem
              key={team.id}
              redirection={`/team/${team.id}/agents`}
              name={team.name}
              roles={team.roles}
              imgUrl={defaultTeamAvatarFile ? `/images/${defaultTeamAvatarFile}` : undefined}
              avatarName={team.name}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
