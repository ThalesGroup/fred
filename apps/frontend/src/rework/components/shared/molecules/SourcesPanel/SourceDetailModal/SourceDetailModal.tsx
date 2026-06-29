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

import { useEffect } from "react";
import type { VectorSearchHit } from "../../../../../../slices/runtime/runtimeOpenApi";
import { MarkdownRenderer } from "../../MarkdownRenderer/MarkdownRenderer";
import { buildDocumentViewerPath } from "../../../../../utils/documentViewerUtils";
import styles from "./SourceDetailModal.module.css";

interface SourceDetailModalProps {
  source: VectorSearchHit;
  index: number;
  onClose: () => void;
}

function MetaRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (!value && value !== 0) return null;
  return (
    <div className={styles.metaRow}>
      <span className={styles.metaLabel}>{label}</span>
      <span className={styles.metaValue}>{value}</span>
    </div>
  );
}

export function SourceDetailModal({ source, index, onClose }: SourceDetailModalProps) {
  const score = typeof source.score === "number" ? Math.round(source.score * 100) : null;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <>
      <div className={styles.overlay} onClick={onClose} aria-hidden="true" />
      <div className={styles.modal} role="dialog" aria-modal="true" aria-label={`Source ${index}: ${source.title}`}>
        <header className={styles.header}>
          <div className={styles.titleRow}>
            <span className={styles.index}>[{index}]</span>
            <h2 className={styles.title}>{source.title || source.file_name || "Untitled"}</h2>
            {score !== null && <span className={styles.score}>{score}%</span>}
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <div className={styles.body}>
          <div className={styles.meta}>
            <MetaRow label="File" value={source.file_name} />
            <MetaRow label="Page" value={source.page} />
            <MetaRow label="Section" value={source.section} />
            <MetaRow label="Type" value={source.mime_type} />
            <MetaRow label="Language" value={source.language} />
            <MetaRow label="Author" value={source.author} />
            <MetaRow label="Repository" value={source.repository} />
          </div>

          {source.content && (
            <div className={styles.contentSection}>
              <p className={styles.contentLabel}>Extract</p>
              <div className={styles.content}>
                <MarkdownRenderer text={source.content} />
              </div>
            </div>
          )}

          {source.uid && source.uid !== "Unknown" && (
            <a
              className={styles.openDocLink}
              href={buildDocumentViewerPath(source)}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open document ↗
            </a>
          )}
        </div>
      </div>
    </>
  );
}
