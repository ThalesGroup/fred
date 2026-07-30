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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import type { ButtonGroupItemProps } from "@shared/atoms/ButtonGroup/ButtonGroupItem/ButtonGroupItem.tsx";
import { PdfStreamingDocumentViewer } from "../../../../../common/PdfStreamingDocumentViewer";
import { useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { decodeMaybeBase64Utf8, isPdfFile, isTabularFile } from "../../../../utils/documentViewerUtils";
import styles from "./DocumentViewer.module.css";

export type ViewMode = "file" | "raw";

const VIEW_TABS: ViewMode[] = ["file", "raw"];

interface DocumentViewerProps {
  documentUid: string;
  /** Real file name incl. extension — decides the render strategy (§2.1, FRONT-13). Falls
   * back to markdown rendering when absent, matching the pre-FRONT-13 behavior. */
  fileName?: string | null;
  /** Called once markdown content loads successfully — lets a host derive a title
   * fallback (e.g. the first H1) without duplicating the fetch. Never called for PDFs. */
  onMarkdownLoaded?: (content: string) => void;
  /** Renders the given mode's content instead of picking one strategy
   *  automatically — the corpus workspace preview drawer pairs this with a
   *  `DocumentViewerModeToggle` rendered in its own header (left of the
   *  close button), so the toggle isn't fighting the document for vertical
   *  space inside this "chrome-less" body. Ignored for non-PDF files: every
   *  other format already renders nothing but its markdown extraction, so
   *  there is nothing to toggle to. Omit to keep the pre-FRONT-09 single-
   *  strategy behavior (`DocumentViewerPage`). */
  view?: ViewMode;
}

/**
 * Shared document content renderer used by both the chat-citation viewer
 * (`DocumentViewerPage`) and the corpus workspace preview drawer
 * (`DocumentWorkspace`). Picks a native PDF renderer or the markdown
 * extraction based on the file's extension — see FRONT-13.
 *
 * Deliberately chrome-less: both hosting contexts already provide their own
 * header/close affordance (the page's top bar, `InlineDrawer`'s header).
 */
export function DocumentViewer({ documentUid, fileName, onMarkdownLoaded, view }: DocumentViewerProps) {
  const isPdf = isPdfFile(fileName);

  if (!isPdf) {
    return (
      <MarkdownDocumentBody documentUid={documentUid} onLoaded={onMarkdownLoaded} fullWidth={isTabularFile(fileName)} />
    );
  }

  if (!view) {
    return <PdfStreamingDocumentViewer documentUid={documentUid} />;
  }

  return (
    <div className={styles.viewerBody}>
      {view === "file" ? (
        <PdfStreamingDocumentViewer documentUid={documentUid} />
      ) : (
        <MarkdownDocumentBody documentUid={documentUid} onLoaded={onMarkdownLoaded} />
      )}
    </div>
  );
}

/**
 * The "Fichier"/"Raw" mode toggle for `DocumentViewer`'s `view` prop —
 * rendered separately (not inside `DocumentViewer` itself) so a host can
 * place it in its own header, e.g. `InlineDrawer`'s `headerActions` (left of
 * the close button), instead of stealing a row of vertical space from the
 * document body.
 */
export function DocumentViewerModeToggle({ view, onChange }: { view: ViewMode; onChange: (view: ViewMode) => void }) {
  const { t } = useTranslation();
  const viewTabItems: ButtonGroupItemProps[] = [
    { label: t("rework.resources.preview.tabs.file") },
    { label: t("rework.resources.preview.tabs.raw") },
  ];

  return (
    <ButtonGroup
      items={viewTabItems}
      size="xs"
      color="secondary"
      variant="tabs"
      aria-label={t("rework.resources.preview.tabsAria")}
      selectedIndex={VIEW_TABS.indexOf(view)}
      onSelectedIndexChange={(index) => onChange(VIEW_TABS[index])}
    />
  );
}

function MarkdownDocumentBody({
  documentUid,
  onLoaded,
  fullWidth,
}: {
  documentUid: string;
  onLoaded?: (content: string) => void;
  fullWidth?: boolean;
}) {
  const { t } = useTranslation();
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  // Set when the markdown extraction cannot be served (404 — the document never
  // went through a preview-generating pipeline, or the extraction failed). Kept
  // separate from `content` so it renders as an empty state rather than as
  // document text the user could mistake for the file's real content.
  const [unavailable, setUnavailable] = useState(false);
  const [fetchPreview] = useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery();

  useEffect(() => {
    if (!documentUid) return;
    // Guards against a superseded response winning the race: if `documentUid`
    // changes again before this fetch resolves, `cancelled` flips true and the
    // stale `.then()`/`.catch()` below becomes a no-op, so an out-of-order
    // response can never overwrite the newer document's content or title.
    let cancelled = false;
    setLoading(true);
    setUnavailable(false);
    fetchPreview({ documentUid })
      .unwrap()
      .then((resp) => {
        if (cancelled) return;
        const decoded = decodeMaybeBase64Utf8(resp?.content ?? "");
        setContent(decoded);
        setUnavailable(decoded.trim() === "");
        onLoaded?.(decoded);
      })
      .catch(() => {
        if (cancelled) return;
        setContent("");
        setUnavailable(true);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // onLoaded is a per-render callback (title-derivation), not a fetch dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentUid, fetchPreview]);

  if (loading) {
    return (
      <div className={styles.markdownBody}>
        <p className={styles.loading}>{t("rework.resources.preview.loading")}</p>
      </div>
    );
  }
  if (unavailable) {
    return (
      <div className={styles.markdownBody}>
        <p className={styles.unavailable}>{t("rework.resources.preview.markdownUnavailable")}</p>
      </div>
    );
  }
  return (
    <div className={styles.markdownBody}>
      <MarkdownRenderer text={content} fullWidth={fullWidth} />
    </div>
  );
}
