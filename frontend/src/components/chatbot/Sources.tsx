// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// ...

import LibraryBooksIcon from "@mui/icons-material/LibraryBooks";
import { Box } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useEffect, useRef, useState } from "react";
import { VectorSearchHit } from "../../slices/agentic/agenticOpenApi.ts"; 
import FoldableChatSection from "./FoldableChatSection";
import { SourceCard } from "./SourceCard.tsx";

type Props = {
  /** New schema: metadata.sources */
  sources: VectorSearchHit[];
  /** Expand the foldable section by default */
  expandSources?: boolean;
  /** Show/hide the section entirely */
  enableSources?: boolean;
};

export default function Sources({ sources, expandSources = false, enableSources = false }: Props) {
  const theme = useTheme();

  // Group hits by document uid
  const groupedByDoc: Record<string, VectorSearchHit[]> = sources.reduce((acc, hit) => {
    const docId = hit.uid; // ✅ new schema field
    if (!docId) return acc; // guard
    if (!acc[docId]) acc[docId] = [];
    acc[docId].push(hit);
    return acc;
  }, {} as Record<string, VectorSearchHit[]>);

  // Gradient visibility state and ref
  const scrollBoxRef = useRef<HTMLDivElement>(null);
  const [showGradient, setShowGradient] = useState(false);

  useEffect(() => {
    const scrollBox = scrollBoxRef.current;
    if (!scrollBox) return;

    const checkScroll = () => {
      if (scrollBox.scrollHeight <= scrollBox.clientHeight + 1) {
        setShowGradient(false);
        return;
      }
      const atBottom = scrollBox.scrollTop + scrollBox.clientHeight >= scrollBox.scrollHeight - 8;
      setShowGradient(!atBottom);
    };

    checkScroll();
    scrollBox.addEventListener("scroll", checkScroll);
    window.addEventListener("resize", checkScroll);

    return () => {
      scrollBox.removeEventListener("scroll", checkScroll);
      window.removeEventListener("resize", checkScroll);
    };
  }, [sources]);

  if (!enableSources || sources.length === 0) return null;

  const docCount = Object.keys(groupedByDoc).length;

  return (
    <FoldableChatSection
      title={`Sources (${docCount})`}
      icon={<LibraryBooksIcon />}
      defaultOpen={expandSources}
      sx={{ mt: 2 }}
    >
      <Box
        sx={{
          position: "relative",
          mt: 1,
          borderRadius: 2,
          overflow: "hidden",
          border: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Box
          ref={scrollBoxRef}
          sx={{
            display: "flex",
            flexDirection: "column",
            scrollbarWidth: "thin",
            gap: 0,
            overflow: "auto",
            p: 1,
            maxHeight: "150px",
          }}
        >
          {Object.entries(groupedByDoc).map(([uid, hits], idx) => (
            <Box key={`${uid}-${idx}`}>
              {/* ✅ SourceCard updated to accept VectorSearchHit[] */}
              <SourceCard documentId={uid} hits={hits} />
            </Box>
          ))}
        </Box>

        {/* Bottom gradient overlay for scroll hint */}
        {showGradient && (
          <Box
            sx={{
              pointerEvents: "none",
              position: "absolute",
              left: 0,
              right: 0,
              bottom: 0,
              height: 28,
              background: `linear-gradient(to bottom, rgba(255,255,255,0) 0%, ${theme.palette.background.default} 100%)`,
            }}
          />
        )}
      </Box>
    </FoldableChatSection>
  );
}
