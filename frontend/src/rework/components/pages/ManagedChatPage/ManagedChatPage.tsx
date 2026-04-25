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

import { KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { v4 as uuidv4 } from "uuid";

import Button from "@shared/atoms/Button/Button";
import TextArea from "@shared/atoms/TextArea/TextArea";
import { HitlPrompt } from "@shared/molecules/HitlPrompt/HitlPrompt.tsx";
import { ThoughtTrace } from "@shared/molecules/ThoughtTrace/ThoughtTrace";
import { useToast } from "../../../../components/ToastProvider";
import { ChatSseCallbacks, useChatSse } from "../../../../hooks/useChatSse";
import type { AwaitingHumanEvent, ChatMessage } from "../../../../slices/agentic/agenticOpenApi";
import {
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { isTraceChannel } from "../../../../rework/utils/traceUtils";
import { MessageBubble } from "./MessageBubble/MessageBubble";
import { useSessionHistory } from "./useSessionHistory";

import styles from "./ManagedChatPage.module.css";

interface Turn {
  exchangeId: string;
  userMessages: ChatMessage[];
  traceMessages: ChatMessage[];
  finalMessages: ChatMessage[];
}

function groupIntoTurns(messages: ChatMessage[]): Turn[] {
  const order: string[] = [];
  const map = new Map<string, Turn>();

  for (const msg of messages) {
    const eid = msg.exchange_id;
    if (!map.has(eid)) {
      order.push(eid);
      map.set(eid, { exchangeId: eid, userMessages: [], traceMessages: [], finalMessages: [] });
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

  return order.map((eid) => map.get(eid)!);
}

export default function ManagedChatPage() {
  const { teamId, agentInstanceId } = useParams<{ teamId: string; agentInstanceId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { showError } = useToast();

  const [sessionId, setSessionId] = useState<string | null>(() => searchParams.get("session"));
  const [input, setInput] = useState("");
  const [pendingHitl, setPendingHitl] = useState<AwaitingHumanEvent | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Agent display name — never show the raw agent_instance_id to the user.
  const { data: agentInstances } = useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery(
    { teamId: teamId ?? "" },
    { skip: !teamId },
  );
  const agentDisplayName =
    agentInstances?.find((i) => i.agent_instance_id === agentInstanceId)?.display_name ?? "Agent";

  const [registerSession] = usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation();

  const bindSessionId = useCallback(
    (sid: string) => {
      setSessionId(sid);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("session", sid);
        return next;
      }, { replace: true });
    },
    [setSearchParams],
  );

  const sseCallbacks: ChatSseCallbacks = {
    onBindDraftAgentToSessionId: bindSessionId,
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

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

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

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
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
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("session");
      return next;
    }, { replace: true });
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <span className={styles.headerTitle}>{agentDisplayName}</span>
        <Button color="on-surface" variant="text" size="small" onClick={handleNewConversation}>
          New conversation
        </Button>
      </header>

      <div className={styles.messages} role="log" aria-live="polite" aria-label="Conversation">
        {isLoadingHistory && <p className={styles.hint}>Loading conversation history…</p>}
        {!isLoadingHistory && turns.length === 0 && !waitResponse && (
          <p className={styles.empty}>Send a message to start the conversation.</p>
        )}

        {turns.map((turn) => (
          <div key={turn.exchangeId} className={styles.turn}>
            {turn.userMessages.map((msg, i) => (
              <MessageBubble
                key={`${msg.exchange_id}|user|${i}`}
                msg={msg}
              />
            ))}
            {(turn.traceMessages.length > 0 || turn.finalMessages.length > 0) && (
              <div className={styles.agentRow}>
                {turn.traceMessages.length > 0 && (
                  <div className={styles.traceColumn}>
                    <ThoughtTrace
                      messages={turn.traceMessages}
                      done={turn.finalMessages.length > 0}
                    />
                  </div>
                )}
                <div className={styles.responseColumn}>
                  {turn.finalMessages.map((msg, i) => (
                    <MessageBubble
                      key={`${msg.exchange_id}|final|${msg.rank}|${i}`}
                      msg={msg}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}

        {waitResponse && <p className={styles.hint}>Agent is thinking…</p>}
        {pendingHitl && <HitlPrompt event={pendingHitl} onAnswer={handleHitlAnswer} />}
        <div ref={bottomRef} />
      </div>

      <footer className={styles.footer}>
        <TextArea
          label="Message"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={waitResponse || isLoadingHistory}
          rows={2}
          placeholder="Press Enter to send, Shift+Enter for newline"
        />
        <Button
          color="primary"
          variant="filled"
          size="medium"
          disabled={!input.trim() || waitResponse || isLoadingHistory}
          onClick={handleSend}
        >
          Send
        </Button>
      </footer>
    </div>
  );
}
