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

import CloseIcon from "@mui/icons-material/Close";
import DownloadIcon from "@mui/icons-material/Download";
import { AppBar, Box, CircularProgress, IconButton, Toolbar, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { useGetDocumentMarkdownPreviewMutation } from "../slices/documentApi.tsx";
import MarkdownRendererWithHighlights, { HighlightedPart } from "../components/markdown/MarkdownRendererWithHighlights.tsx";

// Props definition for the DocumentViewer component
interface DocumentViewerProps {
  document: {
    document_uid: string; // Unique identifier of the document
    file_name?: string; // Optional file name (used for display and download)
    file_url?: string; // Optional direct URL to fetch content from
    content?: string; // Optional inline content (may be base64-encoded)
  } | null;
  onClose: () => void; // Callback when the component should be closed
  highlightedParts?: HighlightedPart[]; // Optional array of parts to highlight in the document
  chunksToHighlight?: string[]; // Optional array of text chunks to highlight in the document
}

/**
 * DocumentViewer
 *
 * This component is responsible for:
 * - Downloading and rendering markdown documents
 * - Supporting both inline base64 content and remote file URLs
 * - Showing a progress spinner while loading content
 * - Offering a download button for the file (if URL is present)
 *
 * It encapsulates all logic related to document fetching and rendering.
 * The parent component does **not** need to handle downloading or decoding.
 */
export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  document: doc,
  onClose,
  highlightedParts = [],
  chunksToHighlight = [],
}) => {
  const [docContent, setDocContent] = useState<string>(""); // Parsed document content (decoded)
  const [isLoadingDoc, setIsLoadingDoc] = useState<boolean>(false); // Internal loading state
  const [getFullDocument] = useGetDocumentMarkdownPreviewMutation(); // API call to fetch full document

  // Compute chunk parts to highlight in the document
  const highlightedPartsFromExtracts = chunksToHighlight.map((chunk) => {
    const start = docContent.indexOf(chunk);
    const end = start + chunk.length;
    return { start, end };
  });

  // Load markdown content whenever a document is provided
  useEffect(() => {
    if (!doc?.document_uid) return;

    const load = async () => {
      setIsLoadingDoc(true);

      try {
        let content = doc.content;
        let fileUrl = doc.file_url;
        let fileName = doc.file_name;
        console.log("[DocumentViewer] content:", content);
        console.log("[DocumentViewer] file_url:", fileUrl);
        console.log("[DocumentViewer] file_name:", fileName);
        // If content and file_url are missing, try fetching full document
        if (!content && !fileUrl) {
          console.log("[DocumentViewer] fetching from API via document_uid:", doc.document_uid);
          const response = await getFullDocument({
            document_uid: doc.document_uid,
          }).unwrap();
          console.log("[DocumentViewer] GOT :", response);
          content = response.content;
        }

        // Try decoding embedded content
        if (content) {
          try {
            setDocContent(atob(content));
          } catch {
            setDocContent(content);
          }
        } else if (fileUrl) {
          const res = await fetch(fileUrl);
          const text = await res.text();
          setDocContent(text);
        } else {
          setDocContent("No content found.");
        }
      } catch (e) {
        console.error("[DocumentViewer] Error fetching document:", e);
        setDocContent("Error loading document.");
      } finally {
        setIsLoadingDoc(false);
      }
    };

    load();
  }, [doc]);

  // Triggers file download via <a download>
  const handleDownload = () => {
    if (doc?.file_url) {
      const link = window.document.createElement("a");
      link.href = doc.file_url;
      link.download = doc.file_name || "document.md";
      link.target = "_blank";
      window.document.body.appendChild(link);
      link.click();
      window.document.body.removeChild(link);
    }
  };
  //console.log("DocumentViewer rendering docContent: ", docContent);
  return (
    <Box
      sx={{
        width: "80vw",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header with title and actions */}
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

      {/* Main content area */}
      <Box sx={{ flex: 1, overflow: "auto", p: 3 }}>
        {isLoadingDoc ? (
          <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            <MarkdownRendererWithHighlights
              highlightedParts={[...highlightedParts, ...highlightedPartsFromExtracts]}
              content={docContent}
              size="medium"
              enableEmojiSubstitution={true}
            />
            {/* <CustomMarkdownRenderer content={docContent} size="small" /> */}
          </>
        )}
      </Box>
    </Box>
  );
};

export default DocumentViewer;
