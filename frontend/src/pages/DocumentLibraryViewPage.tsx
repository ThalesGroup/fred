import { useParams } from "react-router-dom";
import { Container, Typography, Box, CircularProgress, Paper } from "@mui/material";
import {
  DocumentMetadata,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { TopBar } from "../common/TopBar";
import { use } from "i18next";
import { useEffect, useState } from "react";
import { DocumentTable } from "../components/documents/DocumentTable";

export const DocumentLibraryViewPage = () => {
  const { libraryId } = useParams<{ libraryId: string }>();
  const { data: library, isLoading } = useGetTagKnowledgeFlowV1TagsTagIdGetQuery({ tagId: libraryId });
  const [getDocumentsMetadata] = useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation();

  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);

  async function fetchDocumentsMetadata() {
    const promises: Promise<DocumentMetadata | undefined>[] = [];
    for (const id of library.document_ids || []) {
      promises.push(
        getDocumentsMetadata({ filters: { document_uid: id } }).then((result) => {
          // result.data may be undefined or an object containing the metadata
          // Adjust this extraction as needed based on your actual API response shape
          if (result.error) {
            console.error(`Error fetching metadata for document ${id}:`, result.error);
            return undefined; // Skip this document on error
          }
          return result.data.documents && result.data.documents[0];
        }),
      );
    }
    const docs = (await Promise.all(promises)).filter((doc): doc is DocumentMetadata => !!doc);
    setDocuments(docs);
  }

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
      <TopBar title={library.name} description={library.description || ""} />
      <Container maxWidth="xl">
        <Paper sx={{ p: 3, borderRadius: 4, mt: 2 }}>
          <Typography variant="h4" gutterBottom>
            {library.name}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {library.description || "No description available."}
          </Typography>
        </Paper>
        <Paper sx={{ p: 2, borderRadius: 4, mt: 2 }}>
          <DocumentTable
            files={documents}
            selectedFiles={[]}
            onToggleSelect={() => {}}
            onToggleAll={() => {}}
            onDelete={() => {}}
            onDownload={() => {}}
            onToggleRetrievable={() => {}}
            onOpen={() => {}}
            onProcess={() => {}}
            isAdmin={true}
          />
        </Paper>
      </Container>
    </>
  );
};
