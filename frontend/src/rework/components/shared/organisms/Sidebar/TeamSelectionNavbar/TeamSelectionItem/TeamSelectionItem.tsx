import { useTranslation } from "react-i18next";
import styles from "./TeamSelectionItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import { useState } from "react";
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
  icon = { category: "outlined", type: "group", filled: true },
}: TeamSelectionItemProps) {
  const { t } = useTranslation();
  const [isLoaded, setIsLoaded] = useState(false);
  return (
    <div
      className={`${styles["team-avatar-container"]} ${selected ? styles["selected"] : ""} ${isLoaded ? styles["loaded"] : ""}`}
    >
      <Link to={redirection}>
        <div className={styles["state-layer"]}>
          <span className={styles.icon}>
            <Icon {...icon} />
          </span>
          <img
            className={styles["team-avatar"]}
            src={imgUrl ? imgUrl : ""}
            alt={t("rework.sidebar.team.avatarAlt", { teamName: teamName })}
            onLoad={() => setIsLoaded(true)}
          />
        </div>
      </Link>
      <span className={styles["team-tooltip"]}>{teamName}</span>
    </div>
  );
}
