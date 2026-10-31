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

// PptPreviewPane
// --------------
// The ppt_filler capability's side panel (CapabilitySidePanel) — a read-only pane
// that renders the filled deck as a PDF. It reads the deck the OPEN conversation
// registered (every rendered card registers one), fetches the bytes with the live
// bearer (usePptPreview), and draws every page vertically with react-pdf.
//
// The pdf.js worker lifecycle lives in usePdfWorker.

import { useEffect, useRef, useState } from "react";
import { Document, Page } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import type { CapabilitySidePanelProps } from "../types";
import { useSessionPptPreview } from "./useSessionPptPreview";
import { usePptPreview } from "./usePptPreview";
import PptxDownloadButton from "./PptxDownloadButton";
import DeckSummaryButton from "./DeckSummaryButton";
import { usePdfWorker } from "./usePdfWorker";
import styles from "./PptPreviewPane.module.css";

const PDF_SCALE = 0.95;

/** react-pdf remount key when this conversation has no deck. */
const NO_PREVIEW_KEY = "none";

export function PptPreviewPane({ onClose }: CapabilitySidePanelProps) {
  const { t } = useTranslation();
  const current = useSessionPptPreview();
  const { objectUrl, isLoading, error } = usePptPreview(current);

  const [numPages, setNumPages] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Fit the page width to the pane, less padding, tracking resizes.
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [pageWidth, setPageWidth] = useState<number>(600);
  useEffect(() => {
    if (!contentRef.current) return;
    const el = contentRef.current;
    const measure = () => {
      const base = Math.max(280, Math.floor(el.clientWidth - 24));
      setPageWidth(Math.floor(base * PDF_SCALE));
    };
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    measure();
    return () => ro.disconnect();
  }, []);

  // A re-fill or another deck remounts the <Document> with a fresh worker. The blob
  // URL is part of the key: pdf.js caches one PDFWorker per port, so a new `file`
  // on the port of the load it replaces would hit a worker being destroyed.
  const remountKey = current ? `${current.preview_id}:${current.version}:${objectUrl ?? ""}` : NO_PREVIEW_KEY;

  usePdfWorker(remountKey, Boolean(objectUrl));

  useEffect(() => {
    setNumPages(null);
    setLoadError(null);
  }, [remountKey]);

  const untitled = t("capability.ppt_filler.preview.untitled", { defaultValue: "Presentation" });
  const loadErrorMsg = t("capability.ppt_filler.preview.loadError", { defaultValue: "Failed to load preview." });

  const shownError = error ? loadErrorMsg : loadError;

  return (
    <div className={styles.pane}>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <Icon category="outlined" type="slideshow" />
          <span className={styles.title}>{current?.title || untitled}</span>
        </div>
        <div className={styles.tools}>
          <DeckSummaryButton summary={current?.summary} />
          {current?.pptx_download_url && (
            <PptxDownloadButton href={current.pptx_download_url} fileName={current.file_name} />
          )}
          <IconButton
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "close" }}
            aria-label="Close panel"
            // Blur first: closing flips aria-hidden on the drawer, which the browser
            // blocks while a descendant still holds focus (InlineDrawer does the same).
            onClick={(e) => {
              e.currentTarget.blur();
              onClose();
            }}
          />
        </div>
      </div>

      <div className={styles.body} ref={contentRef}>
        {!current && (
          <div className={styles.empty}>
            {t("capability.ppt_filler.preview.empty", {
              defaultValue: "No presentation yet. Ask the assistant to create one.",
            })}
          </div>
        )}
        {current && shownError && <div className={styles.error}>{shownError}</div>}
        {current && !shownError && isLoading && !objectUrl && (
          <div className={styles.loading}>
            {t("capability.ppt_filler.preview.loading", { defaultValue: "Loading preview…" })}
          </div>
        )}
        {current && !shownError && objectUrl && (
          <Document
            key={remountKey}
            file={objectUrl}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            onLoadError={(err: Error) => setLoadError(err?.message || loadErrorMsg)}
            loading={
              <div className={styles.loading}>
                {t("capability.ppt_filler.preview.loading", { defaultValue: "Loading preview…" })}
              </div>
            }
            error={<div className={styles.error}>{loadErrorMsg}</div>}
          >
            {Array.from({ length: numPages ?? 0 }, (_, i) => (
              <Page
                key={`page_${i + 1}`}
                pageNumber={i + 1}
                width={pageWidth}
                renderAnnotationLayer={false}
                renderTextLayer={false}
                className={styles.page}
              >
                <span className={styles.pageNumber} aria-hidden="true">
                  {i + 1}
                </span>
              </Page>
            ))}
          </Document>
        )}
      </div>
    </div>
  );
}
