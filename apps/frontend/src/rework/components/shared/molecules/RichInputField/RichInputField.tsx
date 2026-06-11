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
import { useTranslation } from "react-i18next";
import styles from "./RichInputField.module.css";

// All three slots and the send button are optional so the component is usable
// as a plain auto-growing textarea, a search bar with filters, or a full
// chat input with context pickers and attachment chips.

interface RichInputFieldProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  /** Called when the user clicks the stop button during streaming. */
  onInterrupt?: () => void;
  disabled?: boolean;
  placeholder?: string;
  /** Rendered above the textarea — typically attachment chips that should stay close to the cursor. */
  aboveTextSlot?: ReactNode;
  /** Rendered in the bottom-left area — context pickers, scope selectors, attachment chips. */
  topSlot?: ReactNode;
  /** Rendered next to the textarea controls — one compact command such as attach-file. */
  leftSlot?: ReactNode;
  /** Rendered to the right of the textarea — replaces the default send/stop buttons. */
  rightSlot?: ReactNode;
  /** When true, shows send/stop buttons based on state (ignored if rightSlot is provided). */
  showSendButton?: boolean;
  maxHeight?: number;
}

export function RichInputField({
  value,
  onChange,
  onSend,
  onInterrupt,
  disabled = false,
  placeholder,
  aboveTextSlot,
  topSlot,
  leftSlot,
  rightSlot,
  showSendButton = false,
  maxHeight = 200,
}: RichInputFieldProps) {
  const { t } = useTranslation();
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

  // Re-focus after the assistant reply completes (disabled: true → false).
  useEffect(() => {
    if (!disabled) {
      textareaRef.current?.focus();
    }
  }, [disabled]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey && !disabled && !e.nativeEvent.isComposing) {
        e.preventDefault();
        onSend();
      }
    },
    [disabled, onSend],
  );

  const hasText = value.trim().length > 0;
  const showStop = showSendButton && disabled && !!onInterrupt;
  const showSend = showSendButton && !disabled && hasText;
  const showBottomRow = !!(topSlot || leftSlot || rightSlot || showStop || showSend);

  return (
    <div className={styles.bar}>
      <div className={styles.field}>
        {aboveTextSlot && <div className={styles.aboveTextSlot}>{aboveTextSlot}</div>}
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

        {showBottomRow && (
          <div className={styles.bottomRow}>
            {leftSlot && <div className={styles.commandSlot}>{leftSlot}</div>}
            {topSlot && <div className={styles.bottomLeft}>{topSlot}</div>}

            {(rightSlot || showStop || showSend) && (
              <div className={styles.rightSlot}>
                {rightSlot ??
                  (showStop ? (
                    <button
                      type="button"
                      className={styles.sendBtn}
                      onClick={onInterrupt}
                      aria-label={t("chatbot.stopResponse")}
                    >
                      <span className={styles.stopIcon} aria-hidden />
                    </button>
                  ) : (
                    <button
                      type="button"
                      className={styles.sendBtn}
                      onClick={onSend}
                      aria-label={t("chatbot.sendMessage")}
                    >
                      <span className="material-symbols-outlined" aria-hidden>
                        arrow_upward
                      </span>
                    </button>
                  ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
