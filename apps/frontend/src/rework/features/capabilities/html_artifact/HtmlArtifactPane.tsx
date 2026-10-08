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
// SECURITY (RFC §4.7): the preview renders the SANDBOXED SHELL, not the artifact
// itself — the shell's `frame-src blob:` is what stops the artifact navigating
// itself to an attacker URL, which nothing in the artifact's own CSP can do. The
// frame is `sandbox={SHELL_SANDBOX}` — `allow-scripts` so the shell boots, and
// NEVER `allow-same-origin`, so it stays an opaque origin with no access to the
// app's DOM, cookies or storage. `srcDoc` (never `src`) keeps it out of any app URL.

import { useEffect, useMemo, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import type { CapabilitySidePanelProps } from "../types";
import { useOpenSessionId } from "../useOpenSessionId";
import {
  closeHtmlArtifact,
  selectHtmlArtifact,
  selectHtmlArtifactClosedIds,
  selectHtmlArtifactSelectedId,
  selectHtmlArtifactSessionId,
  selectHtmlArtifactsById,
} from "./htmlArtifactSlice";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  SHELL_SANDBOX,
  ZOOM_LEVELS,
  artifactHasScript,
  composeHtmlDocument,
  openHtmlArtifactInNewTab,
  sandboxedShellDocument,
  zoomIn,
  zoomOut,
} from "./htmlArtifactDocument";
import { nextBufferAction } from "./previewBuffers";
import { measureArtifactWidth } from "./htmlArtifactExport";
import HtmlArtifactDownloadButton from "./HtmlArtifactDownloadButton";
import { useCheckHtmlArtifactJavaScriptAllowed, useHtmlArtifactJavaScriptAllowed } from "./useHtmlArtifactJavaScript";
import styles from "./HtmlArtifactPane.module.css";

export function HtmlArtifactPane({ onClose }: CapabilitySidePanelProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const { showSuccess, showError } = useToast();
  const openSessionId = useOpenSessionId();
  const sliceSessionId = useSelector(selectHtmlArtifactSessionId);
  const byId = useSelector(selectHtmlArtifactsById);
  const selectedId = useSelector(selectHtmlArtifactSelectedId);
  const closedIds = useSelector(selectHtmlArtifactClosedIds);
  // Browser-like zoom for the Preview (reflows content via CSS `zoom`), so a wide
  // page can be shrunk to fit. Download / open-in-new-tab stay at 100%.
  const [zoom, setZoom] = useState(1);
  // A stop switch, not a gate: an artifact runs on arrival (RFC §4.7), and this is
  // how a reader ends a page that hangs the tab or shows something it should not.
  // Unmounting the frames is the kill — it destroys the browsing contexts, so
  // scripts, timers and workers all stop; there is nothing left to keep running.
  const [stopped, setStopped] = useState(false);
  const previewWrapRef = useRef<HTMLDivElement>(null);

  // Only surface artifacts belonging to the conversation currently open.
  // Closed artifacts stay in the slice so their chat card can reopen them; the
  // pane simply does not list them.
  const artifacts = useMemo(
    () => (sliceSessionId === openSessionId ? Object.values(byId).filter((a) => !closedIds[a.artifact_id]) : []),
    [byId, sliceSessionId, openSessionId, closedIds],
  );
  const hasClosedOnly = useMemo(
    () => artifacts.length === 0 && Object.keys(byId).length > 0 && sliceSessionId === openSessionId,
    [artifacts, byId, sliceSessionId, openSessionId],
  );

  // Selection is the slice's single source of truth: both a card's Open button and
  // this pane's switcher dispatch `selectHtmlArtifact`, so neither masks the other.
  const selected = useMemo(
    () => artifacts.find((a) => a.artifact_id === selectedId) ?? artifacts[0],
    [artifacts, selectedId],
  );

  // Whether THIS team may run script, resolved now rather than when the artifact
  // was produced — withdrawing the right has to reach pages that already exist.
  const postureKey = selected ? `${selected.artifact_id}:${selected.version}` : "";
  const allowJavaScript = useHtmlArtifactJavaScriptAllowed(postureKey);
  const checkJavaScriptAllowed = useCheckHtmlArtifactJavaScriptAllowed();

  // The composed, CSP-carrying document for the Preview iframe (recomputed when the
  // selected artifact's markup, the zoom, OR the team's posture changes).
  const composed = useMemo(
    () => (selected ? sandboxedShellDocument(selected.html, selected.css, zoom, allowJavaScript) : ""),
    [selected, zoom, allowJavaScript],
  );

  // Stopping is about the page in front of you, so switching artifact starts the
  // new one running rather than inheriting the previous one's stopped state.
  const selectedKey = selected?.artifact_id;
  useEffect(() => setStopped(false), [selectedKey]);

  // Whether the markup carries anything the browser WOULD execute. Parsed, so a
  // page merely displaying `onclick="…"` in a <pre> does not count.
  const carriesScript = useMemo(() => (selected ? artifactHasScript(selected.html) : false), [selected]);

  // Only a page that can execute has anything to stop.
  const canStop = carriesScript && allowJavaScript;

  // Script that exists but will not run. This is the visible half of the posture:
  // the page was produced while the team could run script and the right has since
  // been withdrawn, so it would otherwise just look broken.
  const scriptSuppressed = carriesScript && !allowJavaScript;

  // Double-buffer only inert pages: a hidden old frame must not keep running
  // script after its artifact is closed or its team's right is withdrawn.
  const [buffers, setBuffers] = useState<[string, string]>(["", ""]);
  const [front, setFront] = useState<0 | 1>(0);
  // What each buffer has actually painted. Switching back to an already-seen
  // document doesn't reload the iframe (same srcDoc), so no onLoad fires — we must
  // recognise "already painted here" and flip to it directly, or the pane freezes.
  const paintedRef = useRef<[string, string]>(["", ""]);
  // On the very first open there is no prior frame to hold, so the empty front
  // iframe would flash its white background before the artifact paints. Keep both
  // frames hidden (the pane's own surface shows through) until that first paint.
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    if (allowJavaScript) return;
    const action = nextBufferAction(composed, buffers, paintedRef.current, front);
    if (action.kind === "flip") {
      setFront(action.to);
      setRevealed(true);
    } else if (action.kind === "load") {
      // This buffer is about to reload, so its previously-painted content is void:
      // clear it now, or a quick switch back to that old doc would flip to this
      // buffer mid-load (showing the new doc) instead of reloading the old one.
      paintedRef.current[action.into] = "";
      setBuffers((b) => {
        const next: [string, string] = [b[0], b[1]];
        next[action.into] = composed;
        return next;
      });
    }
  }, [allowJavaScript, composed, front, buffers]);

  const handleFrameLoad = (idx: 0 | 1) => {
    paintedRef.current[idx] = buffers[idx];
    // Reveal the freshly loaded buffer only once the doc we asked it to load has
    // painted AND it is still the current target (a fast switch may have moved on).
    if (buffers[idx] === composed && front !== idx) {
      setFront(idx);
      setRevealed(true);
    }
  };

  const untitled = t("capability.html_artifact.untitled", { defaultValue: "HTML artifact" });

  const copyMarkup = async () => {
    if (!selected) return;
    try {
      // Deliberately the readable composed page, not the shell: Copy exists to hand
      // over source the user can edit, and it is the source already shown in the
      // HTML/CSS tabs. It carries author script — an output path whose safety is the
      // user's own judgement, enumerated as such in RFC §4.7.
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
              onClick={() => {
                void checkJavaScriptAllowed().then((allowed) =>
                  openHtmlArtifactInNewTab(selected.html, selected.css, allowed),
                );
              }}
              aria-label={t("capability.html_artifact.openInNewTab", { defaultValue: "Open in a new tab" })}
            />
          </Tooltip>
        )}
        {selected && (
          <HtmlArtifactDownloadButton
            html={selected.html}
            css={selected.css}
            title={selected.title}
            allowJavaScript={allowJavaScript}
          />
        )}
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
          {hasClosedOnly
            ? t("capability.html_artifact.allClosed", {
                defaultValue: "No preview open. Reopen one from its card in the conversation.",
              })
            : t("capability.html_artifact.empty", {
                defaultValue: "No artifact yet. Ask the assistant to build a page or component.",
              })}
        </div>
      )}

      {selected && (
        <>
          <div className={styles.controlsBar}>
            <div className={styles.artifactTabs} role="tablist" aria-label="Artifacts">
              {artifacts.map((a) => (
                <div
                  key={a.artifact_id}
                  className={`${styles.tabWrap} ${a.artifact_id === selected.artifact_id ? styles.tabWrapActive : ""}`}
                >
                  <Tooltip text={a.title || untitled} placement="top">
                    <button
                      role="tab"
                      aria-selected={a.artifact_id === selected.artifact_id}
                      className={`${styles.tab} ${a.artifact_id === selected.artifact_id ? styles.tabActive : ""}`}
                      onClick={() => dispatch(selectHtmlArtifact(a.artifact_id))}
                    >
                      {a.title || untitled}
                    </button>
                  </Tooltip>
                  {/* Sibling, not nested: a button inside a button is invalid markup
                      and the inner click would not reliably reach its own handler. */}
                  <IconButton
                    variant="icon"
                    size="2xs"
                    color={a.artifact_id === selected.artifact_id ? "primary" : "on-surface-retreat"}
                    icon={{ category: "outlined", type: "close" }}
                    onClick={() => dispatch(closeHtmlArtifact(a.artifact_id))}
                    aria-label={t("capability.html_artifact.closeArtifact", {
                      defaultValue: "Close this artifact",
                    })}
                  />
                </div>
              ))}
            </div>
            <div className={styles.zoomCluster}>
              {canStop && (
                <Tooltip
                  text={
                    stopped
                      ? t("capability.html_artifact.restart", { defaultValue: "Run the page again" })
                      : t("capability.html_artifact.stop", { defaultValue: "Stop the page" })
                  }
                >
                  <IconButton
                    variant="icon"
                    size="small"
                    icon={{ category: "outlined", type: stopped ? "refresh" : "stop" }}
                    onClick={() => setStopped((value) => !value)}
                    aria-label={
                      stopped
                        ? t("capability.html_artifact.restart", { defaultValue: "Run the page again" })
                        : t("capability.html_artifact.stop", { defaultValue: "Stop the page" })
                    }
                  />
                </Tooltip>
              )}
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

          <div className={styles.body}>
            {scriptSuppressed && (
              <div className={styles.suppressedNotice} role="status">
                <Icon category="outlined" type="info" />
                <span>
                  {t("capability.html_artifact.scriptSuppressedNotice", {
                    defaultValue:
                      "This page contains JavaScript, which your team is not allowed to run. It is shown without interaction.",
                  })}
                </span>
              </div>
            )}
            <div ref={previewWrapRef} className={styles.previewFrameWrap}>
              {stopped ? (
                <div className={styles.stoppedNotice}>
                  {t("capability.html_artifact.stoppedNotice", { defaultValue: "The page has been stopped." })}
                </div>
              ) : allowJavaScript ? (
                <iframe
                  key={selectedKey}
                  srcDoc={composed}
                  className={`${styles.previewFrame} ${styles.frameFront}`}
                  title={selected.title || untitled}
                  sandbox={SHELL_SANDBOX}
                  referrerPolicy="no-referrer"
                />
              ) : (
                ([0, 1] as const).map((i) => (
                  <iframe
                    key={i}
                    // No attribute while empty: in Chromium, a doc set while the empty srcdoc is
                    // still loading paints blank.
                    srcDoc={buffers[i] || undefined}
                    className={`${styles.previewFrame} ${revealed && front === i ? styles.frameFront : styles.frameBack}`}
                    title={selected.title || untitled}
                    // The frame hosts our TRUSTED shell, whose bootstrap is a
                    // script. The ARTIFACT's own permission is one level down,
                    // on the inner frame the shell writes.
                    sandbox={SHELL_SANDBOX}
                    referrerPolicy="no-referrer"
                    onLoad={() => handleFrameLoad(i)}
                  />
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
