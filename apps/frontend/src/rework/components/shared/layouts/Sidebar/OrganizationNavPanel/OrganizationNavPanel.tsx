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
import styles from "./OrganizationNavPanel.module.scss";
import SpaceHeader from "@shared/molecules/SpaceHeader/SpaceHeader.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { spaceRolesCaption } from "@shared/utils/teamRoleLabel";
import NavigationMenu from "@shared/molecules/NavigationMenu/NavigationMenu.tsx";
import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import TeamSelectionListItem from "@shared/molecules/TeamSelectionListItem/TeamSelectionListItem.tsx";
import { useLocation, useNavigate } from "react-router-dom";
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
import { useSpaceContentItems } from "../useSpaceContentItems.tsx";

/** The working organization's panel: personal space, the organization's content, then its teams. */
export default function OrganizationNavPanel() {
  const { organizationId } = useWorkingOrganization();
  return <WorkingOrganizationNavPanel key={organizationId ?? "no-context"} />;
}

function WorkingOrganizationNavPanel() {
  const { t } = useTranslation();
  const { defaultTeamAvatarFile } = useFrontendProperties();
  const { currentData: pictureUrl } = useGetMyAvatarQuery(undefined, { refetchOnMountOrArgChange: 60 });
  const [search, setSearch] = useState("");
  const { memberships: spaces, organizationId, organization } = useWorkingOrganization();
  const me = useMeQuery();
  const navigate = useNavigate();
  const location = useLocation();
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
  const org = spaces.isError
    ? undefined
    : spaces.currentData?.find((space) => space.kind === "organization" && space.id === organizationId);
  // An existing personal space is a plain link; only its first opening creates it on the server.
  const personalSpace = org
    ? spaces.currentData?.find((space) => space.kind === "personal" && space.organization_id === org.id)
    : undefined;
  const organizationContent = useSpaceAccess(org?.id, "read");
  const organizationManage = useSpaceAccess(org?.id, "manage");
  const contentItems = useSpaceContentItems({
    teamId: org?.id,
    space: org,
    canReadContent: !!org && organizationContent.offered,
    isPersonalTeam: false,
  });
  const canOpen =
    !spaces.isError &&
    !me.isError &&
    org &&
    me.data &&
    spaces.data?.some(
      (space) => space.kind !== "personal" && space.organization_id === org.id && space.roles.includes("member"),
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

  // Same right as the gear of the organization's former panel; back from settings, focus returns here.
  const showGear = !!org && organizationManage.offered;
  const gear = useRef<HTMLSpanElement>(null);
  const returnToGear = (location.state as { focusSettings?: boolean } | null)?.focusSettings === true;
  useEffect(() => {
    if (returnToGear && showGear) gear.current?.querySelector("button")?.focus();
  }, [returnToGear, showGear]);

  // The search field is hidden behind a magnifier button and only mounts (as an
  // overlay over the list header) once opened; it collapses again when it loses
  // focus, but only while empty — a live filter keeps it open.
  const [searchOpen, setSearchOpen] = useState(false);
  const searchButton = useRef<HTMLSpanElement>(null);
  const sortMode = useCurrentUserPreference("team_sort_mode", "recent") as TeamSortMode;
  // Read once on mount — recency only changes while the user is inside a team,
  // and this panel remounts when they return to it.
  const recency = useMemo(() => getTeamRecency(), []);

  const query = search.trim().toLowerCase();
  // Teams of this organization where the person holds a direct role; projects are reached from their team.
  const teams = useMemo(() => {
    if (spaces.isError) return [];
    return (spaces.currentData ?? [])
      .filter(
        (space) =>
          space.kind === "team" &&
          space.organization_id === organizationId &&
          space.roles.length > 0 &&
          space.name.toLowerCase().includes(query),
      )
      .sort(
        (a, b) =>
          (sortMode === "recent" ? (recency[b.id] ?? 0) - (recency[a.id] ?? 0) : 0) || a.name.localeCompare(b.name),
      );
  }, [spaces.currentData, spaces.isError, organizationId, query, sortMode, recency]);

  const sortOptions: TeamSortOption<TeamSortMode>[] = [
    { value: "recent", label: t("rework.home.sort.recent") },
    { value: "alpha", label: t("rework.home.sort.alpha") },
  ];

  return (
    <div className={styles.panel}>
      {/* Without an organization, the panel keeps the Home title. */}
      <SpaceHeader
        eyebrow={organization ? t("rework.manager.kinds.organization") : undefined}
        leading={organization && <Icon category="outlined" type="domain" />}
        title={organization?.name ?? t("rework.home.title")}
        caption={org && spaceRolesCaption(org.roles, t)}
        action={
          showGear && (
            <span ref={gear} className={styles.settingsButton}>
              <IconButton
                size="small"
                variant="icon"
                icon={{ category: "outlined", type: "settings", filled: true }}
                onClick={() => navigate(`/team/${org.id}/settings/members`, { state: { focusPanel: true } })}
                title={t("rework.teamSettings.navigation.settings")}
              />
            </span>
          )
        }
      />

      {/* Destinations above the teams: the organization's marketplace, then the personal space. */}
      <div className={styles.personalSpace}>
        <TeamSelectionListItem
          redirection="/marketplace"
          name={t("rework.mainNav.marketplace")}
          icon="storefront"
          avatarName=""
        />
        {canOpen && (
          <>
            <TeamSelectionListItem
              {...(personalSpace
                ? { redirection: `/team/${personalSpace.id}/agents` }
                : { onActivate: () => void activatePersonal(), pending: opening })}
              name={t("rework.home.personalSpace")}
              personal
              imgUrl={pictureUrl || undefined}
              avatarName={KeyCloakService.GetUserFullName()}
              avatarColor={PERSONAL_TEAM_COLOR}
            />
            {opening && (
              <span role="status" className={styles.notice}>
                {t("common.loading")}
              </span>
            )}
            {failed && (
              <span role="alert" className={styles.notice}>
                {t("rework.manager.unavailable")}
              </span>
            )}
          </>
        )}
      </div>

      {contentItems.length > 0 && <NavigationMenu items={contentItems} />}

      <div className={styles.teamList}>
        <div className={styles.teamListHeader}>
          <span className={styles.teamListHeaderLabel}>{t("rework.home.yourTeams")}</span>
          <span className={styles.teamListActions}>
            <TeamSortSelect<TeamSortMode>
              value={sortMode}
              options={sortOptions}
              onChange={setTeamSortMode}
              ariaLabel={t("rework.home.sort.aria")}
            />
            <span ref={searchButton} className={styles.teamListActions}>
              <IconButton
                size="small"
                variant="icon"
                icon={{ category: "outlined", type: "search" }}
                aria-label={t("rework.home.searchPlaceholder")}
                onClick={() => setSearchOpen(true)}
              />
            </span>
          </span>
          {searchOpen && (
            <div
              className={styles.searchOverlay}
              // Escape always empties and closes the search; focus returns to its button.
              onKeyDown={(event) => {
                if (event.key !== "Escape") return;
                event.preventDefault();
                setSearch("");
                setSearchOpen(false);
                searchButton.current?.querySelector("button")?.focus();
              }}
            >
              <SearchInput
                size="xs"
                value={search}
                onChange={setSearch}
                autoFocus
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
        <ul className={styles.scroll}>
          {teams.map((team) => (
            <li key={team.id}>
              <TeamSelectionListItem
                redirection={`/team/${team.id}`}
                avatarSpaceId={team.id}
                name={team.name}
                roles={team.roles}
                imgUrl={defaultTeamAvatarFile ? `/images/${defaultTeamAvatarFile}` : undefined}
                avatarName={team.name}
              />
            </li>
          ))}
          {!teams.length && !spaces.isLoading && (
            <li className={styles.empty} role={spaces.isError ? "alert" : "status"}>
              {t(spaces.isError ? "rework.manager.unavailable" : "rework.home.noTeams")}
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
