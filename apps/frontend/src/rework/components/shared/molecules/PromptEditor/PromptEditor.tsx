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

// PromptEditor — the editing surface for anything an LLM reads as a prompt.
//
// CodeMirror in markdown mode, which also colours inline HTML/XML tags, so the
// same editor serves markdown prompts and tag-structured ones (Mistral). Plain
// text in, plain text out: no AST round-trip, so what the author typed is what
// the model receives, byte for byte. Chrome mirrors the TextArea atom so it does
// not look foreign next to the other fields of a form.

import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { Annotation, Compartment, EditorState, Transaction } from "@codemirror/state";
import { EditorView, keymap, placeholder as placeholderExtension } from "@codemirror/view";
import { tags } from "@lezer/highlight";
import { type CSSProperties, useEffect, useId, useRef } from "react";
import styles from "./PromptEditor.module.css";

export interface PromptEditorProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  /** Visible height in lines before the editor scrolls. */
  rows?: number;
}

// Marks a document change this component made to adopt an incoming `value`, so
// it is not echoed back to the parent as if the user had typed it.
const externalSync = Annotation.define<boolean>();

// Tags map to class names rather than colours: the palette then lives in the
// stylesheet, on semantic tokens, and follows the theme with no JS branch.
const promptHighlighting = HighlightStyle.define([
  { tag: tags.heading, class: styles.heading },
  { tag: tags.strong, class: styles.strong },
  { tag: tags.emphasis, class: styles.emphasis },
  { tag: tags.link, class: styles.link },
  { tag: tags.url, class: styles.link },
  { tag: tags.monospace, class: styles.code },
  { tag: tags.quote, class: styles.quote },
  { tag: [tags.tagName, tags.angleBracket], class: styles.tag },
  { tag: tags.attributeName, class: styles.attribute },
  { tag: [tags.attributeValue, tags.string], class: styles.value },
  { tag: [tags.list, tags.processingInstruction], class: styles.marker },
  { tag: tags.comment, class: styles.comment },
]);

export function PromptEditor({
  label,
  value,
  onChange,
  placeholder,
  disabled = false,
  required = false,
  error,
  rows = 12,
}: PromptEditorProps) {
  const labelId = useId();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const editableRef = useRef(new Compartment());
  const placeholderRef = useRef(new Compartment());

  // The listener reads the current onChange through a ref: rebuilding the
  // editor on every render would drop the selection on each keystroke.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const view = new EditorView({
      state: EditorState.create({
        doc: value,
        extensions: [
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          markdown(),
          EditorView.lineWrapping,
          syntaxHighlighting(promptHighlighting),
          placeholderRef.current.of(placeholder ? placeholderExtension(placeholder) : []),
          // The editing surface is a contenteditable, not a form control, so a
          // `<label for>` would not reach it — name it explicitly instead.
          EditorView.contentAttributes.of({ "aria-labelledby": labelId }),
          editableRef.current.of(EditorView.editable.of(true)),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged) return;
            if (update.transactions.some((tr) => tr.annotation(externalSync))) return;
            onChangeRef.current(update.state.doc.toString());
          }),
        ],
      }),
      parent: host,
    });
    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // Mount once. Everything that can change afterwards — the document, the
    // placeholder, the editable flag — is reconfigured by the effects below,
    // so that typing never rebuilds the editor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Adopt a value set from outside (picking a prompt from the library, loading
  // an agent). Comparing against the live document first is what keeps the
  // caret in place while the user types — the round-trip through the parent's
  // state would otherwise replace the document on every keystroke.
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current === value) return;
    view.dispatch({
      changes: { from: 0, to: current.length, insert: value },
      // Kept out of the undo stack: a caller seeding the field after mount is
      // not an edit, and undoing past it would empty the document and report
      // that erasure as the user's own.
      annotations: [externalSync.of(true), Transaction.addToHistory.of(false)],
    });
  }, [value]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({
      effects: editableRef.current.reconfigure(EditorView.editable.of(!disabled)),
    });
  }, [disabled]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({
      effects: placeholderRef.current.reconfigure(placeholder ? placeholderExtension(placeholder) : []),
    });
  }, [placeholder]);

  return (
    <div className={`${styles.editor} ${disabled ? styles.disabled : ""} ${!disabled && error ? styles.error : ""}`}>
      <span className={styles.label} id={labelId}>
        {required ? `${label} *` : label}
      </span>

      <div ref={hostRef} className={styles.host} style={{ "--prompt-editor-rows": rows } as CSSProperties} />

      {error && <span className={styles.information}>{error}</span>}
    </div>
  );
}
