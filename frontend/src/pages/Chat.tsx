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
import { Box, CircularProgress, Grid, Typography } from "@mui/material";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { AnyAgent } from "../common/agent";
import ChatBot from "../components/chatbot/ChatBot";

import { useListAgentsAgenticV1AgentsGetQuery } from "../slices/agentic/agenticOpenApi";
import { normalizeAgenticFlows } from "../utils/agenticFlows";

const isInternalConversationAgent = (agent: AnyAgent) =>
  agent.metadata?.internal_agent === true || agent.metadata?.deep_search_hidden_in_ui === true;

export default function Chat() {
  const { sessionId, "agent-id": agentId } = useParams<{ sessionId?: string; "agent-id"?: string }>();
  const navigate = useNavigate();
  const { i18n } = useTranslation();

  const {
    data: rawAgentsFromServer = [],
    isLoading: flowsLoading,
    isError: flowsError,
    error: flowsErrObj,
  } = useListAgentsAgenticV1AgentsGetQuery(
    {},
    {
      refetchOnMountOrArgChange: true,
      refetchOnFocus: false,
      refetchOnReconnect: false,
    },
  );

  const agentsFromServer = useMemo<AnyAgent[]>(() => normalizeAgenticFlows(rawAgentsFromServer), [rawAgentsFromServer]);
  const enabledAgents = useMemo(
    () => (agentsFromServer ?? []).filter((agent) => agent.enabled === true),
    [agentsFromServer],
  );
  const visibleAgents = useMemo(
    () => enabledAgents.filter((agent) => !isInternalConversationAgent(agent)),
    [enabledAgents],
  );
  const internalAgents = useMemo(
    () => enabledAgents.filter((agent) => isInternalConversationAgent(agent)),
    [enabledAgents],
  );

  // Base runtime context propagated to every message (language, etc.)
  const baseRuntimeContext = useMemo(() => ({ language: i18n.language || undefined }), [i18n.language]);

  // Find the initial agent based on URL parameter (if present)
  const initialAgent = useMemo<AnyAgent | undefined>(() => {
    if (!agentId || visibleAgents.length === 0) return undefined;

    // Decode the URL-encoded agent name
    const decodedAgentId = decodeURIComponent(agentId);

    const match = visibleAgents.find((a) => a.id === decodedAgentId);
    if (!match) {
      console.warn(`[CHAT] Agent "${decodedAgentId}" not found in visible agents. Defaulting to first agent.`);
    }
    return match;
  }, [agentId, visibleAgents]);

  // Handle navigation when a new session is created
  const handleNewSessionCreated = (newSessionId: string) => {
    console.log(`New session created -> redirecting to session page /chat/${newSessionId}`);
    navigate(`/chat/${newSessionId}`);
  };

  if (flowsLoading) {
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

  if (visibleAgents.length === 0) {
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
      <Grid>
        <ChatBot
          chatSessionId={sessionId}
          agents={visibleAgents}
          internalAgents={internalAgents}
          initialAgent={initialAgent}
          onNewSessionCreated={handleNewSessionCreated}
          runtimeContext={baseRuntimeContext}
        />
      </Grid>
    </Box>
  );
}
