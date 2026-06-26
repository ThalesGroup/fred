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

import type { VectorSearchHit } from "../../../../../../slices/runtime/runtimeOpenApi";
import styles from "./SourceCard.module.css";

interface SourceCardProps {
  source: VectorSearchHit;
  index: number;
  active?: boolean;
  onSelect: (source: VectorSearchHit) => void;
}

export function SourceCard({ source, index, active = false, onSelect }: SourceCardProps) {
  const score = typeof source.score === "number" ? Math.round(source.score * 100) : null;

  return (
    <div
      className={`${styles.card} ${active ? styles.active : ""}`}
      role="button"
      tabIndex={0}
      aria-label={`Source ${index}: ${source.title}`}
      onClick={() => onSelect(source)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(source)}
    >
      <div className={styles.header}>
        <span className={styles.index}>[{index}]</span>
        <span className={styles.title}>{source.title || source.file_name || "Untitled"}</span>
        {score !== null && <span className={styles.score}>{score}%</span>}
      </div>
      {source.content && <p className={styles.excerpt}>{source.content}</p>}
    </div>
  );
}
