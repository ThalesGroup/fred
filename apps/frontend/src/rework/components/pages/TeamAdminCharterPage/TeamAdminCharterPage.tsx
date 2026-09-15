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

import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import TeamAdminCharterContent from "@shared/molecules/TeamAdminCharterContent/TeamAdminCharterContent.tsx";
import { useAcceptTeamAdminCharterMutation } from "../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import styles from "./TeamAdminCharterPage.module.css";

/** Stands in for a team's pages until its pending admin accepts the charter. */
export default function TeamAdminCharterPage() {
  const { t } = useTranslation();
  const [acceptCharter, { isLoading }] = useAcceptTeamAdminCharterMutation();
  const [endReached, setEndReached] = useState(false);
  const handleEndReached = useCallback(() => setEndReached(true), []);

  return (
    <div className={styles.page}>
      <div className={styles.title}>{t("rework.teamAdminCharter.title")}</div>
      <div className={styles.content}>
        <TeamAdminCharterContent onEndReached={handleEndReached} />
      </div>
      <div className={styles.actions}>
        <span className={styles.information}>{t("rework.teamAdminCharter.lockInformation")}</span>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          disabled={!endReached || isLoading}
          onClick={() => void acceptCharter()}
        >
          {t("rework.teamAdminCharter.accept")}
        </Button>
      </div>
    </div>
  );
}
