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
 * Freshness: each fill mints a NEW presigned URL (fresh signature + different object) and a
 * new `version`, which is the react-pdf remount key. A re-fill therefore fetches the latest
 * deck instead of showing a browser-cached stale one. (The version is NOT appended to the
 * URL — a presigned signature covers the whole query string, so an extra `?v=` would 403.)
 *
 * Built with the rework design system for the header (CSS modules + shared atoms); the PDF
 * body uses react-pdf like the existing viewer.
 */

import { CircularProgress } from "@mui/material";
import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import type { UsePptPreview } from "./usePptPreview.ts";
import PptxDownloadButton from "./PptxDownloadButton.tsx";
// Shared pdf.js worker plumbing: hands each <Document> a FRESH module worker so remounting
// (opening a second preview / re-filling the open deck) never races a worker teardown and
// throws "the worker is being destroyed" — see pdfWorker.ts for the full rationale.
import { configurePdfWorkerPort } from "../../common/pdfWorker.ts";
import styles from "./PptPreviewPane.module.css";

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

  // Give this <Document> mount its own pdf.js worker. Running in useMemo (during render,
  // before the child <Document> mounts) means the worker is in place when react-pdf reads
  // GlobalWorkerOptions, and a new remountKey (switch deck / re-fill) provisions a fresh
  // worker so the previous Document's teardown can't race this one's start.
  useMemo(() => configurePdfWorkerPort(), [remountKey]);

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
          <PptxDownloadButton href={selected.pptx_download_url} fileName={selected.file_name} />
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
            onLoadError={(err) =>
              setLoadError(err?.message || t("chat.pptPreview.loadError", "Failed to load preview."))
            }
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
