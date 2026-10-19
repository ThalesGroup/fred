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

import { useEffect, useRef } from "react";
import { EditorState, Compartment, Annotation } from "@codemirror/state";
import { EditorView, keymap, lineNumbers, drawSelection } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { HighlightStyle, LanguageDescription, syntaxHighlighting } from "@codemirror/language";
import { languages } from "@codemirror/language-data";
import { tags } from "@lezer/highlight";
import type { Extension } from "@codemirror/state";
import styles from "./SourceEditor.module.css";

interface SourceEditorProps {
  value: string;
  label: string;
  readOnly?: boolean;
  onChange?: (value: string) => void;
  language?: Extension;
  filename?: string;
}
const PLAIN_TEXT: Extension = [];
const sourceHighlighting = HighlightStyle.define([
  { tag: [tags.keyword, tags.modifier], class: styles.keyword },
  { tag: [tags.string, tags.attributeValue], class: styles.string },
  { tag: [tags.number, tags.bool, tags.null], class: styles.literal },
  { tag: [tags.typeName, tags.className, tags.tagName], class: styles.type },
  { tag: [tags.propertyName, tags.attributeName], class: styles.property },
  { tag: tags.comment, class: styles.comment },
  { tag: tags.invalid, class: styles.invalid },
]);
const externalSync = Annotation.define<boolean>();
export function SourceEditor({ value, label, readOnly = false, onChange, language, filename }: SourceEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const options = useRef(new Compartment());
  const languageConfig = useRef(new Compartment());
  useEffect(() => {
    if (!host.current) return;
    const editor = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          drawSelection(),
          history(),
          syntaxHighlighting(sourceHighlighting),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          options.current.of([]),
          languageConfig.current.of([]),
          EditorView.updateListener.of((update) => {
            if (update.docChanged && !update.transactions.some((transaction) => transaction.annotation(externalSync)))
              onChangeRef.current?.(update.state.doc.toString());
          }),
        ],
      }),
    });
    view.current = editor;
    return () => {
      editor.destroy();
      view.current = null;
    };
    // The document and options are updated separately without recreating the view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    view.current?.dispatch({
      effects: options.current.reconfigure([
        EditorState.readOnly.of(readOnly),
        EditorView.contentAttributes.of({
          "aria-label": label,
          "aria-readonly": String(readOnly),
          role: "textbox",
          "aria-multiline": "true",
          tabindex: "0",
        }),
      ]),
    });
  }, [readOnly, label]);
  useEffect(() => {
    let current = true;
    const apply = (extension: Extension) => {
      if (current) view.current?.dispatch({ effects: languageConfig.current.reconfigure(extension) });
    };
    apply(language ?? PLAIN_TEXT);
    if (!language && filename) {
      // The catalog's literal dynamic imports become Fred-hosted build chunks.
      // Match the basename as well as its extension (e.g. Dockerfile).
      const description = LanguageDescription.matchFilename(languages, filename.split("/").pop()!);
      description
        ?.load()
        .then(apply)
        .catch(() => apply(PLAIN_TEXT));
    }
    return () => {
      current = false;
    };
  }, [language, filename]);
  useEffect(() => {
    const editor = view.current;
    if (editor && editor.state.doc.toString() !== value)
      editor.dispatch({
        changes: { from: 0, to: editor.state.doc.length, insert: value },
        annotations: externalSync.of(true),
      });
  }, [value]);
  return <div className={styles.host} ref={host} />;
}
