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

import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog.tsx";
import { useTranslation } from "react-i18next";
import styles from "./RepublishProposalDialog.module.css";

export type RepublishProposalCause = "saved" | "reactivated";

interface RepublishProposalDialogProps {
  open: boolean;
  agentName: string;
  cause: RepublishProposalCause;
  /** Why Publish is greyed (quota reached), shown in its place. */
  blockedReason?: string;
  onPublish: () => void;
  onIgnore: () => void;
}

/** Closed only by an explicit choice: the scrim and Escape do nothing. */
export default function RepublishProposalDialog({
  open,
  agentName,
  cause,
  blockedReason,
  onPublish,
  onIgnore,
}: RepublishProposalDialogProps) {
  const { t } = useTranslation();
  return (
    <ConfirmationDialog
      open={open}
      dismissible={false}
      title={t("rework.agentMarketplace.proposal.title")}
      message={t(`rework.agentMarketplace.proposal.${cause}`, { name: agentName })}
      details={blockedReason ? <p className={styles.blocked}>{blockedReason}</p> : undefined}
      confirmLabel={t("rework.agentMarketplace.proposal.publish")}
      cancelLabel={t("rework.agentMarketplace.proposal.ignore")}
      confirmDisabled={Boolean(blockedReason)}
      onConfirm={onPublish}
      onCancel={onIgnore}
    />
  );
}
