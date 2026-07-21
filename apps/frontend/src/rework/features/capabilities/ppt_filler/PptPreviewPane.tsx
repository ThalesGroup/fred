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
// The ppt_filler capability's side panel (CapabilitySidePanel) — a read-only,
// floating-card pane (Kea parity) that renders the filled deck as a PDF. It
// reads the "current" preview from the slice (set by the chat cards), fetches
// the bytes with the live bearer (usePptPreview), and draws every page
// vertically with react-pdf. Hosted headless: the InlineDrawer chrome is
// hidden, so this pane's own header (title + download + close) is the ONLY
// chrome — exactly one close button.
//
// pdf.js worker rule (this exact bug was fought before — see `utils/pdfWorker.ts`
// for the full rationale): each `<Document>` mount gets its OWN fresh module
// worker, provisioned during render (useMemo, keyed on the remount key) so it
// is in place before react-pdf reads GlobalWorkerOptions. The old worker is
// NOT terminated by us — react-pdf's own `loadingTask.destroy()` tears it down
// with its Document. Terminating it ourselves leaves `workerPort` pointing at
// a dead worker under StrictMode's mount→cleanup→remount (the pane then hangs
// on "Loading preview…" forever) and races the next mount with
// "PDFWorker.fromPort - the worker is being destroyed".

import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { configurePdfWorkerPort } from "../../../utils/pdfWorker";
import type { CapabilitySidePanelProps } from "../types";
import { selectCurrentPreview } from "./pptPreviewSlice";
import { usePptPreview } from "./usePptPreview";
import PptxDownloadButton from "./PptxDownloadButton";
import styles from "./PptPreviewPane.module.css";

const PDF_SCALE = 0.95;

export function PptPreviewPane({ onClose }: CapabilitySidePanelProps) {
  const { t } = useTranslation();
  const current = useSelector(selectCurrentPreview);
  const { objectUrl, isLoading, error } = usePptPreview(current);

  const [numPages, setNumPages] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Fit the page width to the pane, less padding, tracking resizes (the pane
  // is resizable, so pages re-fit live while the user drags).
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

  // A re-fill (or switching decks) changes this key → react-pdf remounts the
  // <Document> with a freshly provisioned worker.
  const remountKey = current ? `${current.preview_id}:${current.version}` : "none";

  // Give this <Document> mount its own pdf.js worker. Running in useMemo
  // (during render, before the child <Document> mounts) means the worker is in
  // place when react-pdf reads GlobalWorkerOptions; the previous Document's
  // teardown destroys its OWN worker, so no destroy can race this mount.
  useMemo(() => configurePdfWorkerPort(), [remountKey]);

  useEffect(() => {
    setNumPages(null);
    setLoadError(null);
  }, [remountKey]);

  const untitled = t("capability.ppt_filler.preview.untitled", { defaultValue: "Presentation" });
  const closeLabel = t("capability.ppt_filler.preview.close", { defaultValue: "Close preview" });
  const loadErrorMsg = t("capability.ppt_filler.preview.loadError", { defaultValue: "Failed to load preview." });

  const shownError = error ? loadErrorMsg : loadError;

  return (
    <div className={styles.pane}>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <Icon category="outlined" type="slideshow" />
          <span className={styles.title}>{current?.title || untitled}</span>
        </div>
        {current?.pptx_download_url && (
          <PptxDownloadButton href={current.pptx_download_url} fileName={current.file_name} />
        )}
        <IconButton
          color="on-surface"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "close" }}
          onClick={onClose}
          aria-label={closeLabel}
        />
      </div>

      <div className={styles.body} ref={contentRef}>
        {!current && (
          <div className={styles.empty}>
            {t("capability.ppt_filler.preview.empty", {
              defaultValue: "No preview yet. Ask the assistant to fill a deck.",
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
                renderAnnotationLayer
                // Text layer on (Kea parity): overlays invisible positioned
                // spans on the canvas so slide text can be selected/copied.
                renderTextLayer
                className={styles.page}
              />
            ))}
          </Document>
        )}
      </div>
    </div>
  );
}
