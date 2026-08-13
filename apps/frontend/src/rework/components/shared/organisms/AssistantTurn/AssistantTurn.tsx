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

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ChatMessage, VectorSearchHit } from "../../../../../slices/runtime/runtimeOpenApi";
import type { RawUiPart } from "@rework/types/parts";
import { toEmailHtml, toPlainText, writeRichClipboard } from "@rework/utils/clipboardUtils";
import { ThoughtTrace } from "@shared/molecules/ThoughtTrace/ThoughtTrace";
import { AssistantMessage } from "@shared/molecules/AssistantMessage/AssistantMessage";
import { UiParts } from "@shared/molecules/UiParts/UiParts";
import { HorizontalScrollRow } from "@shared/molecules/HorizontalScrollRow/HorizontalScrollRow";
import { SourceCard } from "@shared/molecules/SourceCard/SourceCard";
import { SourceDetailModal } from "@shared/molecules/SourcesPanel/SourceDetailModal/SourceDetailModal";
import { ActionBar } from "@shared/molecules/ActionBar/ActionBar";
import { TokenUsageBadge } from "@shared/molecules/TokenUsageBadge/TokenUsageBadge";
import { hitToSource } from "../../../../utils/conversationUtils";
import type { Action } from "@shared/molecules/ActionBar/ActionBar";
import type { TokenUsage } from "@rework/types/conversation";
import styles from "./AssistantTurn.module.css";

interface AssistantTurnProps {
  text: string;
  traceMessages: ChatMessage[];
  sources: VectorSearchHit[];
  /** Raw chat parts (#1977); rendering dispatches through the part-renderer registry. */
  uiParts: RawUiPart[];
  tokenUsage?: TokenUsage | null;
  isStreaming: boolean;
  /** call_ids of every tool call currently gated behind an unanswered HITL prompt, if any — see statusForEntry(). */
  pendingToolCallIds?: readonly string[] | null;
}

// Memoized: sibling turns in a long thread must not re-render on unrelated
// parent renders (e.g. a composer keystroke, or a streaming delta on a
// different message) — see #2221.
export const AssistantTurn = memo(function AssistantTurn({
  text,
  traceMessages,
  sources,
  uiParts,
  tokenUsage,
  isStreaming,
  pendingToolCallIds,
}: AssistantTurnProps) {
  const { t } = useTranslation();
  const [activeSourceIndex, setActiveSourceIndex] = useState<number | null>(null);
  const [selected, setSelected] = useState<{ source: VectorSearchHit; index: number } | null>(null);
  const [copied, setCopied] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const revertTimer = useRef<number | null>(null);

  // All hooks before any conditional returns.
  const uiSources = useMemo(() => sources.map((h, i) => hitToSource(h, i)), [sources]);

  useEffect(() => {
    if (activeSourceIndex == null) return;
    const i = activeSourceIndex - 1;
    const source = sources[i];
    if (!source) return;
    setSelected({ source, index: activeSourceIndex });
  }, [activeSourceIndex, sources]);

  // Kept identical to UserTurn's (#2359): cancel a pending revert before
  // arming the next, so a second click inside the 2s window is not cut short
  // by the first click's timer, and drop it on unmount.
  const confirmCopied = useCallback(() => {
    setCopied(true);
    if (revertTimer.current !== null) window.clearTimeout(revertTimer.current);
    revertTimer.current = window.setTimeout(() => setCopied(false), 2000);
  }, []);

  useEffect(
    () => () => {
      if (revertTimer.current !== null) window.clearTimeout(revertTimer.current);
    },
    [],
  );

  const copyAction = useCallback(() => {
    // Copy from the rendered markdown, not the raw `text` prop, so the
    // clipboard gets real bold/lists/tables/links instead of literal
    // markdown syntax — same email-safe serialisation as manual selection.
    const node = contentRef.current;
    const write = node ? writeRichClipboard(toEmailHtml(node), toPlainText(node)) : writeRichClipboard("", text);
    write.then((success) => {
      if (success) confirmCopied();
    });
  }, [text, confirmCopied]);

  const actions: Action[] = useMemo(
    () => [
      {
        id: "copy",
        icon: copied ? "check" : "content_copy",
        label: copied ? t("chatbot.copyMessage.copied") : t("chatbot.copyMessage.response"),
        onClick: copyAction,
      },
    ],
    [copied, copyAction, t],
  );

  const hasContent = traceMessages.length > 0 || text.length > 0 || uiParts.length > 0 || isStreaming;
  if (!hasContent) return null;

  return (
    <div className={styles.turn}>
      {/* ThoughtTrace owns its own expand/collapse — no wrapper needed */}
      {/* pendingToolCallIds is forwarded regardless of isStreaming: the SSE
          stream itself ends the instant the backend pauses for HITL approval
          (the interrupt closes the response), so isStreaming/waitResponse is
          already false by the time the confirmation prompt is showing — the
          exact moment this status needs to apply. Safe unconditionally: it
          can only ever match a combo entry that both shares one of these
          globally-unique call_ids AND still has no result, which a genuinely
          completed historical turn never does. */}
      {traceMessages.length > 0 && (
        <ThoughtTrace messages={traceMessages} done={!isStreaming} pendingToolCallIds={pendingToolCallIds} />
      )}

      <AssistantMessage
        ref={contentRef}
        text={text}
        isStreaming={isStreaming}
        onSourceClick={uiSources.length > 0 ? setActiveSourceIndex : undefined}
      />

      {!isStreaming && uiSources.length > 0 && (
        <HorizontalScrollRow className={styles.sources}>
          {uiSources.map((src, i) => (
            <SourceCard
              key={src.id}
              source={src}
              index={i + 1}
              onClick={() => {
                setActiveSourceIndex(i + 1);
                setSelected({ source: sources[i], index: i + 1 });
              }}
            />
          ))}
        </HorizontalScrollRow>
      )}

      {!isStreaming && uiParts.length > 0 && <UiParts parts={uiParts} />}

      {!isStreaming && text && (
        <div className={styles.footer}>
          <ActionBar actions={actions} alwaysVisible />
          {tokenUsage && <TokenUsageBadge usage={tokenUsage} />}
        </div>
      )}

      {selected && (
        <SourceDetailModal
          source={selected.source}
          index={selected.index}
          onClose={() => {
            setSelected(null);
            setActiveSourceIndex(null);
          }}
        />
      )}
    </div>
  );
});
