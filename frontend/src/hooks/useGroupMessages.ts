import { useMemo } from "react";
import { ChatMessage } from "../slices/agentic/agenticOpenApi";
import { getExtras } from "../components/chatbot/ChatBotUtils";

// A structured representation of a single conversation turn (one user message + responses)
interface ChatExchange {
  userMessage?: ChatMessage;
  reasoningSteps: ChatMessage[];
  finals: ChatMessage[];
  otherMessages: ChatMessage[];
  keptSources?: any[];
}

/**
 * Custom hook to group raw messages into logical conversation exchanges.
 *
 * @param messages The raw array of ChatMessage objects.
 * @returns An array of structured ChatExchange objects.
 */
export function useGroupedMessages(messages: ChatMessage[]): ChatExchange[] {
  return useMemo(() => {
    const sorted = [...messages].sort((a, b) => a.rank - b.rank);
    const grouped = new Map<string, ChatMessage[]>();

    for (const msg of sorted) {
      const key = `${msg.session_id}-${msg.exchange_id}`;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(msg);
    }

    const exchanges: ChatExchange[] = [];

    for (const [, group] of grouped.entries()) {
      const reasoningSteps: ChatMessage[] = [];
      const finals: ChatMessage[] = [];
      const others: ChatMessage[] = [];
      let userMessage: ChatMessage | undefined;
      let keptSources: any[] | undefined;

      for (const msg of group) {
        if (msg.role === "user" && msg.channel === "final") {
          userMessage = msg;
          continue;
        }

        const extras = getExtras(msg);
        if (
          extras?.node === "grade_documents" &&
          Array.isArray(msg.metadata?.sources) &&
          msg.metadata!.sources!.length
        ) {
          keptSources = msg.metadata!.sources as any[];
        }

        const TRACE_CHANNELS = [
          "plan",
          "thought",
          "observation",
          "tool_call",
          "tool_result",
          "system_note",
          "error",
        ] as const;

        if (TRACE_CHANNELS.includes(msg.channel as any)) {
          reasoningSteps.push(msg);
          continue;
        }

        if (msg.role === "assistant" && msg.channel === "final") {
          finals.push(msg);
          continue;
        }

        others.push(msg);
      }

      exchanges.push({
        userMessage,
        reasoningSteps,
        finals,
        otherMessages: others,
        keptSources,
      });
    }

    return exchanges;
  }, [messages]);
}
