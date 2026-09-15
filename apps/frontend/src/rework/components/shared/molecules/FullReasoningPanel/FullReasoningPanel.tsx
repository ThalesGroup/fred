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

import { memo, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Switch from "@shared/atoms/Switch/Switch";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import type { ChatMessage } from "../../../../../slices/runtime/runtimeOpenApi";
import { formatLatencyMs } from "../../../../utils/traceUtils";
import ChatSidePanel from "../ChatSidePanel/ChatSidePanel";
import { MarkdownRenderer } from "../MarkdownRenderer/MarkdownRenderer";
import { fullReasoning, fullReasoningMarkdown, type ReasoningTurn } from "./fullReasoning";
import styles from "./FullReasoningPanel.module.css";

interface FullReasoningPanelProps {
  open: boolean;
  onClose: () => void;
  messages: ChatMessage[];
}

const NO_TURNS: ReasoningTurn[] = [];

// Memoized so a streamed token re-renders only the block it lands in, not the
// markdown of every earlier block in the conversation.
const ReasoningBlock = memo(function ReasoningBlock({
  text,
  durationMs,
  streaming,
  restatedLabel,
}: {
  text: string;
  durationMs: number | null;
  streaming: boolean;
  /** Set when the block said nothing new, shown in place of its text. */
  restatedLabel: string | null;
}) {
  return (
    <div className={styles.block}>
      {restatedLabel ? (
        <span className={styles.restated}>{restatedLabel}</span>
      ) : (
        <MarkdownRenderer text={text} streaming={streaming} />
      )}
      {durationMs != null && !streaming && <span className={styles.duration}>{formatLatencyMs(durationMs)}</span>}
    </div>
  );
});

/**
 * Expert view of the agent's whole reasoning across the conversation, untrimmed,
 * next to the condensed chain of thought each turn shows. Rationale: COMPONENT-UX.md.
 */
export function FullReasoningPanel({ open, onClose, messages }: FullReasoningPanelProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [hideRestatements, setHideRestatements] = useState(false);
  // Computed only while open: `messages` changes on every streamed token. Closed,
  // it keeps the last result, which the drawer still shows while it slides out.
  const lastTurns = useRef(NO_TURNS);
  const turns = useMemo(
    () => (open ? fullReasoning(messages, hideRestatements) : lastTurns.current),
    [open, messages, hideRestatements],
  );
  lastTurns.current = turns;
  const restatedLabel = t("rework.chatTrace.restatedReasoning");
  const hideLabel = t("chatbot.fullReasoning.hideRestatements");

  const handleCopy = () => {
    // Copies what the panel shows, restatements hidden or not.
    writeRichClipboard("", fullReasoningMarkdown(turns, restatedLabel)).then((ok) => {
      if (!ok) return;
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const copyLabel = t(copied ? "chatbot.fullReasoning.copied" : "chatbot.fullReasoning.copy");

  return (
    <ChatSidePanel
      open={open}
      onClose={onClose}
      title={t("chatbot.fullReasoning.title")}
      persistKey="full-reasoning-panel"
      width="560px"
      fill
      headerActions={
        <Tooltip text={copyLabel}>
          <IconButton
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: copied ? "check_circle" : "content_copy" }}
            aria-label={copyLabel}
            disabled={turns.length === 0}
            onClick={handleCopy}
          />
        </Tooltip>
      }
    >
      <div className={styles.toolbar}>
        <Switch
          checked={hideRestatements}
          onChange={(event) => setHideRestatements(event.target.checked)}
          aria-label={hideLabel}
        />
        <span className={styles.toolbarLabel}>{hideLabel}</span>
      </div>
      {turns.length === 0 ? (
        <p className={styles.empty}>{t("chatbot.fullReasoning.empty")}</p>
      ) : (
        <div className={styles.turns}>
          {turns.map((turn) => (
            <section key={turn.exchangeId} className={styles.turn}>
              {turn.question && <h3 className={styles.question}>{turn.question}</h3>}
              <div className={styles.steps}>
                {turn.steps.map((step) =>
                  step.kind === "reasoning" ? (
                    <ReasoningBlock
                      key={step.key}
                      text={step.text}
                      durationMs={step.durationMs}
                      streaming={step.streaming}
                      restatedLabel={step.restated ? restatedLabel : null}
                    />
                  ) : (
                    <div key={step.key} className={styles.tools}>
                      <Icon category="outlined" type="build" />
                      <span className={styles.toolLabels}>{step.labels.join(" · ")}</span>
                    </div>
                  ),
                )}
              </div>
            </section>
          ))}
        </div>
      )}
    </ChatSidePanel>
  );
}
