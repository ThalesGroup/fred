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

import { useMemo, useState } from "react";
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
import { composeHtmlDocument, openHtmlArtifactInNewTab } from "./htmlArtifactDocument";
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

  // The composed, CSP-carrying document for the Preview iframe (recomputed only
  // when the selected artifact's markup changes).
  const composed = useMemo(() => (selected ? composeHtmlDocument(selected.html, selected.css) : ""), [selected]);

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
          </div>

          <div className={styles.body}>
            {tab === "preview" && (
              <iframe
                key={`${selected.artifact_id}:${selected.version}`}
                className={styles.previewFrame}
                title={selected.title || untitled}
                sandbox=""
                referrerPolicy="no-referrer"
                srcDoc={composed}
              />
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
