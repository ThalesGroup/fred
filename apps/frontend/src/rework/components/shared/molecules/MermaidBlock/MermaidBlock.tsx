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

import { useEffect, useId, useState } from "react";
import mermaid from "mermaid";
import { useIsDark } from "../../../../core/hooks/useIsDark";
import styles from "./MermaidBlock.module.css";

interface MermaidBlockProps {
  code: string;
}

export function MermaidBlock({ code }: MermaidBlockProps) {
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const isDark = useIsDark();

  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  // useId produces a stable, unique id per component instance (e.g. ":r0:").
  // Mermaid requires a plain alphanumeric DOM id.
  const uid = useId();
  const diagramId = `mermaid${uid.replace(/[^a-zA-Z0-9]/g, "")}`;

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setError(null);

    mermaid.initialize({ startOnLoad: false, theme: isDark ? "dark" : "default" });

    mermaid
      .render(diagramId, code)
      .then(({ svg: rendered }) => {
        if (!cancelled) setSvg(rendered);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Diagram could not be rendered.");
      });

    return () => {
      cancelled = true;
    };
  }, [code, isDark, diagramId]);

  if (error) {
    return (
      <div className={styles.block}>
        <div className={styles.header}>
          <span className={styles.lang}>mermaid</span>
        </div>
        <div className={styles.error}>
          <span className={styles.errorLabel}>Diagram error</span>
          <pre className={styles.errorDetail}>{error}</pre>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.block}>
      <div className={styles.header}>
        <span className={styles.lang}>mermaid</span>
        <button className={styles.copy} onClick={handleCopy} aria-label="Copy diagram source">
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <div className={styles.body}>
        {svg === null ? (
          <span className={styles.loading}>Rendering diagram…</span>
        ) : (
          // Safe: SVG is produced by the mermaid library from our own agent
          // content — never from raw user input.
          <div className={styles.diagram} dangerouslySetInnerHTML={{ __html: svg }} />
        )}
      </div>
    </div>
  );
}
