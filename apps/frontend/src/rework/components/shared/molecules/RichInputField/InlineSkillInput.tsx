// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0.

import { useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Annotation, Compartment, EditorState, StateEffect, StateField, Transaction, Prec } from "@codemirror/state";
import { defaultKeymap, history, historyKeymap, invertedEffects } from "@codemirror/commands";
import { Decoration, EditorView, keymap, WidgetType } from "@codemirror/view";
import type { CommandChoice, CommandKeyEvent, CommandTriggerBinding, DraftEdit } from "./RichInputField";
import { skillPresentation } from "@rework/utils/skillPresentation";
import badgeStyles from "../SkillBadge/SkillBadge.module.css";
import iconStyles from "../../atoms/Icon/Icon.module.scss";
import styles from "./InlineSkillInput.module.css";

export interface InlinePromptToken {
  from: number;
  to: number;
  name: string;
  /** The prompt behind the token and the library it was picked from. */
  promptId: string;
  promptTeamId: string;
  description?: string | null;
  source?: "personal" | "team";
  /** Name of the conversation's team, for the hover hint of a team prompt. */
  teamName?: string;
}

/** What an activated prompt token hands to its opener. No position: a widget
 *  outlives the edits made before it. */
export type InlinePromptTarget = Pick<InlinePromptToken, "promptId" | "promptTeamId" | "name"> & { command: string };

export interface InlineSkillToken {
  from: number;
  to: number;
  name: string;
  description?: string;
  builtin?: boolean;
  onOpen: (name: string) => void;
}

class SkillWidget extends WidgetType {
  constructor(
    readonly token: InlineSkillToken,
    readonly hint: string,
    readonly label: string,
    readonly title: string,
  ) {
    super();
  }
  eq(other: SkillWidget) {
    return (
      this.token.name === other.token.name &&
      this.hint === other.hint &&
      this.label === other.label &&
      this.title === other.title &&
      this.token.onOpen === other.token.onOpen
    );
  }
  toDOM() {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `${badgeStyles.badge} ${badgeStyles.action}`;
    button.dataset.kind = "skill";
    button.title = this.hint;
    button.setAttribute("aria-label", this.label);
    const icon = document.createElement("span");
    icon.className = `${iconStyles.icon} ${iconStyles.customIcon}`;
    icon.style.maskImage = "url(/images/icons/customPlatformSkill.svg)";
    icon.style.webkitMaskImage = icon.style.maskImage;
    icon.setAttribute("aria-hidden", "true");
    const name = document.createElement("span");
    name.className = badgeStyles.name;
    name.textContent = this.title === this.token.name ? `/${this.token.name}` : this.title;
    button.append(icon, name);
    button.onclick = () => this.token.onOpen(this.token.name);
    return button;
  }
  ignoreEvent() {
    return true;
  }
}

class PromptWidget extends WidgetType {
  constructor(
    readonly target: InlinePromptTarget,
    readonly hint: string,
    readonly label: string,
    readonly onOpen?: (target: InlinePromptTarget) => void,
  ) {
    super();
  }
  // The opener is one callback for every token, so a keystroke rebuilds none.
  eq(other: PromptWidget) {
    return (
      this.target.command === other.target.command &&
      this.target.promptId === other.target.promptId &&
      this.target.promptTeamId === other.target.promptTeamId &&
      this.hint === other.hint &&
      this.label === other.label &&
      this.onOpen === other.onOpen
    );
  }
  toDOM() {
    // A button when it can open its preview, like the skill token.
    const token = document.createElement(this.onOpen ? "button" : "span");
    token.className = badgeStyles.badge;
    token.dataset.kind = "prompt";
    token.title = this.hint;
    if (token instanceof HTMLButtonElement) {
      token.type = "button";
      token.classList.add(badgeStyles.action);
      token.setAttribute("aria-label", this.label);
      token.onclick = () => this.onOpen?.(this.target);
    } else {
      token.setAttribute("role", "group");
      token.setAttribute("aria-label", this.hint);
    }
    const icon = document.createElement("span");
    icon.className = `material-symbols-outlined ${iconStyles.icon}`;
    icon.textContent = "edit_note";
    icon.setAttribute("aria-hidden", "true");
    const name = document.createElement("span");
    name.className = badgeStyles.name;
    name.textContent = `/${this.target.command}`;
    token.append(icon, name);
    return token;
  }
  ignoreEvent() {
    return Boolean(this.onOpen);
  }
}

type TokenRange = { from: number; to: number };

// Removes the token the caret touches as one block. The space after it goes
// too when one already precedes it, so no double or leading space is left.
function deleteToken(view: EditorView, tokens: readonly TokenRange[], forward: boolean): boolean {
  const { main } = view.state.selection;
  const token = main.empty && tokens.find((range) => (forward ? range.from : range.to) === main.head);
  if (!token || view.state.sliceDoc(token.from, token.from + 1) !== "/") return false;
  const before = token.from === 0 ? "\n" : view.state.sliceDoc(token.from - 1, token.from);
  const spaceAfter = view.state.sliceDoc(token.to, token.to + 1) === " " && /\s/.test(before);
  view.dispatch({
    changes: { from: token.from, to: token.to + (spaceAfter ? 1 : 0) },
    selection: { anchor: token.from },
    userEvent: forward ? "delete.forward" : "delete.backward",
    scrollIntoView: true,
  });
  return true;
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
  promptTokens?: readonly InlinePromptToken[];
  /** Opens a prompt token's preview; without it the tokens are not clickable.
   *  Keep one identity across renders. */
  onOpenPrompt?: (target: InlinePromptTarget) => void;
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
  const tokenRangesRef = useRef<readonly TokenRange[]>([]);

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
          keymap.of([
            { key: "Backspace", run: (view) => deleteToken(view, tokenRangesRef.current, false) },
            { key: "Delete", run: (view) => deleteToken(view, tokenRangesRef.current, true) },
            ...defaultKeymap,
            ...historyKeymap,
          ]),
          EditorView.lineWrapping,
          configuration.current.of([]),
          Prec.highest(
            EditorView.domEventHandlers({
              keydown(event) {
                propsRef.current.onKeyDown({
                  key: event.key,
                  shiftKey: event.shiftKey,
                  ctrlKey: event.ctrlKey,
                  altKey: event.altKey,
                  metaKey: event.metaKey,
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
              const edits: DraftEdit[] = [];
              update.changes.iterChanges((from, to, _fromB, _toB, inserted) =>
                edits.push({ from, to, insert: inserted.length }),
              );
              propsRef.current.commandTrigger?.onDraftEdit?.(edits);
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
    props.tokens.map(({ from, to, name, description, builtin }) => ({ from, to, name, description, builtin })),
  );
  const callbacksRef = useRef<InlineSkillToken["onOpen"][]>([]);
  if (
    props.tokens.length !== callbacksRef.current.length ||
    props.tokens.some((token, index) => token.onOpen !== callbacksRef.current[index])
  )
    callbacksRef.current = props.tokens.map((token) => token.onOpen);
  const tokenCallbacks = callbacksRef.current;
  const promptKey = JSON.stringify(
    (props.promptTokens ?? []).map((token) => [
      token.from,
      token.to,
      token.name,
      token.promptId,
      token.promptTeamId,
      token.description,
      token.source,
      token.teamName,
    ]),
  );
  const onOpenPrompt = props.onOpenPrompt;
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
    // Tokens are atomic: the caret, a selection and a deletion take one as a
    // whole instead of stepping through the `/name` hidden under it.
    const promptTokens = props.promptTokens ?? [];
    tokenRangesRef.current = [...promptTokens, ...props.tokens].map(({ from, to }) => ({ from, to }));
    const atomic = Decoration.set(
      tokenRangesRef.current.map(({ from, to }) => Decoration.mark({}).range(from, to)),
      true,
    );
    const decorations = Decoration.set(
      [
        ...promptTokens.map((token) => {
          const command = props.value.slice(token.from + 1, token.to);
          return Decoration.replace({
            widget: new PromptWidget(
              { promptId: token.promptId, promptTeamId: token.promptTeamId, name: token.name, command },
              // The source reads like the heading of its section in the menu.
              [
                token.name,
                token.source === "personal"
                  ? t("chatbot.commandMenu.sections.personal")
                  : token.source === "team"
                    ? token.teamName
                      ? t("chatbot.commandMenu.sections.team", { name: token.teamName })
                      : t("chatbot.commandMenu.sections.teamFallback")
                    : "",
                token.description?.trim(),
              ]
                .filter(Boolean)
                .join("\n"),
              t("chatbot.commandTurn.open", { command }),
              onOpenPrompt,
            ),
          }).range(token.from, token.to);
        }),
        ...props.tokens.flatMap((token) => [
          Decoration.replace({
            widget: new SkillWidget(
              token,
              [
                t("chatbot.skills.platformProvided"),
                token.builtin ? `/${token.name}` : null,
                skillPresentation(t, token).description.trim(),
              ]
                .filter(Boolean)
                .join("\n"),
              t("chatbot.skills.open", { name: skillPresentation(t, token).title }),
              skillPresentation(t, token).title,
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
          EditorView.atomicRanges.of(() => atomic),
          EditorView.contentAttributes.of({
            spellcheck: "true",
            ...(props.placeholder ? { "aria-placeholder": props.placeholder } : {}),
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
    promptKey,
    onOpenPrompt,
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

  // The placeholder lives outside the editable line, which then holds nothing
  // the native caret could be drawn against or sized from.
  return (
    <div className={styles.field}>
      {props.placeholder && props.value === "" && (
        <span className={styles.placeholder} aria-hidden="true">
          {props.placeholder}
        </span>
      )}
      <div
        ref={hostRef}
        className={styles.editor}
        aria-disabled={props.disabled}
        style={{ maxHeight: props.maxHeight }}
      />
    </div>
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
