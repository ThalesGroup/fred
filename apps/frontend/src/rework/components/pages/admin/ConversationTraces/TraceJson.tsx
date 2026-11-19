// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { json, jsonLanguage } from "@codemirror/lang-json";
import { foldEffect, foldGutter, foldKeymap, HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import { Decoration, EditorView, keymap, lineNumbers, ViewPlugin, type ViewUpdate } from "@codemirror/view";
import { tags } from "@lezer/highlight";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import Button from "@shared/atoms/Button/Button.tsx";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./ConversationTraces.module.css";

const traceSyntax = HighlightStyle.define([
  { tag: tags.propertyName, color: "var(--primary)" },
  { tag: tags.string, color: "var(--success)" },
  { tag: tags.number, color: "var(--tertiary)" },
  { tag: [tags.bool, tags.null], color: "var(--error)" },
]);

const traceEditorTheme = EditorView.theme({
  "&": {
    fontSize: "0.8125rem",
    color: "var(--on-surface)",
    background: "var(--surface-container-low)",
  },
  ".cm-scroller": { overflow: "auto", maxHeight: "32lh" },
  ".cm-content": { padding: "var(--spacing-xs) 0" },
  ".cm-gutters": {
    color: "var(--on-surface-retreat)",
    background: "var(--surface-container-low)",
    borderColor: "var(--outline-muted)",
  },
  ".cm-foldGutter .cm-gutterElement, .cm-foldPlaceholder": { cursor: "pointer" },
  ".cm-foldPlaceholder": {
    color: "var(--primary)",
    background: "var(--surface-container)",
    borderColor: "var(--outline-variant)",
  },
  ".cm-line.trace-message-even": { background: "var(--surface-main)" },
  ".cm-line.trace-message-odd": { background: "var(--surface-container)" },
});

function modelRequestLayout(code: string) {
  const root = jsonLanguage.parser.parse(code).topNode.getChild("Object");
  const properties = root?.getChildren("Property") ?? [];
  const valueOf = (key: string, type: string) =>
    properties
      .find((property) => {
        const name = property.getChild("PropertyName");
        return name && code.slice(name.from, name.to) === JSON.stringify(key);
      })
      ?.getChild(type);
  const tools = valueOf("tools", "Array") ?? valueOf("tools", "Object");
  const messages = valueOf("messages", "Array")?.getChildren("Object") ?? [];
  const bands = ["trace-message-even", "trace-message-odd"].map((className) => Decoration.line({ class: className }));

  function visibleBands(view: EditorView) {
    const { doc } = view.state;
    const first = doc.lineAt(view.viewport.from).number;
    const last = doc.lineAt(view.viewport.to).number;
    return Decoration.set(
      messages.flatMap((message, index) => {
        if (message.to <= view.viewport.from || message.from > view.viewport.to) return [];
        const start = Math.max(first, doc.lineAt(message.from).number);
        const end = Math.min(last, doc.lineAt(message.to - 1).number);
        return Array.from({ length: end - start + 1 }, (_, offset) =>
          bands[index % bands.length].range(doc.line(start + offset).from),
        );
      }),
      true,
    );
  }

  const messageBands = ViewPlugin.fromClass(
    class {
      decorations;

      constructor(view: EditorView) {
        this.decorations = visibleBands(view);
      }

      update(update: ViewUpdate) {
        if (update.viewportChanged) this.decorations = visibleBands(update.view);
      }
    },
    { decorations: (plugin) => plugin.decorations },
  );
  return { tools, messageBands };
}

export default function TraceJson({
  code,
  label,
  copyText = code,
  modelRequest = false,
}: {
  code: string;
  label: string;
  copyText?: string;
  modelRequest?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const host = useRef<HTMLDivElement>(null);
  const [copiedText, setCopiedText] = useState<string>();
  const foldLabel = t("rework.admin.conversationTraces.http.foldJson");
  const unfoldLabel = t("rework.admin.conversationTraces.http.unfoldJson");

  useEffect(() => {
    if (!host.current) return;
    const layout = modelRequest ? modelRequestLayout(code) : undefined;
    const view = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: code,
        extensions: [
          json(),
          lineNumbers(),
          foldGutter({ openText: "▾", closedText: "▸" }),
          keymap.of(foldKeymap),
          EditorState.phrases.of({ "Fold line": foldLabel, "Unfold line": unfoldLabel, unfold: unfoldLabel }),
          EditorState.readOnly.of(true),
          EditorView.editable.of(false),
          EditorView.contentAttributes.of({
            tabindex: "0",
            "aria-label": label,
            "aria-readonly": "true",
            lang: i18n.language,
          }),
          syntaxHighlighting(traceSyntax),
          traceEditorTheme,
          layout?.messageBands ?? [],
        ],
      }),
    });
    const tools = layout?.tools;
    if (tools && tools.to - tools.from > 2) {
      view.dispatch({ effects: foldEffect.of({ from: tools.from + 1, to: tools.to - 1 }) });
    }
    return () => view.destroy();
  }, [code, label, i18n.language, foldLabel, unfoldLabel, modelRequest]);

  return (
    <div className={styles.traceJson}>
      <div className={styles.jsonToolbar}>
        <span>JSON</span>
        <Button
          type="button"
          size="2xs"
          variant="text"
          color="on-surface"
          aria-label={t("common.copyCode")}
          onClick={async () => {
            if (await writeRichClipboard("", copyText)) setCopiedText(copyText);
          }}
        >
          {copiedText === copyText ? t("common.copied") : t("common.copy")}
        </Button>
      </div>
      <div ref={host} />
    </div>
  );
}
