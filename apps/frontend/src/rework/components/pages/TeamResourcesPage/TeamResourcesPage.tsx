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
import {
  useListTagsQuery,
  useGetTagCorpusTypeStatsQuery,
} from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { KeyCloakService } from "../../../../security/KeycloakService.ts";
import { isPersonalTeamId, personalTeamId } from "@shared/utils/teamId.ts";
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
  // isPersonalTeamId alone is authoritative (handles both the bare "personal"
  // alias and the canonical "personal-<uid>" id — see its own doc comment).
  const isPersonalTeam = isPersonalTeamId(teamId);
  const userId = KeyCloakService.GetUserId() ?? "";
  // Resolve the bare personal alias before querying corpus data and importing files.
  const fsTeamId = teamId === "personal" ? personalTeamId(userId) : teamId;
  // `refetch` as well as `data`: the storage-quota meter below reads this team
  // row's `current_resources_storage_size`, but every write to it comes from
  // the knowledge-flow API (upload charges it, delete releases it) — a
  // different RTK Query instance, whose tag invalidations cannot reach this
  // control-plane cache entry. Without a manual refetch on the workspace's own
  // change signal the meter keeps showing the figure it had at mount.
  const { data: team, refetch: refetchTeam, isUninitialized: teamUninitialized } = useGetTeamQuery({ teamId });
  const [statsOpen, setStatsOpen] = useState(false);
  // The corpus query walks every readable library and document; fetch only
  // when the usage panel is open.
  const corpusStats = useGetTagCorpusTypeStatsQuery(
    { teamId: fsTeamId },
    { skip: !statsOpen },
  );

  // KF health gate — identical pattern to the old KnowledgeHubPage.
  const { isError, isLoading, isFetching, isUninitialized } = useListTagsQuery({
    type: "document",
    limit: 1,
    offset: 0,
  });
  // Blocks on the first answer only. This gate returns the whole page to a
  // spinner, which unmounts DocumentWorkspace with it — and that workspace owns
  // the folder you are standing in, its loaded document pages and its resolved
  // folder sizes, none of which survive. Letting a background revalidation do
  // that turned one probe refetch into a full reload of the page.
  const kfState = getQueryUiState(
    { isLoading, isFetching, isUninitialized, isError },
    { keepPreviousWhileRefetching: true },
  );

  if (kfState === "loading") {
    return (
      <div className={styles.loadingState}>
        <Spinner size={20} />
        {t("rework.resources.loading")}
      </div>
    );
  }
  if (kfState === "error") {
    return (
      <ServiceNotice
        icon="cloud_off"
        title={t("rework.serviceNotice.knowledgeService.title")}
        description={t("rework.serviceNotice.knowledgeService.description")}
        centered
      />
    );
  }

  const hasQuota = team?.max_resources_storage_size != null;

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
                  {formatBytes(team!.current_resources_storage_size ?? 0)} /{" "}
                  {formatBytes(team!.max_resources_storage_size!)}
                </span>
              </div>
              <ProgressBar
                theme="primary"
                current={team!.current_resources_storage_size ?? 0}
                max={team!.max_resources_storage_size!}
              />
            </div>
          )}
        </div>
      </header>

      {statsOpen && (
        <ResourceStatsCards
          entries={corpusStats.data?.entries}
          isLoading={corpusStats.isLoading}
          isError={corpusStats.isError}
        />
      )}

      <div className={styles.panel}>
        <div className={styles.workspace}>
          <DocumentWorkspace
            teamId={teamId}
            importScopeId={fsTeamId}
            isPersonalTeam={isPersonalTeam}
            onDocumentsChanged={() => {
              if (!corpusStats.isUninitialized) void corpusStats.refetch();
              if (!teamUninitialized) void refetchTeam();
            }}
          />
        </div>

        {/* A rail beside the documents card until it is opened, when it
            widens in place into the panel itself. */}
        <ImportPanel teamId={fsTeamId} />
      </div>
    </div>
  );
}
