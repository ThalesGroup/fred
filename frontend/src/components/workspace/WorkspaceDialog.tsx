// components/profile/CreateWorkspaceDialog.tsx
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
  useTheme,
  Box
} from "@mui/material";
import { useState } from "react";
import CloseIcon from "@mui/icons-material/Close";
import { useDropzone } from "react-dropzone";
import { useCreateWorkspaceMutation } from "../../slices/workspaceApi";
import { useToast } from "../ToastProvider";
import DocumentScannerIcon from '@mui/icons-material/DocumentScanner';

interface FileWithDescription {
  file: File;
  description: string;
}

interface CreateWorkspaceDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export const CreateWorkspaceDialog = ({ open, onClose, onCreated }: CreateWorkspaceDialogProps) => {
  const theme = useTheme();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<FileWithDescription[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [createWorkspace] = useCreateWorkspaceMutation();
  const { showError } = useToast();

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (accepted) => {
      const newFiles = accepted.map((f) => ({ file: f, description: "" }));
      setFiles((prev) => [...prev, ...newFiles]);
    },
    accept: [".pdf", ".docx", ".xlsx", ".pptx"]
  });

  const handleCreate = async () => {
    if (!title.trim()) return;
    setIsLoading(true);
    try {
      await createWorkspace({
        title,
        description,
        files: files.map((f) => f.file),
        // envoyer aussi les descriptions si supporté côté backend
      }).unwrap();
      setTitle("");
      setDescription("");
      setFiles([]);
      onCreated();
      onClose();
    } catch (e) {
      showError({
        summary: "Creation failed",
        detail: `Could not create profile: ${e?.data?.detail || e.message}`,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleDescriptionChange = (index: number, value: string) => {
    setFiles((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], description: value };
      return updated;
    });
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">New Workspace</Typography>
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
          />

          <TextField
            label="Description"
            fullWidth
            multiline
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />

          <Box
            {...getRootProps()}
            sx={{
              p: 3,
              border: `2px dashed ${isDragActive ? theme.palette.primary.main : theme.palette.divider}`,
              borderRadius: 2,
              textAlign: "center",
              backgroundColor: theme.palette.background.default,
              cursor: "pointer",
              transition: "all 0.2s ease"
            }}
          >
            <input {...getInputProps()} />
            <Typography variant="body2" color="text.secondary">
              {isDragActive ? "Drop files here" : "Click or drag files here"}
            </Typography>
          </Box>

          {files.length > 0 && (
            <Stack spacing={1.5}>
              {files.map((fileItem, i) => (
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
                  <Box display="flex" alignItems="center" gap={1}>
                    <DocumentScannerIcon fontSize="small" />
                    <Box>
                      <Typography variant="body2" fontWeight={500} noWrap>
                        {fileItem.file.name}
                      </Typography>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ fontStyle: "italic", lineHeight: 1.4 }}
                      >
                        {(fileItem.file.size / 1024).toFixed(1)} KB
                      </Typography>
                    </Box>
                  </Box>
                  <TextField
                    label="Document description (optional)"
                    fullWidth
                    size="small"
                    value={fileItem.description}
                    onChange={(e) => handleDescriptionChange(i, e.target.value)}
                    multiline
                    rows={2}
                    sx={{ mt: 1.5 }}
                  />
                </Box>
              ))}
            </Stack>
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