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
 * Durability (why we presign LAZILY): a presigned URL expires (~1h), but the `ppt_preview`
 * part is persisted in the conversation. Baking a presigned URL into it means reopening the
 * chat later hands react-pdf an expired signature → 403 ("Unexpected server response (403)
 * while retrieving PDF"). Instead the part carries a durable KF href (`pdf_presign_url`);
 * this pane calls it (with the bearer) each time it opens/remounts to mint a FRESH presigned
 * URL, then points react-pdf at that. Mirrors how the `.pptx` download stays durable.
 *
 * Freshness: `version` is the react-pdf remount key. A re-fill (or reopen) changes the
 * remount key → we re-presign and refetch instead of showing a browser-cached stale deck.
 * (The version is NOT appended to the presigned URL — a presigned signature covers the whole
 * query string, so an extra `?v=` would 403.)
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
import { useLazyPresignedHrefQuery } from "../../slices/knowledgeFlow/knowledgeFlowApi.blob.ts";
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

  // `version` is the react-pdf remount key so a re-fill (or switching decks) forces a fresh
  // <Document>. The URL is minted LAZILY below — the part carries a durable presign href, not
  // a frozen presigned URL, so reopening an old chat re-presigns instead of 403-ing on an
  // expired signature. We must NOT append our own query param to the minted URL — the
  // presigned signature covers the whole query string, so an extra `?v=` → 403.
  const remountKey = selected ? `${selected.preview_id}:${selected.version}` : "none";

  // Mint a fresh presigned PDF URL from the durable KF href each time the shown deck changes
  // (remount key) — the persisted href never expires; the URL it returns is short-lived, so
  // we fetch it at render time rather than trusting a stored one.
  const [mintPresign] = useLazyPresignedHrefQuery();
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!selected?.pdf_presign_url) {
      setFileUrl(null);
      return;
    }
    let cancelled = false;
    setFileUrl(null);
    mintPresign({ href: selected.pdf_presign_url })
      .unwrap()
      .then((res) => {
        if (!cancelled) setFileUrl(res.url);
      })
      .catch((err) => {
        if (!cancelled)
          setLoadError(err?.message || t("chat.pptPreview.loadError", "Failed to load preview."));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remountKey]);

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
                // Text layer on: overlays invisible positioned spans on the canvas so slide
                // text can be selected/copied (and browser-searched). CSS is imported above.
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
