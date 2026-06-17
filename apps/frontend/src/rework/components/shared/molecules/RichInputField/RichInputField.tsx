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

import { KeyboardEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { appendVoiceTranscript, audioFileExtensionForMimeType } from "./voiceInputUtils";
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
  /** Renders the command slot inline with the text cursor for compact composer layouts. */
  compactLayout?: boolean;
  enableVoiceInput?: boolean;
  onTranscribeAudio?: (file: File) => Promise<string>;
  voiceInputDisabled?: boolean;
  onVoiceInputError?: (message: string) => void;
  maxHeight?: number;
}

type VoiceInputState = "idle" | "recording" | "transcribing";

function getPreferredRecordingMimeType(): string | null {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") {
    return null;
  }
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? null;
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
  compactLayout = false,
  enableVoiceInput = false,
  onTranscribeAudio,
  voiceInputDisabled = false,
  onVoiceInputError,
  maxHeight = 200,
}: RichInputFieldProps) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const valueRef = useRef(value);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const [voiceInputState, setVoiceInputState] = useState<VoiceInputState>("idle");

  valueRef.current = value;

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

  const cleanupMediaResources = useCallback(() => {
    mediaRecorderRef.current = null;
    audioChunksRef.current = [];
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  }, []);

  useEffect(() => () => cleanupMediaResources(), [cleanupMediaResources]);

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
  const canUseVoiceInput = enableVoiceInput && !!onTranscribeAudio;
  const hasDefaultAction = canUseVoiceInput || showStop || showSend;
  const showBottomRow = !!(topSlot || leftSlot || rightSlot || hasDefaultAction);
  const voiceControlDisabled = disabled || voiceInputDisabled || voiceInputState === "transcribing";

  const reportVoiceError = useCallback(
    (message: string) => {
      onVoiceInputError?.(message);
    },
    [onVoiceInputError],
  );

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  }, []);

  const startRecording = useCallback(async () => {
    if (!onTranscribeAudio) {
      return;
    }
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      reportVoiceError(t("chatbot.voiceInputUnavailable"));
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = getPreferredRecordingMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

      audioChunksRef.current = [];
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const recordedMimeType = recorder.mimeType || mimeType || "audio/webm";
        const audioBlob = new Blob(audioChunksRef.current, { type: recordedMimeType });
        cleanupMediaResources();
        setVoiceInputState("transcribing");

        void (async () => {
          try {
            const file = new File([audioBlob], `dictation${audioFileExtensionForMimeType(recordedMimeType)}`, {
              type: recordedMimeType,
            });
            const transcript = await onTranscribeAudio(file);
            onChange(appendVoiceTranscript(valueRef.current, transcript));
            requestAnimationFrame(() => resize());
          } catch (error) {
            const fallback = t("chatbot.voiceInputTranscriptionFailed");
            reportVoiceError(error instanceof Error && error.message ? error.message : fallback);
          } finally {
            setVoiceInputState("idle");
          }
        })();
      };

      recorder.start();
      setVoiceInputState("recording");
    } catch (error) {
      cleanupMediaResources();
      const key = error instanceof DOMException && error.name === "NotAllowedError"
        ? "chatbot.voiceInputPermissionDenied"
        : "chatbot.voiceInputStartFailed";
      reportVoiceError(t(key));
      setVoiceInputState("idle");
    }
  }, [cleanupMediaResources, onChange, onTranscribeAudio, reportVoiceError, t]);

  useEffect(() => {
    if (voiceInputState === "recording" && voiceInputDisabled) {
      stopRecording();
    }
  }, [stopRecording, voiceInputDisabled, voiceInputState]);

  const defaultActionSlot = (
    <div className={styles.actionGroup}>
      {canUseVoiceInput && (
        <button
          type="button"
          className={`${styles.sendBtn} ${styles.voiceBtn} ${
            voiceInputState === "recording"
              ? styles.voiceBtnRecording
              : voiceInputState === "transcribing"
                ? styles.voiceBtnBusy
                : styles.voiceBtnIdle
          }`}
          disabled={voiceControlDisabled && voiceInputState !== "recording"}
          onClick={voiceInputState === "recording" ? stopRecording : () => void startRecording()}
          aria-label={
            voiceInputState === "recording"
              ? t("chatbot.stopRecording")
              : voiceInputState === "transcribing"
                ? t("chatbot.transcribingAudio")
                : t("chatbot.recordAudio")
          }
        >
          {voiceInputState === "recording" ? (
            <span className={styles.stopIcon} aria-hidden />
          ) : (
            <span
              className={`material-symbols-outlined ${voiceInputState === "transcribing" ? styles.spinningIcon : ""}`}
              aria-hidden
            >
              {voiceInputState === "transcribing" ? "progress_activity" : "mic"}
            </span>
          )}
        </button>
      )}
      {showStop ? (
        <button type="button" className={styles.sendBtn} onClick={onInterrupt} aria-label={t("chatbot.stopResponse")}>
          <span className={styles.stopIcon} aria-hidden />
        </button>
      ) : showSend ? (
        <button type="button" className={styles.sendBtn} onClick={onSend} aria-label={t("chatbot.sendMessage")}>
          <span className="material-symbols-outlined" aria-hidden>
            arrow_upward
          </span>
        </button>
      ) : null}
    </div>
  );

  const actionSlot = rightSlot ? rightSlot : hasDefaultAction ? defaultActionSlot : null;

  return (
    <div className={styles.bar}>
      <div className={styles.field}>
        {aboveTextSlot && <div className={styles.aboveTextSlot}>{aboveTextSlot}</div>}
        {compactLayout ? (
          <div className={styles.inlineRow}>
            {leftSlot && <div className={styles.commandSlot}>{leftSlot}</div>}
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
            {actionSlot && <div className={styles.rightSlot}>{actionSlot}</div>}
          </div>
        ) : (
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
        )}

        {showBottomRow && !compactLayout && (
          <div className={styles.bottomRow}>
            {leftSlot && <div className={styles.commandSlot}>{leftSlot}</div>}
            {topSlot && <div className={styles.bottomLeft}>{topSlot}</div>}

            {actionSlot && <div className={styles.rightSlot}>{actionSlot}</div>}
          </div>
        )}
        {compactLayout && topSlot && (
          <div className={styles.bottomRow}>{<div className={styles.bottomLeft}>{topSlot}</div>}</div>
        )}
      </div>
    </div>
  );
}
