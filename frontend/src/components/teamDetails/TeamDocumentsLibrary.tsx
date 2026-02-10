import { Box } from "@mui/material";
import DocumentLibraryList from "../documents/libraries/DocumentLibraryList";

export interface TeamDocumentsLibraryProps {
  teamId?: string;
  canCreateTag?: boolean;
}

export function TeamDocumentsLibrary({ teamId, canCreateTag }: TeamDocumentsLibraryProps) {
  return (
    <Box sx={{ p: 3, flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <DocumentLibraryList teamId={teamId} canCreateTag={canCreateTag} />
    </Box>
  );
}
