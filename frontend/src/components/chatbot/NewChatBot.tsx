// src/components/chatbot/ChatBot.tsx
// Copyright Thales 2025
// Apache-2.0

import { Box, Grid2, Tooltip, Typography, useTheme, Divider } from "@mui/material";
import { useEffect, useRef, useState, useLayoutEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { getConfig } from "../../common/config.tsx";
import DotsLoader from "../../common/DotsLoader.tsx";
import { usePostTranscribeAudioMutation } from "../../frugalit/slices/api.tsx";
import { KeyCloakService } from "../../security/KeycloakService.ts";
import {
  AgenticFlow,
  RuntimeContext,
  SessionSchema,
  useLazyGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery,
} from "../../slices/agentic/agenticOpenApi.ts";
import { getAgentBadge } from "../../utils/avatar.tsx";
import { useToast } from "../ToastProvider.tsx";
import { MessagesArea } from "./MessagesArea.tsx";
import UserInput, { UserInputContent } from "./UserInput.tsx";
import { sortMessages } from "./ChatBotUtils.tsx";
import {
  TagType,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import ChatKnowledge from "./ChatKnowledge.tsx";
import { useChatSocket } from "../../hooks/useChatSocket.ts";

interface TranscriptionResponse {
  text?: string;
}

export interface ChatBotProps {
  currentChatBotSession: SessionSchema | null;
  currentAgenticFlow: AgenticFlow;
  agenticFlows: AgenticFlow[];
  onUpdateOrAddSession: (session: SessionSchema) => void;
  isCreatingNewConversation: boolean;
  runtimeContext?: RuntimeContext;
  onBindDraftAgentToSessionId?: (sessionId: string) => void;
}

const ChatBot = ({
  currentChatBotSession,
  currentAgenticFlow,
  agenticFlows,
  onUpdateOrAddSession,
  isCreatingNewConversation,
  runtimeContext: baseRuntimeContext,
  onBindDraftAgentToSessionId,
}: ChatBotProps) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const { showInfo, showError } = useToast();

  const [contextOpen, setContextOpen] = useState<boolean>(() => {
    try {
      const uid = KeyCloakService.GetUserId?.() || "anon";
      return localStorage.getItem(`chatctx_open:${uid}`) === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      const uid = KeyCloakService.GetUserId?.() || "anon";
      localStorage.setItem(`chatctx_open:${uid}`, contextOpen ? "1" : "0");
    } catch {}
  }, [contextOpen]);

  // Use the new custom hook to handle all WebSocket logic
  const { messages, waitResponse, send, replaceAllMessages } = useChatSocket({
    currentSession: currentChatBotSession,
    currentAgenticFlow,
    onUpdateOrAddSession,
    onBindDraftAgentToSessionId,
  });

  const [postTranscribeAudio] = usePostTranscribeAudioMutation();

  // Lazy messages fetcher
  const [fetchHistory] = useLazyGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery();

  // === SINGLE scroll container ref (attach to the ONLY overflow element) ===
  const scrollerRef = useRef<HTMLDivElement>(null);

  // === Hard guarantee: snap to absolute bottom after render ===
  useLayoutEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, currentChatBotSession?.id]);

  // Fetch messages when the session changes
  useEffect(() => {
    const id = currentChatBotSession?.id;
    if (!id) return;

    replaceAllMessages([]); // clear view while fetching

    fetchHistory({ sessionId: id })
      .unwrap()
      .then((serverMessages) => {
        const sorted = sortMessages(serverMessages);
        replaceAllMessages(sorted);
        // NEW — If this is the first time we "see" this id, bind draft now.
        onBindDraftAgentToSessionId?.(id);
      })
      .catch((e) => {
        console.error("[❌ ChatBot] Failed to load messages:", e);
        showError({ summary: "Failed to load messages", detail: e.message || "Please try again later." });
      });
  }, [currentChatBotSession?.id, fetchHistory, onBindDraftAgentToSessionId, replaceAllMessages, showError]);

  // Chat knowledge persistence
  const storageKey = useMemo(() => {
    const uid = KeyCloakService.GetUserId?.() || "anon";
    const agent = currentAgenticFlow?.name || "default";
    return `chatctx:${uid}:${agent}`;
  }, [currentAgenticFlow?.name]);

  // Init values (rehydration)
  const [initialCtx, setInitialCtx] = useState<{
    documentLibraryIds: string[];
    promptResourceIds: string[];
    templateResourceIds: string[];
  }>({
    documentLibraryIds: [],
    promptResourceIds: [],
    templateResourceIds: [],
  });

  // Load from local storage
  const { data: docLibs = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" as TagType });
  const { data: promptResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "prompt" });
  const { data: templateResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "template" });

  const libraryNameMap = useMemo(
    () => Object.fromEntries((docLibs as any[]).map((x: any) => [x.id, x.name])),
    [docLibs],
  );
  const promptNameMap = useMemo(
    () => Object.fromEntries((promptResources as any[]).map((x: any) => [x.id, x.name ?? x.id])),
    [promptResources],
  );
  const templateNameMap = useMemo(
    () => Object.fromEntries((templateResources as any[]).map((x: any) => [x.id, x.name ?? x.id])),
    [templateResources],
  );

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        setInitialCtx({
          documentLibraryIds: parsed.documentLibraryIds ?? [],
          promptResourceIds: parsed.promptResourceIds ?? [],
          templateResourceIds: parsed.templateResourceIds ?? [],
        });
      } else {
        setInitialCtx({ documentLibraryIds: [], promptResourceIds: [], templateResourceIds: [] });
      }
    } catch (e) {
      console.warn("Local context load failed:", e);
    }
  }, [storageKey]);

  const [userInputContext, setUserInputContext] = useState<any>(null);

  // Save per-agent defaults *only before a session exists*
  useEffect(() => {
    if (!userInputContext) return;
    const sessionId = currentChatBotSession?.id;
    if (sessionId) return; // session exists -> do NOT save per-agent defaults here

    try {
      const payload = {
        documentLibraryIds: userInputContext.documentLibraryIds ?? [],
        promptResourceIds: userInputContext.promptResourceIds ?? [],
        templateResourceIds: userInputContext.templateResourceIds ?? [],
      };
      localStorage.setItem(storageKey, JSON.stringify(payload));
    } catch (e) {
      console.warn("Local context save failed:", e);
    }
  }, [
    userInputContext?.documentLibraryIds,
    userInputContext?.promptResourceIds,
    userInputContext?.templateResourceIds,
    storageKey,
    currentChatBotSession?.id,
  ]);

  // Handle user input (text/audio/files)
  const handleSend = async (content: UserInputContent) => {
    const userId = KeyCloakService.GetUserId();
    const sessionId = currentChatBotSession?.id;
    const agentName = currentAgenticFlow.name;

    const runtimeContext: RuntimeContext = { ...baseRuntimeContext };
    if (content.documentLibraryIds?.length) runtimeContext.selected_document_libraries_ids = content.documentLibraryIds;
    if (content.promptResourceIds?.length) runtimeContext.selected_prompt_ids = content.promptResourceIds;
    if (content.templateResourceIds?.length) runtimeContext.selected_template_ids = content.templateResourceIds;

    // Files upload
    if (content.files?.length) {
      for (const file of content.files) {
        const formData = new FormData();
        formData.append("user_id", userId || "");
        formData.append("session_id", sessionId || "");
        formData.append("agent_name", agentName);
        formData.append("file", file);

        try {
          const response = await fetch(`${getConfig().backend_url_api}/agentic/v1/chatbot/upload`, {
            method: "POST",
            body: formData,
          });
          if (!response.ok) throw new Error(`Failed to upload ${file.name}: ${response.statusText}`);
          showInfo({ summary: "File Upload", detail: `File ${file.name} uploaded successfully.` });
        } catch (err) {
          showError({ summary: "File Upload Error", detail: (err as Error).message });
          return; // Stop if upload fails
        }
      }
    }

    if (content.text) {
      send(content.text.trim(), runtimeContext);
    } else if (content.audio) {
      const audioFile: File = new File([content.audio], "audio.mp3", { type: content.audio.type });
      postTranscribeAudio({ file: audioFile }).then((response) => {
        const message: TranscriptionResponse = (response as any).data as TranscriptionResponse;
        if (message?.text) send(message.text, runtimeContext);
      });
    } else {
      console.warn("No content to send.");
    }
  };

  const outputTokenCounts: number = messages.reduce((sum, msg) => sum + (msg.metadata?.token_usage?.output_tokens || 0), 0);
  const inputTokenCounts: number = messages.reduce((sum, msg) => sum + (msg.metadata?.token_usage?.input_tokens || 0), 0);
  
  const showWelcome = !waitResponse && (isCreatingNewConversation || messages.length === 0);
  const hasContext =
    !!userInputContext &&
    ((userInputContext?.files?.length ?? 0) > 0 ||
      !!userInputContext?.audioBlob ||
      (userInputContext?.documentLibraryIds?.length ?? 0) > 0 ||
      (userInputContext?.promptResourceIds?.length ?? 0) > 0 ||
      (userInputContext?.templateResourceIds?.length ?? 0) > 0);

  return (
    <Box width={"100%"} height="100%" display="flex" flexDirection="column" alignItems="center" sx={{ minHeight: 0 }}>
      <Box
        width="80%"
        maxWidth="768px"
        display="flex"
        height="100vh"
        flexDirection="column"
        alignItems="center"
        paddingBottom={1}
        sx={{ minHeight: 0, overflow: "hidden" }}
      >
        {showWelcome ? (
          <Box
            sx={{
              minHeight: "100vh",
              width: "100%",
              px: { xs: 2, sm: 3 },
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 2.5,
            }}
          >
            <Box
              sx={{
                width: "min(900px, 100%)",
                borderRadius: 3,
                border: (t) => `1px solid ${t.palette.divider}`,
                background: (t) => `linear-gradient(180deg, ${t.palette.heroBackgroundGrad.gradientFrom}, ${t.palette.heroBackgroundGrad.gradientTo})`,
                boxShadow: (t) => (t.palette.mode === "light" ? "0 1px 2px rgba(0,0,0,0.06)" : "0 1px 2px rgba(0,0,0,0.25)"),
                px: { xs: 2, sm: 3 },
                py: { xs: 2, sm: 2.5 },
              }}
            >
              <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 1.25, textAlign: "center", flexWrap: "nowrap" }}>
                {getAgentBadge(currentAgenticFlow.nickname)}
                <Typography variant="h5" sx={{ fontWeight: 600, letterSpacing: 0.2 }}>
                  {t("chatbot.startNew", { name: currentAgenticFlow.nickname })}
                </Typography>
              </Box>
              <Divider sx={{ my: 1.25 }} />
              <Typography variant="body2" sx={{ fontStyle: "italic", textAlign: "center", color: "text.secondary" }}>
                {currentAgenticFlow.role}
              </Typography>
            </Box>
            <Box sx={{ width: "min(900px, 100%)" }}>
              <UserInput
                enableFilesAttachment
                enableAudioAttachment
                isWaiting={waitResponse}
                onSend={handleSend}
                onContextChange={setUserInputContext}
                sessionId={currentChatBotSession?.id}
                initialDocumentLibraryIds={initialCtx.documentLibraryIds}
                initialPromptResourceIds={initialCtx.promptResourceIds}
                initialTemplateResourceIds={initialCtx.templateResourceIds}
              />
            </Box>
          </Box>
        ) : (
          <>
            <Grid2 ref={scrollerRef} display="flex" flexDirection="column" flex="1" width="100%" p={2} sx={{ overflowY: "auto", overflowX: "hidden", scrollbarWidth: "none", wordBreak: "break-word", alignContent: "center" }}>
              <MessagesArea
                key={currentChatBotSession?.id}
                messages={messages}
                agenticFlows={agenticFlows}
                currentAgenticFlow={currentAgenticFlow}
              />
              {waitResponse && (
                <Box mt={1} sx={{ alignSelf: "flex-start" }}>
                  <DotsLoader dotColor={theme.palette.text.primary} />
                </Box>
              )}
            </Grid2>
            <Grid2 container width="100%" alignContent="center">
              <UserInput
                enableFilesAttachment={true}
                enableAudioAttachment={true}
                isWaiting={waitResponse}
                onSend={handleSend}
                onContextChange={setUserInputContext}
                sessionId={currentChatBotSession?.id}
                initialDocumentLibraryIds={initialCtx.documentLibraryIds}
                initialPromptResourceIds={initialCtx.promptResourceIds}
                initialTemplateResourceIds={initialCtx.templateResourceIds}
              />
            </Grid2>
            <Grid2 container width="100%" display="flex" justifyContent="flex-end" marginTop={0.5}>
              <Tooltip
                title={t("chatbot.tooltip.tokenUsage", {
                  input: inputTokenCounts,
                  output: outputTokenCounts,
                })}
              >
                <Typography fontSize="0.8rem" color={theme.palette.text.secondary} fontStyle="italic">
                  {t("chatbot.tooltip.tokenCount", {
                    total: outputTokenCounts + inputTokenCounts > 0 ? outputTokenCounts + inputTokenCounts : "...",
                  })}
                </Typography>
              </Tooltip>
            </Grid2>
          </>
        )}
      </Box>
      <ChatKnowledge
        open={contextOpen}
        hasContext={hasContext}
        userInputContext={userInputContext}
        onClose={() => setContextOpen(false)}
        libraryNameMap={libraryNameMap}
        promptNameMap={promptNameMap}
        templateNameMap={templateNameMap}
      />
    </Box>
  );
};

export default ChatBot;
