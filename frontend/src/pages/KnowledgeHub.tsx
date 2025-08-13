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

import { Box, Button, ButtonGroup, Container } from "@mui/material";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import { DocumentOperations } from "../components/documents/operations/DocumentOperations";
import InvisibleLink from "../components/InvisibleLink";
import DocumentLibraryList from "../components/documents/libraries/DocumentLibraryList";
import ResourceLibraryList from "../components/resources/ResourceLibraryList";

const knowledgeHubViews = ["templates", "prompts", "operations", "documents"] as const;
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
            <InvisibleLink to="/knowledge?view=templates">
              <Button variant={selectedView === "templates" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.templates")}
              </Button>
            </InvisibleLink>
            <InvisibleLink to="/knowledge?view=prompts">
              <Button variant={selectedView === "prompts" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.prompts")}
              </Button>
            </InvisibleLink>
            <InvisibleLink to="/knowledge?view=documents">
              <Button variant={selectedView === "documents" ? "contained" : "outlined"}>
                {t("knowledge.viewSelector.documents")}
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

      <Box sx={{ mb: 3 }}>
        {selectedView === "documents" && (
          <Container maxWidth="xl">
            <DocumentLibraryList />
          </Container>
        )}
        {selectedView === "prompts" && (
          <Container maxWidth="xl">
            <ResourceLibraryList kind="prompt" />
          </Container>
        )}
        {selectedView === "templates" && (
          <Container maxWidth="xl">
            <ResourceLibraryList kind="template" />
          </Container>
        )}
        {selectedView === "operations" && <DocumentOperations />}
      </Box>
    </>
  );
};
