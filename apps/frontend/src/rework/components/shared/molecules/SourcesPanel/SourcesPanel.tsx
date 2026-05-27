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

import { useEffect, useState } from "react";
import type { VectorSearchHit } from "../../../../../slices/agentic/agenticOpenApi";
import { SourceCard } from "./SourceCard/SourceCard";
import { SourceDetailModal } from "./SourceDetailModal/SourceDetailModal";
import styles from "./SourcesPanel.module.css";

interface SourcesPanelProps {
  sources: VectorSearchHit[];
  /** 1-based index of the source highlighted via a citation badge click */
  activeIndex?: number | null;
}

export function SourcesPanel({ sources, activeIndex }: SourcesPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const [selected, setSelected] = useState<{ source: VectorSearchHit; index: number } | null>(null);

  // Auto-expand when a citation badge is clicked
  useEffect(() => {
    if (activeIndex != null) setExpanded(true);
  }, [activeIndex]);

  if (sources.length === 0) return null;

  return (
    <div className={styles.root}>
      <button className={styles.toggle} onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
        <span className={`${styles.chevron} ${expanded ? styles.chevronOpen : ""}`}>›</span>
        <span className={styles.heading}>Sources</span>
        <span className={styles.count}>({sources.length})</span>
      </button>

      {expanded && (
        <div className={styles.list}>
          {sources.map((src, i) => (
            <SourceCard
              key={src.uid ?? i}
              source={src}
              index={i + 1}
              active={activeIndex === i + 1}
              onSelect={(s) => setSelected({ source: s, index: i + 1 })}
            />
          ))}
        </div>
      )}

      {selected && (
        <SourceDetailModal source={selected.source} index={selected.index} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
