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
import type { MySpace } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import SpaceHeader from "@shared/molecules/SpaceHeader/SpaceHeader.tsx";
import Separator from "@shared/atoms/Separator/Separator";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import TeamSelectionListItem from "@shared/molecules/TeamSelectionListItem/TeamSelectionListItem.tsx";
import { useNavigate } from "react-router-dom";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import {
  useGetMyAvatarQuery,
  useMeQuery,
  useCreatePersonalSpaceMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { PERSONAL_TEAM_COLOR } from "@shared/atoms/TeamInitials/teamColor.ts";
import TeamSortSelect, { type TeamSortOption } from "./TeamSortSelect.tsx";
import { getTeamRecency, setTeamSortMode, type TeamSortMode } from "@shared/utils/teamRecency.ts";
import { useCurrentUserPreference } from "../../../../../../app/userPreferences.ts";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { KeyCloakService } from "../../../../../../security/KeycloakService.ts";

/** Home navigation uses Control Plane memberships and current space permissions. */
export default function HomeNavPanel() {
  const { organizationId } = useWorkingOrganization();
  return <OrganizationHomeNavPanel key={organizationId ?? "no-context"} />;
}

function OrganizationHomeNavPanel() {
  const { t } = useTranslation();
  const { defaultTeamAvatarFile } = useFrontendProperties();
  const { currentData: pictureUrl } = useGetMyAvatarQuery(undefined, { refetchOnMountOrArgChange: 60 });
  const [search, setSearch] = useState("");
  const { memberships: spaces, organizationId, organization } = useWorkingOrganization();
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
  const org = spaces.currentData?.find((space) => space.kind === "organization" && space.id === organizationId);
  const organizationContent = useSpaceAccess(spaces.isError ? undefined : org?.id, "read");
  const canOpen =
    !spaces.isError &&
    !me.isError &&
    org &&
    me.data &&
    spaces.data?.some(
      (space) =>
        space.kind !== "personal" &&
        space.organization_id === org.id &&
        space.roles.some((role) => ["owner", "member", "editor", "analyst"].includes(role)),
    );
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

  const [collapsedTeams, setCollapsedTeams] = useState<string[]>([]);
  const query = search.trim().toLowerCase();
  const groups = useMemo(() => {
    if (spaces.isError) return [];
    const available = (spaces.currentData ?? []).filter(
      (space) => (space.kind === "team" || space.kind === "project") && space.organization_id === organizationId,
    );
    const compare = (a: MySpace, b: MySpace) =>
      (sortMode === "recent" ? (recency[b.id] ?? 0) - (recency[a.id] ?? 0) : 0) || a.name.localeCompare(b.name);
    available.sort(compare);
    const teams = new Set(available.filter((space) => space.kind === "team").map((space) => space.id));
    const children = new Map<string, MySpace[]>();
    for (const space of available) {
      if (space.kind === "project" && space.parent_id && teams.has(space.parent_id)) {
        const projects = children.get(space.parent_id) ?? [];
        projects.push(space);
        children.set(space.parent_id, projects);
      }
    }
    // A project without a visible parent remains a direct entry. Memberships,
    // not the hierarchy, determine which spaces can be displayed.
    return available
      .filter((space) => space.kind === "team" || !space.parent_id || !teams.has(space.parent_id))
      .map((space) => {
        const projects = children.get(space.id) ?? [];
        return {
          space,
          recent: projects.reduce((last, project) => Math.max(last, recency[project.id] ?? 0), recency[space.id] ?? 0),
          projects: space.name.toLowerCase().includes(query)
            ? projects
            : projects.filter((project) => project.name.toLowerCase().includes(query)),
        };
      })
      .filter(({ space, projects }) => space.name.toLowerCase().includes(query) || projects.length > 0)
      .sort((a, b) => (sortMode === "recent" ? b.recent - a.recent : 0) || a.space.name.localeCompare(b.space.name));
  }, [spaces.currentData, spaces.isError, organizationId, query, sortMode, recency]);

  const sortOptions: TeamSortOption<TeamSortMode>[] = [
    { value: "recent", label: t("rework.home.sort.recent") },
    { value: "alpha", label: t("rework.home.sort.alpha") },
  ];

  return (
    <div className={styles.panel}>
      <SpaceHeader eyebrow={organization?.name} title={t("rework.home.title")} />

      {((org && organizationContent.allowed) || canOpen) && (
        <section className={styles.spaces} aria-labelledby="home-spaces-title">
          <h3 id="home-spaces-title">{t("rework.home.yourSpaces")}</h3>
          {org && organizationContent.allowed && (
            <TeamSelectionListItem
              redirection={`/team/${org.id}`}
              name={t("rework.home.organizationSpace")}
              roles={org.roles}
              avatarName={org.name}
            />
          )}
          {canOpen && (
            <>
              <TeamSelectionListItem
                onActivate={() => void activatePersonal()}
                pending={opening}
                name={t("rework.home.personalSpace")}
                description={t("rework.home.personalSpaceDescription")}
                personal
                imgUrl={pictureUrl || undefined}
                avatarName={KeyCloakService.GetUserFullName()}
                avatarColor={PERSONAL_TEAM_COLOR}
              />
              {opening && <p role="status">{t("common.loading")}</p>}
              {failed && <p role="alert">{t("rework.manager.unavailable")}</p>}
            </>
          )}
          <Separator margin="var(--spacing-s) var(--spacing-xs) 0" />
        </section>
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
        <ul className={styles.scroll}>
          {groups.map(({ space, projects }) => {
            const expanded = !!query || !collapsedTeams.includes(space.id);
            return (
              <li key={space.id}>
                <div className={styles.teamRow}>
                  <TeamSelectionListItem
                    redirection={`/team/${space.id}`}
                    name={space.name}
                    description={t(`rework.userSettings.spaceKinds.${space.kind}`)}
                    roles={space.roles}
                    imgUrl={defaultTeamAvatarFile ? `/images/${defaultTeamAvatarFile}` : undefined}
                    avatarName={space.name}
                  />
                  {projects.length > 0 && (
                    <IconButton
                      size="small"
                      variant="icon"
                      icon={{ category: "outlined", type: expanded ? "expand_more" : "chevron_right" }}
                      aria-label={t("rework.home.projectsOf", { name: space.name })}
                      aria-expanded={expanded}
                      aria-controls={`projects-${space.id}`}
                      disabled={!!query}
                      onClick={() =>
                        setCollapsedTeams((ids) =>
                          ids.includes(space.id) ? ids.filter((id) => id !== space.id) : [...ids, space.id],
                        )
                      }
                    />
                  )}
                </div>
                {projects.length > 0 && (
                  <ul id={`projects-${space.id}`} className={styles.projects} hidden={!expanded}>
                    {projects.map((project) => (
                      <li key={project.id}>
                        <TeamSelectionListItem
                          redirection={`/team/${project.id}`}
                          name={project.name}
                          description={t("rework.userSettings.spaceKinds.project")}
                          roles={project.roles}
                          imgUrl={defaultTeamAvatarFile ? `/images/${defaultTeamAvatarFile}` : undefined}
                          avatarName={project.name}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
          {!groups.length && !spaces.isLoading && (
            <li className={styles.empty} role={spaces.isError ? "alert" : "status"}>
              {t(spaces.isError ? "rework.manager.unavailable" : "rework.home.noSpaces")}
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
