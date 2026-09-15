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
import { useAcceptTeamAdminCharterMutation } from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import styles from "./TeamSettingsResponsibilities.module.scss";

interface TeamSettingsResponsibilitiesProps {
  /** A pending admin accepts the charter here without leaving the team. */
  canAccept?: boolean;
}

/** The team administrator charter, readable at any time by admins and accepted here by pending ones. */
export default function TeamSettingsResponsibilities({ canAccept = false }: TeamSettingsResponsibilitiesProps) {
  const { t } = useTranslation();
  const [acceptCharter, { isLoading }] = useAcceptTeamAdminCharterMutation();

  return (
    <div className={styles.responsibilities}>
      <TeamAdminCharterContent />
      {canAccept && (
        <div className={styles.actions}>
          <Button
            color="primary"
            variant="filled"
            size="medium"
            disabled={isLoading}
            onClick={() => void acceptCharter()}
          >
            {t("rework.teamAdminCharter.accept")}
          </Button>
        </div>
      )}
    </div>
  );
}
