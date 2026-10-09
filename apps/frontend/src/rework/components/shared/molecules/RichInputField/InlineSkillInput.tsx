// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0.

import { useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Annotation, Compartment, EditorState, StateEffect, StateField, Transaction, Prec } from "@codemirror/state";
import { defaultKeymap, history, historyKeymap, invertedEffects } from "@codemirror/commands";
import { Decoration, EditorView, keymap, placeholder, WidgetType } from "@codemirror/view";
import type { CommandChoice, CommandKeyEvent, CommandTriggerBinding } from "./RichInputField";
import badgeStyles from "../SkillBadge/SkillBadge.module.css";
import iconStyles from "../../atoms/Icon/Icon.module.scss";
import styles from "./InlineSkillInput.module.css";

export interface InlinePromptToken {
  from: number;
  to: number;
  name: string;
  description?: string | null;
  source?: "personal" | "team";
}

export interface InlineSkillToken {
  from: number;
  to: number;
  name: string;
  description?: string;
  onOpen: (name: string) => void;
}

class SkillWidget extends WidgetType {
  constructor(
    readonly token: InlineSkillToken,
    readonly hint: string,
    readonly label: string,
  ) {
    super();
  }
  eq(other: SkillWidget) {
    return (
      this.token.name === other.token.name &&
      this.hint === other.hint &&
      this.label === other.label &&
      this.token.onOpen === other.token.onOpen
    );
  }
  toDOM() {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `${badgeStyles.badge} ${badgeStyles.action}`;
    button.title = this.hint;
    button.setAttribute("aria-label", this.label);
    const icon = document.createElement("span");
    icon.className = `${iconStyles.icon} ${iconStyles.customIcon}`;
    icon.style.maskImage = "url(/images/icons/customPlatformSkill.svg)";
    icon.style.webkitMaskImage = icon.style.maskImage;
    icon.setAttribute("aria-hidden", "true");
    const name = document.createElement("span");
    name.className = badgeStyles.name;
    name.textContent = this.token.name;
    button.append(icon, name);
    button.onclick = () => this.token.onOpen(this.token.name);
    return button;
  }
  // The widget is deliberately not an atomic range. Deleting or editing one
  // underlying character makes the name incomplete and removes its import.
  ignoreEvent() {
    return true;
  }
}

class PromptWidget extends WidgetType {
  constructor(
    readonly command: string,
    readonly hint: string,
  ) {
    super();
  }
  eq(other: PromptWidget) {
    return this.command === other.command && this.hint === other.hint;
  }
  toDOM() {
    const token = document.createElement("span");
    token.className = `${badgeStyles.badge} ${styles.promptToken}`;
    token.title = this.hint;
    token.setAttribute("role", "group");
    token.setAttribute("aria-label", this.hint);
    const icon = document.createElement("span");
    icon.className = `material-symbols-outlined ${iconStyles.icon}`;
    icon.textContent = "edit_note";
    icon.setAttribute("aria-hidden", "true");
    const name = document.createElement("span");
    name.className = badgeStyles.name;
    name.textContent = this.command.slice(1);
    token.append(icon, name);
    return token;
  }
  ignoreEvent() {
    return false;
  }
}

const rememberChoices = StateEffect.define<readonly CommandChoice[]>({
  map: (choices, changes) =>
    choices.map((choice) => ({ ...choice, from: changes.mapPos(choice.from), to: changes.mapPos(choice.to) })),
});
const choiceHistory = StateField.define<readonly CommandChoice[]>({
  create: () => [],
  update: (choices, transaction) => {
    for (const effect of transaction.effects) if (effect.is(rememberChoices)) choices = effect.value;
    return choices;
  },
});

const externalSync = Annotation.define<boolean>();

interface Props {
  value: string;
  onChange: (value: string) => void;
  tokens: InlineSkillToken[];
  promptToken?: InlinePromptToken | null;
  placeholder?: string;
  disabled: boolean;
  maxHeight: number;
  describedBy?: string;
  invalid: boolean;
  commandTrigger?: CommandTriggerBinding;
  onKeyDown: (event: CommandKeyEvent) => void;
  onSelection: (caret: number, value: string) => void;
  focusEndRequestId?: number;
}

export function InlineSkillInput(props: Props) {
  const { t } = useTranslation();
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const propsRef = useRef(props);
  propsRef.current = props;
  const configuration = useRef(new Compartment());

  useLayoutEffect(() => {
    if (!hostRef.current) return;
    const view = new EditorView({
      parent: hostRef.current,
      state: EditorState.create({
        doc: propsRef.current.value,
        extensions: [
          history(),
          choiceHistory,
          invertedEffects.of((transaction) =>
            transaction.docChanged ? [rememberChoices.of(transaction.startState.field(choiceHistory))] : [],
          ),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          EditorView.lineWrapping,
          configuration.current.of([]),
          Prec.highest(
            EditorView.domEventHandlers({
              keydown(event) {
                propsRef.current.onKeyDown({
                  key: event.key,
                  shiftKey: event.shiftKey,
                  nativeEvent: event,
                  preventDefault: () => event.preventDefault(),
                });
                return event.defaultPrevented;
              },
              beforeinput(_event, view) {
                const { from, to } = view.state.selection.main;
                if (from === 0 && to === view.state.doc.length && to > 0)
                  propsRef.current.commandTrigger?.onDraftReplace?.();
              },
              paste(_event, view) {
                const { from, to } = view.state.selection.main;
                if (from === 0 && to === view.state.doc.length && to > 0)
                  propsRef.current.commandTrigger?.onDraftReplace?.();
              },
              focus() {
                propsRef.current.commandTrigger?.onFocusChange(true);
              },
              blur(event) {
                // Clicking a token stays within the composer; only actual focus
                // departure dismisses its completion menu.
                if (!hostRef.current?.contains(event.relatedTarget as Node | null))
                  propsRef.current.commandTrigger?.onFocusChange(false);
              },
            }),
          ),
          EditorView.updateListener.of((update) => {
            if (update.docChanged && !update.transactions.some((tr) => tr.annotation(externalSync))) {
              if (update.transactions.some((tr) => tr.isUserEvent("undo") || tr.isUserEvent("redo")))
                propsRef.current.commandTrigger?.onChoicesRestore?.(update.state.field(choiceHistory));
              propsRef.current.onChange(update.state.doc.toString());
            }
            if (update.docChanged || update.selectionSet)
              propsRef.current.onSelection(update.state.selection.main.head, update.state.doc.toString());
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, []);

  const choicesKey = JSON.stringify(props.commandTrigger?.choices ?? []);
  const tokenKey = JSON.stringify(
    props.tokens.map(({ from, to, name, description }) => ({ from, to, name, description })),
  );
  const callbacksRef = useRef<InlineSkillToken["onOpen"][]>([]);
  if (
    props.tokens.length !== callbacksRef.current.length ||
    props.tokens.some((token, index) => token.onOpen !== callbacksRef.current[index])
  )
    callbacksRef.current = props.tokens.map((token) => token.onOpen);
  const tokenCallbacks = callbacksRef.current;
  const promptFrom = props.promptToken?.from;
  const promptTo = props.promptToken?.to;
  const promptName = props.promptToken?.name;
  const promptDescription = props.promptToken?.description;
  const promptSource = props.promptToken?.source;
  const hasTrigger = Boolean(props.commandTrigger);
  const triggerOpen = props.commandTrigger?.open;
  const triggerListboxId = props.commandTrigger?.listboxId;
  const triggerActiveDescendantId = props.commandTrigger?.activeDescendantId;

  useLayoutEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current !== props.value) {
      // Adopt external edits without dropping the selection on typed updates.
      view.dispatch({
        changes: { from: 0, to: current.length, insert: props.value },
        selection: { anchor: Math.min(view.state.selection.main.head, props.value.length) },
        annotations: externalSync.of(true),
      });
    }
    const decorations = Decoration.set(
      [
        ...(promptFrom !== undefined && promptTo !== undefined && promptName !== undefined
          ? [
              Decoration.replace({
                widget: new PromptWidget(
                  props.value.slice(promptFrom, promptTo),
                  [
                    promptName,
                    promptSource ? t(`chatbot.commandMenu.sources.${promptSource}`) : "",
                    promptDescription?.trim(),
                  ]
                    .filter(Boolean)
                    .join("\n"),
                ),
              }).range(promptFrom, promptTo),
            ]
          : []),
        ...props.tokens.flatMap((token) => [
          Decoration.replace({
            widget: new SkillWidget(
              token,
              [t("chatbot.skills.platformProvided"), token.description?.trim()].filter(Boolean).join("\n"),
              t("chatbot.skills.open", { name: token.name }),
            ),
          }).range(token.from, token.to),
          ...(props.tokens.length === 1 && props.value.trim() === `/${token.name}` && props.placeholder
            ? [Decoration.widget({ widget: new HintWidget(props.placeholder), side: 1 }).range(props.value.length)]
            : []),
        ]),
      ],
      true,
    );
    view.dispatch({
      annotations: Transaction.addToHistory.of(false),
      effects: [
        rememberChoices.of(props.commandTrigger?.choices ?? []),
        configuration.current.reconfigure([
          EditorView.editable.of(!props.disabled),
          EditorState.readOnly.of(props.disabled),
          EditorView.decorations.of(decorations),
          props.placeholder ? placeholder(props.placeholder) : [],
          EditorView.contentAttributes.of({
            spellcheck: "true",
            "aria-label": t("chatbot.composerPlaceholder"),
            "aria-invalid": String(props.invalid),
            ...(props.describedBy ? { "aria-describedby": props.describedBy } : {}),
            ...(hasTrigger
              ? {
                  role: "combobox",
                  "aria-autocomplete": "list",
                  "aria-expanded": String(triggerOpen),
                  ...(triggerOpen ? { "aria-controls": triggerListboxId! } : {}),
                  ...(triggerActiveDescendantId ? { "aria-activedescendant": triggerActiveDescendantId } : {}),
                }
              : { role: "textbox", "aria-multiline": "true" }),
          }),
        ]),
      ],
    });
  }, [
    props.value,
    tokenKey,
    choicesKey,
    tokenCallbacks,
    promptFrom,
    promptTo,
    promptName,
    promptDescription,
    promptSource,
    props.placeholder,
    props.disabled,
    props.invalid,
    props.describedBy,
    hasTrigger,
    triggerOpen,
    triggerListboxId,
    triggerActiveDescendantId,
    t,
  ]);

  const selectionRequest = props.commandTrigger?.selectionRequest;
  useLayoutEffect(() => {
    const view = viewRef.current;
    if (view && selectionRequest) {
      const caret = Math.min(selectionRequest.caret, view.state.doc.length);
      view.dispatch({ selection: { anchor: caret }, scrollIntoView: true });
      view.focus();
    }
  }, [selectionRequest]);

  const lastFocusRequest = useRef(props.focusEndRequestId);
  useLayoutEffect(() => {
    const previous = lastFocusRequest.current;
    lastFocusRequest.current = props.focusEndRequestId;
    if (props.focusEndRequestId === undefined || previous === props.focusEndRequestId) return;
    const view = viewRef.current;
    view?.dispatch({ selection: { anchor: view.state.doc.length }, scrollIntoView: true });
    view?.focus();
  }, [props.focusEndRequestId]);
  useLayoutEffect(() => {
    if (!props.disabled) viewRef.current?.focus();
  }, [props.disabled]);

  return (
    <div
      ref={hostRef}
      className={styles.editor}
      aria-disabled={props.disabled}
      style={{ maxHeight: props.maxHeight }}
    />
  );
}

class HintWidget extends WidgetType {
  constructor(readonly text: string) {
    super();
  }
  eq(other: HintWidget) {
    return this.text === other.text;
  }
  toDOM() {
    const hint = document.createElement("span");
    hint.className = styles.hint;
    hint.setAttribute("aria-hidden", "true");
    hint.textContent = this.text;
    return hint;
  }
}
