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
import AvatarGroup from "@shared/molecules/AvatarGroup/AvatarGroup";
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
  const ownerNames = [
    ...team.owners.map((owner) => owner.display_name),
    ...(extraOwners > 0 ? [`+${extraOwners}`] : []),
  ];
  // Swift's footer: owner avatars on the left, the join offer on the right. The
  // row is narrower beside the join button. A photo needs the caller's read access
  // to the space; outsiders see initials.
  const joinOffered = !team.is_member && team.can_join;
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
      <div className={styles.teamCardFooter}>
        {team.owner_count > 0 && (
          <div
            className={styles.teamCardOwners}
            role="img"
            aria-label={t("rework.teamCard.owners", { names: ownerNames.join(", ") })}
          >
            <AvatarGroup
              avatars={team.owners.map((owner) => ({
                name: owner.display_name,
                subject: team.is_member ? { spaceId: team.id, userId: owner.id } : undefined,
              }))}
              total={team.owner_count}
              max={joinOffered ? 2 : 4}
            />
          </div>
        )}
        {joinOffered ? (
          <Button
            className={styles.teamCardJoinAction}
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
          !team.is_member && (
            <span className={styles.teamJoiningLabel}>
              {t(
                team.joining_mode === "invite_only"
                  ? "rework.teamCard.inviteOnly"
                  : project
                    ? "rework.projectParameters.card.notEligible"
                    : "rework.teamDiscovery.notEligible",
              )}
            </span>
          )
        )}
      </div>
      {failed && (
        <span role="alert" className={styles.teamJoiningLabel}>
          {t(project ? "rework.projectParameters.card.joinFailed" : "rework.teamDiscovery.joinFailed")}
        </span>
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
