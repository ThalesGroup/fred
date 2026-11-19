// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { json } from "@codemirror/lang-json";
import { foldGutter, foldKeymap, HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
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
  ".cm-scroller": { overflow: "auto", maxHeight: "34lh" },
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
});

export default function TraceJson({
  code,
  label,
  copyText = code,
}: {
  code: string;
  label: string;
  copyText?: string;
}) {
  const { t, i18n } = useTranslation();
  const host = useRef<HTMLDivElement>(null);
  const [copiedText, setCopiedText] = useState<string>();
  const foldLabel = t("rework.admin.conversationTraces.http.foldJson");
  const unfoldLabel = t("rework.admin.conversationTraces.http.unfoldJson");

  useEffect(() => {
    if (!host.current) return;
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
        ],
      }),
    });
    return () => view.destroy();
  }, [code, label, i18n.language, foldLabel, unfoldLabel]);

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
