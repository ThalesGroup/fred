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

import { markdownShortcutPlugin, MDXEditor, toolbarPlugin } from "@mdxeditor/editor";
import "@mdxeditor/editor/style.css";
import { useContext, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApplicationContext } from "../../../../app/ApplicationContextProvider";
import Button from "@shared/atoms/Button/Button";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import Select, { type SelectOption } from "@shared/molecules/Select/Select";
import { ProseToolbarButtons, proseMdxPlugins } from "@shared/organisms/ProseMdxEditor/ProseMdxEditor";
import styles from "./WikiEditor.module.css";

/** What an ordinary page lets the editor change besides its text: "" is the root. */
export interface WikiPagePlacement {
  title: string;
  parentId: string;
}

interface WikiEditorProps {
  title: string;
  /** Ordinary pages only: the rules page keeps a fixed title, no parent and no delete. */
  placement?: { parentId: string; parentOptions: SelectOption<string>[]; onDelete: () => void };
  initialContent: string;
  /** Character cap the backend enforces; shown once the draft approaches it. */
  maxChars: number;
  saving: boolean;
  /** Set when the server refused the save because the page moved on. */
  conflict: { currentContentMd: string } | null;
  /** Shown above the editor when it opened on a starting outline rather than on
   *  text the team wrote — how to fill it in belongs here, not in the page. */
  hint?: string;
  onSave: (contentMd: string, placement: WikiPagePlacement | null) => void;
  onCancel: () => void;
  onTakeTheirs: (contentMd: string) => void;
}

/**
 * Edit one wiki page.
 *
 * The same `MDXEditor` configuration as the collaborative document, minus the
 * code-block plugins: a wiki page is prose, and a code editor inside a
 * knowledge base invites pasting a file where a link belongs.
 */
export function WikiEditor({
  title,
  placement,
  initialContent,
  maxChars,
  saving,
  conflict,
  hint,
  onSave,
  onCancel,
  onTakeTheirs,
}: WikiEditorProps) {
  const { t } = useTranslation();
  const { darkMode } = useContext(ApplicationContext);
  const [draft, setDraft] = useState(initialContent);
  const [titleDraft, setTitleDraft] = useState(title);
  const [parentDraft, setParentDraft] = useState(placement?.parentId ?? "");

  const tooLong = draft.length > maxChars;
  const titleMissing = placement !== undefined && !titleDraft.trim();

  return (
    <section className={styles.editor}>
      <header className={styles.header}>
        {/* Follows the title field as it is typed, so the bar always names the page being saved. */}
        <h1 className={styles.title}>{placement ? titleDraft.trim() || title : title}</h1>
        <div className={styles.actions}>
          {placement && (
            <span className={styles.deleteAction}>
              <Tooltip text={t("rework.wiki.editor.delete")}>
                <DeleteIconButton
                  size="small"
                  onClick={placement.onDelete}
                  disabled={saving}
                  aria-label={t("rework.wiki.editor.delete")}
                />
              </Tooltip>
            </span>
          )}
          <Button color="on-surface-retreat" variant="text" size="small" onClick={onCancel} disabled={saving}>
            {t("rework.wiki.editor.cancel")}
          </Button>
          <Button
            color="primary"
            variant="filled"
            size="small"
            onClick={() => onSave(draft, placement ? { title: titleDraft.trim(), parentId: parentDraft } : null)}
            disabled={saving || tooLong || titleMissing}
          >
            {t("rework.wiki.editor.save")}
          </Button>
        </div>
      </header>

      {placement && (
        <div className={styles.fields}>
          <TextInput
            size="small"
            label={t("rework.wiki.editor.titleLabel")}
            value={titleDraft}
            onChange={(event) => setTitleDraft(event.target.value)}
          />
          <Select
            size="small"
            label={t("rework.wiki.editor.parentLabel")}
            value={parentDraft}
            onChange={setParentDraft}
            options={placement.parentOptions}
            search={{
              placeholder: t("rework.wiki.editor.parentSearch"),
              noMatchMessage: t("rework.wiki.editor.parentNoMatch"),
            }}
          />
        </div>
      )}

      {/* Someone else saved while this draft was open. The user's own text is
          never discarded for them: they are shown what landed and choose. */}
      {conflict && (
        <div className={styles.conflict} role="alert">
          <p className={styles.conflictText}>{t("rework.wiki.editor.conflict")}</p>
          <div className={styles.conflictActions}>
            <Button
              color="on-surface-retreat"
              variant="outlined"
              size="small"
              onClick={() => onTakeTheirs(conflict.currentContentMd)}
            >
              {t("rework.wiki.editor.loadCurrent")}
            </Button>
          </div>
        </div>
      )}

      {hint && <p className={styles.hint}>{hint}</p>}

      {tooLong && (
        <p className={styles.tooLong} role="alert">
          {t("rework.wiki.editor.tooLong", { max: maxChars })}
        </p>
      )}

      <div className={styles.surface}>
        <MDXEditor
          // The CURRENT draft, not the text the editor opened on: this
          // remounts on a theme flip, and MDXEditor reads `markdown` only at
          // mount — so feeding the original text put it back on screen while
          // Save still held the newer, now invisible, draft.
          markdown={draft}
          onChange={setDraft}
          // Remounts on a theme flip: MDXEditor builds its popup container once,
          // copying this class onto it, so the toolbar's dropdowns would keep
          // the palette they were born with.
          key={darkMode ? "dark" : "light"}
          // `mdxeditor-full-height` is the library's own opt-in: it makes every
          // element between the root and the contenteditable a flex column, so
          // the whole writing area is clickable rather than just its first line.
          className={`mdxeditor-full-height${darkMode ? " dark-theme dark-editor" : ""}`}
          contentEditableClassName="fred-writable-document"
          plugins={[
            ...proseMdxPlugins(),
            markdownShortcutPlugin(),
            toolbarPlugin({
              toolbarContents: () => <ProseToolbarButtons />,
            }),
          ]}
        />
      </div>
    </section>
  );
}
