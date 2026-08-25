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
import type { PDFDocumentProxy } from "pdfjs-dist";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { useTranslation } from "react-i18next";
import { useAuthToken } from "../security/AuthContext";
import styles from "./PdfStreamingDocumentViewer.module.css";

type Props = {
  documentUid: string;
};

// Resolved by Vite to the bundled pdf.js worker asset. Kept as a URL (not a
// `workerSrc` string) so we can spawn a fresh module Worker per Document mount.
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);

// Render pages at the full available width (minus a small scrollbar gutter) so
// the document exploits the whole preview surface — the drawer already provides
// the surrounding chrome/margins.
const PDF_SCALE = 1.0;
// Debounce (ms) for width-driven re-layout. A drag on the preview's resize
// handle fires the ResizeObserver every frame; re-rendering every page of a
// long PDF that often locks the UI. Coalesce to one reflow once the drag settles.
const RESIZE_DEBOUNCE_MS = 150;

// How far outside the scroll viewport a page is mounted as a real canvas (#2273).
// Only pages inside this band exist as a <Page>; every other page is a cheap,
// correctly-sized empty placeholder. This is what bounds memory: a rendered page
// canvas at ~800px wide costs several MB of bitmap, so mounting every page at
// once — the previous behavior — allocated gigabytes on a large PDF and took the
// browser tab down with it.
const PAGE_MOUNT_MARGIN_PX = 600;

// Placeholder aspect ratio (height / width) used until page 1 reports the
// document's real geometry. A4 portrait: being wrong costs one scrollbar
// adjustment on load, never a layout the user can act on.
const FALLBACK_PAGE_ASPECT_RATIO = 297 / 210;

// Above this page count the document is not rendered until the user asks for it.
// Virtualization already bounds the canvases, but one placeholder plus one
// IntersectionObserver entry per page is not free, and pdf.js still has to walk
// the whole page tree — so a pathological document stays opt-in rather than
// being the one shape that can still hurt.
const LARGE_DOCUMENT_PAGE_COUNT = 500;

// Above this file size the document is not handed to pdf.js *at all* until the
// user asks for it. This guard exists because the page-count one above cannot
// do the job on its own: `numPages` is only known from `onLoadSuccess`, i.e.
// after pdf.js has already parsed the document — and for some documents the
// parse itself is the expensive act it should be guarding (#2273):
//
// pdf.js validates `/Count` at open by fetching the LAST page's dict
// (`checkLastPage` → `getPage(numPages - 1)`, pdf.worker.mjs), and
// `Catalog.getPageDict` walks `/Kids` linearly, fetching every kid just to
// learn it is a one-page leaf. A document with a FLAT 3666-ref /Kids array —
// legal, and what naive generators emit — therefore fetches all 3666 page
// dicts at open; interleaved with their content streams they touch every chunk
// of a 50 MB file: 803 serial 64 KB range requests, ~48 s, the whole file read
// before the page-count guard could appear. The same page count in a balanced
// tree (what LaTeX/Word/Acrobat emit — intermediate /Count nodes let the walk
// skip subtrees unfetched) opens in 2 requests / ~1.3 MB, measured on a 91 MB
// file.
//
// Size is the only property of a document knowable before parsing it, so it is
// the only thing a pre-parse guard can key on. It is a proxy, not a measure:
// a 50 MB, 36-page image scan opens fine (36 kid fetches), while a smaller
// flat-tree document could still be slow. It is deliberately conservative —
// being asked to confirm a document that would have opened fine costs one click.
const LARGE_DOCUMENT_BYTES = 20 * 1024 * 1024;

// pdf.js transport options. Module-level so the object identity stays stable:
// a fresh object on every render makes react-pdf tear down and reload the whole
// document.
//
// Both flags are needed to actually fetch by byte range, and `disableStream` is
// the load-bearing one. pdf.js opens a full-file request first, and cancels it
// in favour of range requests only when streaming is off:
//
//     if (!this._isStreamingSupported && this._isRangeSupported) {
//       this.cancel(new AbortException("Streaming is disabled."));   // pdf.mjs
//     }
//
// With `disableStream: false` that request is never cancelled, so the whole
// document streams into memory *alongside* the range requests — a 50 MB PDF
// showed one 200 of 51.86 MB followed by 36 partial 206s. `disableAutoFetch`
// alone does not prevent this: it only suppresses the background prefetch of
// the remaining chunks once ranges are in use.
//
// `/raw_content/stream/{uid}` advertises `Accept-Ranges: bytes` and serves 206
// responses (content_controller.py), so pdf.js takes the range path. If a proxy
// ever strips that header — compressing `application/pdf` drops both it and
// `Content-Length` — pdf.js silently falls back to buffering the entire file.
//
// `rangeChunkSize` raises pdf.js's 64 KB default. On-demand fetching means every
// object pdf.js reaches for that is not yet local costs a round trip, and its
// open-time /Kids walk resolves them strictly one at a time (see
// LARGE_DOCUMENT_BYTES above): a flat-tree 3666-page PDF needed 803 sequential
// 64 KB requests (~48 s) to open, 54×1 MB (~26 s) with this setting. Fetching
// 1 MB per miss trades bytes for round trips — the right trade when the round
// trips are serialized — and costs nothing on well-formed documents, which
// only ever ask for a handful of chunks.
const PDF_OPTIONS = { disableAutoFetch: true, disableStream: true, rangeChunkSize: 1024 * 1024 };

/** Fold a batch of IntersectionObserver entries into the set of pages that
 * should currently hold a real canvas. Returns `prev` unchanged when nothing
 * moved, so a scroll that crosses no page boundary re-renders nothing. */
export function reduceMountedPages(
  prev: ReadonlySet<number>,
  entries: readonly { pageNumber: number; isIntersecting: boolean }[],
): ReadonlySet<number> {
  const next = new Set(prev);
  let changed = false;
  for (const { pageNumber, isIntersecting } of entries) {
    if (!pageNumber) continue;
    if (isIntersecting) {
      if (!next.has(pageNumber)) {
        next.add(pageNumber);
        changed = true;
      }
    } else if (next.delete(pageNumber)) {
      changed = true;
    }
  }
  return changed ? next : prev;
}

// Header-less by design: the two hosting contexts (DocumentViewerPage's own
// top bar, InlineDrawer's own title+close) already provide chrome, so this
// component owns only the PDF surface itself.
export const PdfStreamingDocumentViewer: React.FC<Props> = ({ documentUid }) => {
  const { t } = useTranslation();
  const token = useAuthToken();
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  // Pages currently mounted as real canvases — see PAGE_MOUNT_MARGIN_PX.
  const [mountedPages, setMountedPages] = useState<ReadonlySet<number>>(() => new Set([1]));
  const [pageAspectRatio, setPageAspectRatio] = useState(FALLBACK_PAGE_ASPECT_RATIO);
  // Set once the user opts into rendering a document past LARGE_DOCUMENT_PAGE_COUNT.
  const [largeDocumentConfirmed, setLargeDocumentConfirmed] = useState(false);

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
      // can win first.
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
  }, [reloadKey]);

  const contentRef = useRef<HTMLDivElement | null>(null);
  const [pageWidth, setPageWidth] = useState<number>(800);
  useEffect(() => {
    if (!contentRef.current) return;
    const el = contentRef.current;
    const computeWidth = () => Math.floor(Math.max(320, Math.floor(el.clientWidth - 16)) * PDF_SCALE);
    // Seed synchronously so the first paint is already at the right width.
    setPageWidth(computeWidth());
    // Debounced re-layout: while the user drags the preview wider/narrower the
    // observer fires continuously — only apply the new width (and re-render the
    // pages once) after the drag has paused. Skip a no-op update so an observer
    // tick that didn't actually change the width can't churn the page list.
    let timer: number | null = null;
    const ro = new ResizeObserver(() => {
      if (timer !== null) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        setPageWidth((prev) => {
          const next = computeWidth();
          return next === prev ? prev : next;
        });
      }, RESIZE_DEBOUNCE_MS);
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (timer !== null) window.clearTimeout(timer);
    };
  }, []);

  const pdfUrl = useMemo(() => {
    if (!documentUid) return null;
    return `/knowledge-flow/v1/raw_content/stream/${documentUid}`;
  }, [documentUid]);

  const authHeader = useMemo(() => (token ? (token.startsWith("Bearer ") ? token : `Bearer ${token}`) : null), [token]);

  const fileProp = useMemo(() => {
    if (!pdfUrl) return null;
    // If we have a bearer, send it; otherwise allow cookies (same-site backend).
    return authHeader
      ? { url: pdfUrl, httpHeaders: { Authorization: authHeader } }
      : { url: pdfUrl, withCredentials: true };
  }, [pdfUrl, authHeader]);

  // How big is this document? Asked *before* <Document> mounts, so the size
  // guard can fire without pdf.js ever touching the file (see LARGE_DOCUMENT_BYTES).
  //
  // A one-byte ranged GET is the cheapest way to find out: the 206 carries
  // `Content-Range: bytes 0-0/<total>`. The endpoint exposes no HEAD route, and
  // the metadata that holds the size is not plumbed down to this component —
  // this needs neither.
  //
  // A failed or unparseable probe is not fatal: `sizeBytes` stays null, the
  // guard does not fire, and the viewer behaves exactly as it did before. Being
  // unable to measure a document is not a reason to refuse to show it.
  const [sizeBytes, setSizeBytes] = useState<number | null>(null);
  const [sizeProbed, setSizeProbed] = useState(false);
  useEffect(() => {
    if (!pdfUrl) return;
    let cancelled = false;
    setSizeBytes(null);
    setSizeProbed(false);
    fetch(pdfUrl, {
      headers: { Range: "bytes=0-0", ...(authHeader ? { Authorization: authHeader } : {}) },
      credentials: authHeader ? "same-origin" : "include",
    })
      .then((res) => {
        // "bytes 0-0/52428800" → 52428800. A proxy that rewrites or drops the
        // header lands on NaN, which reads as "unknown" below.
        const total = Number(res.headers.get("Content-Range")?.split("/")[1]);
        if (!cancelled && Number.isFinite(total) && total > 0) setSizeBytes(total);
      })
      .catch(() => {
        // Probe failure is non-fatal by design — fall through to the unguarded path.
      })
      .finally(() => {
        if (!cancelled) setSizeProbed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [pdfUrl, authHeader]);

  // Lets a late-resolving page-geometry probe tell whether it still belongs to
  // the document on screen (see onDocumentLoadSuccess).
  const activeUidRef = useRef(documentUid);
  useEffect(() => {
    activeUidRef.current = documentUid;
  }, [documentUid]);

  const onDocumentLoadSuccess = (pdf: PDFDocumentProxy) => {
    const loadedUid = documentUid;
    setNumPages(pdf.numPages);
    setIsLoading(false);
    // Size every placeholder from the document's own page 1 rather than the A4
    // fallback, so the scrollbar is honest for landscape/A3/slide-shaped PDFs.
    pdf
      .getPage(1)
      .then((page) => {
        if (activeUidRef.current !== loadedUid) return;
        const viewport = page.getViewport({ scale: 1 });
        if (viewport.width > 0 && viewport.height > 0) {
          setPageAspectRatio(viewport.height / viewport.width);
        }
      })
      .catch(() => {
        // Geometry is an optimisation, not a requirement — keep the fallback.
      });
  };
  const onDocumentLoadError = (err: any) => {
    setLoadError(err?.message || "Failed to load PDF.");
    setIsLoading(false);
  };

  useEffect(() => {
    setIsLoading(true);
    setLoadError(null);
    setNumPages(null);
    setMountedPages(new Set([1]));
    setPageAspectRatio(FALLBACK_PAGE_ASPECT_RATIO);
    setLargeDocumentConfirmed(false);
    setReloadKey((k) => k + 1); // remount Document to reset PDF.js
  }, [documentUid]);

  const isLargeDocument = numPages !== null && numPages > LARGE_DOCUMENT_PAGE_COUNT;
  const showPages = numPages !== null && (!isLargeDocument || largeDocumentConfirmed);

  // The size guard withholds the <Document> mount entirely; the page-count guard
  // above can only withhold the pages, pdf.js having already parsed by then.
  const isLargeFile = sizeBytes !== null && sizeBytes > LARGE_DOCUMENT_BYTES;
  const fileGuardBlocking = isLargeFile && !largeDocumentConfirmed;

  // Mount/unmount page canvases as their placeholders enter and leave the scroll
  // viewport. The placeholders themselves never unmount for a given document, so
  // one observer set up here covers the whole page list — no per-page ref
  // plumbing, and no re-observing on every scroll tick.
  useEffect(() => {
    const root = contentRef.current;
    if (!root || !showPages) return;
    if (typeof IntersectionObserver === "undefined") {
      // No observer available (older runtime, test env): fall back to mounting
      // everything rather than showing a document of empty placeholders.
      setMountedPages(new Set(Array.from({ length: numPages ?? 0 }, (_, i) => i + 1)));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        setMountedPages((prev) =>
          reduceMountedPages(
            prev,
            entries.map((entry) => ({
              pageNumber: Number((entry.target as HTMLElement).dataset.pageNumber),
              isIntersecting: entry.isIntersecting,
            })),
          ),
        );
      },
      { root, rootMargin: `${PAGE_MOUNT_MARGIN_PX}px 0px` },
    );
    root.querySelectorAll<HTMLElement>("[data-page-number]").forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [numPages, showPages, reloadKey]);

  // Rebuild the slot list only when the page count, the (debounced) width, the
  // measured geometry or the mounted window actually changes — unrelated state
  // updates (loading flags, worker churn) must not touch the page list.
  const pageSlots = useMemo(() => {
    if (!showPages) return [];
    const placeholderHeight = Math.round(pageWidth * pageAspectRatio);
    return Array.from({ length: numPages ?? 0 }, (_, i) => {
      const pageNumber = i + 1;
      return (
        <div
          key={`page_${pageNumber}`}
          className={styles.pageSlot}
          data-page-number={pageNumber}
          style={{ minHeight: `${placeholderHeight}px` }}
        >
          {mountedPages.has(pageNumber) && (
            <Page
              pageNumber={pageNumber}
              width={pageWidth}
              renderAnnotationLayer
              renderTextLayer={false} // faster by default
            />
          )}
        </div>
      );
    });
  }, [numPages, pageWidth, pageAspectRatio, mountedPages, showPages]);

  const guardPanel = (body: string) => (
    <div className={styles.guard} role="status">
      <p className={styles.guardTitle}>{t("rework.resources.preview.pdf.largeTitle")}</p>
      <p className={styles.guardBody}>{body}</p>
      <button type="button" className={styles.guardAction} onClick={() => setLargeDocumentConfirmed(true)}>
        {t("rework.resources.preview.pdf.largeConfirm")}
      </button>
    </div>
  );

  return (
    <div ref={contentRef} className={styles.viewer}>
      {!isLoading && loadError && <p className={styles.error}>{loadError}</p>}

      {/* The size probe is one request for one byte, but <Document> must not mount
          before it answers — mounting is the expensive act this guard prevents. */}
      {fileProp && !loadError && !sizeProbed && (
        <p className={styles.loading}>{t("rework.resources.preview.loading")}</p>
      )}

      {fileProp &&
        !loadError &&
        sizeProbed &&
        fileGuardBlocking &&
        guardPanel(
          t("rework.resources.preview.pdf.largeBodyBytes", {
            megabytes: Math.round((sizeBytes ?? 0) / (1024 * 1024)),
          }),
        )}

      {fileProp && !loadError && sizeProbed && !fileGuardBlocking && (
        <Document
          key={reloadKey}
          className={styles.document}
          file={fileProp}
          options={PDF_OPTIONS}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={onDocumentLoadError}
          loading={<p className={styles.loading}>{t("rework.resources.preview.loading")}</p>}
          error={<p className={styles.error}>{t("rework.resources.preview.pdf.loadFailed")}</p>}
        >
          {isLargeDocument &&
            !largeDocumentConfirmed &&
            guardPanel(t("rework.resources.preview.pdf.largeBody", { pages: numPages ?? 0 }))}
          {pageSlots}
        </Document>
      )}

      {!fileProp && !loadError && <p className={styles.error}>{t("rework.resources.preview.pdf.unavailable")}</p>}
    </div>
  );
};

export default PdfStreamingDocumentViewer;
