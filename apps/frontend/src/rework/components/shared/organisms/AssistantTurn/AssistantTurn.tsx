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
import type { ChatMessage, LinkPart, VectorSearchHit } from "../../../../../slices/agentic/agenticOpenApi";
import { ThoughtTrace } from "@shared/molecules/ThoughtTrace/ThoughtTrace";
import { AssistantMessage } from "@shared/molecules/AssistantMessage/AssistantMessage";
import { ArtifactLinks } from "@shared/molecules/ArtifactLinks/ArtifactLinks";
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
  links: LinkPart[];
  tokenUsage?: TokenUsage | null;
  isStreaming: boolean;
}

export function AssistantTurn({ text, traceMessages, sources, links, tokenUsage, isStreaming }: AssistantTurnProps) {
  const [activeSourceIndex, setActiveSourceIndex] = useState<number | null>(null);
  const [selected, setSelected] = useState<{ source: VectorSearchHit; index: number } | null>(null);

  // All hooks before any conditional returns.
  const uiSources = useMemo(() => sources.map((h, i) => hitToSource(h, i)), [sources]);

  useEffect(() => {
    if (activeSourceIndex == null) return;
    const i = activeSourceIndex - 1;
    const source = sources[i];
    if (!source) return;
    setSelected({ source, index: activeSourceIndex });
  }, [activeSourceIndex, sources]);

  const copyAction = useCallback(() => {
    navigator.clipboard.writeText(text).catch(() => {});
  }, [text]);

  const actions: Action[] = useMemo(
    () => [{ id: "copy", icon: "content_copy", label: "Copy response", onClick: copyAction }],
    [copyAction],
  );

  const hasContent = traceMessages.length > 0 || text.length > 0 || links.length > 0 || isStreaming;
  if (!hasContent) return null;

  return (
    <div className={styles.turn}>
      {/* ThoughtTrace owns its own expand/collapse — no wrapper needed */}
      {traceMessages.length > 0 && <ThoughtTrace messages={traceMessages} done={!isStreaming} />}

      <AssistantMessage
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

      {!isStreaming && links.length > 0 && <ArtifactLinks links={links} />}

      {!isStreaming && text && (
        <div className={styles.footer}>
          <ActionBar actions={actions} />
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
}
