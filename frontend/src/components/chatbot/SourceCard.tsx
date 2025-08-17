// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// ...

import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import { Box, Tooltip, Typography } from "@mui/material";
import { VectorSearchHit } from "../../slices/agentic/agenticOpenApi.ts"; // ✅ new schema
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

  // Prefer a readable label: title → file_name → documentId
  const label =
    hits[0]?.title?.trim() ||
    hits[0]?.file_name?.trim() ||
    documentId;

  const handleOpenDocument = () => {
    // Prefer precomputed viewer_fragment, otherwise the raw content
    const snippets = hits
      .map((h) => h.viewer_fragment || h.content)
      .filter((s): s is string => Boolean(s && s.trim().length > 0));

    openDocument(
      { document_uid: documentId },
      { chunksToHighlight: snippets }
    );
  };

  const partsCount = hits.length;

  return (
    <Tooltip title={`${partsCount} part${partsCount > 1 ? "s" : ""} of this document were used`}>
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
          "&:hover": {
            background: theme.palette.action.hover,
          },
        })}
        onClick={handleOpenDocument}
      >
        <ArticleOutlinedIcon sx={{ fontSize: "1.2rem", color: "text.secondary" }} />
        <Typography
          sx={{ fontSize: "0.85rem", color: "text.secondary", cursor: "pointer" }}
          onClick={handleOpenDocument}
          title={label}
        >
          {label}
        </Typography>
      </Box>
    </Tooltip>
  );
};
