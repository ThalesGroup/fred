import UploadIcon from "@mui/icons-material/Upload";
import { Box, Button, CircularProgress, Container, Paper, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import { DocumentTable } from "../components/documents/DocumentTable";
import { DocumentUploadDrawer } from "../components/documents/DocumentUploadDrawer";
import { KeyCloakService } from "../security/KeycloakService";
import {
  DocumentMetadata,
  useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

export const DocumentLibraryViewPage = () => {
  const { t } = useTranslation();
  const { libraryId } = useParams<{ libraryId: string }>();
  const {
    data: library,
    isLoading,
    refetch: refetchLibrary,
  } = useGetTagKnowledgeFlowV1TagsTagIdGetQuery({ tagId: libraryId });
  const [getDocumentsMetadata] = useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation();

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

  const handleRefreshData = () => {
    refetchLibrary();
    fetchDocumentsMetadata();
  };

  const handleUploadComplete = () => {
    handleRefreshData();
  };

  useEffect(() => {
    if (library) {
      console.log("Fetching documents for library:", library.name, library.document_ids);
      fetchDocumentsMetadata();
    }
  }, [library]);

  if (isLoading) {
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
      <TopBar title={library.name} description={library.description || ""} backTo="/documentLibrary">
        {hasDocumentManagementPermission() && (
          <Button
            variant="contained"
            startIcon={<UploadIcon />}
            onClick={() => setOpenUploadDrawer(true)}
            size="medium"
            sx={{ borderRadius: "8px" }}
          >
            {t("documentLibrary.uploadInLibrary")}
          </Button>
        )}
      </TopBar>
      <Container maxWidth="xl">
        <Paper sx={{ p: 3, borderRadius: 4, mt: 2 }}>
          <Typography variant="h4" gutterBottom>
            {library.name}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {library.description || "No description available."}
          </Typography>
        </Paper>
        <Paper
          sx={{
            p: 2,
            pt: 7, // To make space for DocumentTableSelectionToolbar (used for bulk actions)
            borderRadius: 4,
            mt: 2,
            position: "relative",
          }}
        >
          <DocumentTable
            files={documents}
            isAdmin={hasDocumentManagementPermission()}
            onRefreshData={handleRefreshData}
            showSelectionActions={true}
            columns={{
              fileName: true,
              dateAdded: true,
              librairies: false, // Hide column in library view
              status: true,
              retrievable: true,
              actions: true,
            }}
          />
        </Paper>
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
