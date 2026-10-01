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

// PptxPreviewPane — read-only PDF preview side panel for a generated deck.
// Mirrors ppt_filler's PptPreviewPane exactly, including its pdf.js
// worker-per-mount lifecycle handling — see that file's header comment for
// the full worker-lifecycle rationale (the "PDFWorker.fromPort" race).

import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import type { CapabilitySidePanelProps } from "../types";
import { useSessionPptxPreview } from "./useSessionPptxPreview";
import { usePptxPreview } from "./usePptxPreview";
import PptxDownloadButton from "./PptxDownloadButton";
import styles from "./PptxPreviewPane.module.css";

const PDF_SCALE = 0.95;

/** react-pdf remount key when this conversation has no deck. */
const NO_PREVIEW_KEY = "none";

// Resolved by Vite to the bundled pdf.js worker asset. Kept as a URL (not a
// `workerSrc` string) so we can spawn a fresh module Worker per Document mount.
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);

export function PptxPreviewPane({ onClose }: CapabilitySidePanelProps) {
  const { t } = useTranslation();
  const current = useSessionPptxPreview();
  const { objectUrl, isLoading, error } = usePptxPreview(current);

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

  // Remount key: includes the blob URL because pdf.js caches one PDFWorker
  // per port, and keying on the deck alone would let a new load reuse a
  // still-tearing-down port (see ppt_filler's PptPreviewPane).
  const remountKey = current ? `${current.preview_id}:${current.version}:${objectUrl ?? ""}` : NO_PREVIEW_KEY;

  // Fresh worker per remount, provisioned before the child <Document> reads
  // GlobalWorkerOptions (useMemo runs ahead of child effects).
  const workerRef = useRef<Worker | null>(null);
  useMemo(() => {
    if (!objectUrl) {
      // Releasing the port lets an outgoing worker's cleanup see itself
      // orphaned and terminate immediately rather than lingering.
      pdfjs.GlobalWorkerOptions.workerPort = null;
      workerRef.current = null;
      return;
    }
    if (typeof Worker === "undefined") {
      pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl.toString();
      workerRef.current = null;
      return;
    }
    const worker = new Worker(pdfWorkerUrl, { type: "module" });
    workerRef.current = worker;
    pdfjs.GlobalWorkerOptions.workerPort = worker;
  }, [remountKey]);

  // True while this instance is mounted — lets the deferred cleanup below
  // tell a StrictMode dev double-invoke from a real final unmount.
  const isAliveRef = useRef(true);
  useEffect(() => {
    isAliveRef.current = true;
    return () => {
      isAliveRef.current = false;
    };
  }, []);

  // Terminate this key's worker only once genuinely orphaned, deferred one
  // tick so a StrictMode remount (or another consumer) can reclaim the port
  // first — see ppt_filler's PptPreviewPane for the full race rationale.
  useEffect(() => {
    const worker = workerRef.current;
    return () => {
      if (!worker) return;
      if (pdfjs.GlobalWorkerOptions.workerPort !== worker) {
        worker.terminate();
        return;
      }
      setTimeout(() => {
        if (pdfjs.GlobalWorkerOptions.workerPort !== worker) {
          // Some other consumer claimed the port in the meantime — orphaned now.
          worker.terminate();
        } else if (!isAliveRef.current) {
          // Still nobody claimed it and this instance never came back — final unmount.
          worker.terminate();
        }
      }, 0);
    };
  }, [remountKey]);

  useEffect(() => {
    setNumPages(null);
    setLoadError(null);
  }, [remountKey]);

  const untitled = t("capability.pptx_generator.preview.untitled", { defaultValue: "Presentation" });
  const loadErrorMsg = t("capability.pptx_generator.preview.loadError", { defaultValue: "Failed to load preview." });

  const shownError = error ? loadErrorMsg : loadError;

  return (
    <div className={styles.pane}>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <Icon category="outlined" type="co_present" />
          <span className={styles.title}>{current?.title || untitled}</span>
        </div>
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

      <div className={styles.body} ref={contentRef}>
        {!current && (
          <div className={styles.empty}>
            {t("capability.pptx_generator.preview.empty", {
              defaultValue: "No preview yet. Ask the assistant to generate a deck.",
            })}
          </div>
        )}
        {current && shownError && <div className={styles.error}>{shownError}</div>}
        {current && !shownError && isLoading && !objectUrl && (
          <div className={styles.loading}>
            {t("capability.pptx_generator.preview.loading", { defaultValue: "Loading preview…" })}
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
                {t("capability.pptx_generator.preview.loading", { defaultValue: "Loading preview…" })}
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
              />
            ))}
          </Document>
        )}
      </div>
    </div>
  );
}
