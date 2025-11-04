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
import AppsIcon from "@mui/icons-material/Apps";
import ChatIcon from "@mui/icons-material/Chat";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";

import { Box, CircularProgress, Grid2, IconButton, Paper, Typography } from "@mui/material";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnyAgent } from "../common/agent";
import ChatBot from "../components/chatbot/ChatBot";
import AgentsList from "../components/chatbot/settings/AgentList";
import { ChatContextPickerPanel } from "../components/chatbot/settings/ChatContextPickerPanel";
import { ConversationList } from "../components/chatbot/settings/ConversationList";
import { useSessionOrchestrator } from "../hooks/useSessionOrchestrator";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import {
  SessionSchema,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
  useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
} from "../slices/agentic/agenticOpenApi";

const PANEL_W = { xs: 300, sm: 340, md: 360 };

type PanelContentType = "agents" | "conversations" | null;

export default function Chat() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { t } = useTranslation();

  const {
    data: agentsFromServer = [],
    isLoading: flowsLoading,
    isError: flowsError,
    error: flowsErrObj,
  } = useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery();

  const {
    data: sessionsFromServer = [],
    isLoading: sessionsLoading,
    isError: sessionsError,
    error: sessionsErrObj,
    refetch: refetchSessions,
  } = useGetSessionsAgenticV1ChatbotSessionsGetQuery(undefined, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: true,
    refetchOnReconnect: true,
  });

  const [deleteSessionMutation] = useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation();

  const {
    sessions,
    currentSession,
    currentAgent,
    isCreatingNewConversation,
    selectSession,
    selectAgentForCurrentSession,
    startNewConversation,
    updateOrAddSession,
    bindDraftAgentToSessionId,
  } = useSessionOrchestrator({
    sessionsFromServer,
    agentsFromServer,
    loading: sessionsLoading || flowsLoading,
  });

  const [selectedChatContextIds, setSelectedChatContextIds] = useLocalStorageState<string[]>(
    "chat.selectedChatContextIds",
    [],
  );

  const [panelContentType, setPanelContentType] = useState<PanelContentType>(null);
  const isPanelOpen = panelContentType !== null;

  const openPanel = (type: PanelContentType) => {
    setPanelContentType(panelContentType === type ? null : type);
  };
  const closePanel = () => setPanelContentType(null);

  const openAgentsPanel = () => openPanel("agents");
  const openConversationsPanel = () => openPanel("conversations");

  const handleSelectAgent = (agent: AnyAgent) => {
    selectAgentForCurrentSession(agent);
  };

  const handleCreateNewConversation = () => {
    startNewConversation();
    if (panelContentType !== "agents") setPanelContentType("agents");
  };

  const handleSelectSession = (s: SessionSchema) => {
    selectSession(s);
    if (panelContentType !== "conversations") {
      closePanel();
    }
  };

  const handleDeleteSession = async (s: SessionSchema) => {
    try {
      await deleteSessionMutation({ sessionId: s.id }).unwrap();
    } catch (e) {
      console.error("Failed to delete session", e);
    } finally {
      setTimeout(() => refetchSessions(), 1000);
    }
  };

  const handleDeleteAllSessions = async () => {
    if (!sessions.length) return;
    const deletePromises = sessions.map((session) =>
      deleteSessionMutation({ sessionId: session.id })
        .unwrap()
        .catch((e) => {
          console.error(`Failed to delete session ${session.id}`, e);
        }),
    );
    try {
      await Promise.all(deletePromises);
    } finally {
      setTimeout(() => refetchSessions(), 1000);
    }
  };

  if (flowsLoading || sessionsLoading) {
    return (
      <Box sx={{ p: 3, display: "grid", placeItems: "center", height: "100vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (flowsError) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h6" color="error">
          Failed to load assistants
        </Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          {(flowsErrObj as any)?.data?.detail || "Please try again later."}
        </Typography>
      </Box>
    );
  }

  if (sessionsError) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h6" color="error">
          Failed to load conversations
        </Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          {(sessionsErrObj as any)?.data?.detail || "Please try again later."}
        </Typography>
      </Box>
    );
  }

  const enabledAgents = (agentsFromServer ?? []).filter((a) => a.enabled === true);

  if (enabledAgents.length === 0) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h6">No assistants available</Typography>
        <Typography variant="body2" sx={{ mt: 1, opacity: 0.7 }}>
          Check your backend configuration.
        </Typography>
      </Box>
    );
  }

  // Helper function to render the correct panel content
  const renderPanelContent = () => {
    switch (panelContentType) {
      case "agents":
        return (
          <AgentsList
            agents={enabledAgents}
            selected={currentAgent}
            onSelect={handleSelectAgent}
            sx={{ flex: 1, minHeight: 0, overflow: "hidden" }}
          />
        );
      case "conversations":
        return (
          <Box sx={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, gap: 1 }}>
            <ChatContextPickerPanel
              selectedChatContextIds={selectedChatContextIds}
              onChangeSelectedChatContextIds={setSelectedChatContextIds}
              sx={{
                flex: "0 0 auto",
                maxHeight: "40%",
                overflowY: "auto",
                borderBottom: (t) => `1px solid ${t.palette.divider}`,
                pb: 1,
              }}
            />
            <Box sx={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
              <ConversationList
                sessions={sessions}
                currentSession={currentSession}
                onSelectSession={handleSelectSession}
                onCreateNewConversation={handleCreateNewConversation}
                onDeleteAllSessions={handleDeleteAllSessions}
                onDeleteSession={handleDeleteSession}
                isCreatingNewConversation={isCreatingNewConversation}
                sx={{ flex: 1, minHeight: 0, overflow: "hidden" }}
              />
            </Box>
          </Box>
        );
      default:
        return null;
    }
  };

  // --- START MODIFIED SECTION ---
  const buttonContainerSx = {
    position: "absolute",
    top: 12,
    zIndex: 10,
    display: "flex",
    alignItems: "center",
    gap: 1,
    transition: (t) => t.transitions.create("left"), // Add transition for smooth movement

    // Conditional left position to move the buttons when the panel is open
    left: isPanelOpen
      ? {
          xs: `calc(${PANEL_W.xs}px + 12px)`,
          sm: `calc(${PANEL_W.sm}px + 12px)`,
          md: `calc(${PANEL_W.md}px + 12px)`,
        }
      : 12, // Original position when closed
  };
  // --- END MODIFIED SECTION ---

  return (
    <Box ref={containerRef} sx={{ height: "100vh", position: "relative", overflow: "hidden" }}>
      {/* Panel toggle buttons */}
      <Box sx={buttonContainerSx}>
        <IconButton
          color={panelContentType === "agents" ? "primary" : "default"}
          onClick={openAgentsPanel}
          title={t("settings.assistants")}
        >
          <AppsIcon />
        </IconButton>
        <IconButton
          color={panelContentType === "conversations" ? "primary" : "default"}
          onClick={openConversationsPanel}
          title={t("settings.conversations")}
        >
          <ChatIcon />
        </IconButton>
      </Box>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: isPanelOpen
            ? { xs: `${PANEL_W.xs}px 1fr`, sm: `${PANEL_W.sm}px 1fr`, md: `${PANEL_W.md}px 1fr` }
            : "0px 1fr",
          transition: (t) =>
            t.transitions.create("grid-template-columns", {
              duration: t.transitions.duration.standard,
              easing: t.transitions.easing.sharp,
            }),
          height: "100%",
        }}
      >
        {/* Side Panel */}
        <Paper
          square
          elevation={isPanelOpen ? 6 : 0}
          sx={{
            overflow: "hidden",
            borderRight: (t) => `1px solid ${t.palette.divider}`,
            bgcolor: (t) => t.palette.sidebar?.background ?? t.palette.background.paper,
            display: "flex",
            flexDirection: "column",
            pointerEvents: isPanelOpen ? "auto" : "none",
          }}
        >
          {/* Panel Header (Static top part) */}
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              px: 1,
              py: 1,
              borderBottom: (t) => `1px solid ${t.palette.divider}`,
              flex: "0 0 auto",
            }}
          >
            {/* Back Button */}
            <IconButton size="small" onClick={closePanel} sx={{ visibility: isPanelOpen ? "visible" : "hidden" }}>
              <ChevronLeftIcon fontSize="small" />
            </IconButton>

            {/* Title */}
          </Box>

          {/* Content Body (Takes the rest of the space) */}
          <Box
            sx={{
              flex: 1,
              minHeight: 0,
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
            }}
          >
            {renderPanelContent()}
          </Box>
        </Paper>

        {/* ChatBot panel */}
        <Grid2>
          <ChatBot
            currentChatBotSession={currentSession}
            currentAgent={currentAgent!}
            agents={enabledAgents}
            onUpdateOrAddSession={updateOrAddSession}
            isCreatingNewConversation={isCreatingNewConversation}
            runtimeContext={{
              selected_chat_context_ids: selectedChatContextIds.length ? selectedChatContextIds : undefined,
            }}
            onBindDraftAgentToSessionId={bindDraftAgentToSessionId}
          />
        </Grid2>
      </Box>
    </Box>
  );
}
