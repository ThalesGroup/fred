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
import Button from "@shared/atoms/Button/Button.tsx";
import TeamAdminCharterContent from "@shared/molecules/TeamAdminCharterContent/TeamAdminCharterContent.tsx";
import {
  useAcceptTeamAdminCharterMutation,
  useGetTeamAdminCharterAcceptanceQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import styles from "./TeamSettingsResponsibilities.module.scss";

interface TeamSettingsResponsibilitiesProps {
  /** A pending admin accepts the charter here without leaving the team. */
  canAccept?: boolean;
}

/** The team administrator charter: admins see when they accepted it, pending admins accept it here. */
export default function TeamSettingsResponsibilities({ canAccept = false }: TeamSettingsResponsibilitiesProps) {
  const { t, i18n } = useTranslation();
  const [acceptCharter, { isLoading }] = useAcceptTeamAdminCharterMutation();
  const { data: acceptance } = useGetTeamAdminCharterAcceptanceQuery(undefined, { skip: canAccept });
  const acceptedAt =
    !canAccept && acceptance?.accepted_at
      ? new Date(acceptance.accepted_at).toLocaleString(i18n.language, { dateStyle: "long", timeStyle: "short" })
      : null;

  return (
    <div className={styles.responsibilities}>
      <TeamAdminCharterContent />
      {(canAccept || acceptedAt) && (
        <div className={styles.footer}>
          {acceptedAt && (
            <span className={styles.acceptedAt}>{t("rework.teamAdminCharter.acceptedOn", { date: acceptedAt })}</span>
          )}
          {canAccept && (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={isLoading}
              onClick={() => void acceptCharter()}
            >
              {t("rework.teamAdminCharter.accept")}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
