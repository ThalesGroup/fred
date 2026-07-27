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
import { PdfStreamingDocumentViewer } from "../../../../../common/PdfStreamingDocumentViewer";
import { useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { decodeMaybeBase64Utf8, isPdfFile, isTabularFile } from "../../../../utils/documentViewerUtils";
import styles from "./DocumentViewer.module.css";

/**
 * Which rendering of the document to show.
 * - `"original"` (default): the native renderer when the format has one (PDF), else markdown.
 * - `"markdown"`: the ingestion's markdown extraction, even for a format with a native
 *   renderer — what the "view as markdown" toggle in the preview drawer selects.
 */
export type DocumentViewerMode = "original" | "markdown";

interface DocumentViewerProps {
  documentUid: string;
  /** Real file name incl. extension — decides the render strategy (§2.1, FRONT-13). Falls
   * back to markdown rendering when absent, matching the pre-FRONT-13 behavior. */
  fileName?: string | null;
  /** Rendering to show. Defaults to `"original"` — hosts without a toggle keep the
   * pre-existing extension-driven behavior untouched. */
  mode?: DocumentViewerMode;
  /** Called once markdown content loads successfully — lets a host derive a title
   * fallback (e.g. the first H1) without duplicating the fetch. Never called for PDFs. */
  onMarkdownLoaded?: (content: string) => void;
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
export function DocumentViewer({ documentUid, fileName, mode = "original", onMarkdownLoaded }: DocumentViewerProps) {
  if (mode === "original" && isPdfFile(fileName)) {
    return <PdfStreamingDocumentViewer documentUid={documentUid} />;
  }
  return (
    <MarkdownDocumentBody documentUid={documentUid} onLoaded={onMarkdownLoaded} fullWidth={isTabularFile(fileName)} />
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
