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

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import type { ButtonGroupItemProps } from "@shared/atoms/ButtonGroup/ButtonGroupItem/ButtonGroupItem.tsx";
import { PdfStreamingDocumentViewer } from "../../../../../common/PdfStreamingDocumentViewer";
import {
  documentPdfSourceUrl,
  hasNativePreview,
  isEmailFile,
  isTabularFile,
} from "../../../../utils/documentViewerUtils";
import { useLazyPreviewQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { MetadataPreview } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./DocumentViewer.module.css";
import { ManagerPreviewImage } from "./ManagerPreviewImage";
import { fetchAuthedBlob } from "../../../../../utils/downloadUtils";

export type ViewMode = "file" | "raw" | "metadata";

interface DocumentViewerProps {
  documentUid: string;
  sessionId?: string;
  sourceUrl?: string;
  sourceFormat?: "text";
  onError?: (error: unknown) => void;
  onLoaded?: () => void;
  /** Real file name incl. extension — decides the render strategy (§2.1, FRONT-13). Falls
   * back to markdown rendering when absent, matching the pre-FRONT-13 behavior. */
  fileName?: string | null;
  /** Called once markdown content loads successfully — lets a host derive a title
   * fallback (e.g. the first H1) without duplicating the fetch. Never called for PDFs. */
  onMarkdownLoaded?: (content: string) => void;
  /** Renders the given mode's content instead of picking one strategy
   *  automatically — the corpus workspace preview drawer pairs this with a
   *  `DocumentViewerModeToggle` rendered in its own header (left of the
   *  close button), so the toggle isn't fighting the document for vertical
   *  space inside this "chrome-less" body. Email also offers extracted facts;
   *  other formats without a native renderer keep their single Markdown view. */
  view?: ViewMode;
}

/**
 * Shared document content renderer used by both the chat-citation viewer
 * (`DocumentViewerPage`) and the corpus workspace preview drawer
 * (`DocumentWorkspace`). Picks a native renderer or the markdown extraction
 * based on the file's extension — see FRONT-13.
 *
 * The native renderer is always the PDF one: a PDF streams from storage
 * untouched, a Word or PowerPoint document goes through the backend's render endpoint,
 * and `documentPdfSourceUrl` decides which.
 *
 * Deliberately chrome-less: both hosting contexts already provide their own
 * header/close affordance (the page's top bar, `InlineDrawer`'s header).
 */
export function DocumentViewer({
  documentUid,
  sessionId,
  fileName,
  onMarkdownLoaded,
  view,
  sourceUrl,
  sourceFormat,
  onError,
  onLoaded,
}: DocumentViewerProps) {
  if (sourceUrl && sourceFormat === "text") {
    return <TextDocumentBody key={sourceUrl} sourceUrl={sourceUrl} onError={onError} onLoaded={onLoaded} />;
  }
  if (!sourceUrl && !hasNativePreview(fileName)) {
    return (
      <MarkdownDocumentBody
        documentUid={documentUid}
        sessionId={sessionId}
        onError={onError}
        onReady={onLoaded}
        onLoaded={onMarkdownLoaded}
        fullWidth={isTabularFile(fileName)}
        artifact={isEmailFile(fileName) && view === "metadata" ? "metadata" : "raw"}
      />
    );
  }

  const nativeBody = (
    <PdfStreamingDocumentViewer
      documentUid={documentUid}
      sourceUrl={
        sourceUrl ??
        `${documentPdfSourceUrl(documentUid)}${sessionId ? `&session_id=${encodeURIComponent(sessionId)}` : ""}`
      }
      onError={onError}
      onLoaded={onLoaded}
    />
  );

  if (!view) {
    return nativeBody;
  }

  return (
    <div className={styles.viewerBody}>
      {view === "file" ? (
        nativeBody
      ) : (
        <MarkdownDocumentBody
          documentUid={documentUid}
          sessionId={sessionId}
          onLoaded={onMarkdownLoaded}
          onError={onError}
          onReady={onLoaded}
        />
      )}
    </div>
  );
}

function TextDocumentBody({
  sourceUrl,
  onError,
  onLoaded,
}: Pick<DocumentViewerProps, "onError" | "onLoaded"> & { sourceUrl: string }) {
  const { t } = useTranslation();
  const [content, setContent] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const blob = await fetchAuthedBlob(sourceUrl);
        const limit = 256 * 1024;
        const text = await blob.slice(0, limit).text();
        if (cancelled) return;
        setContent(text);
        setTruncated(blob.size > limit);
        onLoaded?.();
      } catch (error) {
        if (cancelled) return;
        setFailed(true);
        onError?.(error);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
    // The owning drawer supplies render callbacks; only the source starts a fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceUrl]);
  return (
    <div className={styles.markdownBody}>
      {content === null && !failed && <p role="status">{t("chatbot.sessionAttachments.loading")}</p>}
      {truncated && <p role="status">{t("chatbot.sessionAttachments.previewTruncated")}</p>}
      {content !== null && <pre className={styles.textBody}>{content}</pre>}
    </div>
  );
}

/**
 * The file/raw or file/email-details toggle for `DocumentViewer`'s `view` prop —
 * rendered separately (not inside `DocumentViewer` itself) so a host can
 * place it in its own header, e.g. `InlineDrawer`'s `headerActions` (left of
 * the close button), instead of stealing a row of vertical space from the
 * document body.
 */
export function DocumentViewerModeToggle({
  view,
  onChange,
  fileName,
}: {
  view: ViewMode;
  onChange: (view: ViewMode) => void;
  fileName?: string | null;
}) {
  const { t } = useTranslation();
  const email = isEmailFile(fileName);
  const tabs: ViewMode[] = email ? ["file", "metadata"] : ["file", "raw"];
  const viewTabItems: ButtonGroupItemProps[] = [
    { label: t("rework.resources.preview.tabs.file") },
    { label: t(email ? "rework.resources.preview.tabs.metadata" : "rework.resources.preview.tabs.raw") },
  ];

  return (
    <ButtonGroup
      items={viewTabItems}
      size="2xs"
      color="secondary"
      variant="tabs"
      aria-label={t("rework.resources.preview.tabsAria")}
      selectedIndex={tabs.indexOf(view)}
      onSelectedIndexChange={(index) => onChange(tabs[index])}
    />
  );
}

function MarkdownDocumentBody({
  documentUid,
  sessionId,
  onLoaded,
  onError,
  onReady,
  fullWidth,
  artifact = "raw",
}: {
  documentUid: string;
  sessionId?: string;
  onLoaded?: (content: string) => void;
  onError?: (error: unknown) => void;
  onReady?: () => void;
  fullWidth?: boolean;
  artifact?: "raw" | "metadata";
}) {
  const { t } = useTranslation();
  const callbacks = useRef({ onError, onReady });
  callbacks.current = { onError, onReady };
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  // Set when the markdown extraction cannot be served (404 — the document never
  // went through a preview-generating pipeline, or the extraction failed). Kept
  // separate from `content` so it renders as an empty state rather than as
  // document text the user could mistake for the file's real content.
  const [unavailable, setUnavailable] = useState(false);

  const [fetchManagerPreview] = useLazyPreviewQuery();
  const imageRenderer = useMemo(
    () =>
      function Image(props: { src?: string; alt?: string }) {
        return <ManagerPreviewImage {...props} documentUid={documentUid} />;
      },
    [documentUid],
  );

  useEffect(() => {
    if (!documentUid) return;
    // Guards against a superseded response winning the race: if `documentUid`
    // changes again before this fetch resolves, `cancelled` flips true and the
    // stale `.then()`/`.catch()` below becomes a no-op, so an out-of-order
    // response can never overwrite the newer document's content or title.
    let cancelled = false;
    setLoading(true);
    setUnavailable(false);
    const response = fetchManagerPreview({ id: documentUid, artifact, ...(sessionId ? { sessionId } : {}) })
      .unwrap()
      .then((value) => {
        if (typeof value !== "string") throw new Error("Invalid preview");
        return value;
      });
    response
      .then((decoded) => {
        if (cancelled) return;
        if (artifact === "metadata") {
          const metadata = JSON.parse(decoded) as MetadataPreview;
          if (!metadata.identity || !metadata.extensions?.email) throw new Error("Invalid mail preview");
        }
        setContent(decoded);
        setUnavailable(decoded.trim() === "");
        if (!decoded.trim()) callbacks.current.onError?.(new Error("Empty preview"));
        else callbacks.current.onReady?.();
        if (artifact === "raw") onLoaded?.(decoded);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        callbacks.current.onError?.(error);
        setContent("");
        setUnavailable(true);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // onLoaded is a per-render callback (title-derivation), not a fetch dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentUid, sessionId, artifact, fetchManagerPreview]);

  if (loading) {
    return (
      <div className={styles.markdownBody}>
        <p className={styles.loading}>{t("rework.resources.preview.loading")}</p>
      </div>
    );
  }
  if (unavailable) {
    return (
      <div className={styles.markdownBody}>
        <p className={styles.unavailable}>
          {t(
            artifact === "metadata"
              ? "rework.resources.preview.email.unavailable"
              : "rework.resources.preview.markdownUnavailable",
          )}
        </p>
      </div>
    );
  }
  if (artifact === "metadata") return <EmailDetails content={content} />;
  return (
    <div className={styles.markdownBody}>
      <MarkdownRenderer
        text={content}
        fullWidth={fullWidth}
        imageRenderer={imageRenderer}
        localLinksAsText
        diagramsAsCode
      />
    </div>
  );
}

function EmailDetails({ content }: { content: string }) {
  const { t } = useTranslation();
  let metadata: MetadataPreview;
  try {
    metadata = JSON.parse(content) as MetadataPreview;
    if (!metadata.identity || !metadata.extensions?.email) throw new Error("No extracted mail facts");
  } catch {
    return <p className={styles.unavailable}>{t("rework.resources.preview.email.unavailable")}</p>;
  }
  const email = metadata.extensions!.email!;
  const fields = [
    ["subject", metadata.identity.title],
    ["sender", metadata.identity.author],
    ["sent", metadata.identity.created],
    ["to", email.to.join("; ")],
    ["cc", email.cc.join("; ")],
    ["messageId", email.message_id],
    ["inReplyTo", email.in_reply_to],
  ];
  return (
    <div className={styles.markdownBody}>
      <p>{t("rework.resources.preview.email.description")}</p>
      <dl className={styles.emailDetails}>
        {fields.map(([key, value]) => (
          <div key={key}>
            <dt>{t(`rework.resources.preview.email.${key}`)}</dt>
            <dd>{value || t("rework.resources.preview.email.missing")}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
