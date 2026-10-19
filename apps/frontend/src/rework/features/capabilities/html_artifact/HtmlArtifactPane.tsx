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
// A dedicated viewer opening right of the chat, READ-ONLY (v1): the artifact
// rendered in a SANDBOXED iframe (see below), with a zoom control in the bar.
// When the session holds several artifacts, a switcher strip in that bar picks
// one (source is reachable via Download / open-in-new-tab). The markup rides
// inline on the chat part (no fetch); the slice is the source.
//
// SECURITY (RFC §4.7): the Preview iframe is `sandbox=""` — the empty attribute
// enables ALL sandbox restrictions, so NO script runs (no `allow-scripts`) and the
// frame is an opaque origin with no access to the app (`no allow-same-origin`). The
// composed document also carries a restrictive CSP meta (composeHtmlDocument), so
// no external resource can load even if a sandbox flag ever regressed. `srcDoc`
// (never `src`) keeps the content inert same-document text.

import { useMemo, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import type { CapabilitySidePanelProps } from "../types";
import { useOpenSessionId } from "../useOpenSessionId";
import {
  selectHtmlArtifact,
  selectHtmlArtifactSelectedId,
  selectHtmlArtifactSessionId,
  selectHtmlArtifactsById,
} from "./htmlArtifactSlice";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { composeHtmlDocument, openHtmlArtifactInNewTab, zoomIn, zoomOut, ZOOM_LEVELS } from "./htmlArtifactDocument";
import { HtmlPreview } from "@shared/molecules/HtmlPreview/HtmlPreview";
import { measureArtifactWidth } from "./htmlArtifactExport";
import HtmlArtifactDownloadButton from "./HtmlArtifactDownloadButton";
import styles from "./HtmlArtifactPane.module.css";

export function HtmlArtifactPane({ onClose }: CapabilitySidePanelProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const { showSuccess, showError } = useToast();
  const openSessionId = useOpenSessionId();
  const sliceSessionId = useSelector(selectHtmlArtifactSessionId);
  const byId = useSelector(selectHtmlArtifactsById);
  const selectedId = useSelector(selectHtmlArtifactSelectedId);
  // Browser-like zoom for the Preview (reflows content via CSS `zoom`), so a wide
  // page can be shrunk to fit. Download / open-in-new-tab stay at 100%.
  const [zoom, setZoom] = useState(1);
  const previewWrapRef = useRef<HTMLDivElement>(null);

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

  const untitled = t("capability.html_artifact.untitled", { defaultValue: "HTML artifact" });

  const copyMarkup = async () => {
    if (!selected) return;
    try {
      await navigator.clipboard.writeText(composeHtmlDocument(selected.html, selected.css));
      showSuccess({ summary: t("capability.html_artifact.copied", { defaultValue: "Copied to clipboard" }) });
    } catch {
      showError({ summary: t("capability.html_artifact.copyFailed", { defaultValue: "Could not copy." }) });
    }
  };

  // Fit width: measure the artifact's laid-out width in the panel (via a transient
  // frame — the live preview is opaque) and set the zoom so overflow shrinks to fit;
  // content that already fits resets to 100%.
  const fitToWidth = async () => {
    const wrap = previewWrapRef.current;
    if (!selected || !wrap) return;
    const available = wrap.clientWidth;
    if (available <= 0) return;
    try {
      const content = await measureArtifactWidth(selected.html, selected.css, available);
      setZoom(content > available ? Math.max(available / content, ZOOM_LEVELS[0]) : 1);
    } catch {
      /* leave the zoom unchanged */
    }
  };

  return (
    <div className={styles.pane}>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <Icon category="outlined" type="code" />
          <span className={styles.title}>{selected?.title || untitled}</span>
        </div>
        {selected && (
          <Tooltip text={t("capability.html_artifact.copy", { defaultValue: "Copy to clipboard" })}>
            <IconButton
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "content_copy" }}
              onClick={() => void copyMarkup()}
              aria-label={t("capability.html_artifact.copy", { defaultValue: "Copy to clipboard" })}
            />
          </Tooltip>
        )}
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
          <div className={styles.controlsBar}>
            {artifacts.length > 1 && (
              <div className={styles.artifactTabs} role="tablist" aria-label="Artifacts">
                {artifacts.map((a) => (
                  <Tooltip key={a.artifact_id} text={a.title || untitled} placement="top">
                    <button
                      role="tab"
                      aria-selected={a.artifact_id === selected.artifact_id}
                      className={`${styles.tab} ${a.artifact_id === selected.artifact_id ? styles.tabActive : ""}`}
                      onClick={() => dispatch(selectHtmlArtifact(a.artifact_id))}
                    >
                      {a.title || untitled}
                    </button>
                  </Tooltip>
                ))}
              </div>
            )}
            <div className={styles.zoomCluster}>
              <Tooltip text={t("capability.html_artifact.fitWidth", { defaultValue: "Fit width" })}>
                <IconButton
                  variant="icon"
                  size="small"
                  icon={{ category: "outlined", type: "fit_width" }}
                  onClick={() => void fitToWidth()}
                  aria-label={t("capability.html_artifact.fitWidth", { defaultValue: "Fit width" })}
                />
              </Tooltip>
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
          </div>

          <div ref={previewWrapRef} className={styles.body}>
            <HtmlPreview html={selected.html} css={selected.css} zoom={zoom} title={selected.title || untitled} />
          </div>
        </>
      )}
    </div>
  );
}
