// Copyright Thales 2025
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

import { Box, Fade } from "@mui/material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { TopBar } from "../common/TopBar";
import { AgentGridManager } from "../components/agentHub/AgentGridManager";

// OpenAPI
import {
  useLazyListAgentsAgenticV1AgentsGetQuery,
  useRestoreAgentsAgenticV1AgentsRestorePostMutation,
} from "../slices/agentic/agenticOpenApi";

// UI union facade
import { AnyAgent } from "../common/agent";
import { useConfirmationDialog } from "../components/ConfirmationDialogProvider";
import { useToast } from "../components/ToastProvider";
import { useFrontendProperties } from "../hooks/useFrontendProperties";

export const AgentHub = () => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const [agents, setAgents] = useState<AnyAgent[]>([]);
  const [showElements, setShowElements] = useState(false);

  const [triggerGetFlows, { isLoading }] = useLazyListAgentsAgenticV1AgentsGetQuery();
  const [restoreAgents, { isLoading: isRestoring }] = useRestoreAgentsAgenticV1AgentsRestorePostMutation();

  const fetchAgents = async () => {
    try {
      const flows = (await triggerGetFlows({ ownerFilter: "personal" }).unwrap()) as unknown as AnyAgent[];
      setAgents(flows);
    } catch (err) {
      console.error("Error fetching agents:", err);
    }
  };

  useEffect(() => {
    setShowElements(true);
    fetchAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRestore = () => {
    showConfirmationDialog({
      title: t("agentHub.confirmRestoreTitle") || "Restore agents from configuration?",
      message:
        t("agentHub.confirmRestoreMessage") ||
        "This will overwrite any tuned settings you saved in the UI with the YAML configuration. This action cannot be undone.",
      onConfirm: async () => {
        try {
          // Explicitly request overwrite to avoid sending undefined (FastAPI rejects "undefined" for booleans)
          await restoreAgents({ forceOverwrite: true }).unwrap();
          showSuccess({ summary: t("agentHub.toasts.restored") });
          fetchAgents();
        } catch (error: any) {
          const detail = error?.data?.detail || error?.data || error?.message || "Unknown error";
          showError({ summary: t("agentHub.toasts.error"), detail });
        }
      },
    });
  };

  const { agentsNicknamePlural } = useFrontendProperties();

  return (
    <>
      <TopBar
        title={t("agentHub.title", {
          agentsNicknamePlural,
        })}
        description={t("agentHub.description")}
      />

      <Box
        sx={{
          width: "100%",
          maxWidth: 1280,
          mx: "auto",
          px: { xs: 2, md: 3 },
          pt: { xs: 3, md: 4 },
          pb: { xs: 4, md: 6 },
        }}
      >
        <Fade in={showElements} timeout={1100}>
          <Box>
            <AgentGridManager
              agents={agents}
              isLoading={isLoading}
              onRefetchAgents={fetchAgents}
              showRestoreButton={true}
              onRestore={handleRestore}
              isRestoring={isRestoring}
              showA2ACard={true}
              // For now, all users can manager their personal agents
              canEdit={true}
              canCreate={true}
              canDelete={true}
            />
          </Box>
        </Fade>
      </Box>
    </>
  );
};
