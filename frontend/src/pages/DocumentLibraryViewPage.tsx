import { useParams } from "react-router-dom";
import { Container, Typography, Box, CircularProgress, Paper } from "@mui/material";
import {
  DocumentMetadata,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { TopBar } from "../common/TopBar";
import { useEffect, useState } from "react";
import { DocumentTable } from "../components/documents/DocumentTable";
import { KeyCloakService } from "../security/KeycloakService";

export const DocumentLibraryViewPage = () => {
  const { libraryId } = useParams<{ libraryId: string }>();
  const { data: library, isLoading, refetch: refetchLibrary } = useGetTagKnowledgeFlowV1TagsTagIdGetQuery({ tagId: libraryId });
  const [getDocumentsMetadata] = useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation();

  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  
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
      <TopBar title={library.name} description={library.description || ""} backTo="/documentLibrary" />
      <Container maxWidth="xl">
        <Paper sx={{ p: 3, borderRadius: 4, mt: 2 }}>
          <Typography variant="h4" gutterBottom>
            {library.name}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {library.description || "No description available."}
          </Typography>
        </Paper>
        <Paper sx={{ p: 2, borderRadius: 4, mt: 2, position: "relative" }}>
          <DocumentTable
            files={documents}
            isAdmin={hasDocumentManagementPermission()}
            onRefreshData={handleRefreshData}
            showSelectionActions={true}
          />
        </Paper>
      </Container>
    </>
  );
};
