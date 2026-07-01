// Copyright Thales 2025
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

/**
 * PptPreviewPane
 * --------------
 * The read-only right-hand pane that renders a filled deck as a PDF, mirroring the
 * writable-document pane's shell (header + scrollable body) but with react-pdf instead of
 * an editor. The PDF is fetched directly from a presigned, Range-capable URL, so the
 * backend never proxies the bytes.
 *
 * Freshness: the deck's `version` is appended to the URL (`?v=…`) AND used as the react-pdf
 * remount key. A re-fill carries a new version → a new URL → a fresh fetch and a remount, so
 * the open pane updates to the latest deck instead of showing a browser-cached stale one.
 *
 * Built with the rework design system for the header (CSS modules + shared atoms); the PDF
 * body uses react-pdf like the existing viewer.
 */

import { CircularProgress } from "@mui/material";
import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import type { UsePptPreview } from "./usePptPreview.ts";
import styles from "./PptPreviewPane.module.css";

// React-PDF requires workerSrc to be configured in the same module that renders
// <Document>/<Page>; otherwise its default bare specifier can win at runtime.
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);
if (typeof Worker !== "undefined") {
  pdfjs.GlobalWorkerOptions.workerPort = new Worker(pdfWorkerUrl, { type: "module" });
} else {
  pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl.toString();
}

const PDF_SCALE = 0.95;

export default function PptPreviewPane({ controller }: { controller: UsePptPreview }) {
  const { t } = useTranslation();
  const { selected, closePane } = controller;

  const [numPages, setNumPages] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

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

  // Freshness comes from the presigned URL itself: each fill mints a NEW presigned URL
  // (fresh signature/date + different object), and `version` is the react-pdf remount key
  // so a re-fill forces a fresh <Document> fetch. We must NOT append our own query param —
  // the presigned signature covers the whole query string, so an extra `?v=` → 403.
  const fileUrl = selected ? selected.pdf_url : null;
  const remountKey = selected ? `${selected.preview_id}:${selected.version}` : "none";

  useEffect(() => {
    setNumPages(null);
    setLoadError(null);
  }, [remountKey]);

  if (!selected) return null;

  const untitled = t("chat.pptPreview.untitled", "Presentation");
  const closeLabel = t("chat.pptPreview.close", "Close preview");

  return (
    <div className={styles.pane}>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <Icon category="outlined" type="slideshow" />
          <span className={styles.title}>{selected.title || untitled}</span>
        </div>
        {selected.pptx_download_url && (
          <a
            className={styles.download}
            href={selected.pptx_download_url}
            download={selected.file_name ?? undefined}
          >
            <Icon category="outlined" type="download" />
          </a>
        )}
        <IconButton
          color="on-surface"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "close" }}
          onClick={closePane}
          aria-label={closeLabel}
        />
      </div>

      <div className={styles.body} ref={contentRef}>
        {loadError && <div className={styles.error}>{loadError}</div>}
        {fileUrl && !loadError && (
          <Document
            key={remountKey}
            file={fileUrl}
            onLoadSuccess={({ numPages }) => setNumPages(numPages)}
            onLoadError={(err) => setLoadError(err?.message || t("chat.pptPreview.loadError", "Failed to load preview."))}
            loading={<CircularProgress size={22} />}
            error={<div className={styles.error}>{t("chat.pptPreview.loadError", "Failed to load preview.")}</div>}
          >
            {Array.from({ length: numPages ?? 0 }, (_, i) => (
              <Page
                key={`page_${i + 1}`}
                pageNumber={i + 1}
                width={pageWidth}
                renderAnnotationLayer
                renderTextLayer={false}
                className={styles.page}
              />
            ))}
          </Document>
        )}
      </div>
    </div>
  );
}
