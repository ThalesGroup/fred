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

import { useRef, useState } from "react";
import { Box, CircularProgress, Paper, Typography, Divider, IconButton, PaperProps } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import {
  AgenticFlow,
  SessionSchema,
  useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
} from "../slices/agentic/agenticOpenApi";
import AgentsList from "../components/chatbot/settings/AgentList";
import { ConversationList } from "../components/chatbot/settings/ConversationList";
import { useSessionOrchestrator } from "../hooks/useSessionOrchestrator";
import ChatBot from "../components/chatbot/ChatBot";
import { SidePanelToggle } from "../components/SidePanelToogle";
import { useTranslation } from "react-i18next";

const PANEL_W = { xs: 300, sm: 340, md: 360 };

export default function Chat() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { t } = useTranslation();

  const {
    data: flows = [],
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
  refetchOnMountOrArgChange: true,  // always refetch on component mount
  refetchOnFocus: true,             // when tab regains focus
  refetchOnReconnect: true,         // when network reconnects
});
  const [deleteSessionMutation] = useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation();

  const {
    sessions,
    currentSession,
    currentAgenticFlow,
    isCreatingNewConversation,
    selectSession,
    selectAgenticFlowForCurrentSession,
    startNewConversation,
    updateOrAddSession,
    bindDraftAgentToSessionId,
  } = useSessionOrchestrator({
    sessionsFromServer,
    flowsFromServer: flows,
    loading: sessionsLoading || flowsLoading,
  });

  const [agentsOpen, setAgentsOpen] = useState(false);
  const openAgents = () => setAgentsOpen(true);
  const closeAgents = () => setAgentsOpen(false);

  const handleSelectAgent = (flow: AgenticFlow) => {
    selectAgenticFlowForCurrentSession(flow);
  };

  const handleCreateNewConversation = () => {
    startNewConversation();
    if (!agentsOpen) setAgentsOpen(true);
  };

  const handleSelectSession = (s: SessionSchema) => {
    selectSession(s);
  };

  const handleDeleteSession = async (s: SessionSchema) => {
    try {
      console.log("ChatPOC: Starting delete for session:", s.id);
      await deleteSessionMutation({ sessionId: s.id }).unwrap();
      console.log("ChatPOC: Backend delete successful. Waiting 1 second before refetching.");
    } catch (e) {
      console.error("Failed to delete session", e);
    } finally {
      // Add a small delay to give OpenSearch time to update its index
      setTimeout(() => {
        console.log("ChatPOC: Delay finished. Refetching sessions from server.");
        refetchSessions();
      }, 1000);
    }
  };
  console.log("ChatPOC: Component rendering. Session count:", sessions?.length);
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
  if (flows.length === 0) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h6">No assistants available</Typography>
        <Typography variant="body2" sx={{ mt: 1, opacity: 0.7 }}>
          Check your backend configuration.
        </Typography>
      </Box>
    );
  }

  const PanelShell = (props: PaperProps) => (
    <Paper
      square
      elevation={agentsOpen ? 6 : 0}
      {...props}
      sx={{
        overflow: "hidden",
        borderRight: (t) => `1px solid ${t.palette.divider}`,
        bgcolor: (t) => t.palette.sidebar?.background ?? t.palette.background.paper,
        display: "flex",
        flexDirection: "column",
        pointerEvents: agentsOpen ? "auto" : "none",
        ...props.sx,
      }}
    />
  );

  // ... (rest of the component)

  return (
    <Box ref={containerRef} sx={{ height: "100%", position: "relative", overflow: "hidden" }}>
      {/* This is the toggle button for when the panel is closed. 
        It remains in its original position, which is good. 
      */}
      {!agentsOpen && (
        <Box sx={{ position: "absolute", top: 12, left: 12, zIndex: 10 }}>
          <SidePanelToggle
            isOpen={agentsOpen}
            label={currentAgenticFlow ? currentAgenticFlow.nickname || currentAgenticFlow.name : "Assistants"}
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
        <PanelShell>
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              px: 1,
              py: 1,
              borderBottom: (t) => `1px solid ${t.palette.divider}`,
            }}
          >
            <Typography variant="h6" sx={{ flexGrow: 1, pl: 1 }}>
              {t("panel.conversationSetup", "Conversation setup")}
            </Typography>
            <IconButton size="small" onClick={closeAgents}>
              <ChevronLeftIcon fontSize="small" />
            </IconButton>
          </Box>
          <Box sx={{ flex: 1, overflow: "auto" }}>
            <AgentsList agenticFlows={flows} selected={currentAgenticFlow} onSelect={handleSelectAgent} />
            <Divider />
            <ConversationList
              sessions={sessions}
              currentSession={currentSession}
              onSelectSession={handleSelectSession}
              onCreateNewConversation={handleCreateNewConversation}
              onDeleteSession={handleDeleteSession}
              isCreatingNewConversation={isCreatingNewConversation}
            />
          </Box>
        </PanelShell>

        {/* This is the new ChatBot component! */}
        <ChatBot
          currentChatBotSession={currentSession}
          currentAgenticFlow={currentAgenticFlow!}
          agenticFlows={flows}
          onUpdateOrAddSession={updateOrAddSession}
          isCreatingNewConversation={isCreatingNewConversation}
          onBindDraftAgentToSessionId={bindDraftAgentToSessionId}
        />
      </Box>
    </Box>
  );
}
