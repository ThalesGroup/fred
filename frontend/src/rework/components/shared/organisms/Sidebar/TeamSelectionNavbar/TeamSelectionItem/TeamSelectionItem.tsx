import { useTranslation } from "react-i18next";
import styles from "./TeamSelectionItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import React, { useMemo } from "react";
import { Link, To } from "react-router-dom";

interface TeamSelectionItemProps {
  redirection: To;
  teamName: string;
  selected: boolean;
  imgUrl?: string;
  icon?: IconProps;
}

export default function TeamSelectionItem({
  redirection,
  teamName,
  selected,
  imgUrl,
  icon = { category: "outlined", type: "groups", filled: true },
}: TeamSelectionItemProps) {
  const { t } = useTranslation();
  const tooltipId = useMemo(() => `tooltip-${teamName}`.replace(" ", "_"), [teamName]);

  return (
    <div
      className={styles.teamAvatarContainer}
      data-selected={selected}
      popoverTarget={tooltipId}
      style={{ anchorName: `--${tooltipId}` }}
    >
      <Link to={redirection} className={styles.link}>
        <div className={styles.stateLayer}>
          <span className={styles.icon}>
            <Icon {...icon} />
          </span>
          {imgUrl && (
            <img
              className={styles.teamAvatar}
              src={imgUrl}
              alt={t("rework.sidebar.team.avatarAlt", { teamName: teamName })}
            />
          )}
        </div>
      </Link>
      <span
        id={tooltipId}
        popover={"auto"}
        className={styles.teamTooltip}
        style={{ positionAnchor: `--${tooltipId}` } as React.CSSProperties}
      >
        {teamName}
      </span>
    </div>
  );
}
