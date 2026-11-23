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
  addEditorWrapper$,
  realmPlugin,
  diffSourcePlugin,
  markdownShortcutPlugin,
  MDXEditor,
  type MDXEditorMethods,
  toolbarPlugin,
} from "@mdxeditor/editor";
import "@mdxeditor/editor/style.css";
import { EditorView } from "@codemirror/view";
import { useContext, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApplicationContext } from "../../../../app/ApplicationContextProvider";
import Button from "@shared/atoms/Button/Button";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import Select, { type SelectOption } from "@shared/molecules/Select/Select";
import { ProseToolbarButtons, proseMdxPlugins } from "@shared/organisms/ProseMdxEditor/ProseMdxEditor";
import { hasSameMarkdownContent } from "@shared/molecules/MarkdownRenderer/markdownSyntax";
import TagInput from "@shared/molecules/TagInput/TagInput";
import { errorText } from "@rework/features/teamWiki/wikiErrors";
import type {
  PrepareWikiDocumentRequest,
  WikiFormat,
  WikiPropertiesPatch,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./WikiEditor.module.css";

// DiffSourceWrapper hides, but still mounts, Lexical. Its empty initial state
// exports an empty document even in source mode. This native inner wrapper keeps
// the native source editor mounted without mounting the hidden visual editor.
const sourceOnlyPlugin = realmPlugin({
  init(realm) {
    realm.pub(addEditorWrapper$, () => null);
  },
});

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
  initialFormat?: WikiFormat | null;
  initialError?: string | null;
  /** Ordinary pages only. The server owns frontmatter parsing and validation. */
  onPrepare?: (request: PrepareWikiDocumentRequest) => Promise<WikiFormat>;
  /** Character cap the backend enforces; shown once the draft approaches it. */
  maxChars: number;
  saving: boolean;
  /** Set when the server refused the save because the page moved on. */
  conflict: { currentContentMd: string } | null;
  /** Shown above the editor when it opened on a starting outline rather than on
   *  text the team wrote — how to fill it in belongs here, not in the page. */
  hint?: string;
  onSave: (contentMd: string, placement: WikiPagePlacement | null) => void | Promise<void>;
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
  initialFormat,
  initialError,
  onPrepare,
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
  const [mode, setMode] = useState<"source" | "rich-text">(onPrepare && !initialFormat ? "source" : "rich-text");
  const [draft, setDraft] = useState(initialFormat?.body_md ?? initialContent);
  const [format, setFormat] = useState(initialFormat);
  const [properties, setProperties] = useState<WikiPropertiesPatch>({});
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState(initialError ?? "");
  const editor = useRef<MDXEditorMethods>(null);
  const visualFailed = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const busy = saving || preparing;

  const documentContent = (body: string) => {
    const prefix = format?.frontmatter_prefix ?? "";
    const separator =
      prefix && !prefix.endsWith("\n") && body && !body.startsWith("\n") && !body.startsWith("\r\n")
        ? prefix.startsWith("---\r\n")
          ? "\r\n"
          : "\n"
        : "";
    return prefix + separator + body;
  };
  const prepare = async (target: "source" | "rich-text" | "save", retainedBody?: string) => {
    if (busy && retainedBody === undefined) return;
    const native = retainedBody ?? (visualFailed.current ? draft : editor.current?.getMarkdown()) ?? draft;
    // CodeMirror uses LF internally, even on focus. A no-op source interaction
    // must not rewrite the server's opaque prefix (or the original body).
    const current = mode === "source" && native === draft.replace(/\r\n/g, "\n") ? draft : native;
    setDraft(current);
    setPreparing(true);
    setError("");
    try {
      const full = mode === "source" ? current : documentContent(current);
      const prepared = onPrepare
        ? await onPrepare({ content_md: full, ...(mode === "rich-text" ? { properties } : {}) })
        : null;
      if (!mounted.current) return;
      const source = prepared ? prepared.frontmatter_prefix + prepared.body_md : full;
      if (target === "save") {
        await onSave(source, placement ? { title: titleDraft.trim(), parentId: parentDraft } : null);
      } else {
        setFormat(prepared);
        setProperties({});
        setDraft(target === "source" ? source : (prepared?.body_md ?? source));
        visualFailed.current = false;
        setMode(target);
      }
      return true;
    } catch (failure) {
      if (mounted.current) setError(errorText(failure));
      return false;
    } finally {
      if (mounted.current) setPreparing(false);
    }
  };
  const unsupported = () => {
    if (visualFailed.current) return;
    visualFailed.current = true;
    // Keep the raw body AND pending properties. Preparing the retained body
    // applies those fields before falling back; a refusal leaves both editable.
    void prepare("source", draft).then((prepared) => {
      if (mounted.current && prepared) setError(t("rework.wiki.editor.unsupported"));
    });
  };
  const [titleDraft, setTitleDraft] = useState(title);
  const [parentDraft, setParentDraft] = useState(placement?.parentId ?? "");

  const tooLong = Array.from(mode === "source" ? draft : documentContent(draft)).length > maxChars;
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
                  disabled={busy}
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
            onClick={() => void prepare("save")}
            disabled={busy || tooLong || titleMissing || (mode === "rich-text" && visualFailed.current)}
          >
            {t("rework.wiki.editor.save")}
          </Button>
        </div>
      </header>

      {placement && (
        <div className={styles.fields}>
          <TextInput
            compact
            size="small"
            label={t("rework.wiki.editor.titleLabel")}
            disabled={busy}
            value={titleDraft}
            onChange={(event) => setTitleDraft(event.target.value)}
          />
          <Select
            compact
            size="small"
            label={t("rework.wiki.editor.parentLabel")}
            disabled={busy}
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

      <div className={styles.actions} aria-label={t("rework.wiki.editor.mode")} role="group">
        {(["rich-text", "source"] as const).map((view) => (
          <Button
            key={view}
            color="primary"
            variant={mode === view ? "filled" : "outlined"}
            size="small"
            aria-pressed={mode === view}
            disabled={busy}
            onClick={() => {
              if (view !== mode) void prepare(view);
            }}
          >
            {t(`rework.wiki.editor.${view === "source" ? "markdown" : "visual"}`)}
          </Button>
        ))}
      </div>
      {onPrepare && mode === "rich-text" && (
        <div className={styles.properties}>
          <Select
            compact
            size="small"
            label={t("rework.wiki.editor.typeLabel")}
            disabled={busy}
            value={properties.page_type ?? (format?.page_type === "untyped" ? "" : format?.page_type) ?? ""}
            onChange={(value) => setProperties((current) => ({ ...current, page_type: value }))}
            options={["", "topic", "procedure", "decision", "reference", "source", "hub"].map((value) => ({
              value,
              key: value || "none",
              label: t(`rework.wiki.editor.types.${value || "none"}`),
            }))}
          />
          <TextInput
            compact
            size="small"
            label={t("rework.wiki.editor.descriptionLabel")}
            disabled={busy}
            value={properties.description ?? format?.description ?? ""}
            onChange={(event) => setProperties((current) => ({ ...current, description: event.target.value }))}
          />
          <TagInput
            label={t("rework.wiki.editor.tagsLabel")}
            disabled={busy}
            tags={properties.tags ?? format?.tags ?? []}
            onChange={(tags) => setProperties((current) => ({ ...current, tags }))}
            removeTagAriaLabel={(tag) => t("rework.wiki.editor.removeTag", { tag })}
          />
        </div>
      )}
      {error && (
        <p className={styles.tooLong} role="alert">
          {error}
        </p>
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
              disabled={busy}
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

      <div className={styles.surface} inert={busy || (mode === "rich-text" && visualFailed.current)} aria-busy={busy}>
        <MDXEditor
          // The CURRENT draft, not the text the editor opened on: this
          // remounts on a theme flip, and MDXEditor reads `markdown` only at
          // mount — so feeding the original text put it back on screen while
          // Save still held the newer, now invisible, draft.
          markdown={draft}
          ref={editor}
          trim={false}
          {...(mode === "source" ? { editorState: null } : {})}
          onChange={(value, initialNormalize) => {
            if (mode === "source") {
              setDraft((current) => (value === current.replace(/\r\n/g, "\n") ? current : value));
            } else if (initialNormalize) {
              try {
                if (!hasSameMarkdownContent(draft, value)) unsupported();
              } catch {
                unsupported();
              }
            } else if (!visualFailed.current) setDraft(value);
          }}
          onError={unsupported}
          // Remounts on a theme flip: MDXEditor builds its popup container once,
          // copying this class onto it, so the toolbar's dropdowns would keep
          // the palette they were born with.
          key={`${mode}:${darkMode ? "dark" : "light"}`}
          // `mdxeditor-full-height` is the library's own opt-in: it makes every
          // element between the root and the contenteditable a flex column, so
          // the whole writing area is clickable rather than just its first line.
          className={`mdxeditor-full-height${darkMode ? " dark-theme dark-editor" : ""}`}
          contentEditableClassName="fred-writable-document"
          plugins={[
            ...proseMdxPlugins(),
            diffSourcePlugin({
              viewMode: mode,
              codeMirrorExtensions: [
                EditorView.contentAttributes.of({ "aria-label": t("rework.wiki.editor.markdown") }),
              ],
            }),
            ...(mode === "source" ? [sourceOnlyPlugin()] : []),
            markdownShortcutPlugin(),
            toolbarPlugin({
              toolbarContents: () => (mode === "rich-text" ? <ProseToolbarButtons /> : null),
            }),
          ]}
        />
      </div>
    </section>
  );
}
