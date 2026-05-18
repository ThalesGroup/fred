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

import { KeyboardEvent, ReactNode, useCallback, useEffect, useRef } from "react";
import styles from "./RichInputField.module.css";

// All three slots and the send button are optional so the component is usable
// as a plain auto-growing textarea, a search bar with filters, or a full
// chat input with context pickers and attachment chips.

interface RichInputFieldProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
  /** Rendered above the textarea — attachment chips, file names, etc. */
  topSlot?: ReactNode;
  /** Rendered to the left of the textarea — context pickers, scope selectors. */
  leftSlot?: ReactNode;
  /** Rendered to the right of the textarea — replaces the default send button. */
  rightSlot?: ReactNode;
  /** When true, shows a default send icon button (ignored if rightSlot is provided). */
  showSendButton?: boolean;
  maxHeight?: number;
}

export function RichInputField({
  value,
  onChange,
  onSend,
  disabled = false,
  placeholder,
  topSlot,
  leftSlot,
  rightSlot,
  showSendButton = false,
  maxHeight = 200,
}: RichInputFieldProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(el.scrollHeight, maxHeight);
    el.style.height = `${next}px`;
    el.style.overflowY = next >= maxHeight ? "auto" : "hidden";
  };

  // Reset height when value is cleared externally.
  useEffect(() => {
    if (!value) {
      const el = textareaRef.current;
      if (el) {
        el.style.height = "auto";
        el.style.overflowY = "hidden";
      }
    }
  }, [value]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !disabled) {
      e.preventDefault();
      onSend();
    }
  }, [disabled, onSend]);

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <div className={styles.bar}>
      <div className={styles.field}>
        {topSlot && <div className={styles.topSlot}>{topSlot}</div>}

        <div className={styles.inputRow}>
          {leftSlot && <div className={styles.leftSlot}>{leftSlot}</div>}

          <textarea
            ref={textareaRef}
            className={styles.textarea}
            value={value}
            rows={1}
            disabled={disabled}
            placeholder={placeholder}
            onChange={(e) => {
              onChange(e.target.value);
              resize();
            }}
            onKeyDown={handleKeyDown}
          />

          {(rightSlot || showSendButton) && (
            <div className={styles.rightSlot}>
              {rightSlot ?? (
                <button
                  type="button"
                  className={styles.sendBtn}
                  onClick={onSend}
                  disabled={!canSend}
                  aria-label="Send message"
                >
                  <span className="material-symbols-outlined" aria-hidden>
                    send
                  </span>
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
