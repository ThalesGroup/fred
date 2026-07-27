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
import Tabs from "@shared/molecules/Tabs/Tabs.tsx";
import { PdfStreamingDocumentViewer } from "../../../../../common/PdfStreamingDocumentViewer";
import { useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { decodeMaybeBase64Utf8, isPdfFile, isTabularFile } from "../../../../utils/documentViewerUtils";
import styles from "./DocumentViewer.module.css";

type ViewMode = "file" | "raw";

interface DocumentViewerProps {
  documentUid: string;
  /** Real file name incl. extension — decides the render strategy (§2.1, FRONT-13). Falls
   * back to markdown rendering when absent, matching the pre-FRONT-13 behavior. */
  fileName?: string | null;
  /** Called once markdown content loads successfully — lets a host derive a title
   * fallback (e.g. the first H1) without duplicating the fetch. Never called for PDFs. */
  onMarkdownLoaded?: (content: string) => void;
  /** Shows a "Fichier"/"Raw" toggle above the content, letting the user switch to the
   *  markdown extraction for a file that would otherwise only render its native
   *  strategy (currently: PDF only — every other format already renders nothing but
   *  its markdown extraction, so there is nothing to toggle to). Default off, so
   *  existing callers (`DocumentViewerPage`, the pre-FRONT-09 preview drawer) keep
   *  rendering exactly one strategy per file type, unchanged. */
  showRawToggle?: boolean;
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
export function DocumentViewer({
  documentUid,
  fileName,
  onMarkdownLoaded,
  showRawToggle = false,
}: DocumentViewerProps) {
  const { t } = useTranslation();
  const [view, setView] = useState<ViewMode>("file");
  const isPdf = isPdfFile(fileName);

  if (!isPdf) {
    return (
      <MarkdownDocumentBody documentUid={documentUid} onLoaded={onMarkdownLoaded} fullWidth={isTabularFile(fileName)} />
    );
  }

  if (!showRawToggle) {
    return <PdfStreamingDocumentViewer documentUid={documentUid} />;
  }

  return (
    <div className={styles.viewerWithToggle}>
      <div className={styles.viewerTabs}>
        <Tabs<ViewMode>
          tabs={[
            { value: "file", label: t("rework.resources.preview.tabs.file") },
            { value: "raw", label: t("rework.resources.preview.tabs.raw") },
          ]}
          value={view}
          onChange={setView}
        />
      </div>
      <div className={styles.viewerBody}>
        {view === "file" ? (
          <PdfStreamingDocumentViewer documentUid={documentUid} />
        ) : (
          <MarkdownDocumentBody documentUid={documentUid} onLoaded={onMarkdownLoaded} />
        )}
      </div>
    </div>
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
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [fetchPreview] = useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery();

  useEffect(() => {
    if (!documentUid) return;
    // Guards against a superseded response winning the race: if `documentUid`
    // changes again before this fetch resolves, `cancelled` flips true and the
    // stale `.then()`/`.catch()` below becomes a no-op, so an out-of-order
    // response can never overwrite the newer document's content or title.
    let cancelled = false;
    setLoading(true);
    fetchPreview({ documentUid })
      .unwrap()
      .then((resp) => {
        if (cancelled) return;
        const decoded = decodeMaybeBase64Utf8(resp?.content ?? "");
        setContent(decoded);
        onLoaded?.(decoded);
      })
      .catch(() => {
        if (cancelled) return;
        setContent("Error loading document.");
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

  return (
    <div className={styles.markdownBody}>
      {loading ? <p className={styles.loading}>Loading…</p> : <MarkdownRenderer text={content} fullWidth={fullWidth} />}
    </div>
  );
}
