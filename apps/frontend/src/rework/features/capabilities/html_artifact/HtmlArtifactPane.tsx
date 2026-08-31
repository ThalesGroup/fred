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

// HtmlArtifactPane — the html_artifact capability's side panel (CapabilitySidePanel).
//
// A dedicated viewer opening right of the chat, READ-ONLY (v1), with three tabs:
//  - Preview: the artifact rendered in a SANDBOXED iframe (see below);
//  - HTML / CSS: the source, syntax-highlighted (the shared CodeBlock).
// When the session holds several artifacts, a switcher strip above the tabs picks
// one. The markup rides inline on the chat part (no fetch); the slice is the source.
//
// SECURITY (RFC §4.7): the Preview iframe is `sandbox=""` — the empty attribute
// enables ALL sandbox restrictions, so NO script runs (no `allow-scripts`) and the
// frame is an opaque origin with no access to the app (`no allow-same-origin`). The
// composed document also carries a restrictive CSP meta (composeHtmlDocument), so
// no external resource can load even if a sandbox flag ever regressed. `srcDoc`
// (never `src`) keeps the content inert same-document text.

import { useEffect, useMemo, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { CodeBlock } from "@shared/molecules/CodeBlock/CodeBlock";
import type { CapabilitySidePanelProps } from "../types";
import { useOpenSessionId } from "../useOpenSessionId";
import {
  selectHtmlArtifact,
  selectHtmlArtifactSelectedId,
  selectHtmlArtifactSessionId,
  selectHtmlArtifactsById,
} from "./htmlArtifactSlice";
import { composeHtmlDocument, openHtmlArtifactInNewTab, zoomIn, zoomOut, ZOOM_LEVELS } from "./htmlArtifactDocument";
import HtmlArtifactDownloadButton from "./HtmlArtifactDownloadButton";
import styles from "./HtmlArtifactPane.module.css";

type ViewTab = "preview" | "html" | "css";

export function HtmlArtifactPane({ onClose }: CapabilitySidePanelProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const openSessionId = useOpenSessionId();
  const sliceSessionId = useSelector(selectHtmlArtifactSessionId);
  const byId = useSelector(selectHtmlArtifactsById);
  const selectedId = useSelector(selectHtmlArtifactSelectedId);
  const [tab, setTab] = useState<ViewTab>("preview");
  // Browser-like zoom for the Preview (reflows content via CSS `zoom`), so a wide
  // page can be shrunk to fit. Download / open-in-new-tab stay at 100%.
  const [zoom, setZoom] = useState(1);

  // Only surface artifacts belonging to the conversation currently open.
  const artifacts = useMemo(
    () => (sliceSessionId === openSessionId ? Object.values(byId) : []),
    [byId, sliceSessionId, openSessionId],
  );

  // Selection is the slice's single source of truth: both a card's Open button and
  // this pane's switcher dispatch `selectHtmlArtifact`, so neither masks the other.
  const selected = useMemo(
    () => artifacts.find((a) => a.artifact_id === selectedId) ?? artifacts[0],
    [artifacts, selectedId],
  );

  // The composed, CSP-carrying document for the Preview iframe (recomputed when the
  // selected artifact's markup OR the zoom changes).
  const composed = useMemo(
    () => (selected ? composeHtmlDocument(selected.html, selected.css, zoom) : ""),
    [selected, zoom],
  );

  // Double-buffer the Preview so a zoom / markup change never flashes the iframe's
  // blank white background: the newly composed document loads into the HIDDEN back
  // buffer and is revealed only once it has painted (onLoad); the front buffer keeps
  // the previous frame visible until then. Each iframe keeps a STABLE key, so only
  // the back one ever reloads — an iframe cannot be re-zoomed without a reload
  // (sandboxed, no allow-scripts), so this hides that reload instead of avoiding it.
  const [buffers, setBuffers] = useState<[string, string]>(["", ""]);
  const [front, setFront] = useState<0 | 1>(0);
  const pendingRef = useRef<0 | 1 | null>(null);

  useEffect(() => {
    if (!composed || buffers[front] === composed) return;
    const back: 0 | 1 = front === 0 ? 1 : 0;
    if (buffers[back] === composed) return; // already loading into the back buffer
    pendingRef.current = back;
    setBuffers((b) => {
      const next: [string, string] = [b[0], b[1]];
      next[back] = composed;
      return next;
    });
  }, [composed, front, buffers]);

  const handleFrameLoad = (idx: 0 | 1) => {
    // Reveal the back buffer only once the doc we asked it to load has painted.
    if (pendingRef.current === idx && buffers[idx] === composed) {
      pendingRef.current = null;
      setFront(idx);
    }
  };

  const untitled = t("capability.html_artifact.untitled", { defaultValue: "HTML artifact" });

  const viewTabs: { id: ViewTab; label: string }[] = [
    { id: "preview", label: t("capability.html_artifact.tabs.preview", { defaultValue: "Preview" }) },
    { id: "html", label: t("capability.html_artifact.tabs.html", { defaultValue: "HTML" }) },
    { id: "css", label: t("capability.html_artifact.tabs.css", { defaultValue: "CSS" }) },
  ];

  return (
    <div className={styles.pane}>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <Icon category="outlined" type="code" />
          <span className={styles.title}>{selected?.title || untitled}</span>
        </div>
        {selected && (
          <Tooltip text={t("capability.html_artifact.openInNewTab", { defaultValue: "Open in a new tab" })}>
            <IconButton
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "open_in_new" }}
              onClick={() => openHtmlArtifactInNewTab(selected.html, selected.css)}
              aria-label={t("capability.html_artifact.openInNewTab", { defaultValue: "Open in a new tab" })}
            />
          </Tooltip>
        )}
        {selected && <HtmlArtifactDownloadButton html={selected.html} css={selected.css} title={selected.title} />}
        <IconButton
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "close" }}
          aria-label={t("capability.html_artifact.close", { defaultValue: "Close panel" })}
          // Blur first: closing flips aria-hidden on the drawer, which the browser
          // blocks while a descendant still holds focus (mirrors WritableDocumentPane).
          onClick={(e) => {
            e.currentTarget.blur();
            onClose();
          }}
        />
      </div>

      {!selected && (
        <div className={styles.empty}>
          {t("capability.html_artifact.empty", {
            defaultValue: "No artifact yet. Ask the assistant to build a page or component.",
          })}
        </div>
      )}

      {selected && (
        <>
          {artifacts.length > 1 && (
            <div className={`${styles.tabs} ${styles.switcher}`} role="tablist" aria-label="Artifacts">
              {artifacts.map((a) => (
                <button
                  key={a.artifact_id}
                  role="tab"
                  aria-selected={a.artifact_id === selected.artifact_id}
                  className={`${styles.tab} ${a.artifact_id === selected.artifact_id ? styles.tabActive : ""}`}
                  onClick={() => dispatch(selectHtmlArtifact(a.artifact_id))}
                >
                  {a.title || untitled}
                </button>
              ))}
            </div>
          )}

          <div className={styles.tabs} role="tablist" aria-label="View">
            {viewTabs.map((v) => (
              <button
                key={v.id}
                role="tab"
                aria-selected={tab === v.id}
                className={`${styles.tab} ${tab === v.id ? styles.tabActive : ""}`}
                onClick={() => setTab(v.id)}
              >
                {v.label}
              </button>
            ))}
            {tab === "preview" && (
              <div className={styles.zoomCluster}>
                <Tooltip text={t("capability.html_artifact.zoomOut", { defaultValue: "Zoom out" })}>
                  <IconButton
                    variant="icon"
                    size="small"
                    icon={{ category: "outlined", type: "zoom_out" }}
                    onClick={() => setZoom(zoomOut)}
                    disabled={zoom <= ZOOM_LEVELS[0]}
                    aria-label={t("capability.html_artifact.zoomOut", { defaultValue: "Zoom out" })}
                  />
                </Tooltip>
                <Tooltip text={t("capability.html_artifact.resetZoom", { defaultValue: "Reset zoom" })}>
                  <button className={styles.zoomLabel} onClick={() => setZoom(1)}>
                    {Math.round(zoom * 100)}%
                  </button>
                </Tooltip>
                <Tooltip text={t("capability.html_artifact.zoomIn", { defaultValue: "Zoom in" })}>
                  <IconButton
                    variant="icon"
                    size="small"
                    icon={{ category: "outlined", type: "zoom_in" }}
                    onClick={() => setZoom(zoomIn)}
                    disabled={zoom >= ZOOM_LEVELS[ZOOM_LEVELS.length - 1]}
                    aria-label={t("capability.html_artifact.zoomIn", { defaultValue: "Zoom in" })}
                  />
                </Tooltip>
              </div>
            )}
          </div>

          <div className={styles.body}>
            {tab === "preview" && (
              <div className={styles.previewFrameWrap}>
                {([0, 1] as const).map((i) => (
                  <iframe
                    key={i}
                    srcDoc={buffers[i]}
                    className={`${styles.previewFrame} ${front === i ? styles.frameFront : styles.frameBack}`}
                    title={selected.title || untitled}
                    sandbox=""
                    referrerPolicy="no-referrer"
                    onLoad={() => handleFrameLoad(i)}
                  />
                ))}
              </div>
            )}
            {tab === "html" && (
              <div className={styles.source}>
                <CodeBlock code={selected.html} language="html" />
              </div>
            )}
            {tab === "css" && (
              <div className={styles.source}>
                <CodeBlock code={selected.css} language="css" />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
