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


import { Grid2 } from "@mui/material";
import "dayjs/locale/en-gb";
import { useSearchParams } from "react-router-dom";

import LoadingWithProgress from "../components/LoadingWithProgress";
import ChatBot from "../components/chatbot/ChatBot";
import { Settings } from "../components/chatbot/Settings";
import { useSessionController } from "../hooks/useSessionController";

export const Chat = () => {
  const [searchParams] = useSearchParams();
  const cluster = searchParams.get("cluster") || undefined;

  const {
    loading,
    agenticFlows,
    sessions,
    currentSession,
    currentAgenticFlow,
    isCreatingNewConversation,

    selectSession,
    selectAgenticFlowForCurrentSession,
    startNewConversation,
    updateOrAddSession,
    deleteSession,
    bindDraftAgentToSessionId,
  } = useSessionController();

  // ---- DEBUG LOGGING ----
  console.groupCollapsed("🔍 Chat Page State");
  console.log("loading:", loading);
  console.log("agenticFlows:", agenticFlows);
  console.log("sessions:", sessions);
  console.log("currentSession:", currentSession);
  console.log("currentAgenticFlow:", currentAgenticFlow);
  console.log("isCreatingNewConversation:", isCreatingNewConversation);
  console.groupEnd();
  // -----------------------

  if (loading) {
    console.info("⏳ Still loading flows or sessions…");
    return <LoadingWithProgress />;
  }

  const effectiveAgenticFlow = currentAgenticFlow ?? agenticFlows[0]; // safe default
  if (!effectiveAgenticFlow) {
    console.error("❌ No agentic flow available at all!");
    return <div>No agentic flow available</div>;
  }

  console.info("✅ Flows and sessions loaded.");
  return (
    <Grid2 container display="flex" flexDirection="row">
      <Grid2 size="grow">
        <ChatBot
          currentChatBotSession={currentSession}
          currentAgenticFlow={effectiveAgenticFlow}
          agenticFlows={agenticFlows}
          onUpdateOrAddSession={updateOrAddSession}
          isCreatingNewConversation={isCreatingNewConversation}
          runtimeContext={{ cluster }}
          onBindDraftAgentToSessionId={bindDraftAgentToSessionId}  
        />
      </Grid2>

      <Grid2 size="auto">
        <Settings
          sessions={sessions}
          currentSession={currentSession}
          onSelectSession={selectSession}
          onCreateNewConversation={startNewConversation}
          agenticFlows={agenticFlows}
          currentAgenticFlow={effectiveAgenticFlow}
          onSelectAgenticFlow={selectAgenticFlowForCurrentSession}
          onDeleteSession={deleteSession}
          isCreatingNewConversation={isCreatingNewConversation}
        />
      </Grid2>
    </Grid2>
  );
};
