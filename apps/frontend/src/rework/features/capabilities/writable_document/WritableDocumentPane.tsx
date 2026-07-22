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

// WritableDocumentPane — the writable_document capability's side panel
// (CapabilitySidePanel), ported from Kea's pane of the same name.
//
// One MDXEditor edits the selected document (markdown in/out, always editable);
// several documents appear as a tab strip. The editor is keyed on
// `${document_id}:${updated_at}` so it remounts when switching tabs AND when an
// agent writes a new version (MDXEditor reads `markdown` only at mount) — but the
// key is unchanged while the user types, so live editing keeps its cursor. Edits
// autosave (debounced PUT) via useWritableDocuments. The session id comes from the
// URL (`?session=`, the rework convention — there is no redux session selector).

import {
  BlockTypeSelect,
  BoldItalicUnderlineToggles,
  ChangeCodeMirrorLanguage,
  codeBlockPlugin,
  codeMirrorPlugin,
  ConditionalContents,
  CreateLink,
  headingsPlugin,
  imagePlugin,
  InsertCodeBlock,
  InsertTable,
  linkDialogPlugin,
  linkPlugin,
  listsPlugin,
  ListsToggle,
  markdownShortcutPlugin,
  MDXEditor,
  quotePlugin,
  Separator,
  tablePlugin,
  thematicBreakPlugin,
  toolbarPlugin,
  UndoRedo,
} from "@mdxeditor/editor";
import "@mdxeditor/editor/style.css";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import type { CapabilitySidePanelProps } from "../types";
import { useWritableDocuments } from "./useWritableDocuments";
import WritableDocumentDownloadButton from "./WritableDocumentDownloadButton";
import styles from "./WritableDocumentPane.module.css";

const isDarkTheme = () =>
  typeof document !== "undefined" && document.documentElement.getAttribute("data-theme") === "dark";

export function WritableDocumentPane(_props: CapabilitySidePanelProps) {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("session") ?? "";

  const { documents, selectedId, selectDocument, onEditDocument, isSaving } = useWritableDocuments(
    sessionId || undefined,
  );

  const selected = useMemo(
    () => documents.find((d) => d.document_id === selectedId) ?? documents[0],
    [documents, selectedId],
  );

  const untitled = t("capability.writable_document.untitled");

  return (
    <div className={styles.pane}>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <Icon category="outlined" type="edit_note" />
          <span className={styles.title}>{selected?.title || untitled}</span>
        </div>
        {isSaving && <span className={styles.saving}>{t("capability.writable_document.saving")}</span>}
        {selected && sessionId && (
          <WritableDocumentDownloadButton
            sessionId={sessionId}
            documentId={selected.document_id}
            title={selected.title}
          />
        )}
      </div>

      {!sessionId && <div className={styles.empty}>{t("capability.writable_document.noSession")}</div>}

      {sessionId && !selected && <div className={styles.empty}>{t("capability.writable_document.empty")}</div>}

      {documents.length > 1 && (
        <div className={styles.tabs} role="tablist">
          {documents.map((docItem) => (
            <button
              key={docItem.document_id}
              role="tab"
              aria-selected={docItem.document_id === selected?.document_id}
              className={`${styles.tab} ${docItem.document_id === selected?.document_id ? styles.tabActive : ""}`}
              onClick={() => selectDocument(docItem.document_id)}
            >
              {docItem.title || untitled}
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div className={styles.editorArea}>
          <MDXEditor
            key={`${selected.document_id}:${selected.updated_at ?? ""}`}
            markdown={selected.content_md ?? ""}
            onChange={(md) => onEditDocument(selected.document_id, md)}
            className={isDarkTheme() ? "dark-theme dark-editor" : undefined}
            contentEditableClassName="fred-writable-document"
            plugins={[
              headingsPlugin(),
              listsPlugin(),
              quotePlugin(),
              linkPlugin(),
              linkDialogPlugin(),
              thematicBreakPlugin(),
              tablePlugin(),
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
                            <UndoRedo />
                            <Separator />
                            <BoldItalicUnderlineToggles />
                            <Separator />
                            <BlockTypeSelect />
                            <Separator />
                            <ListsToggle />
                            <Separator />
                            <CreateLink />
                            <Separator />
                            <InsertTable />
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
      )}
    </div>
  );
}
