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

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { readMermaidTheme, renderMermaid } from "./mermaidRenderer";
import { prepareMermaidSvg } from "./mermaidSvg";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { FullPageModal } from "../FullPageModal/FullPageModal";
import styles from "./MermaidBlock.module.css";

interface MermaidBlockProps {
  code: string;
}

export function MermaidBlock({ code }: MermaidBlockProps) {
  const { t } = useTranslation();
  const [svg, setSvg] = useState<{ inline: string; enlarged: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [zoomed, setZoomed] = useState(false);
  const [themeRevision, setThemeRevision] = useState(0);
  const blockRef = useRef<HTMLDivElement>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const enlargeTrigger = useRef<HTMLButtonElement | null>(null);
  const renderedSource = useRef(code);

  function closeEnlarged() {
    setZoomed(false);
    enlargeTrigger.current?.focus();
  }

  function handleCopy() {
    writeRichClipboard("", code).then((ok) => {
      if (ok) {
        setCopied(true);
        clearTimeout(copyTimer.current);
        copyTimer.current = setTimeout(() => setCopied(false), 2000);
      }
    });
  }

  const uid = useId();
  const diagramId = `mermaid${uid.replace(/[^a-zA-Z0-9]/g, "")}`;

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeRevision((value) => value + 1));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "data-ui-theme", "data-ui-base-theme"],
    });
    return () => {
      observer.disconnect();
      clearTimeout(copyTimer.current);
    };
  }, []);

  useEffect(() => {
    if (renderedSource.current !== code) {
      setSvg(null);
      renderedSource.current = code;
    }
    setError(null);

    let cancelled = false;
    const theme = readMermaidTheme(blockRef.current!);
    renderMermaid(code, diagramId, theme)
      .then((rendered) => {
        if (!cancelled) {
          setSvg({
            inline: prepareMermaidSvg(rendered, `${diagramId}Inline`),
            enlarged: prepareMermaidSvg(rendered, `${diagramId}Enlarged`),
          });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "");
      });

    return () => {
      cancelled = true;
    };
  }, [code, themeRevision, diagramId]);

  return (
    <div className={styles.preview} ref={blockRef} data-mermaid-preview>
      <div className={styles.toolbar} data-clipboard-ignore>
        {svg !== null && (
          <IconButton
            type="button"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "fullscreen" }}
            aria-label={t("mermaid.enlarge")}
            title={t("mermaid.enlarge")}
            aria-haspopup="dialog"
            onClick={(event) => {
              enlargeTrigger.current = event.currentTarget;
              setZoomed(true);
            }}
          />
        )}
        <IconButton
          type="button"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: copied ? "check" : "content_copy" }}
          onClick={handleCopy}
          aria-label={copied ? t("common.copied") : t("mermaid.copySource")}
          title={copied ? t("common.copied") : t("mermaid.copySource")}
        />
      </div>
      {error !== null ? (
        <div className={styles.error} role="alert">
          <span className={styles.errorLabel}>{t("mermaid.error")}</span>
          <pre className={styles.errorDetail}>{error || t("mermaid.renderError")}</pre>
        </div>
      ) : (
        <div className={styles.body}>
          {svg === null ? (
            <span className={styles.loading} role="status">
              {t("mermaid.loading")}
            </span>
          ) : (
            <div
              id={`${diagramId}Inline`}
              className={styles.diagram}
              role="img"
              aria-label={t("mermaid.diagram")}
              data-clipboard-diagram-label="Mermaid diagram"
              dangerouslySetInnerHTML={{ __html: svg.inline }}
            />
          )}
        </div>
      )}

      {svg !== null && (
        <FullPageModal isOpen={zoomed} onClose={closeEnlarged} id={`${diagramId}Zoom`}>
          <div className={styles.zoomOverlay} onClick={closeEnlarged}>
            <div className={styles.zoomShell} onClick={(event) => event.stopPropagation()}>
              <header className={styles.zoomHeader}>
                <span id={`${diagramId}Zoom-title`} className={styles.title}>
                  {t("mermaid.title")}
                </span>
                <IconButton
                  type="button"
                  autoFocus
                  variant="icon"
                  size="small"
                  icon={{ category: "outlined", type: "fullscreen_exit" }}
                  aria-label={t("mermaid.close")}
                  onClick={closeEnlarged}
                />
              </header>
              <div
                id={`${diagramId}Enlarged`}
                className={styles.zoomBody}
                role="img"
                aria-label={t("mermaid.diagram")}
                dangerouslySetInnerHTML={{ __html: svg.enlarged }}
              />
            </div>
          </div>
        </FullPageModal>
      )}
    </div>
  );
}
