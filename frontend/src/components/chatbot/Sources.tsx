// Copyright Thales 2025
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

import { useState } from "react";
import { useTheme } from "@mui/material/styles";
import { Button, Typography, Modal, Box, IconButton, Divider, Chip } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import VisibilityIcon from "@mui/icons-material/Visibility";
import LibraryBooksIcon from "@mui/icons-material/LibraryBooks";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { ChatSource } from "../../slices/chatApiStructures.ts";
import MarkdownRenderer from "../markdown/MarkdownRenderer.tsx";
import { SourceCard } from "./SourceCard.tsx";
import { getDocumentIcon } from "../documents/DocumentIcon.tsx";
import FoldableChatSection from "./FoldableChatSection";

/**
 * Sources Component
 *
 * This component displays a section for document sources related to a chat interaction.
 *
 * Features:
 * - Collapsible source panel with preview of top 3 sources
 * - Modal popup to quickly preview a document summary
 * - Drawer panel to list and open all sources
 * - DocumentViewer integration to render full content of a selected markdown document
 *
 * Props:
 * - sources: List of ChatSource objects
 * - expandSources: Whether to start with sources expanded
 * - enableSources: Whether to display the sources section at all
 */
export default function Sources({
  sources,
  expandSources = false,
  enableSources = false,
}: {
  sources: ChatSource[];
  expandSources: boolean;
  enableSources: boolean;
}) {
  const theme = useTheme();

  // Group sources by document_uid, value is an array of ChatSource
  const documents: { [docId: string]: ChatSource[] } = sources.reduce(
    (acc, source) => {
      if (!acc[source.document_uid]) {
        acc[source.document_uid] = [];
      }
      acc[source.document_uid].push(source);
      return acc;
    },
    {} as { [docId: string]: ChatSource[] },
  );

  return (
    <>
      {/* Top-level foldable section for sources */}
      {enableSources && sources.length > 0 && (
        <FoldableChatSection
          title={`Sources (${Object.keys(documents).length})`}
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
              {Object.entries(documents).map(([id, sources], index) => (
                <Box key={index}>
                  <SourceCard documentId={id} sources={sources} />
                </Box>
              ))}
            </Box>
            {/* Bottom gradient overlay for scroll hint */}
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
          </Box>
        </FoldableChatSection>
      )}
    </>
  );
}
