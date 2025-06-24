// components/knowledge/KnowledgeContextItem.tsx
import {
  Box,
  Typography,
  Card,
  CardContent,
  IconButton,
  Button
} from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import { getDocumentIcon } from "../documents/DocumentIcon";

interface KnowledgeContextDocument {
  id: string;
  document_name: string;
  document_type: string;
  description?: string;
}

interface KnowledgeContextItemProps {
  id: string;
  title: string;
  description?: string;
  documents?: KnowledgeContextDocument[];
  allowDocuments?: boolean;
  allowDocumentDescription?: boolean;
  onEdit: (item: any) => void;
  onDelete: (id: string) => void;
  onViewDescription?: (item: any) => void;
  size?: "large" | "small";
}

export const KnowledgeContextItem = ({
  id,
  title,
  description,
  documents = [],
  allowDocuments = true,
  allowDocumentDescription = true,
  onEdit,
  onDelete,
  onViewDescription,
}: KnowledgeContextItemProps) => {
  const getPreview = (text: string, maxChars = 300) => {
    if (text.length <= maxChars) return text;
    const shortened = text.slice(0, maxChars);
    const lastSpace = shortened.lastIndexOf(" ");
    return shortened.slice(0, lastSpace) + " ...";
  };

  return (
    <Card
      elevation={1}
      sx={{
        borderRadius: 2,
        display: "flex",
        flexDirection: "column",
        flexGrow: 1,
        backgroundColor: "transparent",
        border: (theme) => `1px solid ${theme.palette.divider}`,
      }}
    >
      <CardContent sx={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Typography variant="h6" fontWeight={600}>{title}</Typography>
          <Box display="flex" gap={1}>
            <IconButton onClick={() => onEdit({ id, title, description, documents })}>
              <EditIcon fontSize="medium" />
            </IconButton>
            <IconButton onClick={() => onDelete(id)}>
              <DeleteIcon fontSize="medium" />
            </IconButton>
          </Box>
        </Box>

        {description && (
          <Box pt={2} mb={2} flexGrow={0}>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{
                backgroundColor: (theme) => theme.palette.background.paper,
                px: 2,
                py: 1.5,
                fontFamily: "monospace",
                whiteSpace: "pre-wrap",
                minHeight: "4.5em",
                borderRadius: 1,
              }}
            >
              {getPreview(description)}
            </Typography>

            {description.length > 200 && onViewDescription && (
              <Button size="small" onClick={() => onViewDescription({ id, title, description, documents })} sx={{ mt: 1 }}>
                View full description
              </Button>
            )}
          </Box>
        )}

        {allowDocuments && documents.length > 0 && (
          <Box mt={1}>
            <Typography variant="subtitle2" fontWeight={500} color="text.primary" gutterBottom>
              Documents ({documents.length})
            </Typography>
            <Box display="flex" flexWrap="wrap" gap={1.5} mt={1}>
              {documents.map((doc) => (
                <Box
                  key={doc.id}
                  display="flex"
                  alignItems="flex-start"
                  px={2}
                  py={1.5}
                  borderRadius={2}
                  bgcolor="background.default"
                  border={(theme) => `1px solid ${theme.palette.divider}`}
                  boxShadow={1}
                  sx={{
                    flex: "1 1 45%",
                    minWidth: "280px"
                  }}
                >
                  {getDocumentIcon(doc.document_name)}

                  <Box ml={1} width="100%">
                    <Typography variant="body2" fontWeight={500} noWrap title={doc.document_name}>
                      {doc.document_name}
                    </Typography>

                    {allowDocumentDescription && doc.description && (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{
                          fontStyle: "italic",
                          lineHeight: 1.5,
                          mt: 0.5,
                          whiteSpace: "normal",
                          overflow: "hidden",
                          display: "-webkit-box",
                          WebkitBoxOrient: "vertical",
                          WebkitLineClamp: 2,
                        }}
                      >
                        {doc.description}
                      </Typography>
                    )}
                  </Box>
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};
