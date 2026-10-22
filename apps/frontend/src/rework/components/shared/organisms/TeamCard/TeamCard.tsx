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

import styles from "./TeamCard.module.scss";
import type { MyTeamJoinRequest, Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useAskToJoinTeamMutation,
  useCancelTeamJoinRequestMutation,
  useJoinTeamMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials.tsx";
import { PERSONAL_TEAM_COLOR, teamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import { useTranslation } from "react-i18next";
import AvatarGroup from "@shared/molecules/AvatarGroup/AvatarGroup.tsx";
import { useFrontendProperties } from "src/hooks/useFrontendProperties";
import { useFrontendBootstrap } from "src/hooks/useFrontendBootstrap";
import Button from "@shared/atoms/Button/Button.tsx";
import React, { useState } from "react";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import { KeyCloakService } from "../../../../../security/KeycloakService.ts";
import { teamDescriptionText } from "@core/utils/teamFields.ts";

export interface TeamCardProps {
  team: Team;
  /** Called after a successful self-service join (JoiningMode.OPEN) — lets the
   * page refresh anything derived outside this card's own team-list cache
   * (e.g. the bootstrap-driven team navbar). */
  onJoined?: () => void;
  /** The caller's own request to this team, for an `on_request` team. */
  joinRequest?: MyTeamJoinRequest;
}

/** The optional message the team admins read with the request. */
export const JOIN_REQUEST_MESSAGE_MAX_LENGTH = 280;

type RequestState = "ask" | "pending" | "declined";

function requestState(request: MyTeamJoinRequest | undefined, now: number): RequestState {
  if (!request) return "ask";
  if (request.status === "pending") return "pending";
  const askAgainAt = request.can_ask_again_at ? Date.parse(request.can_ask_again_at) : 0;
  return askAgainAt > now ? "declined" : "ask";
}

export default function TeamCard({ team, onJoined, joinRequest }: TeamCardProps) {
  const { defaultTeamAvatarFile, defaultPersonalAvatarFile } = useFrontendProperties();
  const { activeTeam } = useFrontendBootstrap();
  const { t, i18n } = useTranslation();
  const [joinTeam, { isLoading: isJoining }] = useJoinTeamMutation();
  const [askToJoin, { isLoading: isAsking }] = useAskToJoinTeamMutation();
  const [cancelRequest, { isLoading: isCancelling }] = useCancelTeamJoinRequestMutation();
  const [askOpen, setAskOpen] = useState(false);
  const [message, setMessage] = useState("");
  const userFullName = KeyCloakService.GetUserFullName();
  const description = teamDescriptionText(team, t);

  // A configured default avatar replaces initials; without one, the card keeps
  // the name-derived coloured initials. The personal space renders round, teams
  // square (#2300 — the team image is now a square avatar, not a wide banner).
  const isPersonal = team.id === activeTeam?.id;
  const avatarFile = isPersonal ? defaultPersonalAvatarFile : defaultTeamAvatarFile;
  const color = isPersonal ? PERSONAL_TEAM_COLOR : teamColor(team.name);
  const avatarName = isPersonal ? userFullName : team.name;
  const roundAvatar = isPersonal ? { borderRadius: "50%" } : undefined;

  const handleJoinTeam = async (e: React.MouseEvent<HTMLButtonElement>): Promise<void> => {
    e.preventDefault();
    try {
      await joinTeam({ teamId: team.id }).unwrap();
      onJoined?.();
    } catch (error) {
      console.error("Join team error:", error);
    }
  };

  const handleAsk = async (): Promise<void> => {
    try {
      const trimmed = message.trim();
      await askToJoin({ teamId: team.id, createTeamJoinRequest: { message: trimmed || null } }).unwrap();
      setAskOpen(false);
      setMessage("");
    } catch (error) {
      // The request list refetches either way, so the card shows the real state.
      console.error("Ask to join error:", error);
      setAskOpen(false);
    }
  };

  const handleCancel = async (e: React.MouseEvent<HTMLButtonElement>): Promise<void> => {
    e.preventDefault();
    try {
      await cancelRequest({ teamId: team.id }).unwrap();
    } catch (error) {
      console.error("Cancel join request error:", error);
    }
  };

  // Non-members see one join affordance: a direct self-service join for OPEN
  // teams, a request for ON_REQUEST teams, an "invite only" label otherwise.
  const canJoinDirectly = !team.is_member && team.joining_mode === "open";
  const isInviteOnlyOutsider = !team.is_member && team.joining_mode === "invite_only";
  const onRequest = !team.is_member && team.joining_mode === "on_request";
  const request = onRequest ? requestState(joinRequest, Date.now()) : undefined;
  const askAgainAt =
    request === "declined" && joinRequest?.can_ask_again_at
      ? new Date(joinRequest.can_ask_again_at).toLocaleString(i18n.language, {
          dateStyle: "medium",
          timeStyle: "short",
        })
      : undefined;

  return (
    <div className={styles.teamCardContainer}>
      <div className={styles.teamCardDetails}>
        <div className={styles.teamCardHeader}>
          {team.avatar_image_url ? (
            <img
              className={styles.teamAvatar}
              style={roundAvatar}
              src={team.avatar_image_url}
              alt=""
              aria-hidden="true"
              width={48}
              height={48}
              decoding="async"
            />
          ) : avatarFile ? (
            <img
              className={styles.teamAvatar}
              style={roundAvatar}
              src={`/images/${avatarFile}`}
              alt=""
              aria-hidden="true"
              width={48}
              height={48}
              decoding="async"
            />
          ) : (
            <TeamInitials
              className={styles.teamAvatar}
              name={avatarName}
              size="medium"
              shape={isPersonal ? "round" : "square"}
              color={color}
            />
          )}
          <div className={styles.teamCardHeaderText}>
            <div className={styles.teamName}>{team.name}</div>
            <div className={styles.teamMemberCount}>
              <span className={styles.teamMemberCountIcon}>
                <Icon category={"outlined"} type={"groups"} />
              </span>
              {t("rework.teamCard.memberCount", { count: team.member_count })}
            </div>
          </div>
        </div>
        {/* Personal spaces have no description: nothing to render. */}
        {description && <div className={styles.teamCardDescription}>{description}</div>}
        <div className={styles.teamCardFooter}>
          <div className={styles.teamCardAdmins}>
            <AvatarGroup
              avatars={(team.admins ?? []).map((o) => ({
                name: o.first_name + " " + o.last_name,
                imageUrl: o.avatar_image_url,
              }))}
              max={canJoinDirectly || onRequest ? 2 : 4}
            />
          </div>
          {canJoinDirectly && (
            <Button
              className={styles.teamCardJoinAction}
              color={"primary"}
              variant={"outlined"}
              size={"small"}
              icon={{ category: "outlined", type: "person_add" }}
              disabled={isJoining}
              onClick={handleJoinTeam}
            >
              {t("rework.teamCard.join")}
            </Button>
          )}
          {isInviteOnlyOutsider && <span className={styles.teamJoiningLabel}>{t("rework.teamCard.inviteOnly")}</span>}
          {request === "ask" && (
            <Button
              className={styles.teamCardJoinAction}
              color={"primary"}
              variant={"outlined"}
              size={"small"}
              icon={{ category: "outlined", type: "person_add" }}
              onClick={(e) => {
                e.preventDefault();
                setAskOpen(true);
              }}
            >
              {t("rework.teamCard.askToJoin")}
            </Button>
          )}
          {request === "pending" && (
            <span className={styles.teamRequestState}>
              <span className={styles.teamJoiningLabel}>{t("rework.teamCard.requestSent")}</span>
              <Button color={"primary"} variant={"text"} size={"small"} disabled={isCancelling} onClick={handleCancel}>
                {t("rework.teamCard.cancelRequest")}
              </Button>
            </span>
          )}
          {request === "declined" && (
            <span className={styles.teamRequestState}>
              <span className={styles.teamJoiningLabel}>{t("rework.teamCard.requestDeclined")}</span>
              {askAgainAt && (
                <span className={styles.teamJoiningLabel}>{t("rework.teamCard.askAgainAt", { date: askAgainAt })}</span>
              )}
            </span>
          )}
        </div>
      </div>
      {onRequest && (
        <Dialog
          open={askOpen}
          title={t("rework.teamCard.askDialog.title", { team: team.name })}
          confirmLabel={t("rework.teamCard.askDialog.confirm")}
          confirmDisabled={isAsking}
          onConfirm={() => void handleAsk()}
          onCancel={() => setAskOpen(false)}
        >
          <TextArea
            label={t("rework.teamCard.askDialog.messageLabel")}
            description={t("rework.teamCard.askDialog.messageDescription")}
            value={message}
            maxLength={JOIN_REQUEST_MESSAGE_MAX_LENGTH}
            rows={4}
            onChange={(e) => setMessage(e.target.value)}
          />
        </Dialog>
      )}
    </div>
  );
}
