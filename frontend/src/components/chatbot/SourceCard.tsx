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

import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import { Box, Tooltip, Typography } from "@mui/material";
import { ChatSource } from "../../slices/chatApiStructures.ts";
import { useDocumentViewer } from "../documents/useDocumentViewer.tsx";

interface SourceCardProps {
  documentId: string; // Unique identifier for the document
  sources: ChatSource[]; // Part of document used to answer
}

export const SourceCard = ({ documentId, sources }: SourceCardProps) => {
  const { openDocument } = useDocumentViewer();
  
  if (!sources || sources.length === 0) {
    return null;
  }

  const handleOpenDocument = () => {
    openDocument(
      { document_uid: documentId },
      { chunksToHighlight: sources.map((source) => source.content) }
    );
  };

  return (
    <Tooltip title={`${sources.length} part(s) of this document were used to answer`}>
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
        >
          {sources[0].file_name}
        </Typography>
      </Box>
    </Tooltip>
  );
};
