import { useTranslation } from "react-i18next";
import styles from "./TeamSelectionItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import React, { useId } from "react";
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
  const id = useId();
  const safeId = `--anchor-${id.replace(/:/g, "")}`;

  return (
    <div
      className={styles.teamAvatarContainer}
      data-selected={selected}
      popoverTarget={safeId}
      style={{ anchorName: `--${safeId}` }}
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
        id={safeId}
        popover={"auto"}
        className={styles.teamTooltip}
        style={{ positionAnchor: `--${safeId}` } as React.CSSProperties}
      >
        {teamName}
      </span>
    </div>
  );
}
