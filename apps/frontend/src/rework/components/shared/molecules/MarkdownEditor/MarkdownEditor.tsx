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

import {
  ChangeCodeMirrorLanguage,
  codeBlockPlugin,
  codeMirrorPlugin,
  ConditionalContents,
  imagePlugin,
  InsertCodeBlock,
  markdownShortcutPlugin,
  MDXEditor,
  Separator,
  toolbarPlugin,
} from "@mdxeditor/editor";
import "@mdxeditor/editor/style.css";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ProseToolbarButtons, proseMdxPlugins } from "./proseMdxPlugins";
import { sanitizeEditorMarkdown } from "./sanitizeEditorMarkdown";
import type { MDXEditorMethods } from "@mdxeditor/editor";
import styles from "./MarkdownEditor.module.css";

export function MarkdownEditor({
  value,
  onChange,
  readOnly = false,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
  label: string;
}) {
  const { t } = useTranslation();
  const editor = useRef<MDXEditorMethods>(null);
  const latest = useRef(value);
  const [initial] = useState(() => sanitizeEditorMarkdown(value));
  useEffect(() => {
    if (latest.current !== value) {
      latest.current = value;
      editor.current?.setMarkdown(sanitizeEditorMarkdown(value));
    }
  }, [value]);
  return (
    <div className={styles.editorArea} aria-label={label}>
      <MDXEditor
        ref={editor}
        markdown={initial}
        readOnly={readOnly}
        onChange={(markdown, initialNormalize) => {
          if (!initialNormalize && !readOnly) {
            latest.current = markdown;
            onChange(markdown);
          }
        }}
        className={
          document.documentElement.getAttribute("data-theme") === "dark" ? "dark-theme dark-editor" : undefined
        }
        contentEditableClassName="fred-writable-document"
        plugins={[
          ...proseMdxPlugins(),
          imagePlugin(),
          codeBlockPlugin({ defaultCodeBlockLanguage: "" }),
          codeMirrorPlugin({
            codeBlockLanguages: {
              "": t("capability.writable_document.code.plainText"),
              bash: "Bash",
              css: "CSS",
              html: "HTML",
              java: "Java",
              js: "JavaScript",
              json: "JSON",
              jsx: "JSX",
              markdown: "Markdown",
              python: "Python",
              sql: "SQL",
              ts: "TypeScript",
              tsx: "TSX",
              yaml: "YAML",
            },
          }),
          markdownShortcutPlugin(),
          toolbarPlugin({
            toolbarContents: () => (
              <ConditionalContents
                options={[
                  {
                    when: (editor) => editor?.editorType === "codeblock",
                    contents: () => <ChangeCodeMirrorLanguage />,
                  },
                  {
                    fallback: () => (
                      <>
                        <ProseToolbarButtons />
                        <Separator />
                        <InsertCodeBlock />
                      </>
                    ),
                  },
                ]}
              />
            ),
          }),
        ]}
      />
    </div>
  );
}
