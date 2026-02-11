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
import Grid2 from "@mui/material/Grid2";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AnyAgent, isLeader } from "../../common/agent";
import { useAgentUpdater } from "../../hooks/useAgentUpdater";
import { Leader } from "../../slices/agentic/agenticOpenApi";
import { useLazyGetRuntimeSourceTextQuery } from "../../slices/agentic/agenticSourceApi";
import { LoadingSpinner } from "../../utils/loadingSpinner";
import { useToast } from "../ToastProvider";

import { useFrontendProperties } from "../../hooks/useFrontendProperties";
import { A2aCardDialog } from "./A2aCardDialog";
import { AgentCard } from "./AgentCard";
import { AgentConfigWorkspaceManagerDrawer } from "./AgentConfigWorkspaceManagerDrawer";
import { AgentEditDrawer } from "./AgentEditDrawer";
import { CreateAgentModal } from "./CreateAgentModal";
import { CrewEditor } from "./CrewEditor";

interface AgentGridManagerProps {
  // Data
  agents: AnyAgent[];
  isLoading?: boolean;

  // Ownership
  teamId?: string;

  // Permissions
  canEdit?: boolean;
  canCreate?: boolean;
  canDelete?: boolean;

  // Callbacks
  onRefetchAgents?: () => void | Promise<void>;

  // Toolbar customization
  showRestoreButton?: boolean;
  onRestore?: () => void;
  isRestoring?: boolean;

  // Feature flags
  showA2ACard?: boolean;

  // Customization
  emptyStateMessage?: string;
}

export const AgentGridManager = ({
  agents,
  isLoading = false,
  teamId,
  canEdit = false,
  canCreate = false,
  canDelete = false,
  onRefetchAgents,
  showRestoreButton = false,
  onRestore,
  isRestoring = false,
  showA2ACard = true,
  emptyStateMessage,
}: AgentGridManagerProps) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const { showError } = useToast();

  // State for drawers/modals
  const [selected, setSelected] = useState<AnyAgent | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [crewOpen, setCrewOpen] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createModalType, setCreateModalType] = useState<"basic" | "a2a_proxy">("basic");
  const [assetManagerOpen, setAssetManagerOpen] = useState(false);
  const [agentForAssetManagement, setAgentForAssetManagement] = useState<AnyAgent | null>(null);
  const [a2aCardView, setA2aCardView] = useState<{ open: boolean; card: any | null; agentName: string | null }>({
    open: false,
    card: null,
    agentName: null,
  });
  const [codeDrawer, setCodeDrawer] = useState<{
    open: boolean;
    title: string;
    content: string | null;
  }>({ open: false, title: "", content: null });

  const { updateEnabled } = useAgentUpdater();
  const [triggerGetSource] = useLazyGetRuntimeSourceTextQuery();

  // Handlers for create modal
  const handleOpenCreateAgent = () => {
    setCreateModalType("basic");
    setCreateModalOpen(true);
  };

  const handleOpenRegisterA2AAgent = () => {
    setCreateModalType("a2a_proxy");
    setCreateModalOpen(true);
  };

  const handleCloseCreateAgent = () => setCreateModalOpen(false);

  // Code inspector handler
  const handleCloseCodeDrawer = () => {
    setCodeDrawer({ open: false, title: "", content: null });
  };

  const handleInspectCode = async (agent: AnyAgent) => {
    const AGENT_CODE_KEY = `agent.${agent.id}`;

    setCodeDrawer({ open: true, title: `Fetching Source: ${agent.id}...`, content: null });

    try {
      const code = await triggerGetSource({ key: AGENT_CODE_KEY }).unwrap();

      setCodeDrawer({
        open: true,
        title: `Source: ${agent.id}`,
        content: code,
      });
    } catch (error: any) {
      console.error("Error fetching agent source:", error);
      handleCloseCodeDrawer();

      const detail = error?.data || error?.message || "Check network connection or agent exposure.";

      showError({
        summary: "Code Inspection Failed",
        detail: `Could not retrieve source for ${agent.id}. Details: ${detail}`,
      });
    }
  };

  // A2A card handler
  const handleViewA2ACard = (agent: AnyAgent) => {
    const card = (agent as any)?.metadata?.a2a_card;
    if (!card) {
      showError({
        summary: t("agentHub.noA2ACardSummary"),
        detail: t("agentHub.noA2ACardDetail"),
      });
      return;
    }
    setA2aCardView({ open: true, card, agentName: agent.id });
  };

  // Action handlers wired to card
  const handleEdit = (agent: AnyAgent) => {
    setSelected(agent);
    setEditOpen(true);
  };

  const handleToggleEnabled = async (agent: AnyAgent) => {
    const isEnabled = agent.enabled !== false;
    await updateEnabled(agent, !isEnabled);
    if (onRefetchAgents) {
      await onRefetchAgents();
    }
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

  const handleRefetch = async () => {
    if (onRefetchAgents) {
      await onRefetchAgents();
    }
  };

  const { showAgentRegisterA2A, showAgentRestoreFromConfiguration } = useFrontendProperties();

  return (
    <>
      <CardContent sx={{ p: { xs: 2, md: 3 } }}>
        {isLoading ? (
          <Box display="flex" justifyContent="center" alignItems="center" minHeight="360px">
            <LoadingSpinner />
          </Box>
        ) : (
          <>
            {/* Toolbar */}
            <Box display="flex" justifyContent="flex-end" alignItems="center" mb={2}>
              <Box sx={{ display: "flex", gap: 1 }}>
                {showAgentRestoreFromConfiguration && showRestoreButton && onRestore && (
                  <Button
                    variant="outlined"
                    startIcon={<RefreshIcon />}
                    onClick={canEdit ? onRestore : undefined}
                    disabled={!canEdit || isRestoring}
                  >
                    {t("agentHub.restoreButton")}
                  </Button>
                )}
                {showAgentRegisterA2A && (
                  <Button
                    variant="outlined"
                    startIcon={<CloudQueueIcon />}
                    onClick={canCreate ? handleOpenRegisterA2AAgent : undefined}
                    disabled={!canCreate}
                  >
                    {t("agentHub.registerA2A")}
                  </Button>
                )}
                <Button
                  variant="contained"
                  startIcon={<AddIcon />}
                  onClick={canCreate ? handleOpenCreateAgent : undefined}
                  disabled={!canCreate}
                >
                  {t("agentHub.create")}
                </Button>
              </Box>
            </Box>

            {/* Grid */}
            {agents.length > 0 ? (
              <Grid2 container spacing={2}>
                {agents.map((agent) => (
                  <Grid2 key={agent.id} size={{ xs: 12, sm: 6, md: 4, lg: 4, xl: 4 }} sx={{ display: "flex" }}>
                    <Fade in timeout={500}>
                      <Box sx={{ width: "100%" }}>
                        <AgentCard
                          agent={agent}
                          onEdit={canEdit ? handleEdit : undefined}
                          onToggleEnabled={canEdit ? handleToggleEnabled : undefined}
                          onManageCrew={canEdit && isLeader(agent) ? handleManageCrew : undefined}
                          onManageAssets={canEdit ? handleManageAssets : undefined}
                          onInspectCode={handleInspectCode}
                          onViewA2ACard={showA2ACard ? handleViewA2ACard : undefined}
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
                  {emptyStateMessage || t("agentHub.noAgents")}
                </Typography>
              </Box>
            )}

            {/* Create modal */}
            {createModalOpen && (
              <CreateAgentModal
                open={createModalOpen}
                onClose={handleCloseCreateAgent}
                onCreated={() => {
                  handleCloseCreateAgent();
                  handleRefetch();
                }}
                initialType={createModalType}
                disableTypeToggle
                teamId={teamId}
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

      {/* Drawers / Modals */}
      <AgentEditDrawer
        canDelete={canDelete}
        open={editOpen}
        agent={selected}
        onClose={() => setEditOpen(false)}
        onSaved={handleRefetch}
        onDeleted={handleRefetch}
      />
      <CrewEditor
        open={crewOpen}
        leader={selected && isLeader(selected) ? (selected as Leader & { type: "leader" }) : null}
        allAgents={agents}
        onClose={() => setCrewOpen(false)}
        onSaved={handleRefetch}
      />
      {agentForAssetManagement && (
        <AgentConfigWorkspaceManagerDrawer
          isOpen={assetManagerOpen}
          onClose={handleCloseAssetManager}
          agentId={agentForAssetManagement.id}
        />
      )}

      {/* Code Inspector Drawer */}
      <Box
        component={Drawer}
        anchor="right"
        open={codeDrawer.open}
        onClose={handleCloseCodeDrawer}
        slotProps={{
          paper: {
            sx: {
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
            height: "100%",
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
                  padding: { top: 10, bottom: 10 },
                  fontSize: 12,
                }}
              />
            ) : (
              <Box display="flex" justifyContent="center" alignItems="center" height="100%">
                <Typography align="center" sx={{ p: 4 }}>
                  Loading agent source code...
                </Typography>
              </Box>
            )}
          </Box>
        </Box>
      </Box>
    </>
  );
};
