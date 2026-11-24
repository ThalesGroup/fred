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

// A chapter's text (paragraphs and lists) in the "Rédaction" view: read as
// text, edited in MDXEditor with explicit save/cancel, one `write` per save.
// Only the Markdown subset `write` accepts is offered; placed images move with
// the text but are not resizable (a resized image would serialise as HTML).
// MDXEditor reads `markdown` only at mount, so a notice says when the AI
// changed the open passage.

import {
  BoldItalicUnderlineToggles,
  imagePlugin,
  listsPlugin,
  ListsToggle,
  markdownShortcutPlugin,
  MDXEditor,
  Separator,
  toolbarPlugin,
  UndoRedo,
} from "@mdxeditor/editor";
import "@mdxeditor/editor/style.css";
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import type { TextSegment } from "./api/wordTemplateCapabilityOpenApi";
import { segmentOperation } from "./contentView";
import { IMAGE_REF_PREFIX, type ImageResolver, useImageResolver } from "./sessionImages";
import { usePlaceDraft } from "./usePlaceDraft";
import type { ApplyOperations } from "./WordTemplateBlocks";
import { DraftNotes } from "./WordTemplatePlaceField";
import styles from "./WordTemplateRichText.module.css";

const isDarkTheme = () =>
  typeof document !== "undefined" && document.documentElement.getAttribute("data-theme") === "dark";

const editorPlugins = (resolveImage: ImageResolver) => [
  listsPlugin(),
  imagePlugin({ imagePreviewHandler: resolveImage, disableImageResize: true, disableImageSettingsButton: true }),
  markdownShortcutPlugin(),
  toolbarPlugin({
    toolbarContents: () => (
      <>
        <UndoRedo />
        <Separator />
        <BoldItalicUnderlineToggles options={["Bold", "Italic"]} />
        <Separator />
        <ListsToggle options={["bullet", "number"]} />
      </>
    ),
  }),
];

/** Keeps `img:` sources (resolved by `SessionImage`); the default rule for any other URL. */
export const keepImageRefs = (url: string) => (url.startsWith(IMAGE_REF_PREFIX) ? url : defaultUrlTransform(url));

/** A session image in the reading view, fetched with the bearer. */
function SessionImage({ src, alt }: { src?: string; alt?: string }) {
  const resolveImage = useImageResolver();
  const [shown, setShown] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setShown(null);
    if (src)
      resolveImage(src)
        .then((url) => live && setShown(url))
        .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [src, resolveImage]);
  return shown ? <img className={styles.image} src={shown} alt={alt ?? ""} /> : <span>{alt}</span>;
}

const markdownComponents = { img: SessionImage };

interface RichTextProps {
  segment: TextSegment;
  apply: ApplyOperations;
  disabled?: boolean;
}

export function WordTemplateRichText({ segment, apply, disabled }: RichTextProps) {
  const { t } = useTranslation();
  const serverValue = segment.markdown ?? "";
  const [open, setOpen] = useState(false);
  // Remount the editor on each opening, from the value shown at that moment.
  const [openCount, setOpenCount] = useState(0);
  const resolveImage = useImageResolver();
  const plugins = useMemo(() => editorPlugins(resolveImage), [resolveImage]);
  const draft = usePlaceDraft(serverValue, (value) => apply([segmentOperation(segment, value)]));

  const startEditing = () => {
    if (disabled) return;
    // The editor keeps the text it opened with: an AI change after this must show.
    draft.begin();
    setOpenCount((n) => n + 1);
    setOpen(true);
  };

  const save = async () => {
    // A refused save (409/422) keeps the draft and the editor open.
    if (await draft.commit()) setOpen(false);
  };

  const cancel = () => {
    draft.cancel();
    setOpen(false);
  };

  if (!open) {
    const empty = !draft.value.trim();
    return (
      <div className={styles.segment}>
        <button
          type="button"
          className={styles.reading}
          disabled={disabled}
          onClick={startEditing}
          aria-label={t("capability.word_template.editor.editText")}
        >
          {empty ? (
            <span className={styles.placeholder}>{t("capability.word_template.editor.emptyText")}</span>
          ) : (
            <ReactMarkdown urlTransform={keepImageRefs} components={markdownComponents}>
              {draft.value}
            </ReactMarkdown>
          )}
        </button>
        <DraftNotes dirty={draft.dirty} remoteChange={draft.remoteChange} onCancel={draft.cancel} />
      </div>
    );
  }

  return (
    <div className={styles.segment}>
      <div className={styles.editorArea}>
        <MDXEditor
          key={openCount}
          markdown={draft.value}
          autoFocus
          onChange={(md, initialNormalize) => {
            // The editor's own re-serialisation at mount is not an edit.
            if (!initialNormalize) draft.onType(md);
          }}
          className={isDarkTheme() ? "dark-theme dark-editor" : undefined}
          contentEditableClassName={styles.editable}
          plugins={plugins}
        />
      </div>
      <DraftNotes dirty={false} remoteChange={draft.remoteChange} onCancel={cancel} />
      <div className={styles.actions}>
        <Button color="on-surface" variant="text" size="small" onClick={cancel}>
          {t("capability.word_template.editor.cancel")}
        </Button>
        <Button color="primary" variant="filled" size="small" disabled={disabled} onClick={() => void save()}>
          {t("capability.word_template.editor.save")}
        </Button>
      </div>
    </div>
  );
}
