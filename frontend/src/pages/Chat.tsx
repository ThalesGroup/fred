// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// ...

import { Grid2 } from "@mui/material";
import "dayjs/locale/en-gb";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import LoadingWithProgress from "../components/LoadingWithProgress.tsx";
import ChatBot from "../components/chatbot/ChatBot.tsx";
import { Settings } from "../components/chatbot/Settings.tsx";

import {
  AgenticFlow,
  SessionSchema,
  useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
} from "../slices/agentic/agenticOpenApi.ts";

export const Chat = () => {
  const [searchParams] = useSearchParams();
  const cluster = searchParams.get("cluster") || undefined;

  // --- Queries (new OpenAPI hooks) ---
  const {
    data: flowsData,
    isLoading: flowsLoading,
  } = useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery();

  const {
    data: sessionsData,
    isLoading: sessionsLoading,
    refetch: refetchSessions,
  } = useGetSessionsAgenticV1ChatbotSessionsGetQuery();

  const [deleteSession] =
    useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation();

  // --- Local state (UI selection/persistence) ---
  const [agenticFlows, setAgenticFlows] = useState<AgenticFlow[]>([]);
  const [currentAgenticFlow, setCurrentAgenticFlow] = useState<AgenticFlow | null>(null);

  const [chatBotSessions, setChatBotSessions] = useState<SessionSchema[]>([]);
  const [currentChatBotSession, setCurrentChatBotSession] = useState<SessionSchema | null>(null);

  const [isCreatingNewConversation, setIsCreatingNewConversation] = useState(false);

  // --- Effects: hydrate state from queries + sessionStorage ---
  useEffect(() => {
    if (!flowsLoading && flowsData) {
      setAgenticFlows(flowsData);

      const savedFlowStr = sessionStorage.getItem("currentAgenticFlow");
      if (savedFlowStr) {
        try {
          const savedFlow: AgenticFlow = JSON.parse(savedFlowStr);
          const exists = flowsData.find((f) => f.name === savedFlow.name);
          setCurrentAgenticFlow(exists || flowsData[0] || null);
        } catch {
          setCurrentAgenticFlow(flowsData[0] || null);
        }
      } else {
        setCurrentAgenticFlow(flowsData[0] || null);
      }
    }
  }, [flowsLoading, flowsData]);

  useEffect(() => {
    if (!sessionsLoading && sessionsData) {
      setChatBotSessions(sessionsData);

      const savedSessionStr = sessionStorage.getItem("currentChatBotSession");
      if (savedSessionStr) {
        try {
          const saved: SessionSchema = JSON.parse(savedSessionStr);
          const exists = sessionsData.find((s) => s.id === saved.id);
          setCurrentChatBotSession(exists || null);
        } catch {
          setCurrentChatBotSession(null);
        }
      }
    }
  }, [sessionsLoading, sessionsData]);

  // Keep “new conversation” flag sane when a session gets selected
  useEffect(() => {
    if (isCreatingNewConversation && currentChatBotSession !== null) {
      setIsCreatingNewConversation(false);
    }
  }, [isCreatingNewConversation, currentChatBotSession]);

  // --- Handlers ---
  const handleSelectAgenticFlow = (flow: AgenticFlow) => {
    setCurrentAgenticFlow(flow);
    sessionStorage.setItem("currentAgenticFlow", JSON.stringify(flow));
  };

  const handleSelectSession = (session: SessionSchema) => {
    setCurrentChatBotSession(session);
    sessionStorage.setItem("currentChatBotSession", JSON.stringify(session));
    // user navigated into an existing conversation
    setIsCreatingNewConversation(false);
  };

  const handleCreateNewConversation = () => {
    setCurrentChatBotSession(null);
    setIsCreatingNewConversation(true);
    sessionStorage.removeItem("currentChatBotSession");
  };

  const handleDeleteSession = async (session: SessionSchema) => {
    try {
      await deleteSession({ sessionId: session.id }).unwrap();
      // Optimistic local update
      setChatBotSessions((prev) => prev.filter((s) => s.id !== session.id));
      if (currentChatBotSession?.id === session.id) {
        setCurrentChatBotSession(null);
        sessionStorage.removeItem("currentChatBotSession");
      }
      // Optionally refetch to stay in sync with backend
      refetchSessions();
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("Failed to delete session:", e);
    }
  };

  // Upsert/replace session coming back from the chatbot “final” event
  const handleUpdateOrAddSession = (session: SessionSchema) => {
    setChatBotSessions((prev) => {
      const exists = prev.some((s) => s.id === session.id);
      return exists ? prev.map((s) => (s.id === session.id ? session : s)) : [...prev, session];
    });
    if (!currentChatBotSession || currentChatBotSession.id !== session.id) {
      handleSelectSession(session);
    }
  };

  // --- Loading / Error states ---
  const loading = flowsLoading || sessionsLoading;
  if (loading) return <LoadingWithProgress />;
  if (!currentAgenticFlow) {
    // Loaded but no flows found (or error)
    return <LoadingWithProgress />;
  }

  return (
    <Grid2 container display="flex" flexDirection="row">
      <Grid2 size="grow">
        <ChatBot
          currentChatBotSession={currentChatBotSession as SessionSchema | null}
          currentAgenticFlow={currentAgenticFlow as AgenticFlow}
          agenticFlows={agenticFlows}
          onUpdateOrAddSession={handleUpdateOrAddSession}
          isCreatingNewConversation={isCreatingNewConversation}
          runtimeContext={{ cluster }}
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
        />
      </Grid2>
    </Grid2>
  );
};
