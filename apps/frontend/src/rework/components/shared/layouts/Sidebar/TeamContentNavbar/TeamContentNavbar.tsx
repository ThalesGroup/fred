// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import NavigationMenu from "@shared/molecules/NavigationMenu/NavigationMenu.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials.tsx";
import { teamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import { KeyCloakService } from "../../../../../../security/KeycloakService";
import { useMySpacesQuery } from "../../../../../../slices/fredManager/fredManagerApiEnhancements";
import styles from "./TeamContentNavbar.module.scss";

export default function TeamContentNavbar({ spaceId }: { spaceId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const spaces = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const space = !spaces.isFetching && !spaces.isError ? spaces.currentData?.find((s) => s.id === spaceId) : undefined;
  const personal = !!space?.personal_owner;
  const name = personal ? t("rework.sidebar.team.userTeam") : space?.name;
  return (
    <div className={styles.mainNavPanel}>
      {space && (
        <div className={styles.teamPanelHeader}>
          <div className={styles.teamPanelHeaderText}>
            <div className={styles.teamPanelIdentity}>
              {personal ? (
                <UserAvatar name={KeyCloakService.GetUserFullName()} size="x-small" />
              ) : (
                <TeamInitials
                  className={styles.teamPanelAvatar}
                  name={space.name}
                  size="small"
                  shape="square"
                  color={teamColor(space.name)}
                />
              )}
              <div className={styles.teamPanelTitle}>
                {!personal && <span className={styles.teamPanelKicker}>{t(`rework.manager.kinds.${space.kind}`)}</span>}
                <span className={styles.teamPanelName}>{name}</span>
              </div>
            </div>
            {!personal && (
              <span className={styles.teamPanelRoles}>
                {space.roles.map((r) => t(`rework.manager.roles.${r}`)).join(", ")}
              </span>
            )}
          </div>
        </div>
      )}
      <div className={styles.navigationContainer}>
        <div className={styles["settings-back-container"]}>
          <Button
            color="primary"
            variant="text"
            size="small"
            icon={{ category: "outlined", type: "arrow_back" }}
            onClick={() => navigate("/home")}
          >
            {t("rework.back")}
          </Button>
        </div>
        {space && space.kind !== "organization" && (
          <NavigationMenu
            items={[
              {
                type: "link",
                label: t("rework.sidebar.team.menu.resources"),
                icon: { category: "outlined", type: "folder", filled: true },
                linkProps: { to: `/team/${space.id}/resources` },
              },
            ]}
          />
        )}
      </div>
    </div>
  );
}
