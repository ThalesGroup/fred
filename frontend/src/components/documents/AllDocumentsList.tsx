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

import {
  Box,
  Button,
  Checkbox,
  Container,
  FormControl,
  Grid2,
  IconButton,
  InputAdornment,
  InputLabel,
  ListItemText,
  MenuItem,
  OutlinedInput,
  Pagination,
  Paper,
  Select,
  SelectChangeEvent,
  TextField,
  Typography,
  useTheme,
} from "@mui/material";

import ClearIcon from "@mui/icons-material/Clear";
import LibraryBooksRoundedIcon from "@mui/icons-material/LibraryBooksRounded";
import SearchIcon from "@mui/icons-material/Search";
import UploadIcon from "@mui/icons-material/Upload";
import RefreshIcon from "@mui/icons-material/Refresh";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { KeyCloakService } from "../../security/KeycloakService";
import { DOCUMENT_PROCESSING_STAGES, useRescanCatalogSourceMutation } from "../../slices/documentApi";
import {
  DocumentMetadata,
  useBrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostMutation,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { EmptyState } from "../EmptyState";
import { TableSkeleton } from "../TableSkeleton";
import { useToast } from "../ToastProvider";
import { DocumentTable } from "./DocumentTable";
import { DocumentUploadDrawer } from "./DocumentUploadDrawer";
import { useDocumentSources } from "../../hooks/useDocumentSources";
import { useDocumentTags } from "../../hooks/useDocumentTags";

interface DocumentsViewProps {}

export const AllDocumentsList = ({}: DocumentsViewProps) => {
  const { showError } = useToast();
  const { t } = useTranslation();
  const theme = useTheme();

  // API Hooks
  const [browseDocuments, { isLoading }] = useBrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostMutation();
  const { sources: allSources } = useDocumentSources();
  const { tags: allDocumentLibraries } = useDocumentTags();
  const tagMap = new Map(allDocumentLibraries.map((tag) => [tag.id, tag.name]));

  const [rescanCatalogSource] = useRescanCatalogSourceMutation();

  // UI States
  const [documentsPerPage, setDocumentsPerPage] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);
  const [openUploadDrawer, setOpenUploadDrawer] = useState(false);
  const [selectedSourceTag, setSelectedSourceTag] = useState<string | null>(null);

  // Filter states (moved from DocumentLibrary)
  const [selectedLibrary, setSelectLibraries] = useState<string[]>([]);
  const [selectedStages, setSelectedStages] = useState<string[]>([]);
  const [searchableFilter, setSearchableFilter] = useState<"all" | "true" | "false">("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Backend Data States
  const [allDocuments, setAllDocuments] = useState<DocumentMetadata[]>([]);
  const [totalDocCount, setTotalDocCount] = useState<number>();

  const selectedSource = allSources?.find((s) => s.tag === selectedSourceTag);
  const isPullMode = selectedSource?.type === "pull";

  const hasDocumentManagementPermission = () => {
    const userRoles = KeyCloakService.GetUserRoles();
    return userRoles.includes("admin") || userRoles.includes("editor");
  };

  const userInfo = {
    name: KeyCloakService.GetUserName(),
    canManageDocuments: hasDocumentManagementPermission(),
    roles: KeyCloakService.GetUserRoles(),
  };
  const handleRefreshPullSource = async () => {
    if (!selectedSourceTag) return;
    try {
      await rescanCatalogSource(selectedSourceTag).unwrap();
      await fetchFiles(); // Re-fetch after refresh
    } catch (err) {
      console.error("Refresh failed:", err);
      showError({
        summary: t("documentLibrary.refreshFailed"),
        detail: err?.data?.detail || err.message || "Unknown error occurred while refreshing.",
      });
    }
  };
  const fetchFiles = async () => {
    if (!selectedSourceTag) return;
    const filters = {
      ...(searchQuery ? { document_name: searchQuery } : {}),
      ...(selectedLibrary.length > 0 ? { tags: selectedLibrary } : {}),
      ...(selectedStages.length > 0
        ? {
            processing_stages: Object.fromEntries(selectedStages.map((stage) => [stage, "done"])),
          }
        : {}),
      ...(searchableFilter !== "all" ? { retrievable: searchableFilter === "true" } : {}),
    };
    try {
      const response = await browseDocuments({
        browseDocumentsRequest: {
          source_tag: selectedSourceTag,
          filters,
          offset: (currentPage - 1) * documentsPerPage,
          limit: documentsPerPage,
        },
      }).unwrap();

      const docs = response.documents;
      setTotalDocCount(response.total);
      setAllDocuments(docs);
    } catch (error) {
      console.error("Error fetching documents:", error);
      showError({
        summary: "Fetch Failed",
        detail: error?.data?.detail || error.message || "Unknown error occurred while fetching.",
      });
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
    fetchFiles();
  }, [selectedSourceTag, searchQuery, selectedLibrary, selectedStages, searchableFilter, currentPage, documentsPerPage]);

  const handleUploadComplete = async () => {
    await fetchFiles();
  };

  return (
    <Container maxWidth="xl">
      {/* Source Selector and Upload Button */}
      <Box display="flex" justifyContent="flex-end" alignItems="center" gap={2} mb={2}>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="sources-label">Document Sources</InputLabel>
          <Select
            labelId="sources-label"
            value={selectedSourceTag || ""}
            onChange={(e: SelectChangeEvent) => {
              const value = e.target.value;
              setSelectedSourceTag(value === "" ? null : value);
            }}
            input={<OutlinedInput label="Document Sources" />}
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

        {/* Upload Button */}
        {userInfo.canManageDocuments && !isPullMode && (
          <Button
            variant="contained"
            startIcon={<UploadIcon />}
            onClick={() => setOpenUploadDrawer(true)}
            size="medium"
            sx={{ borderRadius: "8px" }}
          >
            {t("documentLibrary.upload")}
          </Button>
        )}
        {userInfo.canManageDocuments && isPullMode && (
          <Button
            variant="contained"
            startIcon={<RefreshIcon />}
            onClick={() => handleRefreshPullSource()}
            size="medium"
            sx={{ borderRadius: "8px" }}
          >
            {t("documentLibrary.refresh")}
          </Button>
        )}
      </Box>

      {/* Filter Section */}
      <Paper
        elevation={2}
        sx={{
          p: 3,
          borderRadius: 4,
          border: `1px solid ${theme.palette.divider}`,
          mb: 3,
        }}
      >
        {/* Filters */}
        <Grid2 container spacing={2} alignItems="center">
          <Grid2 size={{ xs: 12, md: 12 }}>
            <Grid2 container spacing={2} sx={{ mb: 2 }}>
              {/* Tags filter */}
              <Grid2 size={{ xs: 4 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Library</InputLabel>
                  <Select
                    multiple
                    value={selectedLibrary}
                    onChange={(e) => setSelectLibraries(e.target.value as string[])}
                    input={<OutlinedInput label="Library" />}
                    renderValue={(selected) => selected.map((id) => tagMap.get(id) ?? id).join(", ")}
                  >
                    {allDocumentLibraries.map((tag) => (
                      <MenuItem key={tag.id} value={tag.id}>
                        <Checkbox checked={selectedLibrary.includes(tag.id)} />
                        <ListItemText primary={tag.name} />
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
              slotProps={{
                input: {
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
                },
              }}
              size="small"
            />
          </Grid2>
        </Grid2>
      </Paper>

      {/* Documents Section */}
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
          <TableSkeleton
            columns={[
              { padding: "checkbox" },
              { width: 200, hasIcon: true },
              { width: 100 },
              { width: 100 },
              { width: 120 },
              { width: 100 },
              { width: 15 },
            ]}
          />
        ) : totalDocCount !== undefined && totalDocCount > 0 ? (
          <Box>
            <Typography variant="h6" fontWeight="bold" gutterBottom sx={{ mb: 2 }}>
              {t("documentLibrary.documents", { count: totalDocCount })}
            </Typography>

            <DocumentTable
              files={allDocuments}
              isAdmin={userInfo.canManageDocuments}
              onRefreshData={fetchFiles}
              showSelectionActions={true}
            />
            <Box display="flex" alignItems="center" mt={3} justifyContent="space-between">
              <Pagination
                count={Math.ceil(allDocuments.length / documentsPerPage)}
                page={currentPage}
                onChange={(_, value) => setCurrentPage(value)}
                color="primary"
                size="small"
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
          <EmptyState
            icon={<LibraryBooksRoundedIcon />}
            title={t("documentLibrary.noDocument")}
            description={t("documentLibrary.modifySearch")}
            actionButton={
              userInfo.canManageDocuments
                ? {
                    label: t("documentLibrary.addDocuments"),
                    onClick: () => setOpenUploadDrawer(true),
                    startIcon: <UploadIcon />,
                  }
                : undefined
            }
          />
        )}
      </Paper>

      {/* Upload Drawer */}
      {userInfo.canManageDocuments && (
        <DocumentUploadDrawer
          isOpen={openUploadDrawer}
          onClose={() => setOpenUploadDrawer(false)}
          onUploadComplete={handleUploadComplete}
          metadata={{ source_tag: selectedSourceTag }}
        />
      )}
    </Container>
  );
};
