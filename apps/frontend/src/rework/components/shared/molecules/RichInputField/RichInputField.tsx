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

import { KeyboardEvent, ReactNode, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { CharacterLimitNotice } from "@shared/atoms/CharacterLimitNotice/CharacterLimitNotice";
import { appendVoiceTranscript, audioFileExtensionForMimeType } from "./voiceInputUtils";
import styles from "./RichInputField.module.css";
import { InlineSkillInput, type InlineSkillToken, type InlinePromptToken } from "./InlineSkillInput";

export type CommandKeyEvent = Pick<KeyboardEvent, "key" | "shiftKey" | "preventDefault"> & {
  nativeEvent: { isComposing: boolean };
};

// All three slots and the send button are optional so the component is usable
// as a plain auto-growing textarea, a search bar with filters, or a full
// chat input with context pickers and attachment chips.

/** Selection identity is part of the editor's undo history, alongside text. */
export type CommandChoice = { name: string; from: number; to: number; scope: number } & (
  | { kind: "skill" }
  | { kind: "prompt"; promptId: string; promptTeamId: string }
);

/** The host's side of the command trigger — see `commandTrigger`. */
export interface CommandTriggerBinding {
  /** The active command at the caret, with its replaceable range. */
  onQueryChange: (query: string | null, range?: { start: number; end: number }) => void;
  selectionRequest?: { id: number; caret: number };
  onDraftReplace?: () => void;
  choices?: readonly CommandChoice[];
  onChoicesRestore?: (choices: readonly CommandChoice[]) => void;
  /** Additional command names eligible for completion inside existing text. */
  inlineCommandNames?: readonly string[];
  /** Return true to consume the key: the field then neither sends nor types. */
  onKeyDown: (event: CommandKeyEvent) => boolean;
  /** The menu belongs to the focused field: it closes when focus leaves and
   *  comes back when focus returns, so it never floats over the thread. */
  onFocusChange: (focused: boolean) => void;
  /** Combobox wiring for the menu the host renders in `aboveFieldSlot`. */
  listboxId: string;
  open: boolean;
  activeDescendantId: string | null;
}

/**
 * The host supplies command names eligible at a whitespace
 * boundary near the caret; ordinary paths and slashes in prose stay plain text.
 */
export function commandQueryOf(
  value: string,
  caret = value.length,
  inlineCommandNames: readonly string[] = [],
): string | null {
  const beforeCaret = value.slice(0, caret);
  const match =
    /^\/(skill [a-z0-9-]*|\S*)$/.exec(value) ?? /(?:^|\s)\/(skill(?: [a-z0-9-]*)?|skil|ski|sk|s|)$/.exec(beforeCaret);
  if (match) return match[1];
  const named = /(?:^|\s)\/([a-z0-9_-]+)$/.exec(beforeCaret);
  return named && inlineCommandNames.some((name) => name.startsWith(named[1])) ? named[1] : null;
}

interface RichInputFieldProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  /** Called when the user clicks the stop button during streaming. */
  onInterrupt?: () => void;
  disabled?: boolean;
  /** Blocks sending (Enter + send button) while typing stays enabled — e.g. attachments still uploading. */
  sendDisabled?: boolean;
  /** Code-point count for the exact value the caller will submit. */
  characterCount?: number;
  /** Runtime-published code-point limit; omitted for older runtime pods. */
  characterLimit?: number;
  placeholder?: string;
  /**
   * Durable instruction for assistive technology. A placeholder is neither
   * reliably announced nor does it survive the first keystroke, so a hint the
   * user must be able to come back to belongs here as well.
   */
  accessibleDescription?: string;
  /** Rendered above the textarea — typically attachment chips that should stay close to the cursor. */
  aboveTextSlot?: ReactNode;
  /** Opt-in plain-text editor with inline skill and prompt visuals. */
  inlineSkills?: { tokens: InlineSkillToken[]; promptToken?: InlinePromptToken | null };
  /** Rendered floating just above the field — the command menu. */
  aboveFieldSlot?: ReactNode;
  /**
   * Opt-in command trigger. Absent — the default — a leading `/` is ordinary
   * text and the field behaves exactly as it always has.
   */
  commandTrigger?: CommandTriggerBinding;
  /** Rendered in the bottom-left area — context pickers, scope selectors, attachment chips. */
  topSlot?: ReactNode;
  /** Rendered next to the textarea controls — one compact command such as attach-file. */
  leftSlot?: ReactNode;
  /** Rendered to the right of the textarea — replaces the default send/stop buttons. */
  rightSlot?: ReactNode;
  /**
   * Rendered inside the right-side slot, just before the send/stop/mic action
   * group — a compact always-visible control such as the reasoning chip.
   * Unlike `rightSlot`, it composes with the default actions instead of
   * replacing them.
   */
  rightExtraSlot?: ReactNode;
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
  characterCount,
  characterLimit,
  placeholder,
  accessibleDescription,
  aboveTextSlot,
  inlineSkills,
  aboveFieldSlot,
  commandTrigger,
  topSlot,
  leftSlot,
  rightSlot,
  rightExtraSlot,
  showSendButton = false,
  enableVoiceInput = false,
  onTranscribeAudio,
  voiceInputDisabled = false,
  onVoiceInputError,
  maxHeight = 200,
  focusEndRequestId,
}: RichInputFieldProps) {
  const { t } = useTranslation();
  const characterInfoId = useId();
  const accessibleDescriptionId = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [commandSelection, setCommandSelection] = useState({ value, caret: value.length });
  const valueRef = useRef(value);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const [voiceInputState, setVoiceInputState] = useState<VoiceInputState>("idle");

  valueRef.current = value;

  // Reported from the value itself rather than from the keystroke, so a paste
  // or a programmatic insert is seen the same way. Through a ref so a host
  // that rebuilds the binding every render does not re-report on every render.
  const commandCaret = commandSelection.value === value ? commandSelection.caret : value.length;
  const commandQuery = commandTrigger ? commandQueryOf(value, commandCaret, commandTrigger.inlineCommandNames) : null;
  const commandEnd = commandQuery !== null && value === `/${commandQuery}` ? value.length : commandCaret;
  const onCommandQueryChangeRef = useRef(commandTrigger?.onQueryChange);
  onCommandQueryChangeRef.current = commandTrigger?.onQueryChange;
  const lastCommandQueryRef = useRef({ query: null as string | null, caret: -1 });
  useEffect(() => {
    if (
      lastCommandQueryRef.current.query === commandQuery &&
      (commandQuery === null || lastCommandQueryRef.current.caret === commandEnd)
    )
      return;
    lastCommandQueryRef.current = { query: commandQuery, caret: commandEnd };
    if (commandQuery === null) onCommandQueryChangeRef.current?.(null);
    else
      onCommandQueryChangeRef.current?.(commandQuery, {
        start: commandEnd - commandQuery.length - 1,
        end: commandEnd,
      });
  }, [commandQuery, commandEnd]);

  const selectionRequest = commandTrigger?.selectionRequest;
  const reportDraftReplacement = () => {
    const textarea = textareaRef.current;
    if (textarea && textarea.selectionStart === 0 && textarea.selectionEnd === value.length)
      commandTrigger?.onDraftReplace?.();
  };
  useLayoutEffect(() => {
    if (!selectionRequest || !textareaRef.current) return;
    const caret = Math.min(selectionRequest.caret, textareaRef.current.value.length);
    textareaRef.current.setSelectionRange(caret, caret);
    setCommandSelection({ value: textareaRef.current.value, caret });
  }, [selectionRequest]);

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
    (e: CommandKeyEvent) => {
      // The menu owns Enter, Tab, the arrows and Esc while it is open, and says
      // so by returning true — it has already called preventDefault. Enter is
      // withheld while sending is blocked: running a command IS sending, so it
      // must obey the same gate as the send button, and the menu has no reason
      // to know about uploads or an over-limit draft.
      const sendBlocked = disabled || sendDisabled;
      if (!(e.key === "Enter" && sendBlocked) && commandTrigger?.onKeyDown(e)) return;
      if (e.key === "Enter" && !e.shiftKey && !disabled && !sendDisabled && !e.nativeEvent.isComposing) {
        e.preventDefault();
        onSend();
      }
    },
    [disabled, sendDisabled, onSend, commandTrigger],
  );

  const hasText = value.trim().length > 0;
  const showStop = showSendButton && disabled && !!onInterrupt;
  const showSend = showSendButton && !disabled && hasText;
  const canUseVoiceInput = enableVoiceInput && !!onTranscribeAudio;
  const hasDefaultAction = canUseVoiceInput || showStop || showSend;
  const showBottomRow = !!(topSlot || leftSlot || rightSlot || hasDefaultAction);
  const voiceControlDisabled = disabled || voiceInputDisabled || voiceInputState === "transcribing";
  const hasCharacterLimit = characterLimit !== undefined && characterCount !== undefined;
  const isOverCharacterLimit = hasCharacterLimit && characterCount > characterLimit;
  const describedBy =
    [accessibleDescription ? accessibleDescriptionId : null, hasCharacterLimit ? characterInfoId : null]
      .filter(Boolean)
      .join(" ") || undefined;

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
        {aboveFieldSlot}
        {aboveTextSlot && <div className={styles.aboveTextSlot}>{aboveTextSlot}</div>}
        <div className={styles.textRow}>
          {inlineSkills ? (
            <InlineSkillInput
              value={value}
              onChange={onChange}
              tokens={inlineSkills.tokens}
              promptToken={inlineSkills.promptToken}
              placeholder={placeholder}
              disabled={disabled}
              maxHeight={maxHeight}
              describedBy={describedBy}
              invalid={isOverCharacterLimit}
              commandTrigger={commandTrigger}
              onKeyDown={handleKeyDown}
              onSelection={(caret, text) => setCommandSelection({ value: text, caret })}
              focusEndRequestId={focusEndRequestId}
            />
          ) : (
            <textarea
              ref={textareaRef}
              className={styles.textarea}
              value={value}
              rows={1}
              disabled={disabled}
              placeholder={placeholder}
              aria-invalid={isOverCharacterLimit || undefined}
              aria-describedby={describedBy}
              {...(commandTrigger
                ? {
                    role: "combobox",
                    "aria-autocomplete": "list" as const,
                    "aria-expanded": commandTrigger.open,
                    ...(commandTrigger.open ? { "aria-controls": commandTrigger.listboxId } : {}),
                    ...(commandTrigger.activeDescendantId
                      ? { "aria-activedescendant": commandTrigger.activeDescendantId }
                      : {}),
                  }
                : {})}
              onChange={(e) => {
                if (commandTrigger) setCommandSelection({ value: e.target.value, caret: e.target.selectionStart });
                onChange(e.target.value);
                resize();
              }}
              onKeyDown={handleKeyDown}
              onBeforeInput={reportDraftReplacement}
              onPaste={reportDraftReplacement}
              onSelect={
                commandTrigger
                  ? (e) => setCommandSelection({ value: e.currentTarget.value, caret: e.currentTarget.selectionStart })
                  : undefined
              }
              onFocus={
                commandTrigger
                  ? (e) => {
                      setCommandSelection({ value: e.currentTarget.value, caret: e.currentTarget.selectionStart });
                      commandTrigger.onFocusChange(true);
                    }
                  : undefined
              }
              onBlur={commandTrigger ? () => commandTrigger.onFocusChange(false) : undefined}
            />
          )}
        </div>

        {accessibleDescription && (
          <span id={accessibleDescriptionId} className={styles.accessibleDescription}>
            {accessibleDescription}
          </span>
        )}

        <CharacterLimitNotice
          id={characterInfoId}
          count={characterCount}
          limit={characterLimit}
          className={styles.characterInfo}
        />

        {showBottomRow && (
          <div className={styles.bottomRow}>
            {leftSlot && <div className={styles.commandSlot}>{leftSlot}</div>}
            {topSlot && <div className={styles.bottomLeft}>{topSlot}</div>}

            {(actionSlot || rightExtraSlot) && (
              <div className={styles.rightSlot}>
                {rightExtraSlot}
                {actionSlot}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
