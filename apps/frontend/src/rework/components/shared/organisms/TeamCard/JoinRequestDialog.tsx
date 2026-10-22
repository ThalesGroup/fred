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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useAskToJoinTeamMutation } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";

/** The optional message the team admins read with the request. */
export const JOIN_REQUEST_MESSAGE_MAX_LENGTH = 280;

interface JoinRequestDialogProps {
  team: Pick<Team, "id" | "name">;
  open: boolean;
  onClose: () => void;
}

/** Asks to join an `on_request` team, with an optional message for its admins. */
export default function JoinRequestDialog({ team, open, onClose }: JoinRequestDialogProps) {
  const { t } = useTranslation();
  const [askToJoin, { isLoading: isAsking }] = useAskToJoinTeamMutation();
  const [message, setMessage] = useState("");

  const handleAsk = async (): Promise<void> => {
    try {
      const trimmed = message.trim();
      await askToJoin({ teamId: team.id, createTeamJoinRequest: { message: trimmed || null } }).unwrap();
      setMessage("");
    } catch (error) {
      // The request list refetches either way, so the caller shows the real state.
      console.error("Ask to join error:", error);
    }
    onClose();
  };

  return (
    <Dialog
      open={open}
      title={t("rework.teamCard.askDialog.title", { team: team.name })}
      confirmLabel={t("rework.teamCard.askDialog.confirm")}
      confirmDisabled={isAsking}
      onConfirm={() => void handleAsk()}
      onCancel={onClose}
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
  );
}
