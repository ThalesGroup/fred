// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

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

export default function TeamCard({ team, onJoined }: { team: DiscoverableTeam; onJoined?: () => void }) {
  const { t } = useTranslation();
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
            <div className={styles.teamName} title={team.name}>
              {team.name}
            </div>
          </div>
        </div>
        {team.description && (
          <div className={styles.teamCardDescription} title={team.description}>
            {team.description}
          </div>
        )}
        <div className={styles.teamCardFooter}>
          {team.is_member ? (
            <Link to={`/team/${team.id}`}>{t("rework.teamDiscovery.openTeam")}</Link>
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
                team.joining_mode === "invite_only" ? "rework.teamCard.inviteOnly" : "rework.teamDiscovery.notEligible",
              )}
            </span>
          )}
        </div>
        {failed && <p role="alert">{t("rework.teamDiscovery.joinFailed")}</p>}
      </div>
    </div>
  );
}
