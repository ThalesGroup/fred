import { Box } from "@mui/material";
import DocumentLibraryList from "../documents/libraries/DocumentLibraryList";

export interface TeamDocumentsLibraryProps {
  teamId?: string;
}

export function TeamDocumentsLibrary({ teamId }: TeamDocumentsLibraryProps) {
  return (
    <Box sx={{ p: 3 }}>
      <DocumentLibraryList teamId={teamId} />
    </Box>
  );
}
