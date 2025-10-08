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
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import { Box, CircularProgress, Divider, Grid2, IconButton, Paper, Typography } from "@mui/material";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnyAgent } from "../common/agent";
import ChatBot from "../components/chatbot/ChatBot";
import AgentsList from "../components/chatbot/settings/AgentList";
import { ChatContextPickerPanel } from "../components/chatbot/settings/ChatContextPickerPanel";
import { ConversationList } from "../components/chatbot/settings/ConversationList";
import { SidePanelToggle } from "../components/SidePanelToogle";
import { useSessionOrchestrator } from "../hooks/useSessionOrchestrator";
import {
  SessionSchema,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
  useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
} from "../slices/agentic/agenticOpenApi";

const PANEL_W = { xs: 300, sm: 340, md: 360 };

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

  const [baseRuntimeContext] = useState<Record<string, any>>({});
  const [selectedChatContextIds, setSelectedChatContextIds] = useState<string[]>([]);
  const [agentsOpen, setAgentsOpen] = useState(false);

  const openAgents = () => setAgentsOpen(true);
  const closeAgents = () => setAgentsOpen(false);

  const handleSelectAgent = (agent: AnyAgent) => selectAgentForCurrentSession(agent);

  const handleCreateNewConversation = () => {
    startNewConversation();
    if (!agentsOpen) setAgentsOpen(true);
  };

  const handleSelectSession = (s: SessionSchema) => selectSession(s);

  const handleDeleteSession = async (s: SessionSchema) => {
    try {
      await deleteSessionMutation({ sessionId: s.id }).unwrap();
    } catch (e) {
      console.error("Failed to delete session", e);
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

  return (
    <Box ref={containerRef} sx={{ height: "100vh", position: "relative", overflow: "hidden" }}>
      {!agentsOpen && (
        <Box sx={{ position: "absolute", top: 12, left: 12, zIndex: 10 }}>
          <SidePanelToggle
            isOpen={agentsOpen}
            label={currentAgent ? currentAgent.name : "Assistants"}
            onToggle={openAgents}
          />
        </Box>
      )}

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: agentsOpen
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
        <Paper
          square
          elevation={agentsOpen ? 6 : 0}
          sx={{
            overflow: "hidden",
            borderRight: (t) => `1px solid ${t.palette.divider}`,
            bgcolor: (t) => t.palette.sidebar?.background ?? t.palette.background.paper,
            display: "flex",
            flexDirection: "column",
            pointerEvents: agentsOpen ? "auto" : "none",
          }}
        >
          <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
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
              <Typography variant="h6" sx={{ flexGrow: 1, pl: 1 }}>
                {t("settings.conversationSetup")}
              </Typography>

              <IconButton size="small" onClick={closeAgents}>
                <ChevronLeftIcon fontSize="small" />
              </IconButton>
            </Box>

            {/* Chat Context Section */}
            <Box sx={{ flex: "0 0 auto" }}>
              <ChatContextPickerPanel
                selectedChatContextIds={selectedChatContextIds}
                onChangeSelectedChatContextIds={setSelectedChatContextIds}
              />
            </Box>

            <Divider />

            {/* Agents Section */}
            <AgentsList
              agents={enabledAgents}
              selected={currentAgent}
              onSelect={handleSelectAgent}
              sx={{ flex: 1, minHeight: 0, overflow: "hidden", maxHeight: "fit-content" }}
            />

            <Divider />

            {/* Conversations Section */}
            <ConversationList
              sessions={sessions}
              currentSession={currentSession}
              onSelectSession={handleSelectSession}
              onCreateNewConversation={handleCreateNewConversation}
              onDeleteSession={handleDeleteSession}
              isCreatingNewConversation={isCreatingNewConversation}
              sx={{ flex: 1, minHeight: 0, overflow: "hidden" }}
            />
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
              ...baseRuntimeContext,
              selected_chat_context_ids: selectedChatContextIds.length ? selectedChatContextIds : undefined,
            }}
            onBindDraftAgentToSessionId={bindDraftAgentToSessionId}
          />
        </Grid2>
      </Box>
    </Box>
  );
}
