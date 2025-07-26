import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";
import UploadIcon from "@mui/icons-material/Upload";
import {
  Box,
  Button,
  CircularProgress,
  Container,
  Paper,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
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

  const hasDocumentManagementPermission = () => {
    const userRoles = KeyCloakService.GetUserRoles();
    return userRoles.includes("admin") || userRoles.includes("editor");
  };

  const fetchDocumentsMetadata = async () => {
    if (!library?.document_ids) return;

    const promises: Promise<DocumentMetadata | undefined>[] = [];
    for (const id of library.document_ids) {
      promises.push(
        getDocumentsMetadata({ filters: { document_uid: id } }).then((result) => {
          if (result.error) {
            console.error(`Error fetching metadata for document ${id}:`, result.error);
            return undefined;
          }
          return result.data.documents && result.data.documents[0];
        }),
      );
    }
    const docs = (await Promise.all(promises)).filter((doc): doc is DocumentMetadata => !!doc);
    setDocuments(docs);
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
      const updatedDocumentIds = library.document_ids?.filter((id) => !documentIdsToRemove.includes(id)) || [];

      await updateTag({
        tagId: library.id,
        tagUpdate: {
          name: library.name,
          description: library.description,
          type: library.type,
          document_ids: updatedDocumentIds,
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
      console.log("Fetching documents for library:", library.name, library.document_ids);
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

  return (
    <>
      <TopBar title={library.name} description={library.description || ""} backTo="/documentLibrary"></TopBar>

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
              <DocumentTableSkeleton />
            ) : documents.length === 0 ? (
              <EmptyLibraryState
                hasUploadPermission={hasDocumentManagementPermission()}
                onUploadClick={() => setOpenUploadDrawer(true)}
              />
            ) : (
              <DocumentTable
                files={documents}
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

const DocumentTableSkeleton = () => {
  return (
    <TableContainer>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell padding="checkbox">
              <Skeleton variant="rectangular" width={20} height={20} />
            </TableCell>
            <TableCell>
              <Skeleton variant="text" width={100} />
            </TableCell>
            <TableCell>
              <Skeleton variant="text" width={80} />
            </TableCell>
            <TableCell>
              <Skeleton variant="text" width={60} />
            </TableCell>
            <TableCell>
              <Skeleton variant="text" width={80} />
            </TableCell>
            <TableCell align="right">
              <Skeleton variant="text" width={60} />
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {[...Array(5)].map((_, index) => (
            <TableRow key={index}>
              <TableCell padding="checkbox">
                <Skeleton variant="rectangular" width={20} height={20} />
              </TableCell>
              <TableCell>
                <Box display="flex" alignItems="center" gap={1}>
                  <Skeleton variant="rectangular" width={24} height={24} />
                  <Skeleton variant="text" width={200} />
                </Box>
              </TableCell>
              <TableCell>
                <Skeleton variant="text" width={100} />
              </TableCell>
              <TableCell>
                <Skeleton variant="text" width={80} />
              </TableCell>
              <TableCell>
                <Skeleton variant="text" width={60} />
              </TableCell>
              <TableCell align="right">
                <Skeleton variant="rectangular" width={32} height={32} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
};

interface EmptyLibraryStateProps {
  hasUploadPermission: boolean;
  onUploadClick: () => void;
}

const EmptyLibraryState = ({ hasUploadPermission, onUploadClick }: EmptyLibraryStateProps) => {
  const { t } = useTranslation();

  return (
    <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" py={8} gap={1}>
      <FolderOpenIcon sx={{ fontSize: 64, color: "text.secondary" }} />
      <Typography variant="h6" color="text.secondary">
        {t("documentLibrary.emptyLibraryTitle")}
      </Typography>
      <Typography variant="body2" color="text.secondary" textAlign="center" maxWidth={400}>
        {t("documentLibrary.emptyLibraryDescription")}
      </Typography>
      {hasUploadPermission && (
        <Button variant="outlined" startIcon={<UploadIcon />} onClick={onUploadClick} sx={{ mt: 1 }}>
          {t("documentLibrary.uploadFirstDocument")}
        </Button>
      )}
    </Box>
  );
};
