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

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { useAuthToken } from "../security/AuthContext";
import styles from "./PdfStreamingDocumentViewer.module.css";

type Props = {
  documentUid: string;
};

// Resolved by Vite to the bundled pdf.js worker asset. Kept as a URL (not a
// `workerSrc` string) so we can spawn a fresh module Worker per Document mount.
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);

const PDF_SCALE = 0.8;

// Header-less by design: the two hosting contexts (DocumentViewerPage's own
// top bar, InlineDrawer's own title+close) already provide chrome, so this
// component owns only the PDF surface itself.
export const PdfStreamingDocumentViewer: React.FC<Props> = ({ documentUid }) => {
  const token = useAuthToken();
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // pdf.js worker rule (see PptPreviewPane.tsx for the full rationale): each
  // <Document> mount MUST get its OWN module worker. A single shared
  // GlobalWorkerOptions.workerPort reused across remounts throws "PDFWorker.fromPort
  // - the worker is being destroyed" when this viewer's Document remounts (on
  // documentUid change) while another react-pdf consumer's unmount destroy() is
  // still racing the same port. Provision a fresh worker per remount key, and only
  // terminate it once it is no longer the active port.
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
  }, [reloadKey]);

  // Tracks whether this component instance is currently mounted, independent of
  // reloadKey churn. StrictMode double-invokes effects (mount, cleanup, remount)
  // synchronously in dev, so a cleanup can't tell "final unmount" from a StrictMode
  // drill by itself — the drill flips this back to true before the deferred check
  // below ever runs.
  const isAliveRef = useRef(true);
  useEffect(() => {
    isAliveRef.current = true;
    return () => {
      isAliveRef.current = false;
    };
  }, []);

  useEffect(() => {
    const worker = workerRef.current;
    return () => {
      if (!worker) return;
      if (pdfjs.GlobalWorkerOptions.workerPort !== worker) {
        // A newer key's worker already took over the active port — this one is
        // orphaned, safe to terminate now.
        worker.terminate();
        return;
      }
      // Still the active port at cleanup time: either a StrictMode dev drill (about
      // to remount) or the real final unmount (no next key coming). Defer one tick
      // so a genuine remount's isAliveRef flip, or another consumer's port swap,
      // can win first; terminate only if neither happened by then.
      setTimeout(() => {
        if (!isAliveRef.current && pdfjs.GlobalWorkerOptions.workerPort === worker) {
          worker.terminate();
        }
      }, 0);
    };
  }, [reloadKey]);

  const contentRef = useRef<HTMLDivElement | null>(null);
  const [pageWidth, setPageWidth] = useState<number>(800);
  useEffect(() => {
    if (!contentRef.current) return;
    const el = contentRef.current;
    const ro = new ResizeObserver(() => {
      const base = Math.max(320, Math.floor(el.clientWidth - 24));
      setPageWidth(Math.floor(base * PDF_SCALE));
    });
    ro.observe(el);
    const base = Math.max(320, Math.floor(el.clientWidth - 24));
    setPageWidth(Math.floor(base * PDF_SCALE));
    return () => ro.disconnect();
  }, []);

  const pdfUrl = useMemo(() => {
    if (!documentUid) return null;
    return `/knowledge-flow/v1/raw_content/stream/${documentUid}`;
  }, [documentUid]);

  const fileProp = useMemo(() => {
    if (!pdfUrl) return null;
    // If we have a bearer, send it; otherwise allow cookies (same-site backend).
    return token
      ? { url: pdfUrl, httpHeaders: { Authorization: token.startsWith("Bearer ") ? token : `Bearer ${token}` } }
      : { url: pdfUrl, withCredentials: true };
  }, [pdfUrl, token]);

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    setIsLoading(false);
  };
  const onDocumentLoadError = (err: any) => {
    setLoadError(err?.message || "Failed to load PDF.");
    setIsLoading(false);
  };

  useEffect(() => {
    setIsLoading(true);
    setLoadError(null);
    setNumPages(null);
    setReloadKey((k) => k + 1); // remount Document to reset PDF.js
  }, [documentUid]);

  return (
    <div ref={contentRef} className={styles.viewer}>
      {!isLoading && loadError && <p className={styles.error}>{loadError}</p>}

      {fileProp && !loadError && (
        <Document
          key={reloadKey}
          file={fileProp}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={onDocumentLoadError}
          loading={<p className={styles.loading}>Loading…</p>}
          error={<p className={styles.error}>Failed to load PDF document.</p>}
        >
          {Array.from({ length: numPages ?? 0 }, (_, i) => (
            <Page
              key={`page_${i + 1}`}
              pageNumber={i + 1}
              width={pageWidth}
              renderAnnotationLayer
              renderTextLayer={false} // faster by default
            />
          ))}
        </Document>
      )}

      {!fileProp && !loadError && <p className={styles.error}>Document content is unavailable.</p>}
    </div>
  );
};

export default PdfStreamingDocumentViewer;
