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

type KnowledgeHubView = "prompts" | "libraries" | "documents";

const defaultView: KnowledgeHubView = "libraries";

export const KnowledgeHub = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const viewParam = searchParams.get("view");

  const isValidView = (v: string | null): v is KnowledgeHubView =>
    v === "prompts" || v === "libraries" || v === "documents";

  const selectedView: KnowledgeHubView = isValidView(viewParam) ? viewParam : defaultView;

  // Ensure a default view in URL if missing
  useEffect(() => {
  if (!isValidView(viewParam)) {
    setSearchParams({ view: String(defaultView) }, { replace: true });
  }
}, [viewParam, setSearchParams]);


  return (
    <>
      <TopBar title={t("documentLibrary.title")} description={t("documentLibrary.description")}>
        <Box>
          <ButtonGroup variant="outlined" color="primary" size="small">
            <Button
              variant={selectedView === "prompts" ? "contained" : "outlined"}
              onClick={() => navigate("/knowledge?view=prompts")}
            >
              {t("documentLibrary.promptView")}
            </Button>
            <Button
              variant={selectedView === "libraries" ? "contained" : "outlined"}
              onClick={() => navigate("/knowledge?view=libraries")}
            >
              {t("documentLibrary.librariesView")}
            </Button>
            <Button
              variant={selectedView === "documents" ? "contained" : "outlined"}
              onClick={() => navigate("/knowledge?view=documents")}
            >
              {t("documentLibrary.documentsView")}
            </Button>
          </ButtonGroup>
        </Box>
      </TopBar>

      <Box sx={{ mb: 3 }}>
        {selectedView === "libraries" && (
          <Container maxWidth="xl">
            <AllLibrariesList />
          </Container>
        )}
        {selectedView === "prompts" && (
          <Container maxWidth="xl">
            <AllPromptsList />
          </Container>
        )}
        {selectedView === "documents" && <AllDocumentsList />}
      </Box>
    </>
  );
};
