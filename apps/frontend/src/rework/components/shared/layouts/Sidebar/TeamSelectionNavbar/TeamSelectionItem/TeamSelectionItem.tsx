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

import styles from "./TeamSelectionItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials.tsx";
import type { TeamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import { Link, To } from "react-router-dom";
import { CSSProperties, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
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
  /** Shown bottom-right of the avatar when the current user is team_admin
   *  of this team (#2100). */
  adminBadge?: boolean;
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
  adminBadge = false,
}: TeamSelectionItemProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [tooltipStyle, setTooltipStyle] = useState<CSSProperties>({});
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipId = useId();

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
    if (isVisible) updatePosition();
  }, [isVisible, updatePosition]);

  // Reposition while visible on scroll (capture: also fires for the
  // scrollable team list) and on resize.
  useEffect(() => {
    if (!isVisible) return;
    const handler = () => updatePosition();
    window.addEventListener("scroll", handler, true);
    window.addEventListener("resize", handler);
    return () => {
      window.removeEventListener("scroll", handler, true);
      window.removeEventListener("resize", handler);
    };
  }, [isVisible, updatePosition]);

  return (
    <div
      className={styles.teamAvatarContainer}
      data-selected={selected}
      ref={containerRef}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      <Link
        to={redirection}
        className={styles.link}
        aria-label={teamName}
        aria-describedby={tooltipId}
        onFocus={() => setIsVisible(true)}
        onBlur={() => setIsVisible(false)}
      >
        <div className={styles.stateLayer}>
          {imgUrl ? (
            <img className={styles.teamAvatar} src={imgUrl} alt="" />
          ) : avatarName ? (
            <TeamInitials className={styles.teamAvatar} name={avatarName} size="small" color={avatarColor} />
          ) : (
            <span className={styles.icon} aria-hidden="true">
              <Icon {...icon} />
            </span>
          )}
        </div>
      </Link>
      {activityDot && <span className={styles.activityDot} aria-hidden="true" />}
      {adminBadge && (
        <span className={styles.adminBadge} aria-hidden="true">
          <Icon category="outlined" type="shield" filled />
        </span>
      )}
      {isVisible &&
        createPortal(
          <span id={tooltipId} role="tooltip" className={styles.teamTooltip} style={tooltipStyle}>
            {teamName}
          </span>,
          document.body,
        )}
    </div>
  );
}
