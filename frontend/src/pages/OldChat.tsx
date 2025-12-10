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
import { Box, CircularProgress, Grid2, Typography } from "@mui/material";
import { useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AnyAgent } from "../common/agent";
import ChatBot from "../components/chatbot/ChatBot";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { useSessionOrchestrator } from "../hooks/useSessionOrchestrator";
import {
  useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
} from "../slices/agentic/agenticOpenApi";
import { normalizeAgenticFlows } from "../utils/agenticFlows";

export default function OldChat() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();

  const {
    data: rawAgentsFromServer = [],
    isLoading: flowsLoading,
    isError: flowsError,
    error: flowsErrObj,
  } = useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery();

  const agentsFromServer = useMemo<AnyAgent[]>(() => normalizeAgenticFlows(rawAgentsFromServer), [rawAgentsFromServer]);

  const {
    data: sessionsFromServer = [],
    isLoading: sessionsLoading,
    isError: sessionsError,
    error: sessionsErrObj,
  } = useGetSessionsAgenticV1ChatbotSessionsGetQuery(undefined, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: true,
    refetchOnReconnect: true,
  });
  const enabledAgents = (agentsFromServer ?? []).filter((a) => a.enabled === true);

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
    agents: enabledAgents,
    loading: sessionsLoading || flowsLoading,
  });

  // Sync URL parameter with session selection
  useEffect(() => {
    if (flowsLoading || sessionsLoading) {
      return;
    }

    if (sessionId) {
      // URL has a session ID - ensure it's selected
      const session = sessions.find((s) => s.id === sessionId);
      if (session) {
        selectSession(session);
      } else if (!session && sessions.length > 0) {
        // Invalid session ID - redirect to new chat (only if sessions have loaded)
        navigate("/chat", { replace: true });
      } else {
      }
    } else if (!sessionId) {
      // URL is /chat without session ID - start new conversation
      startNewConversation();
    } else {
    }
  }, [sessionId, sessions, flowsLoading, sessionsLoading, selectSession, startNewConversation, navigate]);

  // todo: move to the new conversation page
  const [selectedChatContextIds, setSelectedChatContextIds] = useLocalStorageState<string[]>(
    "chat.selectedChatContextIds",
    [],
  );

  const handleSelectAgent = (agent: AnyAgent) => {
    selectAgentForCurrentSession(agent);
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
    <Box sx={{ height: "100vh", position: "relative", overflow: "hidden" }}>
      <Grid2>
        <ChatBot
          currentChatBotSession={currentSession}
          currentAgent={currentAgent!}
          agents={enabledAgents}
          onSelectNewAgent={handleSelectAgent}
          onUpdateOrAddSession={updateOrAddSession}
          isCreatingNewConversation={isCreatingNewConversation}
          runtimeContext={{
            selected_chat_context_ids: selectedChatContextIds.length ? selectedChatContextIds : undefined,
          }}
          onBindDraftAgentToSessionId={bindDraftAgentToSessionId}
        />
      </Grid2>
    </Box>
  );
}
