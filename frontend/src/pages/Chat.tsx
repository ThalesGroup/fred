import { useRef, useState } from "react";
import {
  Box, CircularProgress, Paper, Typography, Divider, IconButton, Tooltip, PaperProps,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import AppsIcon from "@mui/icons-material/Apps";
import {
  AgenticFlow,
  SessionSchema,
  useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
} from "../slices/agentic/agenticOpenApi";
import AgentsList from "../components/chatbot/settings/AgentList";
import { getAgentBadge } from "../utils/avatar";
import { ConversationList } from "../components/chatbot/settings/ConversationList";
import { useSessionOrchestrator } from "../hooks/useSessionOrchestrator";
import ChatBot from "../components/chatbot/ChatBot";

const PANEL_W = { xs: 300, sm: 340, md: 360 };

export default function Chat() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  

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
  } = useGetSessionsAgenticV1ChatbotSessionsGetQuery();

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
    bindDraftAgentToSessionId
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
  };  console.log("ChatPOC: Component rendering. Session count:", sessions?.length);
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
        <Typography variant="h6" color="error">Failed to load assistants</Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          {(flowsErrObj as any)?.data?.detail || "Please try again later."}
        </Typography>
      </Box>
    );
  }
  if (sessionsError) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h6" color="error">Failed to load conversations</Typography>
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

  return (
    <Box ref={containerRef} sx={{ height: "100%", position: "relative", overflow: "hidden" }}>
      {!agentsOpen && (
        <Box sx={{ position: "absolute", top: 12, left: 12, zIndex: 10 }}>
          <Tooltip title="Assistants" arrow>
            <IconButton
              onClick={openAgents}
              size="small"
              aria-label="Choose assistant"
              sx={{
                border: (t) => `1px solid ${t.palette.divider}`,
                bgcolor: "background.paper",
                boxShadow: (t) => (t.palette.mode === "light" ? 1 : 3),
              }}
            >
              {currentAgenticFlow ? (
                <Box sx={{ lineHeight: 0, transform: "scale(0.8)" }}>
                  {getAgentBadge(currentAgenticFlow.nickname || currentAgenticFlow.name)}
                </Box>
              ) : (
                <AppsIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
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
              display: "flex", alignItems: "center", justifyContent: "space-between",
              px: 1, py: 1, borderBottom: (t) => `1px solid ${t.palette.divider}`,
            }}
          >
            <Typography variant="subtitle2" sx={{ fontWeight: 600, pl: 1 }}>
              Assistants & Conversations
            </Typography>
            <IconButton size="small" onClick={closeAgents}>
              <CloseIcon fontSize="small" />
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
