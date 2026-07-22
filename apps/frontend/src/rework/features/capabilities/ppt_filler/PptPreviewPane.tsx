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
// that renders the filled deck as a PDF. It reads the "current" preview from the
// slice (set by a card's Open button / auto-open), fetches the bytes with the live
// bearer (usePptPreview), and draws every page vertically with react-pdf.
//
// pdf.js worker rule (this exact bug was fought before — see the Kea `pdfWorker.ts`
// rationale): each `<Document>` mount MUST get its OWN module worker. A single
// shared `GlobalWorkerOptions.workerPort` reused across remounts throws
// "PDFWorker.fromPort - the worker is being destroyed" when a second preview opens
// or the open deck is re-filled, because react-pdf's unmount `destroy()` races the
// next mount on the same port. So we provision a FRESH worker per remount key (in a
// useMemo, before the child `<Document>` reads GlobalWorkerOptions) and terminate
// that exact instance on unmount / key change. We deliberately do NOT set a
// module-level shared workerPort, and we do NOT rely on `workerSrc` alone (that
// yields a "fake worker" that fails to import the bundled asset).

import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import type { CapabilitySidePanelProps } from "../types";
import { selectCurrentPreview } from "./pptPreviewSlice";
import { usePptPreview } from "./usePptPreview";
import PptxDownloadButton from "./PptxDownloadButton";
import styles from "./PptPreviewPane.module.css";

const PDF_SCALE = 0.95;

// Resolved by Vite to the bundled pdf.js worker asset. Kept as a URL (not a
// `workerSrc` string) so we can spawn a fresh module Worker per Document mount.
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);

export function PptPreviewPane({ onClose }: CapabilitySidePanelProps) {
  const { t } = useTranslation();
  const current = useSelector(selectCurrentPreview);
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

  // A re-fill (or switching decks) changes this key → react-pdf remounts the
  // <Document> and we provision a fresh worker for it.
  const remountKey = current ? `${current.preview_id}:${current.version}` : "none";

  // Provision a fresh worker for THIS remount before the child <Document> reads
  // GlobalWorkerOptions (useMemo runs during render, ahead of child effects). The
  // effect below terminates the exact instance this run created.
  const workerRef = useRef<Worker | null>(null);
  useMemo(() => {
    if (typeof Worker === "undefined") {
      pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl.toString();
      workerRef.current = null;
      return;
    }
    const worker = new Worker(pdfWorkerUrl, { type: "module" });
    workerRef.current = worker;
    pdfjs.GlobalWorkerOptions.workerPort = worker;
  }, [remountKey]);

  // Terminate the worker created for the current key once it is no longer the
  // active port (the next key's useMemo has already swapped a fresh one in by
  // the time this cleanup fires). Guarding on the ACTIVE port matters under
  // StrictMode: its simulated unmount runs this cleanup while the worker is
  // still current and no re-render re-provisions one — unconditionally
  // terminating here left react-pdf waiting forever on a dead worker
  // (endless "Loading preview…"). The still-active worker is deliberately
  // left running on the final unmount, like the legacy pane.
  useEffect(() => {
    const worker = workerRef.current;
    return () => {
      if (worker && pdfjs.GlobalWorkerOptions.workerPort !== worker) {
        worker.terminate();
      }
    };
  }, [remountKey]);

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
