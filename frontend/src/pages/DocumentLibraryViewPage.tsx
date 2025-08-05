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

import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";
import UploadIcon from "@mui/icons-material/Upload";
import {
  Box,
  Button,
  CircularProgress,
  Container,
  FormControl,
  MenuItem,
  Pagination,
  Paper,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import { DocumentTable } from "../components/documents/DocumentTable";
import { CustomRowAction } from "../components/documents/DocumentTableRowActionsMenu";
import { CustomBulkAction } from "../components/documents/DocumentTableSelectionToolbar";
import { DocumentUploadDrawer } from "../components/documents/DocumentUploadDrawer";
import { LibraryInfoCard } from "../components/documents/LibraryInfoCard";
import { useDocumentActions } from "../components/documents/useDocumentActions";
import { EmptyState } from "../components/EmptyState";
import { TableSkeleton } from "../components/TableSkeleton";
import { useToast } from "../components/ToastProvider";
import { KeyCloakService } from "../security/KeycloakService";
import {
  DocumentMetadata,
  useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

export const DocumentLibraryViewPage = () => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { libraryId } = useParams<{ libraryId: string }>();
  const {
    data: library,
    isLoading: isLoadingLibrary,
    refetch: refetchLibrary,
  } = useGetTagKnowledgeFlowV1TagsTagIdGetQuery({ tagId: libraryId || "" }, { skip: !libraryId });
  const [getDocumentsMetadata, { isLoading: isLoadingDocumentsMetadata }] =
    useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation();
  const [updateTag] = useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation();

  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [openUploadDrawer, setOpenUploadDrawer] = useState(false);
  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [documentsPerPage, setDocumentsPerPage] = useState(20);

  const hasDocumentManagementPermission = () => {
    const userRoles = KeyCloakService.GetUserRoles();
    return userRoles.includes("admin") || userRoles.includes("editor");
  };

  const fetchDocumentsMetadata = async () => {
    if (!library?.item_ids?.length) return;

    try {
      const result = await getDocumentsMetadata({
        filters: {
          document_uid: library.item_ids,
        },
      }).unwrap();

      setDocuments(
        [...(result.documents ?? [])].sort((a, b) => (a.document_name || "").localeCompare(b.document_name || "")),
      );
    } catch (err) {
      console.error("Batch metadata fetch failed", err);
      setDocuments([]); // fallback to empty
    }
  };

  const handleRefreshData = async () => {
    await refetchLibrary();
    await fetchDocumentsMetadata();
  };

  const handleUploadComplete = () => {
    handleRefreshData();
  };

  const handleRemoveFromLibrary = async (documents: DocumentMetadata[]) => {
    if (!library) return;

    try {
      const documentIdsToRemove = documents.map((doc) => doc.document_uid);
      const updatedDocumentIds = library.item_ids?.filter((id) => !documentIdsToRemove.includes(id)) || [];

      await updateTag({
        tagId: library.id,
        tagUpdate: {
          name: library.name,
          description: library.description,
          type: library.type,
          item_ids: updatedDocumentIds,
        },
      }).unwrap();

      showSuccess({
        summary: t("documentLibrary.removeSuccess"),
        detail: t("documentLibrary.removedDocuments", { count: documents.length }),
      });
    } catch (error: any) {
      showError({
        summary: t("documentLibrary.removeError"),
        detail: error?.data?.detail || t("documentLibrary.removeErrorGeneric"),
      });
    }
  };

  // Get default document actions
  const { defaultRowActions, defaultBulkActions, handleDocumentPreview } = useDocumentActions(handleRefreshData);

  // Combine custom actions with default ones
  const rowActions: CustomRowAction[] = [
    {
      icon: <RemoveCircleOutlineIcon />,
      name: "Remove from Library",
      handler: (file) => handleRemoveFromLibrary([file]),
    },
    ...defaultRowActions,
  ];

  const bulkActions: CustomBulkAction[] = [
    {
      icon: <RemoveCircleOutlineIcon />,
      name: "Remove from Library",
      handler: (files) => handleRemoveFromLibrary(files),
    },
    ...defaultBulkActions,
  ];

  useEffect(() => {
    if (library) {
      console.log("Fetching documents for library:", library.name, library.item_ids);
      fetchDocumentsMetadata();
    }
  }, [library]);

  if (isLoadingLibrary) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="40vh">
        <CircularProgress />
      </Box>
    );
  }

  if (!library) {
    return (
      <>
        <TopBar title="Library not found" description="The requested document library does not exist." />
        <Typography color="text.secondary" mt={4}>
          No library found for ID: {libraryId}
        </Typography>
      </>
    );
  }

  const paginatedDocuments = documents.slice((currentPage - 1) * documentsPerPage, currentPage * documentsPerPage);

  return (
    <>
      <TopBar title={library.name} description={library.description || ""} backTo="/knowledge?view=libraries"></TopBar>

      <Container maxWidth="xl" sx={{ mb: 3, display: "flex", flexDirection: "column", gap: 4 }}>
        {/* Library name and description */}
        <LibraryInfoCard
          library={library}
          hasEditPermission={hasDocumentManagementPermission()}
          onLibraryUpdated={handleRefreshData}
        />

        <Stack gap={2}>
          {/* Upload button */}
          {hasDocumentManagementPermission() && (
            <Stack direction="row" spacing={2} justifyContent="flex-end">
              <Button
                variant="contained"
                startIcon={<UploadIcon />}
                onClick={() => setOpenUploadDrawer(true)}
                size="medium"
                sx={{ borderRadius: "8px" }}
              >
                {t("documentLibrary.uploadInLibrary")}
              </Button>
            </Stack>
          )}

          {/* List of documents */}
          <Paper
            sx={{
              p: 2,
              pt: 7, // To make space for DocumentTableSelectionToolbar (used for bulk actions)
              borderRadius: 4,
              position: "relative",
            }}
          >
            {isLoadingDocumentsMetadata ? (
              <TableSkeleton
                columns={[
                  { padding: "checkbox" },
                  { width: 200, hasIcon: true },
                  { width: 100 },
                  { width: 80 },
                  { width: 80 },
                  { width: 60 },
                ]}
              />
            ) : documents.length === 0 ? (
              <EmptyState
                icon={<FolderOpenIcon />}
                title={t("documentLibrary.emptyLibraryTitle")}
                description={t("documentLibrary.emptyLibraryDescription")}
                actionButton={
                  hasDocumentManagementPermission()
                    ? {
                        label: t("documentLibrary.uploadFirstDocument"),
                        onClick: () => setOpenUploadDrawer(true),
                        startIcon: <UploadIcon />,
                        variant: "outlined",
                      }
                    : undefined
                }
              />
            ) : (
              <>
                <DocumentTable
                  files={paginatedDocuments}
                  isAdmin={hasDocumentManagementPermission()}
                  onRefreshData={handleRefreshData}
                  showSelectionActions={true}
                  rowActions={hasDocumentManagementPermission() ? rowActions : []} // todo: add a permission check for each action, enforced by DocumentTable
                  bulkActions={hasDocumentManagementPermission() ? bulkActions : []}
                  nameClickAction={handleDocumentPreview}
                  columns={{
                    fileName: true,
                    dateAdded: true,
                    librairies: false, // Hide column in library view
                    status: true,
                    retrievable: true,
                    actions: true,
                  }}
                />
                <Box display="flex" justifyContent="space-between" alignItems="center" mt={2}>
                  <Pagination
                    count={Math.ceil(documents.length / documentsPerPage)}
                    page={currentPage}
                    onChange={(_, page) => setCurrentPage(page)}
                    color="primary"
                  />
                  <FormControl size="small" sx={{ minWidth: 100 }}>
                    <Select
                      value={documentsPerPage.toString()}
                      onChange={(e) => {
                        setDocumentsPerPage(parseInt(e.target.value, 10));
                        setCurrentPage(1);
                      }}
                    >
                      <MenuItem value="10">20</MenuItem>
                      <MenuItem value="20">100</MenuItem>
                      <MenuItem value="50">1000</MenuItem>
                    </Select>
                  </FormControl>
                </Box>
              </>
            )}
          </Paper>
        </Stack>
      </Container>

      {/* Upload Drawer */}
      {hasDocumentManagementPermission() && (
        <DocumentUploadDrawer
          isOpen={openUploadDrawer}
          onClose={() => setOpenUploadDrawer(false)}
          onUploadComplete={handleUploadComplete}
          metadata={{ tags: [library.id] }}
        />
      )}
    </>
  );
};
