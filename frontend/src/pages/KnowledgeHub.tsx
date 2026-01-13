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
import { DocumentOperations } from "../components/documents/operations/DocumentOperations";
import InvisibleLink from "../components/InvisibleLink";
import ResourceLibraryList from "../components/resources/ResourceLibraryList";
import { useListAllTagsKnowledgeFlowV1TagsGetQuery } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

const knowledgeHubViews = ["operations", "documents", "chatContexts", "userAssets"] as const;
type KnowledgeHubView = (typeof knowledgeHubViews)[number];

function isKnowledgeHubView(value: string): value is KnowledgeHubView {
  return (knowledgeHubViews as readonly string[]).includes(value);
}

const defaultView: KnowledgeHubView = "documents";

export const KnowledgeHub = () => {
  const { t } = useTranslation();

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
        <Box>
          <ButtonGroup variant="outlined" color="primary" size="small">
            <InvisibleLink to="/knowledge?view=chatContexts">
              <Button variant={selectedView === "chatContexts" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.chatContexts")}
              </Button>
            </InvisibleLink>
            {/* <InvisibleLink to="/knowledge?view=templates">
              <Button variant={selectedView === "templates" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.templates")}
              </Button>
            </InvisibleLink>
            <InvisibleLink to="/knowledge?view=prompts">
              <Button variant={selectedView === "prompts" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.prompts")}
              </Button>
            </InvisibleLink> */}
            <InvisibleLink to="/knowledge?view=documents">
              <Button variant={selectedView === "documents" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.documents")}
              </Button>
            </InvisibleLink>
            <InvisibleLink to="/knowledge?view=userAssets">
              <Button variant={selectedView === "userAssets" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.userAssets", "My Files (agents & me)")}
              </Button>
            </InvisibleLink>
            <InvisibleLink to="/knowledge?view=operations">
              <Button variant={selectedView === "operations" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.operations")}
              </Button>
            </InvisibleLink>
          </ButtonGroup>
        </Box>
      </TopBar>

      <Box sx={{ mb: 3, mt: 3 }}>
        {selectedView === "chatContexts" && (
          <Container maxWidth="xl">
            <ResourceLibraryList kind="chat-context" />
          </Container>
        )}
        {selectedView === "documents" && (
          <Container maxWidth="xl">
            <DocumentLibraryList />
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
        {selectedView === "operations" && <DocumentOperations />}
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
    refetch,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: "document", limit: 10000, offset: 0 },
    { refetchOnMountOrArgChange: true },
  );

  const userAssetsTagId = tags?.find((t) => t.name === "User Assets" || t.path === "user-assets")?.id;

  return (
    <Container maxWidth="xl">
      <UserAssetsList tagId={userAssetsTagId} />
      {isError && (
        <Box mt={2}>
          <Typography color="error">{t("documentLibrary.failedToLoad")}</Typography>
          <Button onClick={() => refetch()} size="small" variant="outlined">
            {t("dialogs.retry")}
          </Button>
        </Box>
      )}
      {isLoading && (
        <Box mt={2}>
          <Typography variant="body2">{t("documentLibrary.loadingLibraries")}</Typography>
        </Box>
      )}
    </Container>
  );
};
