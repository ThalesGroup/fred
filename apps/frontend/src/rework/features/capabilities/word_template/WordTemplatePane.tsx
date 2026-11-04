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

// The word_template side panel: a "Rédaction" tab (the document's parts,
// edited in place) and an "Aperçu" tab (PDF preview), plus the .docx download.
// Both tabs stay mounted, so the preview shows at once and an open editor
// keeps its draft.
//
// pdf.js: each <Document> mount gets its own worker (as PptPreviewPane); a
// shared workerPort reused across remounts throws "the worker is being destroyed".

import { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { selectCapabilityBaseUrl, type CapabilityRoutingState } from "../../../../common/capabilityRoutingSlice";
import type { CapabilitySidePanelProps } from "../types";
import { useOpenSessionId } from "../useOpenSessionId";
import { CAPABILITY_ID } from "./api/wordTemplateCapabilityApi";
import { downloadSessionDocx, wordTemplateErrorKind } from "./sessionDocument";
import { resolveImagePreview, WordTemplateImagesContext } from "./sessionImages";
import { useWordTemplatePreview } from "./useWordTemplatePreview";
import { WordTemplateEditor } from "./WordTemplateEditor";
import styles from "./WordTemplatePane.module.css";

const PDF_SCALE = 0.95;
const DOCX_FILE_NAME = "document.docx";
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);

type PaneTab = "write" | "preview";

export function WordTemplatePane({ onClose }: CapabilitySidePanelProps) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const sessionId = useOpenSessionId();
  const baseUrl = useSelector((state: { capabilityRouting: CapabilityRoutingState }) =>
    selectCapabilityBaseUrl(state, CAPABILITY_ID),
  );
  const { objectUrl, isLoading, error, version, attachedFilename, refresh } = useWordTemplatePreview(
    baseUrl,
    sessionId,
  );
  // `img:` references in the editor need an authenticated fetch.
  const resolveImage = useMemo(() => resolveImagePreview(baseUrl, sessionId || null), [baseUrl, sessionId]);
  const [isDownloading, setIsDownloading] = useState(false);
  const [tab, setTab] = useState<PaneTab>("write");

  // Each conversation opens on "Rédaction".
  useEffect(() => {
    setTab("write");
  }, [sessionId]);

  const [numPages, setNumPages] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const contentRef = useRef<HTMLDivElement | null>(null);
  const [pageWidth, setPageWidth] = useState<number>(600);
  useEffect(() => {
    if (!contentRef.current) return;
    const el = contentRef.current;
    const measure = () => setPageWidth(Math.floor(Math.max(280, Math.floor(el.clientWidth - 24)) * PDF_SCALE));
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    measure();
    return () => ro.disconnect();
  }, []);

  const remountKey = objectUrl ?? "none";
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- provision once per remountKey
  }, [remountKey]);

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
        worker.terminate();
        return;
      }
      setTimeout(() => {
        if (pdfjs.GlobalWorkerOptions.workerPort !== worker || !isAliveRef.current) worker.terminate();
      }, 0);
    };
  }, [remountKey]);

  useEffect(() => {
    setNumPages(null);
    setLoadError(null);
  }, [remountKey]);

  const handleDownload = async () => {
    if (!baseUrl || !sessionId) return;
    setIsDownloading(true);
    try {
      await downloadSessionDocx(baseUrl, sessionId, DOCX_FILE_NAME);
    } catch (err) {
      const e = err as Error & { status?: number; detail?: string };
      showError({
        summary: t("capability.word_template.preview.downloadError"),
        detail: t(`capability.word_template.preview.error.${wordTemplateErrorKind(e)}`),
      });
    } finally {
      setIsDownloading(false);
    }
  };

  const loadErrorMsg = t("capability.word_template.preview.error.generic");
  const loadingMsg = t("capability.word_template.preview.loading");
  const shownError = error ? t(`capability.word_template.preview.error.${wordTemplateErrorKind(error)}`) : loadError;
  const hasDocument = version !== null;
  const activeTab: PaneTab = hasDocument ? tab : "preview";

  return (
    <div className={styles.pane}>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <Icon category="outlined" type="description" />
          <span className={styles.title}>{t("capability.word_template.panel.word_template_pane.title")}</span>
          {attachedFilename && (
            <span className={styles.baseFile} title={attachedFilename}>
              {t("capability.word_template.preview.attachedBase", { filename: attachedFilename })}
            </span>
          )}
        </div>
        {activeTab === "preview" && isLoading && objectUrl && (
          <span className={styles.status}>{t("capability.word_template.preview.refreshing")}</span>
        )}
        {sessionId && hasDocument && (
          <IconButton
            color="on-surface"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "download" }}
            disabled={isDownloading}
            aria-label={t("capability.word_template.preview.download")}
            onClick={() => void handleDownload()}
          />
        )}
        <IconButton
          color="on-surface"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "close" }}
          aria-label={t("common.close")}
          // Blur first: closing flips aria-hidden on the drawer, which the browser
          // blocks while a descendant still holds focus (InlineDrawer does the same).
          onClick={(e) => {
            e.currentTarget.blur();
            onClose();
          }}
        />
      </div>

      {hasDocument && (
        <div className={styles.tabs} role="tablist">
          {(["write", "preview"] as const).map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={activeTab === value}
              className={`${styles.tab} ${activeTab === value ? styles.tabActive : ""}`}
              onClick={() => setTab(value)}
            >
              {t(`capability.word_template.tabs.${value}`)}
            </button>
          ))}
        </div>
      )}

      {/* Kept mounted on "Aperçu" too: a passage being edited survives a look at the preview. */}
      {sessionId && hasDocument && (
        <div className={styles.editorTab} hidden={activeTab !== "write"}>
          <WordTemplateImagesContext.Provider value={resolveImage}>
            <WordTemplateEditor sessionId={sessionId} versionKey={version} refreshSession={refresh} />
          </WordTemplateImagesContext.Provider>
        </div>
      )}

      <div className={styles.previewBody} ref={contentRef} hidden={activeTab !== "preview"}>
        {!sessionId && <div className={styles.empty}>{t("capability.word_template.preview.noSession")}</div>}
        {sessionId && !hasDocument && <div className={styles.empty}>{t("capability.word_template.preview.empty")}</div>}
        {hasDocument && shownError && <div className={styles.error}>{shownError}</div>}
        {hasDocument && !shownError && isLoading && !objectUrl && <div className={styles.empty}>{loadingMsg}</div>}
        {hasDocument && !shownError && objectUrl && (
          <Document
            key={remountKey}
            file={objectUrl}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            onLoadError={(err: Error) => setLoadError(err?.message || loadErrorMsg)}
            loading={<div className={styles.empty}>{loadingMsg}</div>}
            error={<div className={styles.error}>{loadErrorMsg}</div>}
          >
            {Array.from({ length: numPages ?? 0 }, (_, i) => (
              <Page
                key={`page_${i + 1}`}
                pageNumber={i + 1}
                width={pageWidth}
                renderAnnotationLayer={false}
                renderTextLayer={false}
                className={styles.previewPage}
              />
            ))}
          </Document>
        )}
      </div>
    </div>
  );
}

export default WordTemplatePane;
