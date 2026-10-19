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
import { useParams } from "react-router-dom";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar.tsx";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import { KeyCloakService } from "../../../../security/KeycloakService.ts";
import { managerTypeStats } from "../../../features/imports/managerDocuments";
import { useMySpacesQuery, useSummaryQuery } from "../../../../slices/fredManager/fredManagerApiEnhancements";
import { formatBytes } from "@shared/utils/formatBytes.ts";
import DocumentWorkspace from "./DocumentWorkspace/DocumentWorkspace.tsx";
import ResourceStatsCards from "./ResourceStatsCards/ResourceStatsCards.tsx";
import { ImportPanel } from "@shared/organisms/ImportPanel/ImportPanel.tsx";
import styles from "./TeamResourcesPage.module.css";

/** Document ingestion into the searchable corpus. Files live in a library
 * (folder/tag), so the root creates libraries rather than accepting uploads. */
export default function TeamResourcesPage() {
  const { t } = useTranslation();
  const { teamId = "" } = useParams<{ teamId: string }>();
  const userId = KeyCloakService.GetUserId() ?? "";
  const memberships = useMySpacesQuery();
  const isPersonalTeam = Boolean(memberships.currentData?.find((space) => space.id === teamId)?.personal_owner);
  const fsTeamId = teamId;
  const [statsOpen, setStatsOpen] = useState(false);
  const corpusStats = useSummaryQuery({ id: teamId }, { refetchOnMountOrArgChange: true });
  const summary = corpusStats.isError ? undefined : corpusStats.currentData;

  // Folder availability follows manager; content services do not gate classification.
  const { isError, isLoading, isFetching, isUninitialized } = memberships;
  // Blocks on the first answer only. This gate returns the whole page to a
  // spinner, which unmounts DocumentWorkspace with it — and that workspace owns
  // the folder you are standing in, its loaded document pages and its resolved
  // folder sizes, none of which survive. Letting a background revalidation do
  // that turned one probe refetch into a full reload of the page.
  const managerState = getQueryUiState(
    { isLoading, isFetching, isUninitialized, isError },
    { keepPreviousWhileRefetching: true },
  );

  if (managerState === "loading") {
    return (
      <div className={styles.loadingState}>
        <Spinner size={20} />
        {t("rework.resources.loading")}
      </div>
    );
  }
  if (managerState === "error") {
    return (
      <ServiceNotice
        icon="cloud_off"
        title={t("rework.resources.empty.loadError")}
        description={t("rework.resources.empty.loadError")}
        centered
      />
    );
  }

  const hasQuota = summary !== undefined;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>
            {isPersonalTeam ? t("rework.resources.pageTitlePersonal") : t("rework.resources.pageTitle")}
          </h1>
          <p className={styles.subtitle}>
            {isPersonalTeam ? t("rework.resources.pageSubtitlePersonal") : t("rework.resources.pageSubtitle")}
          </p>
        </div>
        <div className={styles.headerEnd}>
          <Tooltip text={t("rework.resources.stats.toggle")}>
            <IconButton
              color={statsOpen ? "secondary" : "on-surface-retreat"}
              variant={statsOpen ? "tonal" : "icon"}
              size="medium"
              icon={{ category: "outlined", type: "bar_chart", filled: statsOpen }}
              aria-expanded={statsOpen}
              aria-label={t("rework.resources.stats.toggle")}
              onClick={() => setStatsOpen((value) => !value)}
            />
          </Tooltip>
          {hasQuota && (
            <div className={styles.quota}>
              <div className={styles.quotaLabelRow}>
                <span className={styles.quotaLabel}>{t("rework.resources.storageQuota")}</span>
                <span className={styles.quotaValue}>
                  {formatBytes(summary!.used_bytes + summary!.reserved_bytes)} / {formatBytes(summary!.quota_bytes)}
                </span>
              </div>
              <ProgressBar
                theme="primary"
                current={summary!.used_bytes + summary!.reserved_bytes}
                max={summary!.quota_bytes}
              />
            </div>
          )}
        </div>
      </header>

      {statsOpen && (
        <ResourceStatsCards
          entries={managerTypeStats(summary)}
          isLoading={corpusStats.isLoading}
          isError={corpusStats.isError}
        />
      )}

      <div className={styles.panel}>
        <div className={styles.workspace}>
          <DocumentWorkspace
            key={`${userId}:${teamId}`}
            managerSpaceId={teamId}
            teamId={teamId}
            importScopeId={fsTeamId}
            isPersonalTeam={isPersonalTeam}
            onDocumentsChanged={() => {
              if (!corpusStats.isUninitialized) void corpusStats.refetch();
            }}
          />
        </div>

        {/* A rail beside the documents card until it is opened, when it
            widens in place into the panel itself. */}
        <ImportPanel key={`${userId}:${teamId}`} teamId={fsTeamId} managerSpaceId={teamId} />
      </div>
    </div>
  );
}
