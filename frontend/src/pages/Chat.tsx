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

import "dayjs/locale/en-gb";
import { useEffect, useState } from "react";
import { Grid2 } from "@mui/material";

import { PageBodyWrapper } from "../common/PageBodyWrapper.tsx";
import LoadingWithProgress from "../components/LoadingWithProgress.tsx";
import ChatBot from "../components/chatbot/ChatBot.tsx";
import { Settings } from "../components/chatbot/Settings.tsx";
import {
  useDeleteChatbotSessionMutation,
  useGetChatBotAgenticFlowsMutation,
  useGetChatbotSessionsMutation,
} from "../slices/chatApi.tsx";
import { SessionSchema } from "../slices/chatApiStructures.ts";
import { useSearchParams } from "react-router-dom";
import { KnowledgeContext } from "../components/knowledgeContext/KnowledgeContextEditDialog.tsx";

export interface AgenticFlow {
  name: string;
  role: string;
  nickname: string;
  description: string;
  icon?: string | null;
  experts?: string[];
  tags?: string;
}

export interface ChatProfileLight {
  id: string;
  title: string;
  description: string;
}

export const Chat = () => {
  const [searchParams] = useSearchParams();
  const cluster = searchParams.get("cluster");
  console.log("Cluster from params:", cluster);

  const [getAgenticFlows] = useGetChatBotAgenticFlowsMutation();
  const [agenticFlows, setAgenticFlows] = useState<AgenticFlow[]>([]);
  const [currentAgenticFlow, setCurrentAgenticFlow] = useState<AgenticFlow | null>(null);

  const [getChatbotSessions] = useGetChatbotSessionsMutation();
  const [chatBotSessions, setChatBotSessions] = useState<SessionSchema[]>([]);
  const [currentChatBotSession, setCurrentChatBotSession] = useState<SessionSchema | null>(null);
  const [isCreatingNewConversation, setIsCreatingNewConversation] = useState(false);

  const [selectedChatProfile, setSelectedChatProfile] = useState<KnowledgeContext | null>(null);

  const handleSelectAgenticFlow = (flow: AgenticFlow) => {
    setCurrentAgenticFlow(flow);
    sessionStorage.setItem("currentAgenticFlow", JSON.stringify(flow));
  };

  // Select a conversation
  const handleSelectSession = (session: SessionSchema) => {
    setCurrentChatBotSession(session);
    sessionStorage.setItem("currentChatBotSession", JSON.stringify(session));
  };

  // Create a new conversation
  const handleCreateNewConversation = () => {
    setCurrentChatBotSession(null);
    setIsCreatingNewConversation(true);
    sessionStorage.removeItem("currentChatBotSession");
  };

  // Delete the selected conversation
  const [deleteChatbotSession] = useDeleteChatbotSessionMutation();

  const handleDeleteSession = (session: SessionSchema) => {
    deleteChatbotSession({ session_id: session.id });
    setChatBotSessions((prev) => prev.filter((s) => s.id !== session.id));
    if (currentChatBotSession?.id === session.id) {
      setCurrentChatBotSession(null);
      sessionStorage.removeItem("currentChatBotSession");
    }
  };

  // Add a session
  const handleUpdateOrAddSession = (session: SessionSchema) => {
    console.log("[🧠 Session Update] Received session:", session.id);
    console.log("[🧠 Session Update] Current session:", currentChatBotSession?.id);

    setChatBotSessions((prevSessions) => {
      const sessionExists = prevSessions.some((s) => s.id === session.id);
      const updatedSessions = sessionExists
        ? prevSessions.map((s) => (s.id === session.id ? session : s))
        : [...prevSessions, session];
      return updatedSessions;
    });

    if (!currentChatBotSession || currentChatBotSession.id !== session.id) {
      handleSelectSession(session);
    }
  };

  useEffect(() => {
    if (isCreatingNewConversation && currentChatBotSession === null) {
      // reset le flag dès qu'on a bien annulé la session
      setIsCreatingNewConversation(false);
    }
  }, [isCreatingNewConversation, currentChatBotSession]);

  useEffect(() => {
    // Get agentic flows
    getAgenticFlows()
      .unwrap()
      .then((agents) => {
        setAgenticFlows(agents);
        const savedAgenticFlow = sessionStorage.getItem("currentAgenticFlow");
        if (savedAgenticFlow) {
          setCurrentAgenticFlow(JSON.parse(savedAgenticFlow));
        } else {
          setCurrentAgenticFlow(agents[0]);
        }
      })
      .catch((error) => {
        console.error("Error fetching agentic flows:", error);
      });

    // Get sessions
    getChatbotSessions().then((response) => {
      setChatBotSessions(response.data);
      const savedSession = sessionStorage.getItem("currentChatBotSession");
      if (savedSession) {
        console.log("Saved session found in sessionStorage:", savedSession);
        setCurrentChatBotSession(JSON.parse(savedSession));
      } else {
        console.log("No saved session found in sessionStorage.");
      }
    });
  }, []);

  useEffect(() => {
    console.log("Current agentic flow updated:", currentAgenticFlow);
  }, [currentAgenticFlow]);

  useEffect(() => {
    console.log("Current chat bot session updated:", currentChatBotSession);
  }, [currentChatBotSession]);

  useEffect(() => {
    console.log("Chat bot sessions updated:", chatBotSessions);
  }, [chatBotSessions]);

  if (!currentAgenticFlow) {
    return (
      <PageBodyWrapper>
        <LoadingWithProgress />
      </PageBodyWrapper>
    );
  }
  return (
    <PageBodyWrapper>
      <Grid2 container display="flex" flexDirection="row">
        <Grid2 size="grow">
          <ChatBot
            currentChatBotSession={currentChatBotSession}
            currentAgenticFlow={currentAgenticFlow}
            agenticFlows={agenticFlows}
            onUpdateOrAddSession={handleUpdateOrAddSession}
            isCreatingNewConversation={isCreatingNewConversation}
            argument={cluster}
            selectedChatProfile={selectedChatProfile}
          />
        </Grid2>
        <Grid2 size="auto">
          <Settings
            sessions={chatBotSessions}
            currentSession={currentChatBotSession}
            onSelectSession={handleSelectSession}
            onCreateNewConversation={handleCreateNewConversation}
            agenticFlows={agenticFlows}
            currentAgenticFlow={currentAgenticFlow}
            onSelectAgenticFlow={handleSelectAgenticFlow}
            onDeleteSession={handleDeleteSession}
            onSelectChatProfile={(profile) => setSelectedChatProfile(profile)}
          />
        </Grid2>
      </Grid2>
    </PageBodyWrapper>
  );
};
