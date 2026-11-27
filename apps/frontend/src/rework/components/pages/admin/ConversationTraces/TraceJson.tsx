// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { json, jsonLanguage } from "@codemirror/lang-json";
import { foldEffect, foldGutter, foldKeymap, HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { Compartment, EditorState } from "@codemirror/state";
import { Decoration, EditorView, keymap, lineNumbers, ViewPlugin, WidgetType, type ViewUpdate } from "@codemirror/view";
import { tags } from "@lezer/highlight";
import type { SyntaxNode } from "@lezer/common";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import Button from "@shared/atoms/Button/Button.tsx";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TraceMaskedField } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
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
  ".cm-scroller": { overflow: "auto", maxHeight: "var(--trace-code-max-height, 32lh)" },
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
  ".cm-line.trace-message-even": {
    background: "color-mix(in srgb, var(--info) 18%, var(--surface-container-low))",
    boxShadow: "inset 2px 0 var(--info)",
  },
  ".cm-line.trace-message-odd": {
    background: "color-mix(in srgb, var(--warning) 18%, var(--surface-container-low))",
    boxShadow: "inset 2px 0 var(--warning)",
  },
});

class MaskedFieldWidget extends WidgetType {
  constructor(
    readonly text: string,
    readonly indent: number,
  ) {
    super();
  }

  eq(other: MaskedFieldWidget) {
    return this.text === other.text && this.indent === other.indent;
  }

  toDOM() {
    const widget = document.createElement("div");
    widget.className = styles.jsonAnnotation;
    widget.textContent = this.text;
    widget.style.paddingInlineStart = this.indent + "ch";
    widget.contentEditable = "false";
    return widget;
  }
}

function jsonProperty(node: SyntaxNode | null, code: string, key: string) {
  const quoted = JSON.stringify(key);
  return node?.getChildren("Property").find((property) => {
    const name = property.getChild("PropertyName");
    return name && code.slice(name.from, name.to) === quoted;
  });
}

function annotationLayout(
  view: EditorView,
  code: string,
  annotations: TraceMaskedField[],
  label: (field: TraceMaskedField) => string,
) {
  const root = jsonLanguage.parser.parse(code).topNode.firstChild;
  const elementNames = new Set(["Array", "Object", "String", "Number", "True", "False", "Null"]);
  function child(node: SyntaxNode, key: string | number) {
    if (typeof key === "string") {
      return jsonProperty(node, code, key)?.lastChild;
    }
    let index = 0;
    for (let item = node.firstChild; item; item = item.nextSibling) {
      if (elementNames.has(item.name) && index++ === key) return item;
    }
    return null;
  }
  return Decoration.set(
    annotations.flatMap((field) => {
      const parent = field.parent.reduce<SyntaxNode | null>(
        (node, key) => (node ? (child(node, key) ?? null) : null),
        root,
      );
      if (!parent || parent.name !== "Object") return [];
      const next = parent.getChildren("Property")[field.position];
      const offset = next?.from ?? parent.to - 1;
      const line = view.state.doc.lineAt(offset);
      const indent = (line.text.match(/^ */)?.[0].length ?? 0) + (next ? 0 : 2);
      // Empty objects occupy one line. Place their annotations after the line.
      const after = !next && line.number === view.state.doc.lineAt(parent.from).number;
      return [
        Decoration.widget({
          widget: new MaskedFieldWidget(label(field), indent),
          block: true,
          side: after ? 1 : -1,
        }).range(after ? line.to : line.from),
      ];
    }),
    true,
  );
}

function modelRequestLayout(code: string, modelRequest: true | "input") {
  const root = jsonLanguage.parser.parse(code).topNode.getChild("Object");
  const request = modelRequest === "input" ? (jsonProperty(root, code, "input")?.getChild("Object") ?? null) : root;
  const toolsProperty = jsonProperty(request, code, "tools");
  const tools = toolsProperty?.getChild("Array") ?? toolsProperty?.getChild("Object");
  const messages = jsonProperty(request, code, "messages")?.getChild("Array")?.getChildren("Object") ?? [];
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
  annotations,
}: {
  code: string;
  label: string;
  copyText?: string;
  modelRequest?: boolean | "input";
  annotations?: TraceMaskedField[];
}) {
  const { t, i18n } = useTranslation();
  const host = useRef<HTMLDivElement>(null);
  const editor = useRef<EditorView | null>(null);
  const [annotationLayer] = useState(() => new Compartment());
  const [showAnnotations, setShowAnnotations] = useState(true);
  const [copiedText, setCopiedText] = useState<string>();
  const foldLabel = t("rework.admin.conversationTraces.http.foldJson");
  const unfoldLabel = t("rework.admin.conversationTraces.http.unfoldJson");

  useEffect(() => {
    if (!host.current) return;
    const layout = modelRequest ? modelRequestLayout(code, modelRequest) : undefined;
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
          annotationLayer.of([]),
        ],
      }),
    });
    const tools = layout?.tools;
    if (tools && tools.to - tools.from > 2) {
      view.dispatch({ effects: foldEffect.of({ from: tools.from + 1, to: tools.to - 1 }) });
    }
    editor.current = view;
    return () => {
      editor.current = null;
      view.destroy();
    };
  }, [code, label, i18n.language, foldLabel, unfoldLabel, modelRequest, annotationLayer]);

  useEffect(() => {
    const view = editor.current;
    if (!view) return;
    const extension =
      showAnnotations && annotations?.length
        ? EditorView.decorations.of(
            annotationLayout(view, code, annotations, (field) =>
              t(
                `rework.admin.conversationTraces.masking.${
                  field.invalid_json == null ? "field" : field.invalid_json ? "invalidArguments" : "validArguments"
                }`,
                {
                  field: field.key,
                  type: t(`rework.admin.conversationTraces.masking.types.${field.value_type}`),
                },
              ),
            ),
          )
        : [];
    view.dispatch({ effects: annotationLayer.reconfigure(extension) });
  }, [
    annotations,
    annotationLayer,
    code,
    foldLabel,
    i18n.language,
    label,
    modelRequest,
    showAnnotations,
    t,
    unfoldLabel,
  ]);

  return (
    <div className={styles.traceJson}>
      <div className={styles.jsonToolbar}>
        <span>JSON</span>
        {!!annotations?.length && (
          <label className={styles.annotationToggle}>
            <input
              type="checkbox"
              checked={showAnnotations}
              onChange={(event) => setShowAnnotations(event.target.checked)}
            />
            {t("rework.admin.conversationTraces.masking.toggle")}
          </label>
        )}
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
