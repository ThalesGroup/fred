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
import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { AnyAgent } from "../common/agent";
import ChatBot from "../components/chatbot/ChatBot";

import { useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery } from "../slices/agentic/agenticOpenApi";
import { normalizeAgenticFlows } from "../utils/agenticFlows";

export default function Chat() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();

  const {
    data: rawAgentsFromServer = [],
    isLoading: flowsLoading,
    isError: flowsError,
    error: flowsErrObj,
  } = useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery(undefined, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: false,
    refetchOnReconnect: false,
  });

  const agentsFromServer = useMemo<AnyAgent[]>(() => normalizeAgenticFlows(rawAgentsFromServer), [rawAgentsFromServer]);
  const enabledAgents = (agentsFromServer ?? []).filter(
    (a) => a.enabled === true && !a.metadata?.deep_search_hidden_in_ui,
  );

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
          chatSessionId={sessionId}
          agents={enabledAgents}
          onNewSessionCreated={handleNewSessionCreated}
          runtimeContext={{}}
        />
      </Grid2>
    </Box>
  );
}
