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

import styles from "./TeamSelectionListItem.module.scss";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials.tsx";
import type { TeamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import type { UserTeamRelation } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useTranslation } from "react-i18next";
import { Link, type To } from "react-router-dom";

// Same priority the team banner uses (#2100): admin first, then editor, then
// analyst — so "Admin · Analyste" always reads in a stable order regardless of
// the raw relation order the bootstrap returns. `team_member` is the implicit
// baseline and is only shown (as the sole label) when no elevated role is held.
const ROLE_PRIORITY: Record<string, number> = {
  team_admin: 0,
  team_editor: 1,
  team_analyst: 2,
};

interface TeamSelectionListItemProps {
  /** Where clicking the row navigates — into the team (or the personal space). */
  redirection: To;
  /** Display name: the team name, or the personal-space label. */
  name: string;
  /** The current user's folded roles on this team (from `Team.my_relations`).
   *  Ignored for the personal space (`personal`), which shows no role line. */
  roles?: UserTeamRelation[];
  /** Personal space: renders the user's initials avatar and hides the role line. */
  personal?: boolean;
  /** Team banner image; when absent, coloured initials are shown instead. */
  imgUrl?: string;
  /** Initials source — the user's full name for the personal space, the team
   *  name for a team's fallback avatar. */
  avatarName: string;
  /** Override the name-derived avatar colour (the personal-space accent). */
  avatarColor?: TeamColor;
}

/**
 * One row of the Home team list (mainNavPanel): an avatar plus the team name
 * and the user's roles on that team. Clicking navigates into the team, exactly
 * like the former far-left team rail avatar did.
 */
export default function TeamSelectionListItem({
  redirection,
  name,
  roles = [],
  personal = false,
  imgUrl,
  avatarName,
  avatarColor,
}: TeamSelectionListItemProps) {
  const { t } = useTranslation();

  const heldRoles = roles
    .filter((relation) => relation in ROLE_PRIORITY)
    .slice()
    .sort((a, b) => ROLE_PRIORITY[a] - ROLE_PRIORITY[b]);
  const roleLabel =
    heldRoles.length === 0
      ? t("rework.teamRoles.team_member")
      : heldRoles.map((relation) => t(`rework.teamRoles.${relation}`)).join(" · ");

  return (
    <Link to={redirection} className={styles.item} aria-label={name}>
      {personal ? (
        <UserAvatar name={avatarName} size="small" />
      ) : imgUrl ? (
        <img className={styles.avatar} src={imgUrl} alt="" />
      ) : (
        <TeamInitials className={styles.avatar} name={avatarName} size="small" color={avatarColor} />
      )}
      <span className={styles.labels}>
        <span className={styles.name}>{name}</span>
        {!personal && <span className={styles.roles}>{roleLabel}</span>}
      </span>
    </Link>
  );
}
