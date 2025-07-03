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

import { useDropzone } from "react-dropzone";
import {
  Box,
  Typography,
  useTheme,
  TextField,
  FormControl,
  MenuItem,
  Select,
  OutlinedInput,
  Button,
  IconButton,
  InputAdornment,
  Pagination,
  Drawer,
  Container,
  Paper,
  Grid2,
  Fade,
} from "@mui/material";
import ClearIcon from "@mui/icons-material/Clear";
import { useEffect, useState } from "react";
import { LoadingSpinner } from "../utils/loadingSpinner";
import UploadIcon from "@mui/icons-material/Upload";
import SaveIcon from "@mui/icons-material/Save";
import SearchIcon from "@mui/icons-material/Search";
import LibraryBooksRoundedIcon from "@mui/icons-material/LibraryBooksRounded";
import { KeyCloakService } from "../security/KeycloakService";
import {
  KnowledgeDocument,
  useDeleteDocumentMutation,
  useGetDocumentMarkdownPreviewMutation,
  useGetDocumentsWithFilterMutation,
  useLazyGetDocumentRawContentQuery,
  useUpdateDocumentRetrievableMutation,
} from "../slices/documentApi";

import { streamProcessDocument } from "../slices/streamDocumentUpload";
import { useToast } from "../components/ToastProvider";
import { ProgressStep, ProgressStepper } from "../components/ProgressStepper";
import { DocumentTable } from "../components/documents/DocumentTable";
import { DocumentDrawerTable } from "../components/documents/DocumentDrawerTable";
import DocumentViewer from "../components/documents/DocumentViewer";
import { TopBar } from "../common/TopBar";
import { useTranslation } from "react-i18next";

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
 *    - If Markdown content is available, it’s shown in a Drawer viewer with proper rendering.
 *
 * ## Backend Communication:
 *
 * - Uses **RTK Query** to talk to the `knowledge` backend:
 *    - `useGetDocumentsWithFilterMutation()` – to list/search documents
 *    - `useDeleteDocumentMutation()` – to delete a document
 *    - `useGetDocumentMarkdownPreviewMutation()` – to fetch markdown preview
 * - Integrates with `streamProcessDocument()` utility for upload streaming
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
  const { showInfo, showError } = useToast();

  // API Hooks
  const [deleteDocument] = useDeleteDocumentMutation();
  const [getDocumentsWithFilter] = useGetDocumentsWithFilterMutation();
  const [getDocumentMarkdownContent] = useGetDocumentMarkdownPreviewMutation();
  const [selectedDocument, setSelectedDocument] = useState<any>(null);
  const [triggerDownload] = useLazyGetDocumentRawContentQuery();

  const theme = useTheme();
  const { t } = useTranslation();

  const hasDocumentManagementPermission = () => {
    const userRoles = KeyCloakService.GetUserRoles();
    return userRoles.includes("admin") || userRoles.includes("editor");
  };

  // tempFiles:
  // This state holds the list of files that the user has selected or dropped into the upload drawer.
  // These files are pending upload to the server and are not yet part of the main document library.
  // - Files are added to tempFiles when dropped or selected via the Dropzone.
  // - They are displayed inside the Upload Drawer for review or removal.
  // - Upon clicking "Save", files from tempFiles are uploaded to the server.
  // - After upload completes (success or failure), tempFiles is cleared.
  // This ensures a clear separation between "pending uploads" and "uploaded documents."
  const [tempFiles, setTempFiles] = useState([]);

  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);

  // UI States
  const [uploadProgressSteps, setUploadProgressSteps] = useState<ProgressStep[]>([]);

  const [searchQuery, setSearchQuery] = useState(""); // Text entered in the search bar
  const [isLoading, setIsLoading] = useState(false); // Controls loading spinner for fetches/uploads
  const [isHighlighted, setIsHighlighted] = useState(false); // Highlight state for the upload Dropzone
  const [documentsPerPage, setDocumentsPerPage] = useState(10); // Number of documents shown per page
  const [currentPage, setCurrentPage] = useState(1); // Current page in the pagination component
  const [openSide, setOpenSide] = useState(false); // Whether the upload drawer is open
  const [showElements, setShowElements] = useState(false); // Controls whether page elements are faded in

  // Backend Data States
  const [documentViewerOpen, setDocumentViewerOpen] = useState<boolean>(false);

  const [updateDocumentRetrievable] = useUpdateDocumentRetrievableMutation();

  // userInfo:
  // Stores information about the currently authenticated user.
  // - name: username retrieved from Keycloak
  // - canManageDocuments: boolean, true if user has admin/editor role
  // - roles: list of user's assigned roles
  //
  // This allows the UI to adjust behavior (e.g., show/hide upload button) based on user permissions.
  const [userInfo, setUserInfo] = useState({
    name: KeyCloakService.GetUserName(),
    canManageDocuments: hasDocumentManagementPermission(),
    roles: KeyCloakService.GetUserRoles(),
  });

  const { getInputProps, open } = useDropzone({
    noClick: true,
    noKeyboard: true,
    onDrop: (acceptedFiles) => {
      setTempFiles((prevFiles) => [...prevFiles, ...acceptedFiles]);
    },
  });

  const [allDocuments, setAllDocuments] = useState<KnowledgeDocument[]>([]);

  const fetchFiles = async () => {
    try {
      setIsLoading(true);

      const response = await getDocumentsWithFilter(null).unwrap();
      const docs = response.documents as KnowledgeDocument[];
      setAllDocuments(docs);
    } catch (error) {
      console.error("Error fetching documents:", error);
      showError({
        summary: "Fetch Failed",
        detail: error?.data?.detail || error.message || "Unknown error occurred while fetching.",
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    setShowElements(true);
    setUserInfo({
      name: KeyCloakService.GetUserName(),
      canManageDocuments: hasDocumentManagementPermission(),
      roles: KeyCloakService.GetUserRoles(),
    });
  }, []);

  useEffect(() => {
    fetchFiles();
  }, [getDocumentsWithFilter]);

  const handleDownload = async (document_uid: string, file_name: string) => {
    try {
      const { data: blob } = await triggerDownload({ document_uid });
      if (blob) {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = file_name || "document";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      showError({
        summary: "Download failed",
        detail: `Could not download document: ${err?.data?.detail || err.message}`,
      });
    }
  };

  const handleDelete = async (document_uid: string) => {
    try {
      await deleteDocument(document_uid).unwrap();
      showInfo({
        summary: "Delete Success",
        detail: `Document ${document_uid} deleted`,
        duration: 3000,
      });
      await fetchFiles(); // <-- ensures fresh backend state
      setSelectedFiles((prev) => prev.filter((id) => id !== document_uid));
    } catch (error) {
      showError({
        summary: "Delete Failed",
        detail: `Could not delete document: ${error?.data?.detail || error.message}`,
      });
    }
  };

  const handleDeleteTemp = (index) => {
    const newFiles = tempFiles.filter((_, i) => i !== index);
    setTempFiles(newFiles);
  };

  const handleDocumentMarkdownPreview = async (document_uid: string, file_name: string) => {
    try {
      const response = await getDocumentMarkdownContent({
        document_uid,
      }).unwrap();
      const { content } = response;

      setSelectedDocument({
        document_uid,
        file_name,
        content,
      });

      setDocumentViewerOpen(true);
    } catch (error) {
      showError({
        summary: "Preview Error",
        detail: `Could not load document content: ${error?.data?.detail || error.message}`,
      });
    }
  };

  const handleAddFiles = async () => {
    setIsLoading(true);
    setUploadProgressSteps([]);
    try {
      let uploadCount = 0;
      for (const file of tempFiles) {
        try {
          await streamProcessDocument(file, (progress) => {
            setUploadProgressSteps((prev) => [
              ...prev,
              {
                step: progress.step,
                status: progress.status,
                filename: file.name,
              },
            ]);
          });
          uploadCount++;
        } catch (e) {
          console.error("Error uploading file:", e);
          showError({
            summary: "Upload Failed",
            detail: `Error uploading ${file.name}: ${e.message}`,
          });
        }
      }
    } catch (error) {
      showError({
        summary: "Upload Failed",
        detail: `Error uploading ${error}`,
      });
      console.error("Unexpected error:", error);
    } finally {
      await fetchFiles();
      setTempFiles([]);
      setOpenSide(false);
      setIsLoading(false);
    }
  };

  // Pagination
  const indexOfLastDocument = currentPage * documentsPerPage;
  const indexOfFirstDocument = indexOfLastDocument - documentsPerPage;
  const filteredFiles = allDocuments.filter((file) =>
    file.document_name.toLowerCase().includes(searchQuery.toLowerCase()),
  );
  const currentDocuments = filteredFiles.slice(indexOfFirstDocument, indexOfLastDocument);

  const handleCloseDocumentViewer = () => {
    setDocumentViewerOpen(false);
  };

  const handleToggleRetrievable = async (file) => {
    try {
      await updateDocumentRetrievable({
        document_uid: file.document_uid,
        retrievable: !file.retrievable,
      }).unwrap();

      showInfo({
        summary: "Updated",
        detail: `Document "${file.document_name}" is now ${!file.retrievable ? "searchable" : "excluded from search"}.`,
      });

      await fetchFiles(); // recharge les documents
    } catch (error) {
      console.error("Update failed:", error);
      showError({
        summary: "Error updating document",
        detail: error?.data?.detail || error.message,
      });
    }
  };

  return (
    <>
      <TopBar title={t("documentLibrary.title")} description={t("documentLibrary.description")}>
        {userInfo.canManageDocuments && (
          <Grid2
            size={{ xs: 12, md: 12 }}
            sx={{
              display: "flex",
              justifyContent: "flex-end",
              mt: { xs: 1, md: 0 },
            }}
          >
            <Button
              variant="contained"
              startIcon={<UploadIcon />}
              onClick={() => {
                setUploadProgressSteps([]);
                setTempFiles([]);
                setOpenSide(true);
              }}
              size="medium"
              sx={{
                borderRadius: "8px",
              }}
            >
              {t("documentLibrary.upload")}
            </Button>
          </Grid2>
        )}
      </TopBar>

      {/* Search Section */}
      <Container maxWidth="xl" sx={{ mb: 3 }}>
        <Fade in={showElements} timeout={1500}>
          <Paper
            elevation={2}
            sx={{
              p: 3,
              borderRadius: 4,
              border: `1px solid ${theme.palette.divider}`,
            }}
          >
            <Grid2 container spacing={2} alignItems="center">
              <Grid2 size={{ xs: 12, md: 12 }}>
                <TextField
                  fullWidth
                  placeholder={t("documentLibrary.searchPlaceholder")}
                  variant="outlined"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <SearchIcon color="action" />
                      </InputAdornment>
                    ),
                    endAdornment: searchQuery && (
                      <InputAdornment position="end">
                        <IconButton
                          aria-label={t("documentLibrary.clearSearch")}
                          onClick={() => setSearchQuery("")}
                          edge="end"
                          size="small"
                        >
                          <ClearIcon />
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                  size="small"
                />
              </Grid2>
            </Grid2>
          </Paper>
        </Fade>
      </Container>

      {/* Documents Container */}
      <Container maxWidth="xl">
        <Fade in={showElements} timeout={2000}>
          <Paper
            elevation={2}
            sx={{
              p: 3,
              borderRadius: 4,
              mb: 3,
              minHeight: "500px",
              border: `1px solid ${theme.palette.divider}`,
              position: "relative",
            }}
          >
            {isLoading ? (
              <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
                <LoadingSpinner />
              </Box>
            ) : currentDocuments.length > 0 ? (
              <Box>
                <Typography variant="h6" fontWeight="bold" gutterBottom sx={{ mb: 2 }}>
                  {t("documentLibrary.documents", { count: filteredFiles.length })}
                </Typography>
                <DocumentTable
                  files={currentDocuments}
                  selected={selectedFiles}
                  onToggleSelect={(uid) => {
                    setSelectedFiles((prev) => (prev.includes(uid) ? prev.filter((id) => id !== uid) : [...prev, uid]));
                  }}
                  onToggleAll={(checked) => {
                    setSelectedFiles(checked ? currentDocuments.map((f) => f.document_uid) : []);
                  }}
                  onDelete={handleDelete}
                  onDownload={handleDownload}
                  isAdmin={userInfo.canManageDocuments}
                  onOpen={(document_uid, file_name) => handleDocumentMarkdownPreview(document_uid, file_name)}
                  onToggleRetrievable={handleToggleRetrievable}
                />
                <Box display="flex" alignItems="center" mt={3} justifyContent="space-between">
                  <Pagination
                    count={Math.ceil(filteredFiles.length / documentsPerPage)}
                    page={currentPage}
                    onChange={(_, value) => setCurrentPage(value)}
                    color="primary"
                    size="small" // Smaller pagination
                    shape="rounded"
                  />

                  <FormControl sx={{ minWidth: 80 }}>
                    <Select
                      value={documentsPerPage.toString()}
                      onChange={(e) => {
                        setDocumentsPerPage(parseInt(e.target.value, 10));
                        setCurrentPage(1);
                      }}
                      input={<OutlinedInput />}
                      sx={{ height: "32px" }}
                      size="small"
                    >
                      <MenuItem value="10">10</MenuItem>
                      <MenuItem value="20">20</MenuItem>
                      <MenuItem value="50">50</MenuItem>
                    </Select>
                  </FormControl>
                </Box>
              </Box>
            ) : (
              <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" minHeight="400px">
                <LibraryBooksRoundedIcon sx={{ fontSize: 60, color: theme.palette.text.secondary, mb: 2 }} />
                <Typography variant="h5" color="textSecondary" align="center">
                  {t("documentLibrary.noDocument")}
                </Typography>
                <Typography variant="body1" color="textSecondary" align="center" sx={{ mt: 1 }}>
                  {t("documentLibrary.modifySearch")}
                </Typography>
                {userInfo.canManageDocuments && (
                  <Button
                    variant="outlined"
                    startIcon={<UploadIcon />}
                    onClick={() => setOpenSide(true)}
                    sx={{ mt: 2 }}
                  >
                    {t("documentLibrary.addDocuments")}
                  </Button>
                )}
              </Box>
            )}
          </Paper>
        </Fade>
      </Container>

      {/* Upload Drawer - Only visible to admins and editors */}
      {userInfo.canManageDocuments && (
        <Drawer
          anchor="right"
          open={openSide}
          onClose={() => setOpenSide(false)}
          PaperProps={{
            sx: {
              width: { xs: "100%", sm: 450 },
              p: 3,
              borderTopLeftRadius: 16,
              borderBottomLeftRadius: 16,
            },
          }}
        >
          <Typography variant="h5" fontWeight="bold" gutterBottom>
            {t("documentLibrary.uploadDrawerTitle")}
          </Typography>

          <Paper
            sx={{
              mt: 3,
              p: 3,
              border: "1px dashed",
              borderColor: "divider",
              borderRadius: "12px",
              cursor: "pointer",
              minHeight: "180px",
              maxHeight: "400px",
              overflowY: "auto",
              backgroundColor: isHighlighted ? theme.palette.action.hover : theme.palette.background.paper,
              transition: "background-color 0.3s",
              display: "block",
              textAlign: "left",
              flexDirection: "column",
              alignItems: "center",
            }}
            onClick={open}
            onDragOver={(event) => {
              event.preventDefault();
              setIsHighlighted(true);
            }}
            onDragLeave={() => setIsHighlighted(false)}
            onDrop={(event) => {
              event.preventDefault();
              setIsHighlighted(false);
            }}
          >
            <input {...getInputProps()} />
            {!tempFiles.length ? (
              <Box display="flex" flexDirection="column" justifyContent="center" alignItems="center" height="100%">
                <UploadIcon sx={{ fontSize: 40, color: "text.secondary", mb: 2 }} />
                <Typography variant="body1" color="textSecondary">
                  {t("documentLibrary.dropFiles")}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  {t("documentLibrary.maxSize")}
                </Typography>
              </Box>
            ) : (
              <DocumentDrawerTable files={tempFiles} onDelete={handleDeleteTemp} />
            )}
          </Paper>
          {uploadProgressSteps.length > 0 && (
            <Box sx={{ mt: 3, width: "100%" }}>
              <ProgressStepper steps={uploadProgressSteps} />
            </Box>
          )}

          <Box sx={{ mt: 3, display: "flex", justifyContent: "space-between" }}>
            <Button variant="outlined" onClick={() => setOpenSide(false)} sx={{ borderRadius: "8px" }}>
              {t("documentLibrary.cancel")}
            </Button>

            <Button
              variant="contained"
              color="success"
              startIcon={<SaveIcon />}
              onClick={handleAddFiles}
              disabled={!tempFiles.length || isLoading}
              sx={{ borderRadius: "8px" }}
            >
              {isLoading ? t("documentLibrary.saving") : t("documentLibrary.save")}
            </Button>
          </Box>
        </Drawer>
      )}
      <DocumentViewer document={selectedDocument} open={documentViewerOpen} onClose={handleCloseDocumentViewer} />
    </>
  );
};
