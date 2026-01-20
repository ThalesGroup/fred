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

import Editor from "@monaco-editor/react";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import CloudQueueIcon from "@mui/icons-material/CloudQueue";
import RefreshIcon from "@mui/icons-material/Refresh";

import { Box, Button, CardContent, Drawer, Fade, IconButton, Typography, useTheme } from "@mui/material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { usePermissions } from "../security/usePermissions";

import Grid2 from "@mui/material/Grid2";
import { TopBar } from "../common/TopBar";
import { AgentCard } from "../components/agentHub/AgentCard";
import { LoadingSpinner } from "../utils/loadingSpinner";

// Editor pieces
import { AgentEditDrawer } from "../components/agentHub/AgentEditDrawer";
import { CrewEditor } from "../components/agentHub/CrewEditor";

// OpenAPI
import {
  Leader,
  useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery,
  useLazyGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useRestoreAgentsAgenticV1AgentsRestorePostMutation,
} from "../slices/agentic/agenticOpenApi";

// UI union facade
import { AnyAgent, isLeader } from "../common/agent";
import { A2aCardDialog } from "../components/agentHub/A2aCardDialog";
import { AgentAssetManagerDrawer } from "../components/agentHub/AgentAssetManagerDrawer";
import { CreateAgentModal } from "../components/agentHub/CreateAgentModal";
import { useConfirmationDialog } from "../components/ConfirmationDialogProvider";
import { useToast } from "../components/ToastProvider";
import { useAgentUpdater } from "../hooks/useAgentUpdater";
import { useLazyGetRuntimeSourceTextQuery } from "../slices/agentic/agenticSourceApi";

export const AgentHub = () => {
  const theme = useTheme();
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const [agents, setAgents] = useState<AnyAgent[]>([]);
  const [showElements, setShowElements] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createModalType, setCreateModalType] = useState<"basic" | "a2a_proxy">("basic");

  // drawers / selection
  const [selected, setSelected] = useState<AnyAgent | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [crewOpen, setCrewOpen] = useState(false);

  const handleOpenCreateAgent = () => {
    setCreateModalType("basic");
    setCreateModalOpen(true);
  };
  const handleOpenRegisterA2AAgent = () => {
    setCreateModalType("a2a_proxy");
    setCreateModalOpen(true);
  };
  const handleCloseCreateAgent = () => setCreateModalOpen(false);

  const [assetManagerOpen, setAssetManagerOpen] = useState(false);
  const [agentForAssetManagement, setAgentForAssetManagement] = useState<AnyAgent | null>(null);
  const [a2aCardView, setA2aCardView] = useState<{ open: boolean; card: any | null; agentName: string | null }>({
    open: false,
    card: null,
    agentName: null,
  });

  const [triggerGetFlows, { isLoading }] = useLazyGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery();
  const [restoreAgents, { isLoading: isRestoring }] = useRestoreAgentsAgenticV1AgentsRestorePostMutation();

  const { updateEnabled } = useAgentUpdater();
  const [triggerGetSource] = useLazyGetRuntimeSourceTextQuery();

  // RBAC utils
  const { can } = usePermissions();
  const canEditAgents = can("agents", "update");
  const canCreateAgents = can("agents", "create");
  const [codeDrawer, setCodeDrawer] = useState<{
    open: boolean;
    title: string;
    content: string | null;
  }>({ open: false, title: "", content: null });

  const handleCloseCodeDrawer = () => {
    setCodeDrawer({ open: false, title: "", content: null });
  };

  const handleInspectCode = async (agent: AnyAgent) => {
    const AGENT_CODE_KEY = `agent.${agent.name}`;

    // 1. Set loading state and open the drawer immediately
    // 👇 CHANGE: Use setCodeDrawer instead of setCodeViewer
    setCodeDrawer({ open: true, title: `Fetching Source: ${agent.name}...`, content: null });

    try {
      // 2. Trigger the lazy query and unwrap the promise for the result
      // The request parameter is 'key' (for /by-object?key=...)
      const code = await triggerGetSource({ key: AGENT_CODE_KEY }).unwrap();

      // 3. Set the successful content state
      // 👇 CHANGE: Use setCodeDrawer instead of setCodeViewer
      setCodeDrawer({
        open: true,
        title: `Source: ${agent.name}`,
        content: code,
      });
    } catch (error: any) {
      console.error("Error fetching agent source:", error);
      // 👇 CHANGE: Use handleCloseCodeDrawer instead of handleCloseCodeViewer
      handleCloseCodeDrawer(); // Close the drawer

      // Extract detailed error message if possible
      const detail = error?.data || error?.message || "Check network connection or agent exposure.";

      // Assuming your showError function is available
      showError({
        summary: "Code Inspection Failed",
        detail: `Could not retrieve source for ${agent.name}. Details: ${detail}`,
      });
    }
  };

  const handleViewA2ACard = (agent: AnyAgent) => {
    const card = (agent as any)?.metadata?.a2a_card;
    if (!card) {
      showError({
        summary: t("agentHub.noA2ACardSummary"),
        detail: t("agentHub.noA2ACardDetail"),
      });
      return;
    }
    setA2aCardView({ open: true, card, agentName: agent.name });
  };

  const fetchAgents = async () => {
    try {
      const flows = (await triggerGetFlows().unwrap()) as unknown as AnyAgent[];
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

  // ---- ACTION handlers wired to card --------------------------------------

  const handleEdit = (agent: AnyAgent) => {
    setSelected(agent);
    setEditOpen(true);
  };

  const handleToggleEnabled = async (agent: AnyAgent) => {
    const isEnabled = agent.enabled !== false;
    await updateEnabled(agent, !isEnabled);
    fetchAgents();
  };

  const handleManageCrew = (leader: Leader & { type: "leader" }) => {
    setSelected(leader);
    setCrewOpen(true);
  };

  const handleManageAssets = (agent: AnyAgent) => {
    setAgentForAssetManagement(agent);
    setAssetManagerOpen(true);
  };

  const handleCloseAssetManager = () => {
    setAssetManagerOpen(false);
    setAgentForAssetManagement(null);
  };
  // ------------------------------------------------------------------------

  const { data: frontendConfig } = useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery();

  return (
    <>
      <TopBar
        title={t("agentHub.title", {
          agentsNicknamePlural: frontendConfig.frontend_settings.properties.agentsNicknamePlural,
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
        {/* Content */}
        <Fade in={showElements} timeout={1100}>
          <Box>
            <CardContent sx={{ p: { xs: 2, md: 3 } }}>
              {isLoading ? (
                <Box display="flex" justifyContent="center" alignItems="center" minHeight="360px">
                  <LoadingSpinner />
                </Box>
              ) : (
                <>
                  {/* Section header */}
                  <Box display="flex" justifyContent="flex-end" alignItems="center" mb={2}>
                    <Box sx={{ display: "flex", gap: 1 }}>
                      <Button
                        variant="outlined"
                        startIcon={<RefreshIcon />}
                        onClick={canEditAgents ? handleRestore : undefined}
                        disabled={!canEditAgents || isRestoring}
                      >
                        {t("agentHub.restoreButton")}
                      </Button>
                      <Button
                        variant="outlined"
                        startIcon={<CloudQueueIcon />}
                        onClick={canCreateAgents ? handleOpenRegisterA2AAgent : undefined}
                        disabled={!canCreateAgents}
                      >
                        {t("agentHub.registerA2A")}
                      </Button>
                      <Button
                        variant="contained"
                        startIcon={<AddIcon />}
                        onClick={canCreateAgents ? handleOpenCreateAgent : undefined}
                        disabled={!canCreateAgents}
                      >
                        {t("agentHub.create")}
                      </Button>
                    </Box>
                  </Box>

                  {/* Grid */}
                  {agents.length > 0 ? (
                    <Grid2 container spacing={2}>
                      {agents.map((agent) => (
                        <Grid2 key={agent.name} size={{ xs: 12, sm: 6, md: 4, lg: 4, xl: 4 }} sx={{ display: "flex" }}>
                          <Fade in timeout={500}>
                            <Box sx={{ width: "100%" }}>
                              <AgentCard
                                agent={agent}
                                onEdit={canEditAgents ? handleEdit : undefined}
                                onToggleEnabled={canEditAgents ? handleToggleEnabled : undefined}
                                onManageCrew={canEditAgents && isLeader(agent) ? handleManageCrew : undefined}
                                onManageAssets={canEditAgents ? handleManageAssets : undefined}
                                onInspectCode={handleInspectCode}
                                onViewA2ACard={handleViewA2ACard}
                              />
                            </Box>
                          </Fade>
                        </Grid2>
                      ))}
                    </Grid2>
                  ) : (
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="center"
                      justifyContent="center"
                      minHeight="280px"
                      sx={{
                        border: `1px dashed ${theme.palette.divider}`,
                        borderRadius: 2,
                        p: 3,
                      }}
                    >
                      <Typography variant="subtitle1" color="text.secondary" align="center">
                        {t("agentHub.noAgents")}
                      </Typography>
                    </Box>
                  )}

                  {/* Create modal (optional) */}
                  {createModalOpen && (
                    <CreateAgentModal
                      open={createModalOpen}
                      onClose={handleCloseCreateAgent}
                      onCreated={() => {
                        handleCloseCreateAgent();
                        fetchAgents();
                      }}
                      initialType={createModalType}
                      disableTypeToggle
                    />
                  )}

                  <A2aCardDialog
                    open={a2aCardView.open}
                    onClose={() => setA2aCardView({ open: false, card: null, agentName: null })}
                    card={a2aCardView.card}
                  />
                </>
              )}
            </CardContent>
          </Box>
        </Fade>
        {/* Drawers / Modals */}
        <AgentEditDrawer
          open={editOpen}
          agent={selected}
          onClose={() => setEditOpen(false)}
          onSaved={fetchAgents}
          onDeleted={fetchAgents}
        />
        <CrewEditor
          open={crewOpen}
          leader={selected && isLeader(selected) ? (selected as Leader & { type: "leader" }) : null}
          allAgents={agents}
          onClose={() => setCrewOpen(false)}
          onSaved={fetchAgents}
        />
        {agentForAssetManagement && (
          <AgentAssetManagerDrawer
            isOpen={assetManagerOpen}
            onClose={handleCloseAssetManager}
            agentId={agentForAssetManagement.name}
          />
        )}

        <Box
          component={Drawer}
          anchor="right"
          open={codeDrawer.open}
          onClose={handleCloseCodeDrawer}
          // Custom Drawer Paper styling for width
          slotProps={{
            paper: {
              // This 'paper' key targets the internal Paper component of the Drawer
              sx: {
                // Set the desired width, which remains the same as your last request
                width: { xs: "100%", sm: 600, md: 900 },
                maxWidth: "100%",
              },
            },
          }}
        >
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              height: "100%", // Ensures content fills the drawer height
            }}
          >
            {/* Drawer Header */}
            <Box
              sx={{
                p: 2,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                borderBottom: `1px solid ${theme.palette.divider}`,
              }}
            >
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                {codeDrawer.title}
              </Typography>
              <IconButton onClick={handleCloseCodeDrawer} size="large">
                <CloseIcon />
              </IconButton>
            </Box>

            {/* Drawer Content - Monaco Editor */}
            <Box sx={{ flexGrow: 1, overflowY: "hidden" }}>
              {codeDrawer.content ? (
                <Editor
                  // Set height to 100% to fill the remaining space in the drawer
                  height="100%"
                  defaultLanguage="python"
                  language="python"
                  defaultValue={codeDrawer.content}
                  theme={theme.palette.mode === "dark" ? "vs-dark" : "vs-light"}
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    wordWrap: "on",
                    scrollBeyondLastLine: false,
                    // Add padding inside the editor for a cleaner look
                    padding: { top: 10, bottom: 10 },
                    fontSize: 12,
                  }}
                />
              ) : (
                // Loading state
                <Box display="flex" justifyContent="center" alignItems="center" height="100%">
                  <Typography align="center" sx={{ p: 4 }}>
                    Loading agent source code...
                  </Typography>
                </Box>
              )}
            </Box>
          </Box>
        </Box>
      </Box>
    </>
  );
};
