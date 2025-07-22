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
  ButtonGroup,
  InputLabel,
  Checkbox,
  ListItemText,
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
  DOCUMENT_PROCESSING_STAGES,
  KnowledgeDocument,
  useGetDocumentSourcesQuery,
  useBrowseDocumentsMutation,
} from "../slices/documentApi";

import { streamUploadOrProcessDocument } from "../slices/streamDocumentUpload";
import { useToast } from "../components/ToastProvider";
import { ProgressStep, ProgressStepper } from "../components/ProgressStepper";
import { DocumentTable } from "../components/documents/DocumentTable";
import { DocumentDrawerTable } from "../components/documents/DocumentDrawerTable";
import { TopBar } from "../common/TopBar";
import { useTranslation } from "react-i18next";
import { DocumentLibrariesList } from "./DocumentLibrariesList";

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
 *    - If Markdown content is available, it’s shown in a Drawer viewer with proper rendering.
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
  const { showInfo, showError } = useToast();
  const [uploadMode, setUploadMode] = useState<"upload" | "process">("process");

  // API Hooks
  const [browseDocuments] = useBrowseDocumentsMutation();
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedStages, setSelectedStages] = useState<string[]>([]);
  const [searchableFilter, setSearchableFilter] = useState<"all" | "true" | "false">("all");

  const { data: allSources } = useGetDocumentSourcesQuery();
  const [selectedSourceTag, setSelectedSourceTag] = useState<string | null>(null);
  const selectedSource = allSources?.find((s) => s.tag === selectedSourceTag);
  const isPullMode = selectedSource?.type === "pull";

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

  // UI States
  const [uploadProgressSteps, setUploadProgressSteps] = useState<ProgressStep[]>([]);

  const [searchQuery, setSearchQuery] = useState(""); // Text entered in the search bar
  const [isLoading, setIsLoading] = useState(false); // Controls loading spinner for fetches/uploads
  const [isHighlighted, setIsHighlighted] = useState(false); // Highlight state for the upload Dropzone
  const [documentsPerPage, setDocumentsPerPage] = useState(10); // Number of documents shown per page
  const [currentPage, setCurrentPage] = useState(1); // Current page in the pagination component
  const [openSide, setOpenSide] = useState(false); // Whether the upload drawer is open

  // Backend Data States

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
    if (!selectedSourceTag) return;
    const filters = {
      ...(searchQuery ? { document_name: searchQuery } : {}),
      ...(selectedTags.length > 0 ? { tags: selectedTags } : {}),
      ...(selectedStages.length > 0
        ? {
            processing_stages: Object.fromEntries(selectedStages.map((stage) => [stage, "done"])),
          }
        : {}),
      ...(searchableFilter !== "all" ? { retrievable: searchableFilter === "true" } : {}),
    };
    try {
      setIsLoading(true);

      const response = await browseDocuments({
        source_tag: selectedSourceTag,
        filters,
        offset: (currentPage - 1) * documentsPerPage,
        limit: documentsPerPage,
      }).unwrap();

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
    if (allSources && selectedSourceTag === null) {
      const pushSource = allSources.find((s) => s.type === "push");
      if (pushSource) {
        setSelectedSourceTag(pushSource.tag);
      }
    }
  }, [allSources, selectedSourceTag]);

  useEffect(() => {
    setUserInfo({
      name: KeyCloakService.GetUserName(),
      canManageDocuments: hasDocumentManagementPermission(),
      roles: KeyCloakService.GetUserRoles(),
    });
  }, []);

  useEffect(() => {
    fetchFiles();
  }, [selectedSourceTag, searchQuery, selectedTags, selectedStages, searchableFilter, currentPage, documentsPerPage]);

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

  const handleDeleteTemp = (index) => {
    const newFiles = tempFiles.filter((_, i) => i !== index);
    setTempFiles(newFiles);
  };

  const handleAddFiles = async () => {
    setIsLoading(true);
    setUploadProgressSteps([]);
    try {
      let uploadCount = 0;
      for (const file of tempFiles) {
        try {
          await streamUploadOrProcessDocument(file, uploadMode, (progress) => {
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

  const filteredFiles = allDocuments.filter((file) => {
    const matchesSearch = file.document_name.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesTags = selectedTags.length === 0 || (file.tags || []).some((tag) => selectedTags.includes(tag));

    const matchesStage =
      selectedStages.length === 0 || selectedStages.every((stage) => file.processing_stages?.[stage] === "done");

    const matchesRetrievable =
      searchableFilter === "all" ||
      (searchableFilter === "true" && file.retrievable) ||
      (searchableFilter === "false" && !file.retrievable);

    return matchesSearch && matchesTags && matchesStage && matchesRetrievable;
  });

  const currentDocuments = filteredFiles.slice(indexOfFirstDocument, indexOfLastDocument);

  return (
    <>
      <TopBar title={t("documentLibrary.title")} description={t("documentLibrary.description")}>
        <Box
          display="flex"
          flexDirection="row"
          alignItems="center"
          justifyContent="space-between"
          flexWrap="wrap" // Optional: set to 'nowrap' to prevent stacking on narrow screens
          gap={2}
          sx={{ mt: { xs: 10, md: 0 } }}
        >
          {/* Source Selector on the left */}
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel>Source</InputLabel>
            <Select
              value={selectedSourceTag || ""}
              onChange={(e) => {
                const value = e.target.value;
                setSelectedSourceTag(value === "" ? null : value);
              }}
              input={<OutlinedInput label="Source" />}
            >
              {allSources?.map((source) => (
                <MenuItem key={source.tag} value={source.tag}>
                  <Box title={source.description || source.tag} sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                    {source.tag}
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* Upload Button on the right (pull mode only) */}
          {userInfo.canManageDocuments && !isPullMode && (
            <Button
              variant="contained"
              startIcon={<UploadIcon />}
              onClick={() => {
                setUploadProgressSteps([]);
                setTempFiles([]);
                setOpenSide(true);
              }}
              size="medium"
              sx={{ borderRadius: "8px" }}
            >
              {t("documentLibrary.upload")}
            </Button>
          )}
        </Box>
      </TopBar>

      {/* Search Section */}
      <Container maxWidth="xl" sx={{ mb: 3 }}>
        <Paper
          elevation={2}
          sx={{
            p: 3,
            borderRadius: 4,
            border: `1px solid ${theme.palette.divider}`,
          }}
        >
          {/* View Switch Button Group */}
          <Box display="flex" justifyContent="flex-end" mb={2}>
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

          <Grid2 container spacing={2} alignItems="center">
            <Grid2 size={{ xs: 12, md: 12 }}>
              <Grid2 container spacing={2} sx={{ mb: 2 }}>
                {/* Tags filter */}
                <Grid2 size={{ xs: 4 }}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Tags</InputLabel>
                    <Select
                      multiple
                      value={selectedTags}
                      onChange={(e) => setSelectedTags(e.target.value as string[])}
                      input={<OutlinedInput label="Tags" />}
                      renderValue={(selected) => selected.join(", ")}
                    >
                      {Array.from(new Set(allDocuments.flatMap((doc) => doc.tags || []))).map((tag) => (
                        <MenuItem key={tag} value={tag}>
                          <Checkbox checked={selectedTags.includes(tag)} />
                          <ListItemText primary={tag} />
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid2>

                {/* Stages filter */}
                <Grid2 size={{ xs: 4 }}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Stages (done)</InputLabel>
                    <Select
                      multiple
                      value={selectedStages}
                      onChange={(e) => setSelectedStages(e.target.value as string[])}
                      input={<OutlinedInput label="Stages (done)" />}
                      renderValue={(selected) => selected.join(", ")}
                    >
                      {DOCUMENT_PROCESSING_STAGES.map((stage) => (
                        <MenuItem key={stage} value={stage}>
                          <Checkbox checked={selectedStages.includes(stage)} />
                          <ListItemText primary={stage} />
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid2>

                {/* Searchable filter */}
                <Grid2 size={{ xs: 4 }}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Searchable</InputLabel>
                    <Select
                      value={searchableFilter}
                      onChange={(e) => setSearchableFilter(e.target.value as "all" | "true" | "false")}
                      input={<OutlinedInput label="Searchable" />}
                    >
                      <MenuItem value="all">All</MenuItem>
                      <MenuItem value="true">Only Searchable</MenuItem>
                      <MenuItem value="false">Only Excluded</MenuItem>
                    </Select>
                  </FormControl>
                </Grid2>
              </Grid2>
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
      </Container>

      {/* Libraries View */}
      {selectedView === "libraries" && (
        <Container maxWidth="xl">
          <DocumentLibrariesList />
        </Container>
      )}

      {/* Documents View */}
      {selectedView === "documents" && (
        <Container maxWidth="xl">
          <Paper
            elevation={2}
            sx={{
              p: 3,
              borderRadius: 4,
              mb: 3,
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
                  isAdmin={userInfo.canManageDocuments}
                  onRefreshData={fetchFiles}
                  showSelectionActions={true}
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
        </Container>
      )}

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
          <FormControl fullWidth sx={{ mt: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Ingestion Mode
            </Typography>
            <Select
              value={uploadMode}
              onChange={(e) => setUploadMode(e.target.value as "upload" | "process")}
              size="small"
              sx={{ borderRadius: "8px" }}
            >
              <MenuItem value="upload">Upload</MenuItem>
              <MenuItem value="process">Upload and Process</MenuItem>
            </Select>
          </FormControl>

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
    </>
  );
};
