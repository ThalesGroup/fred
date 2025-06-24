import {
  Box,
  Typography,
  Card,
  CardContent,
  Stack,
  IconButton,
  Button,
  Tooltip
} from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import { getDocumentIcon } from "../documents/DocumentIcon";
import { Workspace } from "./WorkspaceEditDialog";

interface Props {
  workspace: Workspace;
  onEdit: (workspace: Workspace) => void;
  onDelete: (id: string) => void;
  onViewDescription: (workspace: Workspace) => void;
}

export const WorkspaceItem = ({
  workspace,
  onEdit,
  onDelete,
  onViewDescription,
}: Props) => {

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
        width: "100%",
        backgroundColor: "transparent",
        border: (theme) => `1px solid ${theme.palette.divider}`,
      }}
    >
      <CardContent sx={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {/* Title */}
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Typography variant="h6" fontWeight={600}>
            {workspace.title}
          </Typography>
          <Box display="flex" gap={1}>
            <IconButton onClick={() => onEdit(workspace)}>
              <EditIcon fontSize="medium" />
            </IconButton>
            <IconButton onClick={() => onDelete(workspace.id)}>
              <DeleteIcon fontSize="medium" />
            </IconButton>
          </Box>
        </Box>
        {/* Workspace description */}
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
            {getPreview(workspace.description || "No description provided.")}
          </Typography>

          {(workspace.description?.length ?? 0) > 200 && (
            <Button
              size="small"
              onClick={() => onViewDescription(workspace)}
              sx={{ mt: 1 }}
            >
              View full description
            </Button>
          )}
        </Box>

        {/* Documents */}
        {workspace.documents?.length > 0 && (
          <Box mt={1}>
            <Typography
              variant="subtitle2"
              fontWeight={500}
              color="text.primary"
              gutterBottom
            >
              Documents ({workspace.documents.length})
            </Typography>
            <Box
              display="flex"
              flexWrap="wrap"
              gap={1.5}
              mt={1}
            >
              {workspace.documents.map((doc) => (
                <Box
                  key={doc.id}
                  display="flex"
                  alignItems="flex-start"
                  px={2}
                  py={1.5}
                  maxWidth="100%"
                  borderRadius={2}
                  bgcolor="background.default"
                  border={(theme) => `1px solid ${theme.palette.divider}`}
                  boxShadow={1}
                  sx={{
                    flex: "1 1 45%",
                    minWidth: "280px",
                  }}
                >
                  {getDocumentIcon(doc.document_name)}

                  <Box ml={1} width="100%">
                    <Typography
                      variant="body2"
                      fontWeight={500}
                      noWrap
                      title={doc.document_name}
                    >
                      {doc.document_name}
                    </Typography>

                    {doc.description && (
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

        {/* Footer: Tokens + actions
        <Box
          mt="auto"
          pt={2}
          display="flex"
          justifyContent="space-between"
          alignItems="flex-end"
        >
          <Box sx={{ width: 200 }}>
            <Typography
              variant="caption"
              color="text.secondary"
              whiteSpace="nowrap"
              sx={{ mb: 0.5 }}
            >
              Tokens: {workspace.tokens} / {maxTokens ?? 12000}
            </Typography>
            <Box
              sx={{
                height: 10,
                width: "100%",
                borderRadius: 5,
                bgcolor: "#eeeeee",
                overflow: "hidden",
              }}
            >
              <Box
                sx={{
                  height: "100%",
                  width: `${tokenUsage * 100}%`,
                  bgcolor:
                    tokenUsage < 0.7
                      ? "success.main"
                      : tokenUsage < 0.9
                        ? "warning.main"
                        : "error.main",
                  transition: "width 0.3s ease-in-out",
                }}
              />
            </Box>
          </Box>
        </Box> */}
      </CardContent>
    </Card>
  );
};
