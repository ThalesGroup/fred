// DocumentList.tsx
import * as React from "react";
import {
  Card,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  TableSortLabel,
} from "@mui/material";
import dayjs from "dayjs";

// Type can match your backend DocumentMetadata model
type DocumentMetadata = {
  document_uid: string;
  title?: string;
  document_name?: string;
  modified?: string;
  tag_ids?: string[];
};

type DocumentListProps = {
  documents: DocumentMetadata[];
  isLoading?: boolean;
  isError?: boolean;
};

export function DocumentList({ documents, isLoading, isError }: DocumentListProps) {
  const [sortBy, setSortBy] = React.useState<"name" | "lastUpdate">("lastUpdate");
  const [sortDirection, setSortDirection] = React.useState<"asc" | "desc">("desc");

  const handleSortChange = (column: "name" | "lastUpdate") => {
    if (sortBy === column) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortDirection("asc");
    }
  };

  const sortedDocs = React.useMemo(() => {
    if (!documents) return [];
    const docs = [...documents];
    return docs.sort((a, b) => {
      let aVal: any, bVal: any;
      if (sortBy === "name") {
        aVal = a.title?.toLowerCase() || a.document_name?.toLowerCase() || "";
        bVal = b.title?.toLowerCase() || b.document_name?.toLowerCase() || "";
      } else {
        aVal = new Date(a.modified || 0).getTime();
        bVal = new Date(b.modified || 0).getTime();
      }
      if (sortDirection === "asc") return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
      return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
    });
  }, [documents, sortBy, sortDirection]);

  return (
    <Card sx={{ borderRadius: 3, p: 2, mt: 2 }}>
      <Typography variant="subtitle1" sx={{ mb: 1 }}>
        Documents ({documents?.length || 0})
      </Typography>

      {isLoading && <Typography variant="body2">Loading documents…</Typography>}
      {isError && <Typography color="error">Failed to load documents.</Typography>}

      {!isLoading && !isError && sortedDocs.length > 0 && (
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 600 }}>
                  <TableSortLabel
                    active={sortBy === "name"}
                    direction={sortBy === "name" ? sortDirection : "asc"}
                    onClick={() => handleSortChange("name")}
                  >
                    Name
                  </TableSortLabel>
                </TableCell>
                <TableCell sx={{ fontWeight: 600 }}>
                  <TableSortLabel
                    active={sortBy === "lastUpdate"}
                    direction={sortBy === "lastUpdate" ? sortDirection : "desc"}
                    onClick={() => handleSortChange("lastUpdate")}
                  >
                    Last Update
                  </TableSortLabel>
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sortedDocs.map((doc) => (
                <TableRow key={doc.document_uid} hover>
                  <TableCell>{doc.title || doc.document_name || doc.document_uid}</TableCell>
                  <TableCell>
                    {doc.modified ? dayjs(doc.modified).format("YYYY-MM-DD HH:mm") : ""}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {!isLoading && !isError && sortedDocs.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          No documents found.
        </Typography>
      )}
    </Card>
  );
}
