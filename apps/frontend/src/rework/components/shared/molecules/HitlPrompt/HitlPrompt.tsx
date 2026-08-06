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

import { useState } from "react";
import Button from "@shared/atoms/Button/Button";
import TextArea from "@shared/atoms/TextArea/TextArea";
import type { RuntimeAwaitingHumanEvent } from "@hooks/useChatSse";
import styles from "./HitlPrompt.module.css";

interface HitlPromptProps {
  event: RuntimeAwaitingHumanEvent;
  onAnswer: (answer: string | boolean | undefined, freeText?: string) => void;
  readonly?: boolean;
}

export function HitlPrompt({ event, onAnswer, readonly = false }: HitlPromptProps) {
  const payload = event.payload;

  const [freeText, setFreeText] = useState("");

  return (
    <div
      className={`${styles.card} ${!readonly ? styles.active : ""}`}
      role="group"
      aria-label="Agent is waiting for your input"
    >
      {payload.title && <p className={styles.title}>{payload.title}</p>}
      {payload.question && <p className={styles.question}>{payload.question}</p>}

      {/* Answered questions hide their choices — the answer is already written into the
          chat as the turn right after this card, so a disabled button row would be redundant. */}
      {!readonly && payload.choices && payload.choices.length > 0 && (
        <div className={styles.choices}>
          {payload.choices.map((c) => (
            <Button
              key={c.id}
              color={c.default ? "primary" : "on-surface-retreat"}
              variant={c.default ? "filled" : "text"}
              size="small"
              style={{ order: c.default ? 2 : 1 }}
              onClick={() => onAnswer(c.id)}
            >
              {c.label}
            </Button>
          ))}
        </div>
      )}

      {payload.free_text && !readonly && (
        <div className={styles.freeText}>
          <TextArea label="Your answer" value={freeText} onChange={(e) => setFreeText(e.target.value)} rows={2} />
          <Button
            color="primary"
            variant="filled"
            size="small"
            disabled={!freeText.trim()}
            onClick={() => onAnswer(undefined, freeText)}
          >
            Send
          </Button>
        </div>
      )}
    </div>
  );
}
