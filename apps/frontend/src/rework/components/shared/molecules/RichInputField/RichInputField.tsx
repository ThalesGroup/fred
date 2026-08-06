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
import IconButton from "@shared/atoms/IconButton/IconButton";
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
  /** Blocks sending (Enter + send button) while typing stays enabled — e.g. attachments still uploading. */
  sendDisabled?: boolean;
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
  enableVoiceInput?: boolean;
  onTranscribeAudio?: (file: File) => Promise<string>;
  voiceInputDisabled?: boolean;
  onVoiceInputError?: (message: string) => void;
  maxHeight?: number;
  /**
   * Bump this (e.g. a counter) whenever the caller has just set `value`
   * programmatically (not from the user typing) and wants the field refocused
   * with the caret at the end — e.g. after inserting a library prompt. Ignored
   * on the initial render so mounting doesn't steal focus.
   */
  focusEndRequestId?: number;
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
  sendDisabled = false,
  placeholder,
  aboveTextSlot,
  topSlot,
  leftSlot,
  rightSlot,
  showSendButton = false,
  enableVoiceInput = false,
  onTranscribeAudio,
  voiceInputDisabled = false,
  onVoiceInputError,
  maxHeight = 200,
  focusEndRequestId,
}: RichInputFieldProps) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const valueRef = useRef(value);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const [voiceInputState, setVoiceInputState] = useState<VoiceInputState>("idle");

  valueRef.current = value;

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    const preCollapseScrollTop = el.scrollTop;
    el.style.height = "auto";
    const overflowing = el.scrollHeight > maxHeight;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    el.style.overflowY = overflowing ? "auto" : "hidden";
    // Collapsing to "auto" above shrinks the box for one tick; while it's
    // shrunk, the browser's native caret-follow can assign scrollTop a
    // nonzero value to keep the caret in view against that tiny transient
    // height. Restoring the real height never resets it, so a paste or long
    // line leaves the box permanently scrolled a few pixels down — with
    // overflow hidden that reads as the top of the text being clipped, not
    // scrollable. When everything fits there's nothing to scroll, so 0 is
    // always correct. When it overflows, forcing scrollHeight (the bottom)
    // on every keystroke fights the user editing earlier in the draft — restore
    // the scrollTop captured before the collapse instead, so the view only
    // moves when the browser's own caret-follow would have moved it anyway.
    el.scrollTop = overflowing ? preCollapseScrollTop : 0;
  }, [maxHeight]);

  // Keep the box in sync with external value changes (cleared draft after send,
  // a voice transcript, or a prompt inserted from the library): reset when empty,
  // otherwise grow to fit so inserted text isn't clipped at one row.
  useEffect(() => {
    if (!value) {
      const el = textareaRef.current;
      if (el) {
        el.style.height = "auto";
        el.style.overflowY = "hidden";
        el.scrollTop = 0;
      }
      return;
    }
    resize();
  }, [value, resize]);

  // Refocus with the caret at the end after a caller-driven insertion (e.g. a
  // library prompt). Skips the mount so mounting the field never steals focus;
  // relies on `value` having already been committed to the DOM by the time this
  // runs, since the caller updates both in the same render (React batches it).
  const lastFocusEndRequestId = useRef(focusEndRequestId);
  useEffect(() => {
    const previous = lastFocusEndRequestId.current;
    lastFocusEndRequestId.current = focusEndRequestId;
    if (focusEndRequestId === undefined || focusEndRequestId === previous) return;
    const el = textareaRef.current;
    if (!el) return;
    el.focus();
    const end = el.value.length;
    el.setSelectionRange(end, end);
  }, [focusEndRequestId]);

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
      if (e.key === "Enter" && !e.shiftKey && !disabled && !sendDisabled && !e.nativeEvent.isComposing) {
        e.preventDefault();
        onSend();
      }
    },
    [disabled, sendDisabled, onSend],
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
    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
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
      const key =
        error instanceof DOMException && error.name === "NotAllowedError"
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
      {canUseVoiceInput &&
        // Voice control — a plain icon button (default on-surface-retreat): mic
        // at rest, a filled stop while recording, and a spinner via `loading`
        // while the clip is being transcribed.
        (voiceInputState === "recording" ? (
          <IconButton
            variant="filled"
            color="error"
            size="small"
            icon={{ category: "outlined", type: "stop", filled: true }}
            onClick={stopRecording}
            aria-label={t("chatbot.stopRecording")}
          />
        ) : voiceInputState === "transcribing" ? (
          <IconButton
            variant="icon"
            size="small"
            loading
            icon={{ category: "outlined", type: "mic" }}
            aria-label={t("chatbot.transcribingAudio")}
          />
        ) : (
          <IconButton
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "mic" }}
            disabled={voiceControlDisabled}
            onClick={() => void startRecording()}
            aria-label={t("chatbot.recordAudio")}
          />
        ))}
      {showStop ? (
        <IconButton
          variant="filled"
          color="error"
          size="small"
          icon={{ category: "outlined", type: "stop", filled: true }}
          onClick={onInterrupt}
          aria-label={t("chatbot.stopResponse")}
        />
      ) : showSend ? (
        <IconButton
          variant="filled"
          color="primary"
          size="small"
          icon={{ category: "outlined", type: "arrow_upward" }}
          onClick={onSend}
          disabled={sendDisabled}
          aria-label={t("chatbot.sendMessage")}
        />
      ) : null}
    </div>
  );

  const actionSlot = rightSlot ? rightSlot : hasDefaultAction ? defaultActionSlot : null;

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

            {actionSlot && <div className={styles.rightSlot}>{actionSlot}</div>}
          </div>
        )}
      </div>
    </div>
  );
}
