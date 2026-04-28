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

import { ThoughtTrace } from "@shared/molecules/ThoughtTrace/ThoughtTrace";
import { AssistantMessage } from "@shared/molecules/AssistantMessage/AssistantMessage";
import { SourcesPanel } from "@shared/molecules/SourcesPanel/SourcesPanel";
import type { ChatMessage, VectorSearchHit } from "../../../../../slices/agentic/agenticOpenApi";
import styles from "./AssistantTurn.module.css";

interface AssistantTurnProps {
  text: string;
  traceMessages: ChatMessage[];
  sources: VectorSearchHit[];
  isStreaming: boolean;
}

export function AssistantTurn({ text, traceMessages, sources, isStreaming }: AssistantTurnProps) {
  const hasContent = traceMessages.length > 0 || text.length > 0 || isStreaming;

  if (!hasContent) return null;

  return (
    <div className={styles.turn}>
      {traceMessages.length > 0 && <ThoughtTrace messages={traceMessages} done={!isStreaming} />}
      <AssistantMessage text={text} isStreaming={isStreaming} />
      {!isStreaming && sources.length > 0 && <SourcesPanel sources={sources} />}
    </div>
  );
}
