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
import { CSSProperties, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

// Gap between the avatar and the portaled tooltip (matches --spacing-xs).
const TOOLTIP_GAP = 8;

interface TeamSelectionItemProps {
  redirection: To;
  teamName: string;
  selected: boolean;
  imgUrl?: string;
  /** When set and there is no `imgUrl`, render coloured initials instead of the icon. */
  avatarName?: string;
  /** Override the name-derived avatar colour (e.g. the personal-space accent). */
  avatarColor?: TeamColor;
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
  icon = { category: "outlined", type: "groups", filled: true },
  activityDot = false,
}: TeamSelectionItemProps) {
  const { t } = useTranslation();
  const [isHovered, setIsHovered] = useState(false);
  const [tooltipStyle, setTooltipStyle] = useState<CSSProperties>({});
  const containerRef = useRef<HTMLDivElement>(null);

  // Position the portaled tooltip relative to the avatar. The tooltip is
  // rendered into document.body so it escapes TeamSelectionNavbar's
  // scrollable team list (`overflow-x: clip`), which otherwise clips it
  // before it becomes visible.
  const updatePosition = useCallback(() => {
    const anchor = containerRef.current;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    setTooltipStyle({
      position: "fixed",
      top: rect.top + rect.height / 2,
      left: rect.right + TOOLTIP_GAP,
      transform: "translateY(-50%)",
    });
  }, []);

  useLayoutEffect(() => {
    if (isHovered) updatePosition();
  }, [isHovered, updatePosition]);

  // Reposition while visible on scroll (capture: also fires for the
  // scrollable team list) and on resize.
  useEffect(() => {
    if (!isHovered) return;
    const handler = () => updatePosition();
    window.addEventListener("scroll", handler, true);
    window.addEventListener("resize", handler);
    return () => {
      window.removeEventListener("scroll", handler, true);
      window.removeEventListener("resize", handler);
    };
  }, [isHovered, updatePosition]);

  return (
    <div
      className={styles.teamAvatarContainer}
      data-selected={selected}
      ref={containerRef}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <Link to={redirection} className={styles.link}>
        <div className={styles.stateLayer}>
          {imgUrl ? (
            <img
              className={styles.teamAvatar}
              src={imgUrl}
              alt={t("rework.sidebar.team.avatarAlt", { teamName: teamName })}
            />
          ) : avatarName ? (
            <TeamInitials className={styles.teamAvatar} name={avatarName} size="small" color={avatarColor} />
          ) : (
            <span className={styles.icon}>
              <Icon {...icon} />
            </span>
          )}
        </div>
      </Link>
      {activityDot && <span className={styles.activityDot} aria-hidden="true" />}
      {isHovered &&
        createPortal(
          <span className={styles.teamTooltip} style={tooltipStyle}>
            {teamName}
          </span>,
          document.body,
        )}
    </div>
  );
}
