// app/components/chat/citations.tsx
import React from "react";
import { ChatMessage } from "../../slices/agentic/agenticOpenApi";

export type CitationMeta = { title?: string | null; href?: string | null };

// Build [n] -> uid using the order of metadata.sources (sorted by rank asc)
export function buildCitationMap(msg: ChatMessage): Map<number, string> {
  const m = new Map<number, string>();
  const src = (msg.metadata?.sources as any[] | undefined) ?? [];
  if (!src.length) return m;
  const ordered = [...src].sort((a, b) => (a?.rank ?? 1e9) - (b?.rank ?? 1e9));
  ordered.forEach((hit, i) => {
    const n = i + 1;
    if (hit?.uid) m.set(n, hit.uid);
  });
  return m;
}

// Replace [1] [2] [3] with clickable superscripts.
// Hover: calls onHover(uid|null)
// Click: calls onClick(n, uid)
export function renderTextWithCitations(
  text: string,
  map: Map<number, string>,
  onHover?: (uid: string | null) => void,
  onClick?: (n: number, uid: string | null) => void
): React.ReactNode {
  if (!text) return null;
  const chunks = text.split(/(\[\d+\])/g); // keep markers
  return chunks.map((chunk, i) => {
    const m = chunk.match(/^\[(\d+)\]$/);
    if (!m) return <React.Fragment key={i}>{chunk}</React.Fragment>;

    const n = Number(m[1]);
    const uid = map.get(n) || null;

    return (
      <sup
        key={i}
        onMouseEnter={() => onHover?.(uid)}
        onMouseLeave={() => onHover?.(null)}
        onClick={() => onClick?.(n, uid)}
        style={{
          cursor: uid ? "pointer" : "default",
          padding: "0 2px",
          borderRadius: 30,
          display: "inline-block",
          color: uid ? "inherit" : "gray",
          fontWeight: 500,
        }}
        aria-label={`Citation [${n}]`}
      >
        [{n}]
      </sup>
    );
  });
}
