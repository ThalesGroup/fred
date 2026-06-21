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
import { useParams } from "react-router-dom";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap.ts";
import { useListAllTagsKnowledgeFlowV1TagsGetQuery } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { KeyCloakService } from "../../../../security/KeycloakService.ts";
import DocumentWorkspace from "./DocumentWorkspace/DocumentWorkspace.tsx";
import TeamFilesystemBrowser from "./TeamFilesystemBrowser/TeamFilesystemBrowser.tsx";
import WorkspaceRoot from "./WorkspaceRoot/WorkspaceRoot.tsx";
import styles from "./TeamResourcesPage.module.css";

/**
 * Official rework workspace page (FILES-04). A single tree with three differentiated roots,
 * visible together:
 * - Resources: document ingestion into the searchable corpus (expanded by default)
 * - Mon espace: the user's personal-in-team files (teams/{team}/users/{uid}, via /fs)
 * - Espace d'équipe: the team-shared files (teams/{team}/shared, via /fs)
 */
export default function TeamResourcesPage() {
  const { t } = useTranslation();
  const { teamId = "" } = useParams<{ teamId: string }>();
  const { activeTeam } = useFrontendBootstrap();
  const isPersonalTeam = teamId === activeTeam?.id;
  const userId = KeyCloakService.GetUserId() ?? "";
  const teamName = activeTeam?.name ?? teamId;

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
        <h1 className={styles.title}>{t("rework.resources.workspaceTitle")}</h1>
      </header>

      <div className={styles.tree}>
        <WorkspaceRoot
          icon={{ category: "outlined", type: "database" }}
          title={t("rework.resources.roots.resources")}
          meta={<span className={styles.badge}>{t("rework.resources.roots.indexed")}</span>}
          defaultOpen
        >
          <DocumentWorkspace teamId={teamId} isPersonalTeam={isPersonalTeam} />
        </WorkspaceRoot>

        <WorkspaceRoot
          icon={{ category: "outlined", type: "person" }}
          title={t("rework.resources.roots.mine")}
          meta={t("rework.resources.roots.private", { team: teamName })}
        >
          <TeamFilesystemBrowser
            root={`teams/${teamId}/users/${userId}`}
            rootLabel={t("rework.resources.roots.mine")}
          />
        </WorkspaceRoot>

        <WorkspaceRoot icon={{ category: "outlined", type: "groups" }} title={t("rework.resources.roots.team")}>
          <TeamFilesystemBrowser root={`teams/${teamId}/shared`} rootLabel={t("rework.resources.roots.team")} />
        </WorkspaceRoot>
      </div>
    </div>
  );
}
