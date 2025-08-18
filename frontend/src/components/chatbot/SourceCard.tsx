// Copyright Thales 2025
// Licensed under the Apache License, Version 2.0

import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import ShieldIcon from "@mui/icons-material/Shield";
import { Box, Chip, Tooltip, Typography } from "@mui/material";
import { VectorSearchHit } from "../../slices/agentic/agenticOpenApi.ts";
import { useDocumentViewer } from "../../common/useDocumentViewer.tsx";

interface SourceCardProps {
  /** Document UID (group key) */
  documentId: string;
  /** All passages from this document that were used */
  hits: VectorSearchHit[];
}

export const SourceCard = ({ documentId, hits }: SourceCardProps) => {
  const { openDocument } = useDocumentViewer();

  if (!hits || hits.length === 0) return null;

  // sort hits: rank asc (if present) => score desc; then dedupe by page|section|fragment|content
  const sorted = hits
    .slice()
    .sort((a, b) => {
      const ra = a.rank ?? Number.MAX_SAFE_INTEGER;
      const rb = b.rank ?? Number.MAX_SAFE_INTEGER;
      if (ra !== rb) return ra - rb;
      return (b.score ?? 0) - (a.score ?? 0);
    });

  const deduped = sorted.filter((h, i, arr) => {
    const key = `${h.page ?? ""}|${h.section ?? ""}|${h.viewer_fragment ?? ""}|${(h.content || "").slice(0, 80)}`;
    const first = arr.findIndex(
      x =>
        `${x.page ?? ""}|${x.section ?? ""}|${x.viewer_fragment ?? ""}|${(x.content || "").slice(0, 80)}` === key
    );
    return first === i;
  });

  // doc-level summary (best available across hits)
  const bestScore = Math.max(...deduped.map(h => h.score ?? 0));
  const title =
    (deduped.find(h => h.title)?.title || deduped[0]?.title)?.trim() ||
    deduped[0]?.file_name?.trim() ||
    documentId;

  const language = deduped.find(h => h.language)?.language || undefined;
  const mime = deduped.find(h => h.mime_type)?.mime_type || undefined;
  const license = deduped.find(h => h.license)?.license || undefined;
  const confidential =
    deduped.find(h => h.confidential !== null && h.confidential !== undefined)?.confidential ?? false;

  const tagNames = Array.from(new Set(deduped.flatMap(h => h.tag_names || [])));
  const partsCount = deduped.length;

  // build snippets for the viewer (prefer viewer_fragment; fallback to content)
  const snippetStrings = deduped
    .map(h => h.viewer_fragment || h.content)
    .filter((s): s is string => Boolean(s && s.trim().length > 0));

  const handleOpenDocument = () => {
    // dev logs to confirm payload
    console.groupCollapsed(`[SourceCard] open ${documentId} (${partsCount} parts)`);
    console.table(
      deduped.map(h => ({
        uid: h.uid,
        page: h.page ?? "",
        section: h.section ?? "",
        score: h.score,
        fragment: (h.viewer_fragment || "").slice(0, 40),
        lang: h.language ?? "",
        mime: h.mime_type ?? "",
        tag_names: (h.tag_names || []).join(", "),
      }))
    );
    console.groupEnd();

    openDocument(
      { document_uid: documentId },
      { chunksToHighlight: snippetStrings }
    );
  };

  return (
    <Tooltip title={`${partsCount} passage${partsCount > 1 ? "s" : ""} from this document were used`}>
      <Box
        flex={1}
        display="flex"
        alignItems="center"
        gap={1}
        sx={(theme) => ({
          cursor: "pointer",
          paddingX: 1,
          paddingY: 0.5,
          borderRadius: 1,
          transition: "background 0.2s",
          "&:hover": { background: theme.palette.action.hover },
        })}
        onClick={handleOpenDocument}
      >
        <ArticleOutlinedIcon sx={{ fontSize: "1.2rem", color: "text.secondary" }} />

        <Box sx={{ minWidth: 0, flex: 1, display: "flex", flexDirection: "column" }}>
          <Typography
            sx={{ fontSize: "0.9rem", fontWeight: 600 }}
            noWrap
            title={title}
          >
            {title}
          </Typography>

          <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 0.25 }}>
            <Chip size="small" label={`${partsCount} parts`} />
            <ScorePill score={bestScore} />
            {language && <Chip size="small" label={language} variant="outlined" />}
            {mime && <Chip size="small" label={mime} variant="outlined" />}
            {license && <Chip size="small" label={`license: ${license}`} variant="outlined" />}
            {confidential && (
              <Chip
                size="small"
                color="warning"
                label={
                  <Box display="flex" alignItems="center" gap={0.5}>
                    <ShieldIcon fontSize="small" /> Confidential
                  </Box>
                }
              />
            )}
            {tagNames.slice(0, 4).map((t) => (
              <Chip key={t} size="small" label={t} />
            ))}
            {tagNames.length > 4 && <Chip size="small" label={`+${tagNames.length - 4}`} />}
          </Box>
        </Box>
      </Box>
    </Tooltip>
  );
};

/** Compact score chip (0..1 → %) */
function ScorePill({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score ?? 0)) * 100;
  return <Chip size="small" label={`${Math.round(pct)}%`} variant="outlined" />;
}
