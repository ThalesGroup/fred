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

  return (
    <div className={styles.teamAvatarContainer} data-selected={selected}>
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
      <span className={styles.teamTooltip}>{teamName}</span>
    </div>
  );
}
