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
import { Tab, Tabs } from "@mui/material";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap.ts";
import { useListAllTagsKnowledgeFlowV1TagsGetQuery } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { KeyCloakService } from "../../../../security/KeycloakService.ts";
import DocumentWorkspace from "./DocumentWorkspace/DocumentWorkspace.tsx";
import TeamFilesystemBrowser from "./TeamFilesystemBrowser/TeamFilesystemBrowser.tsx";
import styles from "./TeamResourcesPage.module.css";

type ResourceArea = "resources" | "mine" | "team";

/**
 * Official rework Resources page. Surfaces three areas: document ingestion (searchable
 * corpus), the user's personal-in-team files, and the team-shared files — the latter two
 * backed by the unified /fs filesystem (FILES-04).
 */
export default function TeamResourcesPage() {
  const { t } = useTranslation();
  const { teamId = "" } = useParams<{ teamId: string }>();
  const { activeTeam } = useFrontendBootstrap();
  const isPersonalTeam = teamId === activeTeam?.id;
  const [area, setArea] = useState<ResourceArea>("resources");
  const userId = KeyCloakService.GetUserId() ?? "";

  // KF health gate — identical pattern to the old KnowledgeHubPage.
  const { isError, isLoading, isFetching, isUninitialized } = useListAllTagsKnowledgeFlowV1TagsGetQuery({
    type: "document",
    limit: 1,
    offset: 0,
  });
  const kfState = getQueryUiState({ isLoading, isFetching, isUninitialized, isError });

  if (kfState === "loading") {
    return <div className={styles.loadingState}>{t("rework.resources.loading")}</div>;
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

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{t("rework.resources.title")}</h1>
      </header>

      <Tabs value={area} onChange={(_event, next: ResourceArea) => setArea(next)}>
        <Tab value="resources" label={t("rework.resources.tabs.resources")} />
        <Tab value="mine" label={t("rework.resources.tabs.mine")} />
        <Tab value="team" label={t("rework.resources.tabs.team")} />
      </Tabs>

      <div className={styles.content}>
        {area === "resources" && <DocumentWorkspace teamId={teamId} isPersonalTeam={isPersonalTeam} />}
        {area === "mine" && (
          <TeamFilesystemBrowser root={`teams/${teamId}/users/${userId}`} rootLabel={t("rework.resources.tabs.mine")} />
        )}
        {area === "team" && (
          <TeamFilesystemBrowser root={`teams/${teamId}/shared`} rootLabel={t("rework.resources.tabs.team")} />
        )}
      </div>
    </div>
  );
}
