// NewDocumentViewer.tsx
// Copyright Thales 2025
// Licensed under the Apache License, Version 2.0

import CloseIcon from "@mui/icons-material/Close";
import DownloadIcon from "@mui/icons-material/Download";
import { AppBar, Box, CircularProgress, IconButton, Toolbar, Typography } from "@mui/material";
import { useEffect, useState } from "react";

import { useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

import MarkdownRendererWithHighlights, { HighlightedPart } from "../components/markdown/MarkdownRendererWithHighlights";

interface DocumentViewerProps {
  document: {
    document_uid: string;
    file_name?: string;
    file_url?: string;
    content?: string;
  } | null;
  onClose: () => void;
  highlightedParts?: HighlightedPart[];
  chunksToHighlight?: string[];
}

const decodeMaybeBase64 = (s: string) => {
  try {
    return atob(s);
  } catch {
    return s;
  }
};

export const NewDocumentViewer: React.FC<DocumentViewerProps> = ({
  document: doc,
  onClose,
  highlightedParts = [],
  chunksToHighlight = [],
}) => {
  const [docContent, setDocContent] = useState<string>("");
  const [isLoadingDoc, setIsLoadingDoc] = useState<boolean>(false);

  // ⬇️ CHANGE 2: generated API exposes a *query* hook; we use the lazy variant to keep identical call style
  const [triggerGetPreview] = useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery();

  // same logic as before (just safer for -1 indices)
  const highlightedPartsFromExtracts = chunksToHighlight
    .map((chunk) => {
      const start = docContent.indexOf(chunk);
      return start >= 0 ? { start, end: start + chunk.length } : null;
    })
    .filter(Boolean) as HighlightedPart[];

  useEffect(() => {
    if (!doc?.document_uid) return;

    const load = async () => {
      setIsLoadingDoc(true);
      try {
        let content = doc.content;
        const fileUrl = doc.file_url;

        if (content) {
          setDocContent(decodeMaybeBase64(content));
        } else if (fileUrl) {
          const res = await fetch(fileUrl);
          const text = await res.text();
          setDocContent(text);
        } else {
          // ⬇️ SAME CALLING PATTERN; NEW HOOK + SAME response shape: { content: string }
          const resp = await triggerGetPreview({ documentUid: doc.document_uid }).unwrap();
          setDocContent(decodeMaybeBase64(resp?.content ?? ""));
        }
      } catch (e) {
        console.error("[NewDocumentViewer] Error fetching document:", e);
        setDocContent("Error loading document.");
      } finally {
        setIsLoadingDoc(false);
      }
    };

    void load();
  }, [doc?.document_uid, doc?.content, doc?.file_url, triggerGetPreview]);

  const handleDownload = () => {
    if (!doc?.file_url) return;
    const link = window.document.createElement("a");
    link.href = doc.file_url;
    link.download = doc.file_name || "document.md";
    link.target = "_blank";
    window.document.body.appendChild(link);
    link.click();
    window.document.body.removeChild(link);
  };

  return (
    <Box sx={{ width: "80vw", height: "100vh", display: "flex", flexDirection: "column" }}>
      <AppBar position="static" color="default" elevation={0}>
        <Toolbar>
          <Typography variant="h6" sx={{ flex: 1 }}>
            {doc?.file_name || "Markdown Document"}
          </Typography>
          <IconButton onClick={handleDownload} disabled={!doc?.file_url}>
            <DownloadIcon />
          </IconButton>
          <IconButton onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </Toolbar>
      </AppBar>

      <Box sx={{ flex: 1, overflow: "auto", p: 3 }}>
        {isLoadingDoc ? (
          <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          <MarkdownRendererWithHighlights
            highlightedParts={[...highlightedParts, ...highlightedPartsFromExtracts]}
            content={docContent}
            size="medium"
            enableEmojiSubstitution
          />
        )}
      </Box>
    </Box>
  );
};

export default NewDocumentViewer;
