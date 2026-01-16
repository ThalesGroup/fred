// Message content pagination helper for "show more" UX.
// Centralizes fetch + state so MessageCard stays lean.

import { useCallback, useEffect, useState } from "react";
import {
  ChatMessage,
  useLazyGetSessionMessageAgenticV1ChatbotSessionSessionIdMessageRankGetQuery,
} from "../../slices/agentic/agenticOpenApi.ts";

type Params = {
  message: ChatMessage;
  paginationHasMore: boolean;
  onError: (err: unknown) => void;
};

export function useMessageContentPagination({ message, paginationHasMore, onError }: Params) {
  const [expandedMessage, setExpandedMessage] = useState<ChatMessage | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoadingFullText, setIsLoadingFullText] = useState(false);
  const [fetchMessage] = useLazyGetSessionMessageAgenticV1ChatbotSessionSessionIdMessageRankGetQuery();

  useEffect(() => {
    setExpandedMessage(null);
    setIsExpanded(false);
    setIsLoadingFullText(false);
  }, [message.exchange_id, message.rank, message.session_id]);

  const loadFullMessage = useCallback(async () => {
    if (isLoadingFullText) return;
    console.log("[CHAT] load full message start", {
      sessionId: message.session_id,
      rank: message.rank,
    });
    setIsLoadingFullText(true);
    try {
      const fullMessage = await fetchMessage({
        sessionId: message.session_id,
        rank: message.rank,
      }).unwrap();
      setExpandedMessage(fullMessage);
      setIsExpanded(true);
      console.log("[CHAT] load full message success", {
        sessionId: message.session_id,
        rank: message.rank,
      });
    } catch (err) {
      console.warn("[CHAT] load full message failed", {
        sessionId: message.session_id,
        rank: message.rank,
        error: err instanceof Error ? err.message : String(err),
      });
      onError(err);
    } finally {
      setIsLoadingFullText(false);
    }
  }, [fetchMessage, isLoadingFullText, message.rank, message.session_id, onError]);

  const toggleExpanded = useCallback(async () => {
    if (!isExpanded && paginationHasMore && !expandedMessage) {
      await loadFullMessage();
      return;
    }
    setIsExpanded((prev) => !prev);
  }, [expandedMessage, isExpanded, loadFullMessage, paginationHasMore]);

  return {
    renderMessage: expandedMessage ?? message,
    isExpanded,
    isLoadingFullText,
    toggleExpanded,
  };
}
