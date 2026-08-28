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

import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { toIconType } from "@shared/utils/Type.ts";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useSelectedTeam } from "../../../../hooks/useSelectedTeam.ts";
import {
  applicationCatalogRevision,
  applicationRegistry,
} from "@rework/features/applications/generated/applicationRegistry.ts";
import { applicationRouteBasePath } from "@rework/features/applications/applicationPath.ts";
import { resolveApplicationRegistration } from "@rework/features/applications/applicationResolution.ts";
import { useTeamApplications } from "@rework/features/applications/useTeamApplications.ts";
import styles from "./TeamApplicationsPage.module.css";

export default function TeamApplicationsPage() {
  const { t } = useTranslation();
  const { teamId, isPersonalTeam } = useSelectedTeam();
  const { data, isLoading, isError } = useTeamApplications(teamId, isPersonalTeam);

  useEffect(() => {
    if (data && data.catalog_revision !== applicationCatalogRevision) {
      console.warn("[applications] frontend and control-plane catalog revisions differ");
    }
  }, [data]);

  const applications = data?.items ?? [];

  return (
    <div className={styles.page}>
      <PageHeader title={t("teamAppsPage.title")} subtitle={t("teamAppsPage.subtitle")} />

      {isLoading && (
        <p className={styles.status} role="status">
          {t("teamAppsPage.loading")}
        </p>
      )}
      {isError && !isPersonalTeam && (
        <p className={styles.error} role="alert">
          {t("teamAppsPage.loadError")}
        </p>
      )}

      {!isLoading && (isPersonalTeam || (!isError && applications.length === 0)) && (
        <PageEmptyState icon="widgets" message={t("teamAppsPage.noAppDescription")} />
      )}

      {!isLoading && !isError && !isPersonalTeam && applications.length > 0 && (
        <ul className={styles.grid}>
          {applications.map((application) => {
            const resolution = resolveApplicationRegistration(application, applicationRegistry);
            const content = (
              <>
                <span className={styles.icon} aria-hidden="true">
                  <Icon category="outlined" type={toIconType(application.icon, "widgets")} filled />
                </span>
                <span className={styles.copy}>
                  <span className={styles.name}>{t(application.name, { defaultValue: application.name })}</span>
                  <span className={styles.description}>
                    {t(application.description, { defaultValue: application.description })}
                  </span>
                  {resolution.status !== "ready" && (
                    <span className={styles.unavailable}>{t("teamAppsPage.localUnavailable")}</span>
                  )}
                </span>
                {resolution.status === "ready" && (
                  <span className={styles.chevron} aria-hidden="true">
                    <Icon category="outlined" type="chevron_right" />
                  </span>
                )}
              </>
            );

            return (
              <li key={application.id}>
                {resolution.status === "ready" && teamId ? (
                  <Link className={styles.card} to={applicationRouteBasePath(teamId, application.id)}>
                    {content}
                  </Link>
                ) : (
                  <div className={`${styles.card} ${styles.cardDisabled}`} aria-disabled="true">
                    {content}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
