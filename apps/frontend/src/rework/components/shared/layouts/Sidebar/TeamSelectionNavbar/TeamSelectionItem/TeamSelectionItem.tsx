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

import { useTranslation } from "react-i18next";
import styles from "./TeamSelectionItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials.tsx";
import type { TeamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import { Link, To } from "react-router-dom";

interface TeamSelectionItemProps {
  redirection: To;
  teamName: string;
  selected: boolean;
  imgUrl?: string;
  /** When set and there is no `imgUrl`, render coloured initials instead of the icon. */
  avatarName?: string;
  /** Override the name-derived avatar colour (e.g. the personal-space accent). */
  avatarColor?: TeamColor;
  /** Square for teams, round for the personal space. */
  avatarShape?: "square" | "round";
  icon?: IconProps;
  activityDot?: boolean;
}

export default function TeamSelectionItem({
  redirection,
  teamName,
  selected,
  imgUrl,
  avatarName,
  avatarColor,
  avatarShape = "square",
  icon = { category: "outlined", type: "groups", filled: true },
  activityDot = false,
}: TeamSelectionItemProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.teamAvatarContainer} data-selected={selected}>
      <Link to={redirection} className={styles.link}>
        <div className={styles.stateLayer}>
          {imgUrl ? (
            <img
              className={styles.teamAvatar}
              src={imgUrl}
              alt={t("rework.sidebar.team.avatarAlt", { teamName: teamName })}
            />
          ) : avatarName ? (
            <TeamInitials
              className={styles.teamAvatar}
              name={avatarName}
              size="small"
              shape={avatarShape}
              color={avatarColor}
            />
          ) : (
            <span className={styles.icon}>
              <Icon {...icon} />
            </span>
          )}
        </div>
      </Link>
      {activityDot && <span className={styles.activityDot} aria-hidden="true" />}
      <span className={styles.teamTooltip}>{teamName}</span>
    </div>
  );
}
