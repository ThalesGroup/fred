// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials";
import { teamColor } from "@shared/atoms/TeamInitials/teamColor";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import type { DiscoverableTeam } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useGetTeamAvatarQuery,
  useJoinTeamMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { sessionQueryArgs } from "../../../../../slices/controlPlane/controlPlaneApi";
import styles from "./TeamCard.module.scss";

/** A team in the organization directory, or a project in its team's list (`kind="project"`). */
export default function TeamCard({
  team,
  kind = "team",
  onJoined,
}: {
  team: DiscoverableTeam;
  kind?: "team" | "project";
  onJoined?: () => void;
}) {
  const { t } = useTranslation();
  const project = kind === "project";
  const { defaultTeamAvatarFile } = useFrontendProperties();
  const avatar = useGetTeamAvatarQuery(sessionQueryArgs({ id: team.id }), {
    ...crossSessionRefreshOptions(false),
    refetchOnMountOrArgChange: true,
  });
  useRefetchOnWindowFocus(avatar.refetch, false, true);
  const image =
    !avatar.isError && !avatar.isFetching && avatar.currentData
      ? avatar.currentData
      : defaultTeamAvatarFile
        ? `/images/${defaultTeamAvatarFile}`
        : undefined;
  const [join, joining] = useJoinTeamMutation();
  const [failed, setFailed] = useState(false);
  const extraOwners = team.owner_count - team.owners.length;
  const owners = [...team.owners, ...(extraOwners > 0 ? [`+${extraOwners}`] : [])].join(", ");
  const details = (
    <div className={styles.teamCardDetails}>
      <div className={styles.teamCardHeader}>
        {image ? (
          <img className={styles.teamAvatar} src={image} alt="" width={48} height={48} />
        ) : (
          <TeamInitials
            className={styles.teamAvatar}
            name={team.name}
            size="medium"
            shape="square"
            color={teamColor(team.name)}
          />
        )}
        <span className={styles.teamCardHeaderText}>
          <span className={styles.teamName}>{team.name}</span>
          <span className={styles.teamMemberCount}>
            <Icon category="outlined" type="groups" />
            {t("rework.teamCard.memberCount", { count: team.member_count })}
          </span>
        </span>
      </div>
      {team.description && <span className={styles.teamCardDescription}>{team.description}</span>}
      {owners && <span className={styles.teamOwners}>{t("rework.teamCard.owners", { names: owners })}</span>}
      {!team.is_member && (
        <div className={styles.teamCardFooter}>
          {team.can_join ? (
            <Button
              color="primary"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "person_add" }}
              disabled={joining.isLoading}
              onClick={async () => {
                setFailed(false);
                try {
                  await join({ id: team.id }).unwrap();
                  onJoined?.();
                } catch {
                  setFailed(true);
                }
              }}
            >
              {t("rework.teamCard.join")}
            </Button>
          ) : (
            <span className={styles.teamJoiningLabel}>
              {t(
                team.joining_mode === "invite_only"
                  ? "rework.teamCard.inviteOnly"
                  : project
                    ? "rework.projectParameters.card.notEligible"
                    : "rework.teamDiscovery.notEligible",
              )}
            </span>
          )}
          {failed && (
            <span role="alert" className={styles.teamJoiningLabel}>
              {t(project ? "rework.projectParameters.card.joinFailed" : "rework.teamDiscovery.joinFailed")}
            </span>
          )}
        </div>
      )}
    </div>
  );
  // Only a member can open the space: the whole card is then one link, holding no
  // other control. A non-member card is not clickable; its only action is joining.
  return team.is_member ? (
    <Link to={`/team/${team.id}`} className={`${styles.teamCardContainer} ${styles.teamCardLink}`}>
      {details}
    </Link>
  ) : (
    <div className={styles.teamCardContainer}>{details}</div>
  );
}
