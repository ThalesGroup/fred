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
import ChatIcon from "@mui/icons-material/Chat";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";

import { Badge, Box, CircularProgress, Grid2, IconButton, Paper, Typography } from "@mui/material";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnyAgent } from "../common/agent";
import ChatBot from "../components/chatbot/ChatBot";
import { ChatContextPickerPanel } from "../components/chatbot/settings/ChatContextPickerPanel";
import { ConversationList } from "../components/chatbot/settings/ConversationList";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { useSessionOrchestrator } from "../hooks/useSessionOrchestrator";
import {
  SessionSchema,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
  useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
} from "../slices/agentic/agenticOpenApi";
import { normalizeAgenticFlows } from "../utils/agenticFlows";

const PANEL_W = { xs: 300, sm: 340, md: 360 };
const ATTACH_PANEL_W = { xs: 320, sm: 340 };

type PanelContentType = "conversations" | null;

export default function Chat() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { t } = useTranslation();

  const {
    data: rawAgentsFromServer = [],
    isLoading: flowsLoading,
    isError: flowsError,
    error: flowsErrObj,
  } = useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery(undefined, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: true,
    refetchOnReconnect: true,
  });

  const agentsFromServer = useMemo<AnyAgent[]>(() => normalizeAgenticFlows(rawAgentsFromServer), [rawAgentsFromServer]);

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

  const [panelContentType, setPanelContentType] = useLocalStorageState<PanelContentType>(
    "chat.panelContentType",
    "conversations",
  );
  const isPanelOpen = panelContentType !== null;
  const [attachmentsPanelOpen, setAttachmentsPanelOpen] = useState<boolean>(false);
  const [attachmentBadgeCount, setAttachmentBadgeCount] = useState<number>(0);
  const lastAttachmentSessionRef = useRef<string | null>(null);

  const handleAttachmentBadgeUpdate = useCallback(
    (count: number) => {
      console.log("XXXXXX attachment badge update", { sessionId: currentSession?.id, count });
      setAttachmentBadgeCount(count);
    },
    [currentSession?.id],
  );

  const openPanel = (type: PanelContentType) => {
    setPanelContentType(panelContentType === type ? null : type);
  };
  const closePanel = () => setPanelContentType(null);

  const openConversationsPanel = () => openPanel("conversations");

  const handleSelectAgent = (agent: AnyAgent) => {
    selectAgentForCurrentSession(agent);
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
                onCreateNewConversation={startNewConversation}
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

  const attachmentButtonContainerSx = {
    position: "absolute",
    top: 12,
    right: attachmentsPanelOpen
      ? {
          xs: ATTACH_PANEL_W.xs + 12,
          sm: ATTACH_PANEL_W.sm + 12,
          md: ATTACH_PANEL_W.sm + 12,
        }
      : 12,
    zIndex: 10,
    display: "flex",
  };

  const serverAttachmentCount = useMemo(() => {
    if (!currentSession) return 0;
    const att = (currentSession as any).attachments;
    if (Array.isArray(att)) return att.length;
    const fileNames = (currentSession as any).file_names;
    if (Array.isArray(fileNames)) return fileNames.length;
    const count = (currentSession as any).attachments_count;
    return typeof count === "number" ? count : 0;
  }, [currentSession]);

  const supportsAttachments = currentAgent?.chat_options?.attach_files === true;
  useEffect(() => {
    if (!currentSession?.id || !supportsAttachments) {
      lastAttachmentSessionRef.current = currentSession?.id ?? null;
      setAttachmentBadgeCount(0);
      return;
    }
    console.log("XXXXXX server attachment snapshot", {
      sessionId: currentSession.id,
      serverAttachmentCount,
    });
    setAttachmentBadgeCount((prev) => {
      const isNewSession = lastAttachmentSessionRef.current !== currentSession.id;
      lastAttachmentSessionRef.current = currentSession.id;
      if (isNewSession) {
        return serverAttachmentCount ?? 0;
      }
      return Math.max(prev, serverAttachmentCount ?? 0);
    });
  }, [currentSession?.id, serverAttachmentCount, supportsAttachments]);
  console.log("XXXXXX current agent", { name: currentAgent?.name, supportsAttachments });

  return (
    <Box ref={containerRef} sx={{ height: "100vh", position: "relative", overflow: "hidden" }}>
      {/* Panel toggle buttons */}
      <Box sx={buttonContainerSx}>
        <IconButton
          color={panelContentType === "conversations" ? "primary" : "default"}
          onClick={openConversationsPanel}
          title={t("settings.conversations")}
        >
          <ChatIcon />
        </IconButton>
      </Box>
      {supportsAttachments && (
        <Box sx={attachmentButtonContainerSx}>
          <IconButton
            color={attachmentsPanelOpen ? "primary" : "default"}
            onClick={() => setAttachmentsPanelOpen((v) => !v)}
            title={t("chatbot.attachments.drawerTitle", "Attachments")}
          >
            <Badge
              color="primary"
              badgeContent={attachmentBadgeCount > 0 ? attachmentBadgeCount : undefined}
              overlap="circular"
              anchorOrigin={{ vertical: "top", horizontal: "right" }}
            >
              <FolderOpenIcon />
            </Badge>
          </IconButton>
        </Box>
      )}

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
            onSelectNewAgent={handleSelectAgent}
            onUpdateOrAddSession={updateOrAddSession}
            isCreatingNewConversation={isCreatingNewConversation}
            runtimeContext={{
              selected_chat_context_ids: selectedChatContextIds.length ? selectedChatContextIds : undefined,
            }}
            onBindDraftAgentToSessionId={bindDraftAgentToSessionId}
            attachmentsPanelOpen={supportsAttachments ? attachmentsPanelOpen : false}
            onAttachmentsPanelOpenChange={supportsAttachments ? setAttachmentsPanelOpen : undefined}
            onAttachmentCountChange={supportsAttachments ? handleAttachmentBadgeUpdate : undefined}
          />
        </Grid2>
      </Box>
    </Box>
  );
}
