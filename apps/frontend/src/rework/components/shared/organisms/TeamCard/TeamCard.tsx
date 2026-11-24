// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials";
import { teamColor } from "@shared/atoms/TeamInitials/teamColor";
import Button from "@shared/atoms/Button/Button";
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
  return (
    <div className={styles.teamCardContainer}>
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
          <div className={styles.teamCardHeaderText}>
            <Tooltip content={team.name} asChild>
              <div tabIndex={0} className={styles.teamName}>
                {team.name}
              </div>
            </Tooltip>
          </div>
        </div>
        {team.description && (
          <Tooltip content={team.description} asChild>
            <div tabIndex={0} className={styles.teamCardDescription}>
              {team.description}
            </div>
          </Tooltip>
        )}
        <div className={styles.teamCardFooter}>
          {team.is_member ? (
            <Link to={`/team/${team.id}`}>
              {t(project ? "rework.projectParameters.card.open" : "rework.teamDiscovery.openTeam")}
            </Link>
          ) : team.can_join ? (
            <Button
              color="primary"
              variant="outlined"
              size="small"
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
        </div>
        {failed && (
          <span role="alert">
            {t(project ? "rework.projectParameters.card.joinFailed" : "rework.teamDiscovery.joinFailed")}
          </span>
        )}
      </div>
    </div>
  );
}
