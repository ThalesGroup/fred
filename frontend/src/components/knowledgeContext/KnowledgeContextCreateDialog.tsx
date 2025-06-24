// components/profile/CreateKnowledgeContextDialog.tsx
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Stack,
  IconButton,
  Typography,
  Box
} from "@mui/material";
import { useState } from "react";
import CloseIcon from "@mui/icons-material/Close";
import { useDropzone } from "react-dropzone";
import DocumentScannerIcon from '@mui/icons-material/DocumentScanner';
import DeleteIcon from "@mui/icons-material/Delete";
import { useCreateKnowledgeContextMutation } from "../../slices/knowledgeContextApi";
import { useToast } from "../ToastProvider";

interface FileWithDescription {
  file: File;
  description: string;
}

interface KnowledgeContextCreateDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  allowDocuments?: boolean;
  allowDocumentDescription?: boolean;
}

export const KnowledgeContextCreateDialog = ({
  open,
  onClose,
  onCreated,
  allowDocuments = true,
  allowDocumentDescription = true
}: KnowledgeContextCreateDialogProps) => {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<FileWithDescription[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [createKnowledgeContext] = useCreateKnowledgeContextMutation();
  const { showError } = useToast();

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (acceptedFiles) => {
      const newFiles: FileWithDescription[] = acceptedFiles.map((file) => ({ file, description: "" }));
      setFiles((prev) => [...prev, ...newFiles]);
    },
    accept: [".pdf", ".docx", ".xlsx", ".pptx"]
  });

  const handleFileDescriptionChange = (index: number, value: string) => {
    setFiles((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], description: value };
      return updated;
    });
  };

  const handleRemoveFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleCreate = async () => {
    if (!title.trim()) return;
    setIsLoading(true);
    try {
      await createKnowledgeContext({
        title,
        description,
        files: files.map((f) => f.file),
      }).unwrap();
      setTitle("");
      setDescription("");
      setFiles([]);
      onCreated();
      onClose();
    } catch (e) {
      showError({
        summary: "Creation failed",
        detail: `Could not create context: ${e?.data?.detail || e.message}`,
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">New Knowledge Context</Typography>
          <IconButton onClick={onClose} disabled={isLoading}>
            <CloseIcon />
          </IconButton>
        </Stack>
      </DialogTitle>

      <DialogContent>
        <Stack spacing={2.5} mt={1}>
          <TextField
            label="Name"
            fullWidth
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            disabled={isLoading}
          />

          <TextField
            label="Description"
            fullWidth
            multiline
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={isLoading}
          />

          {allowDocuments && (
            <>
              <Box
                {...getRootProps()}
                sx={{
                  p: 3,
                  border: `2px dashed #ccc`,
                  borderRadius: 2,
                  textAlign: "center",
                  backgroundColor: "background.default",
                  cursor: isLoading ? "not-allowed" : "pointer",
                  opacity: isLoading ? 0.5 : 1,
                  transition: "all 0.2s ease"
                }}
              >
                <input {...getInputProps()} disabled={isLoading} />
                <Typography variant="body2" color="text.secondary">
                  {isDragActive ? "Drop files here" : "Click or drag and drop files here"}
                </Typography>
              </Box>

              {files.length > 0 && (
                <Stack spacing={1.5}>
                  {files.map((file, i) => (
                    <Box
                      key={i}
                      display="flex"
                      flexDirection="column"
                      px={2}
                      py={1.5}
                      borderRadius={2}
                      bgcolor="background.default"
                      border={(theme) => `1px solid ${theme.palette.divider}`}
                      boxShadow={1}
                    >
                      <Box display="flex" justifyContent="space-between" alignItems="center">
                        <Box display="flex" alignItems="center" gap={1}>
                          <DocumentScannerIcon fontSize="small" />
                          <Typography variant="body2" fontWeight={500} noWrap>
                            {file.file.name}
                          </Typography>
                        </Box>
                        <IconButton
                          size="small"
                          onClick={() => handleRemoveFile(i)}
                          disabled={isLoading}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Box>
                      {allowDocumentDescription && (
                        <TextField
                          label="Document description (optional)"
                          fullWidth
                          size="small"
                          value={file.description || ""}
                          onChange={(e) => handleFileDescriptionChange(i, e.target.value)}
                          multiline
                          rows={2}
                          sx={{ mt: 1.5 }}
                          disabled={isLoading}
                        />
                      )}
                    </Box>
                  ))}
                </Stack>
              )}
            </>
          )}
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={isLoading}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleCreate}
          disabled={isLoading || !title.trim()}
        >
          {isLoading ? "Creating..." : "Create"}
        </Button>
      </DialogActions>
    </Dialog>
  );
};