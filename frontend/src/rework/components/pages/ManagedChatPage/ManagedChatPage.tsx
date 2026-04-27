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

import { useCallback, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { v4 as uuidv4 } from "uuid";

import Button from "@shared/atoms/Button/Button";
import { TogglePanelButton } from "@shared/atoms/TogglePanelButton/TogglePanelButton";
import { HitlPrompt } from "@shared/molecules/HitlPrompt/HitlPrompt.tsx";
import { ChatInputBar } from "@shared/molecules/ChatInputBar/ChatInputBar";
import { UserMessage } from "@shared/molecules/UserMessage/UserMessage";
import { ChatMessagesArea } from "@shared/organisms/ChatMessagesArea/ChatMessagesArea";
import { AssistantTurn } from "@shared/organisms/AssistantTurn/AssistantTurn";
import { useToast } from "../../../../components/ToastProvider";
import { ChatSseCallbacks, useChatSse } from "../../../../hooks/useChatSse";
import type { AwaitingHumanEvent, ChatMessage, VectorSearchHit } from "../../../../slices/agentic/agenticOpenApi";
import {
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { isTraceChannel } from "../../../../rework/utils/traceUtils";
import { useSessionHistory } from "./useSessionHistory";

import styles from "./ManagedChatPage.module.css";

interface Turn {
  exchangeId: string;
  userMessages: ChatMessage[];
  traceMessages: ChatMessage[];
  finalMessages: ChatMessage[];
  sources: VectorSearchHit[];
}

function textOf(msg: ChatMessage): string {
  return (msg.parts ?? [])
    .filter((p) => p.type === "text")
    .map((p) => (p as { type: "text"; text: string }).text)
    .join("");
}

function extractSources(messages: ChatMessage[]): VectorSearchHit[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    const srcs = messages[i].metadata?.sources;
    if (srcs && srcs.length > 0) return srcs;
  }
  return [];
}

function groupIntoTurns(messages: ChatMessage[]): Turn[] {
  const order: string[] = [];
  const map = new Map<string, Turn>();

  for (const msg of messages) {
    const eid = msg.exchange_id;
    if (!map.has(eid)) {
      order.push(eid);
      map.set(eid, { exchangeId: eid, userMessages: [], traceMessages: [], finalMessages: [], sources: [] });
    }
    const turn = map.get(eid)!;
    if (msg.role === "user") {
      turn.userMessages.push(msg);
    } else if (isTraceChannel(msg.channel)) {
      turn.traceMessages.push(msg);
    } else {
      turn.finalMessages.push(msg);
    }
  }

  const turns = order.map((eid) => map.get(eid)!);
  for (const turn of turns) {
    turn.sources = extractSources(turn.finalMessages);
  }
  return turns;
}

export default function ManagedChatPage() {
  const { teamId, agentInstanceId } = useParams<{ teamId: string; agentInstanceId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { showError } = useToast();

  const [sessionId, setSessionId] = useState<string | null>(() => searchParams.get("session"));
  const [input, setInput] = useState("");
  const [pendingHitl, setPendingHitl] = useState<AwaitingHumanEvent | null>(null);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);

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
      setSessionId(sid);
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

  const { messages, waitResponse, send, sendHitlResume, reset, replaceAllMessages } = useChatSse({
    agentInstanceId: agentInstanceId ?? "",
    teamId: teamId ?? "",
    ...sseCallbacks,
  });

  const turns = useMemo(() => groupIntoTurns(messages), [messages]);

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
        createSessionRequest: { session_id: sid, agent_instance_id: agentInstanceId },
      }).catch(() => {});
    }

    send(text, sid);
  };

  const handleHitlAnswer = (answer: string | boolean, freeText?: string) => {
    if (!pendingHitl) return;
    setPendingHitl(null);
    sendHitlResume(pendingHitl, answer, freeText);
  };

  const handleNewConversation = () => {
    reset();
    setSessionId(null);
    setPendingHitl(null);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("session");
        return next;
      },
      { replace: true },
    );
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
            isEmpty={turns.length === 0 && !waitResponse}
            isLoading={isLoadingHistory}
            scrollVersion={messages.length}
          >
            {turns.map((turn, i) => {
              const isStreaming = waitResponse && i === turns.length - 1;
              return (
                <div key={turn.exchangeId} className={styles.turn}>
                  {turn.userMessages.map((msg, j) => (
                    <UserMessage key={`${msg.exchange_id}|user|${j}`} text={textOf(msg)} />
                  ))}
                  {(turn.traceMessages.length > 0 || turn.finalMessages.length > 0 || isStreaming) && (
                    <AssistantTurn
                      traceMessages={turn.traceMessages}
                      finalMessages={turn.finalMessages}
                      sources={turn.sources}
                      isStreaming={isStreaming}
                    />
                  )}
                </div>
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

        {/* Right panel slot — Phase 6C (AgentOptionsPanel) mounts here */}
        {rightPanelOpen && <div className={styles.rightPanel} />}
      </div>
    </div>
  );
}
