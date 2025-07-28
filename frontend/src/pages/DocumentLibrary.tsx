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

import { Box, Button, ButtonGroup, Container } from "@mui/material";
import { useEffect, useState } from "react";

import { useTranslation } from "react-i18next";
import { TopBar } from "../common/TopBar";
import { AllDocumentsList } from "../components/documents/AllDocumentsList";
import { AllLibrariesList } from "../components/documents/AllLibrariesList";

type DocumentLibraryView = "libraries" | "documents";

/**
 * DocumentLibrary.tsx
 *
 * This component renders the **Document Library** page, which enables users to:
 * - View and search documents in the knowledge base
 * - Upload new documents via drag & drop or manual file selection
 * - Delete existing documents (with permission)
 * - Preview documents (Markdown-only for now) in a Drawer-based viewer
 *
 * ## Key Features:
 *
 * 1. **Search & Filter**:
 *    - Users can type keywords to search filenames.
 *
 * 2. **Pagination**:
 *    - Document list is paginated with user-selectable rows per page (10, 20, 50).
 *
 * 3. **Upload Drawer**:
 *    - Only visible to users with "admin" or "editor" roles.
 *    - Allows upload of multiple documents.
 *    - Supports real-time streaming feedback (progress steps).
 *
 * 4. **DocumentTable Integration**:
 *    - Displays a table of documents with actions like:
 *      - Select/delete multiple documents
 *      - Preview documents in a Markdown viewer
 *      - Toggle retrievability (for admins)
 *
 * 5. **DocumentViewer Integration**:
 *    - When a user clicks "preview", the backend is queried using the document UID.
 *    - If Markdown content is available, it's shown in a Drawer viewer with proper rendering.
 *
 *
 * ## User Roles:
 *
 * - Admins/Editors:
 *   - Can upload/delete documents
 *   - See upload drawer
 * - Viewers:
 *   - Can search and preview only
 *
 * ## Design Considerations:
 *
 * - Emphasis on **separation of concerns**:
 *   - Temporary (to-be-uploaded) files are stored separately from backend ones
 *   - Uploading does not interfere with the main list view
 * - React `useCallback` and `useEffect` hooks used to manage state consistency
 * - Drawer and transitions are animated for smooth UX
 * - Responsive layout using MUI's Grid2 and Breakpoints
 */
export const DocumentLibrary = () => {
  const { t } = useTranslation();

  // View state: 'libraries' or 'documents', persisted in localStorage
  const VIEW_KEY = "documentLibrary.selectedView";
  const [selectedView, setSelectedView] = useState<DocumentLibraryView>(() => {
    const defaultView = "libraries";

    // Retrive last used view from localStorage
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(VIEW_KEY);
      return stored === "libraries" || stored === "documents" ? stored : defaultView;
    }
    return defaultView;
  });

  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(VIEW_KEY, selectedView);
    }
  }, [selectedView]);

  return (
    <>
      <TopBar title={t("documentLibrary.title")} description={t("documentLibrary.description")}>
        <Box>
          <ButtonGroup variant="outlined" color="primary" size="small">
            <Button
              variant={selectedView === "libraries" ? "contained" : "outlined"}
              onClick={() => setSelectedView("libraries")}
            >
              {t("documentLibrary.librariesView")}
            </Button>
            <Button
              variant={selectedView === "documents" ? "contained" : "outlined"}
              onClick={() => setSelectedView("documents")}
            >
              {t("documentLibrary.documentsView")}
            </Button>
          </ButtonGroup>
        </Box>
      </TopBar>

      {/* Main content */}
      <Box sx={{ mb: 3 }}>
        {/* View Switch */}

        {/* Libraries View */}
        {selectedView === "libraries" && (
          <Container maxWidth="xl">
            <AllLibrariesList />
          </Container>
        )}

        {/* Documents View */}
        {selectedView === "documents" && <AllDocumentsList />}
      </Box>
    </>
  );
};
