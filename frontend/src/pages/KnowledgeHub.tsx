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
import { useNavigate, useSearchParams } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import { AllDocumentsList } from "../components/documents/AllDocumentsList";
import { AllLibrariesList } from "../components/documents/AllLibrariesList";
import { AllPromptsList } from "../components/prompts/AllPromptsList";

type KnowledgeHubView = "prompts" | "operations" | "documents";

const defaultView: KnowledgeHubView = "documents";

export const KnowledgeHub = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const viewParam = searchParams.get("view");

  const isValidView = (v: string | null): v is KnowledgeHubView =>
    v === "prompts" || v === "documents" || v === "operations";

  const selectedView: KnowledgeHubView = isValidView(viewParam) ? viewParam : defaultView;

  // Ensure a default view in URL if missing
  useEffect(() => {
  if (!isValidView(viewParam)) {
    setSearchParams({ view: String(defaultView) }, { replace: true });
  }
}, [viewParam, setSearchParams]);


  return (
    <>
      <TopBar title={t("knowledge.title")} description={t("knowledge.description")}>
        <Box>
          <ButtonGroup variant="outlined" color="primary" size="small">
            <Button
              variant={selectedView === "prompts" ? "contained" : "outlined"}
              onClick={() => navigate("/knowledge?view=prompts")}
            >
              {t("knowledge.viewSelector.prompts")}
            </Button>
            <Button
              variant={selectedView === "documents" ? "contained" : "outlined"}
              onClick={() => navigate("/knowledge?view=documents")}
            >
              {t("knowledge.viewSelector.documents")}
            </Button>
            <Button
              variant={selectedView === "operations" ? "contained" : "outlined"}
              onClick={() => navigate("/knowledge?view=operations")}
            >
              {t("knowledge.viewSelector.operations")}
            </Button>
          </ButtonGroup>
        </Box>
      </TopBar>

      <Box sx={{ mb: 3 }}>
        {selectedView === "documents" && (
          <Container maxWidth="xl">
            <AllLibrariesList />
          </Container>
        )}
        {selectedView === "prompts" && (
          <Container maxWidth="xl">
            <AllPromptsList />
          </Container>
        )}
        {selectedView === "operations" && <AllDocumentsList />}
      </Box>
    </>
  );
};
