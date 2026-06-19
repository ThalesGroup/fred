// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// You may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { Box, Button, ButtonGroup, Container, Typography } from "@mui/material";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import DocumentLibraryList from "../components/documents/libraries/DocumentLibraryList";
import { UserAssetsList } from "../components/documents/libraries/UserAssetsList";
import InvisibleLink from "../components/InvisibleLink";
import ResourceLibraryList from "../components/resources/ResourceLibraryList";
import { useFrontendBootstrap } from "../hooks/useFrontendBootstrap";
import { usePermissions } from "../security/usePermissions";
import { useListAllTagsKnowledgeFlowV1TagsGetQuery } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";
import ServiceNotice from "../rework/components/shared/molecules/ServiceNotice/ServiceNotice";
import { useGetTeamQuery } from "../slices/controlPlane/controlPlaneApiEnhancements";
import StorageProgressBar from "@shared/molecules/StorageProgressBar/StorageProgressBar.tsx";

const knowledgeHubViews = ["documents", "chatContexts", "userAssets"] as const;
type KnowledgeHubView = (typeof knowledgeHubViews)[number];

function isKnowledgeHubView(value: string): value is KnowledgeHubView {
  return (knowledgeHubViews as readonly string[]).includes(value);
}

const defaultView: KnowledgeHubView = "documents";

/**
 * Render the personal knowledge hub using the bootstrap-owned personal team id.
 *
 * Why this component exists:
 * - the personal knowledge area remains a first-class navigation target during
 *   the frontend bootstrap migration
 *
 * How to use it:
 * - mount it for the personal-team route or when `KnowledgePage` resolves the
 *   active team to the bootstrap personal team
 *
 * Example:
 * - `<KnowledgeHub />`
 */
export const KnowledgeHub = () => {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const canCreateTag = can("tag", "create");
  const { activeTeam } = useFrontendBootstrap();
  const personalTeamId = activeTeam?.id ?? "personal";

  const { data: team, refetch: refetchTeam } = useGetTeamQuery({ teamId: personalTeamId });

  const [searchParams, setSearchParams] = useSearchParams();
  const viewParam = searchParams.get("view");
  const selectedView: KnowledgeHubView = isKnowledgeHubView(viewParam) ? viewParam : defaultView;

  // Ensure a default view in URL if missing
  useEffect(() => {
    if (!isKnowledgeHubView(viewParam)) {
      setSearchParams({ view: String(defaultView) }, { replace: true });
    }
  }, [viewParam, setSearchParams]);

  return (
    <>
      <TopBar title={t("knowledge.title")} description={t("knowledge.description")}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 3 }}>
          <Box sx={{ minWidth: "200px" }}>
            <StorageProgressBar
              currentBytes={team?.current_resources_storage_size ?? 0}
              maxBytes={team?.max_resources_storage_size ?? 0}
              theme={"primary"}
            />
          </Box>
          <ButtonGroup variant="outlined" color="primary" size="small">
            <InvisibleLink to={`/team/${personalTeamId}/ressources?view=chatContexts`}>
              <Button variant={selectedView === "chatContexts" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.chatContexts")}
              </Button>
            </InvisibleLink>
            {/* <InvisibleLink to={`/team/${userDetails?.personalTeam.id}/ressources?view=templates`}>
              <Button variant={selectedView === "templates" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.templates")}
              </Button>
            </InvisibleLink>
            <InvisibleLink to={`/team/${userDetails?.personalTeam.id}/ressources?view=prompts`}>
              <Button variant={selectedView === "prompts" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.prompts")}
              </Button>
            </InvisibleLink> */}
            <InvisibleLink to={`/team/${personalTeamId}/ressources?view=documents`}>
              <Button variant={selectedView === "documents" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.documents")}
              </Button>
            </InvisibleLink>
            <InvisibleLink to={`/team/${personalTeamId}/ressources?view=userAssets`}>
              <Button variant={selectedView === "userAssets" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.userAssets")}
              </Button>
            </InvisibleLink>
          </ButtonGroup>
        </Box>
      </TopBar>

      <Box sx={{ mb: 3, mt: 3, flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
        {selectedView === "chatContexts" && (
          <Container maxWidth="xl">
            <ResourceLibraryList kind="chat-context" />
          </Container>
        )}
        {selectedView === "documents" && (
          <Container maxWidth="xl" sx={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
            <DocumentLibraryList canCreateTag={canCreateTag} onUploadComplete={refetchTeam} />
          </Container>
        )}
        {selectedView === "userAssets" && <UserAssetsTab />}
        {/* {selectedView === "prompts" && (
          <Container maxWidth="xl">
            <ResourceLibraryList kind="prompt" />
          </Container>
        )}
        {selectedView === "templates" && (
          <Container maxWidth="xl">
            <ResourceLibraryList kind="template" />
          </Container>
        )} */}
      </Box>
    </>
  );
};

const UserAssetsTab = () => {
  const { t } = useTranslation();
  const {
    data: tags,
    isLoading,
    isError,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: "document", limit: 10000, offset: 0 },
    { refetchOnMountOrArgChange: true },
  );

  const userAssetsTagId = tags?.find((t) => t.name === "User Assets" || t.path === "user-assets")?.id;

  return (
    <Container maxWidth="xl">
      <UserAssetsList tagId={userAssetsTagId} />
      {isError && (
        <ServiceNotice
          icon="cloud_off"
          title={t("rework.serviceNotice.knowledgeService.title")}
          description={t("rework.serviceNotice.knowledgeService.description")}
          centered
        />
      )}
      {isLoading && (
        <Box mt={2}>
          <Typography variant="body2">{t("documentLibrary.loadingLibraries")}</Typography>
        </Box>
      )}
    </Container>
  );
};
