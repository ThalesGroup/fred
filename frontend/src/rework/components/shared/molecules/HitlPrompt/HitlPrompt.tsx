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
import type { AwaitingHumanEvent } from "../../../../../slices/agentic/agenticOpenApi";
import styles from "./HitlPrompt.module.css";

interface HitlPromptProps {
  event: AwaitingHumanEvent;
  onAnswer: (answer: string | boolean, freeText?: string) => void;
  readonly?: boolean;
}

export function HitlPrompt({ event, onAnswer, readonly = false }: HitlPromptProps) {
  const payload = event.payload as {
    title?: string | null;
    question?: string | null;
    choices?: { id: string; label: string }[] | null;
    free_text?: boolean | null;
  };

  const [freeText, setFreeText] = useState("");

  return (
    <div className={styles.card} role="group" aria-label="Agent is waiting for your input">
      {payload.title && <p className={styles.title}>{payload.title}</p>}
      {payload.question && <p className={styles.question}>{payload.question}</p>}

      {payload.choices && payload.choices.length > 0 && (
        <div className={styles.choices}>
          {payload.choices.map((c) => (
            <Button
              key={c.id}
              color="secondary"
              variant="outlined"
              size="small"
              disabled={readonly}
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
