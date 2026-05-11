// Copyright Thales 2026
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

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { v4 as uuidv4 } from "uuid";

import Button from "@shared/atoms/Button/Button";
import { TogglePanelButton } from "@shared/atoms/TogglePanelButton/TogglePanelButton";
import { HitlPrompt } from "@shared/molecules/HitlPrompt/HitlPrompt.tsx";
import { ChatInputBar } from "@shared/molecules/ChatInputBar/ChatInputBar";
import { UserMessage } from "@shared/molecules/UserMessage/UserMessage";
import { ChatMessagesArea } from "@shared/organisms/ChatMessagesArea/ChatMessagesArea";
import { AssistantTurn } from "@shared/organisms/AssistantTurn/AssistantTurn";
import { AgentOptionsPanel } from "@shared/organisms/AgentOptionsPanel/AgentOptionsPanel";
import { useToast } from "../../../../components/ToastProvider";
import { ChatSseCallbacks, useChatSse } from "../../../../hooks/useChatSse";
import type { AwaitingHumanEvent, ChatMessage, VectorSearchHit } from "../../../../slices/agentic/agenticOpenApi";
import type { SearchPolicyName } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import {
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { isTraceChannel, textOf } from "../../../../rework/utils/traceUtils";
import { useSessionHistory } from "./useSessionHistory";

import styles from "./ManagedChatPage.module.css";

interface ConversationMessage {
  id: string;
  role: "user" | "assistant" | "hitl_request" | "hitl_response";
  text: string;
  isStreaming: boolean;
  traceMessages: ChatMessage[];
  sources: VectorSearchHit[];
  hitlChoices?: Array<{ id: string; label: string }>;
  hitlTitle?: string | null;
}

function toConversationMessages(messages: ChatMessage[], isStreaming: boolean): ConversationMessage[] {
  const order: string[] = [];
  const groups = new Map<string, ChatMessage[]>();

  for (const msg of messages) {
    const eid = msg.exchange_id;
    if (!groups.has(eid)) {
      order.push(eid);
      groups.set(eid, []);
    }
    groups.get(eid)!.push(msg);
  }

  const result: ConversationMessage[] = [];
  const lastEid = order[order.length - 1] as string | undefined;

  for (const eid of order) {
    const msgs = groups.get(eid)!;
    const isLast = eid === lastEid;

    const userMsg = msgs.find((m) => m.role === "user" && (m.channel as string) !== "hitl_response");
    if (userMsg) {
      result.push({
        id: `${eid}:user`,
        role: "user",
        text: textOf(userMsg),
        isStreaming: false,
        traceMessages: [],
        sources: [],
      });
    }

    const hitlReqMsg = msgs.find((m) => (m.channel as string) === "hitl_request");
    if (hitlReqMsg) {
      type ReqPart = { question?: string; choices?: Array<{ id: string; label: string }>; title?: string | null };
      const part = hitlReqMsg.parts?.[0] as unknown as ReqPart | undefined;
      result.push({
        id: `${eid}:hitl_req`,
        role: "hitl_request",
        text: part?.question ?? "",
        isStreaming: false,
        traceMessages: [],
        sources: [],
        hitlChoices: part?.choices ?? [],
        hitlTitle: part?.title,
      });
    }

    const hitlRespMsg = msgs.find((m) => (m.channel as string) === "hitl_response");
    if (hitlRespMsg) {
      type RespPart = { label?: string | null; choice_id?: string };
      const part = hitlRespMsg.parts?.[0] as unknown as RespPart | undefined;
      result.push({
        id: `${eid}:hitl_resp`,
        role: "hitl_response",
        text: part?.label ?? part?.choice_id ?? "",
        isStreaming: false,
        traceMessages: [],
        sources: [],
      });
    }

    const traceMessages = msgs.filter((m) => isTraceChannel(m.channel));
    const finalMessages = msgs.filter((m) => {
      const ch = m.channel as string;
      return m.role !== "user" && ch !== "hitl_request" && ch !== "hitl_response" && !isTraceChannel(m.channel);
    });

    if (traceMessages.length > 0 || finalMessages.length > 0 || (isStreaming && isLast)) {
      const sources: VectorSearchHit[] = [];
      for (let i = finalMessages.length - 1; i >= 0; i--) {
        const srcs = finalMessages[i].metadata?.sources;
        if (srcs && srcs.length > 0) {
          sources.push(...srcs);
          break;
        }
      }
      result.push({
        id: `${eid}:assistant`,
        role: "assistant",
        text: finalMessages.map((m) => textOf(m)).join(""),
        isStreaming: isStreaming && isLast,
        traceMessages,
        sources,
      });
    }
  }

  return result;
}

export default function ManagedChatPage() {
  const { teamId, agentInstanceId } = useParams<{ teamId: string; agentInstanceId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { showError } = useToast();

  const sessionId = searchParams.get("session");
  const [input, setInput] = useState("");
  const [pendingHitl, setPendingHitl] = useState<AwaitingHumanEvent | null>(null);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);

  // Runtime context options — held in local state, passed to send() on each turn.
  const [selectedLibraryIds, setSelectedLibraryIds] = useState<string[]>([]);
  const [searchPolicy, setSearchPolicy] = useState<SearchPolicyName>("hybrid");
  const [ragScope, setRagScope] = useState<"corpus_only" | "hybrid" | "general_only">("hybrid");

  // Agent display name — never show the raw agent_instance_id to the user.
  const { data: agentInstances } = useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery(
    { teamId: teamId ?? "" },
    { skip: !teamId },
  );
  const agentDisplayName =
    agentInstances?.find((i) => i.agent_instance_id === agentInstanceId)?.display_name ?? "Agent";

  const [registerSession] = usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation();
  const [refreshSession] = usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation();

  const bindSessionId = useCallback(
    (sid: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("session", sid);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const sseCallbacks: ChatSseCallbacks = {
    onBindDraftAgentToSessionId: bindSessionId,
    onTurnPersisted: (sid) => {
      if (!teamId) return;
      refreshSession({
        teamId,
        sessionId: sid,
        updateSessionRequest: { updated_at: new Date().toISOString() },
      }).catch(() => {});
    },
    onAwaitingHuman: (event) => setPendingHitl(event),
    onError: (msg) => showError({ summary: "Agent error", detail: msg }),
  };

  const { messages, waitResponse, effectiveChatOptions, send, sendHitlResume, reset, replaceAllMessages } = useChatSse({
    agentInstanceId: agentInstanceId ?? "",
    teamId: teamId ?? "",
    ...sseCallbacks,
  });

  // Clear local state whenever the user navigates to a different session.
  useEffect(() => {
    reset();
    setPendingHitl(null);
    setInput("");
  }, [sessionId, reset]);

  // Sync search defaults from the agent's effective options after the first prepare-execution.
  useEffect(() => {
    if (!effectiveChatOptions) return;
    if (effectiveChatOptions.default_search_policy) setSearchPolicy(effectiveChatOptions.default_search_policy);
    if (effectiveChatOptions.default_search_rag_scope) setRagScope(effectiveChatOptions.default_search_rag_scope);
  }, [effectiveChatOptions]);

  const conversationMessages = useMemo(() => toConversationMessages(messages, waitResponse), [messages, waitResponse]);

  const { isLoading: isLoadingHistory } = useSessionHistory({
    sessionId,
    teamId,
    agentInstanceId,
    onLoaded: replaceAllMessages,
  });

  if (!teamId || !agentInstanceId) {
    return <div className={styles.error}>Missing team or agent context in URL.</div>;
  }

  const handleSend = () => {
    const text = input.trim();
    if (!text || waitResponse) return;
    setInput("");
    setPendingHitl(null);

    let sid = sessionId;
    if (!sid) {
      sid = uuidv4();
      bindSessionId(sid);
      registerSession({
        teamId,
        createSessionRequest: { session_id: sid, agent_instance_id: agentInstanceId, title: text.slice(0, 120) },
      }).catch(() => {});
    }

    send(text, sid, {
      selected_document_libraries_ids: selectedLibraryIds.length > 0 ? selectedLibraryIds : null,
      search_policy: searchPolicy,
      search_rag_scope: ragScope,
    });
  };

  const handleHitlAnswer = (answer: string | boolean, freeText?: string) => {
    if (!pendingHitl) return;
    setPendingHitl(null);
    sendHitlResume(pendingHitl, answer, freeText);
  };

  const handleNewConversation = () => {
    setPendingHitl(null);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("session");
        return next;
      },
      { replace: true },
    );
    // reset() and setInput("") are handled by the sessionId useEffect above.
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <span className={styles.headerTitle}>{agentDisplayName}</span>
        <Button color="on-surface" variant="text" size="small" onClick={handleNewConversation}>
          New conversation
        </Button>
        <TogglePanelButton open={rightPanelOpen} onClick={() => setRightPanelOpen((p) => !p)} />
      </header>

      <div className={styles.body}>
        <div className={styles.chatColumn}>
          <ChatMessagesArea
            isEmpty={conversationMessages.length === 0 && !waitResponse}
            isLoading={isLoadingHistory}
            scrollVersion={messages.length}
          >
            {conversationMessages.map((msg) => {
              if (msg.role === "user" || msg.role === "hitl_response") {
                return <UserMessage key={msg.id} text={msg.text} />;
              }
              if (msg.role === "hitl_request") {
                const frozenEvent: AwaitingHumanEvent = {
                  session_id: "",
                  exchange_id: msg.id,
                  payload: { question: msg.text, choices: msg.hitlChoices, title: msg.hitlTitle },
                };
                return <HitlPrompt key={msg.id} event={frozenEvent} onAnswer={() => {}} readonly />;
              }
              return (
                <AssistantTurn
                  key={msg.id}
                  text={msg.text}
                  traceMessages={msg.traceMessages}
                  sources={msg.sources}
                  isStreaming={msg.isStreaming}
                />
              );
            })}
            {pendingHitl && <HitlPrompt event={pendingHitl} onAnswer={handleHitlAnswer} />}
          </ChatMessagesArea>

          <ChatInputBar
            value={input}
            onChange={setInput}
            onSend={handleSend}
            disabled={waitResponse || isLoadingHistory}
          />
        </div>

        {rightPanelOpen && (
          <div className={styles.rightPanel}>
            <AgentOptionsPanel
              teamId={teamId}
              selectedLibraryIds={selectedLibraryIds}
              onLibraryChange={setSelectedLibraryIds}
              searchPolicy={searchPolicy}
              onSearchPolicyChange={setSearchPolicy}
              ragScope={ragScope}
              onRagScopeChange={setRagScope}
              options={effectiveChatOptions}
              boundLibraryIds={effectiveChatOptions?.bound_library_ids ?? undefined}
            />
          </div>
        )}
      </div>
    </div>
  );
}
