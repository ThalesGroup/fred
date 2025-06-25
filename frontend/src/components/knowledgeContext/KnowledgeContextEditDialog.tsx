import { useEffect, useState } from 'react';
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
  Box,
  CircularProgress,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import DocumentScannerIcon from '@mui/icons-material/DocumentScanner';
import DeleteIcon from "@mui/icons-material/Delete";
import { useDropzone } from 'react-dropzone';
import { useDeleteKnowledgeContextDocumentMutation } from '../../slices/knowledgeContextApi';
import { useToast } from '../ToastProvider';

export interface Document {
  id: string;
  document_name: string;
  document_type: string;
  size?: string;
  description?: string;
}

export interface KnowledgeContext {
  id: string;
  title: string;
  description?: string;
  documents: Document[];
  tokens?: number;
  tag?: string;
}

interface KnowledgeContextEditDialogProps {
  open: boolean;
  onClose: () => void;
  onReloadContext: () => void;
  onSave: (params: {
    title: string;
    description: string;
    files: File[];
    documents: Document[];
    documentsDescription: Record<string, string>;
  }) => Promise<void>;
  context: KnowledgeContext;
  allowDocuments?: boolean;
  allowDocumentDescription?: boolean;
  dialogTitle: string
}

export const KnowledgeContextEditDialog = ({
  open,
  onClose,
  onSave,
  context,
  onReloadContext,
  allowDocuments = true,
  allowDocumentDescription = true,
  dialogTitle,
}: KnowledgeContextEditDialogProps) => {
  const theme = useTheme();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tempFiles, setTempFiles] = useState<File[]>([]);
  const [tempFileDescriptions, setTempFileDescriptions] = useState<Record<string, string>>({});
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loadingDocumentIds, setLoadingDocumentIds] = useState<string[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const { showError } = useToast();

  const [deleteDocument] = useDeleteKnowledgeContextDocumentMutation();

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (accepted) => setTempFiles((prev) => [...prev, ...accepted]),
    accept: [".pdf", ".docx", ".xlsx", ".pptx"]
  });

  useEffect(() => {
    if (context) {
      setTitle(context.title || "");
      setDescription(context.description || "");
      setTempFiles([]);
      setTempFileDescriptions({});
      setDocuments(context.documents || []);
      setLoadingDocumentIds([]);
      setIsSaving(false);
    }
  }, [context]);

  const handleDeleteExisting = async (docId: string) => {
    try {
      setLoadingDocumentIds((prev) => [...prev, docId]);
      await deleteDocument({
        knowledgeContext_id: context.id,
        document_id: docId
      }).unwrap();
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (err) {
      showError({
        summary: "Download failed",
        detail: `Could not delete document: ${err?.data?.detail || err.message}`,
      });
    } finally {
      setLoadingDocumentIds((prev) => prev.filter((id) => id !== docId));
    }
  };

  const handleDescriptionChange = (docId: string, value: string) => {
    setDocuments((prev) =>
      prev.map((doc) =>
        doc.id === docId ? { ...doc, description: value } : doc
      )
    );
  };

  const handleSave = async () => {
    if (!title.trim()) return;
    setIsSaving(true);

    try {
      const documentsDescription: Record<string, string> = {
        ...documents.reduce((acc, doc) => {
          if (doc.document_name && doc.description) {
            acc[doc.document_name] = doc.description;
          }
          return acc;
        }, {} as Record<string, string>),
        ...tempFileDescriptions,
      };

      await onSave({
        title,
        description,
        files: tempFiles,
        documents,
        documentsDescription
      });

      onClose();
    } catch (err: any) {
      showError({
        summary: "Update failed",
        detail: `Could not update context: ${err?.data?.detail || err.message}`,
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={isSaving ? undefined : onClose} fullWidth maxWidth="md">
      <DialogTitle>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">Edit {dialogTitle}</Typography>
          <IconButton onClick={onClose} disabled={isSaving}>
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
            disabled={isSaving}
          />

          <TextField
            label="Description"
            fullWidth
            multiline
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={isSaving}
          />

          {allowDocuments && (
            <>
              <Box
                {...getRootProps()}
                sx={{
                  p: 3,
                  border: `2px dashed ${isDragActive ? theme.palette.primary.main : theme.palette.divider}`,
                  borderRadius: 2,
                  textAlign: "center",
                  backgroundColor: theme.palette.background.default,
                  cursor: isSaving ? "not-allowed" : "pointer",
                  opacity: isSaving ? 0.5 : 1,
                  transition: "all 0.2s ease"
                }}
              >
                <input {...getInputProps()} disabled={isSaving} />
                <Typography variant="body2" color="text.secondary">
                  {isDragActive
                    ? "Drop files here"
                    : "Click or drag and drop files here"}
                </Typography>
              </Box>

              {documents.length > 0 && (
                <Box>
                  <Typography variant="subtitle2">Existing documents:</Typography>
                  <Stack spacing={1.5}>
                    {documents.map((doc) => {
                      const isLoading = loadingDocumentIds.includes(doc.id);
                      return (
                        <Box
                          key={doc.id}
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
                                {doc.document_name}
                              </Typography>
                            </Box>
                            <IconButton
                              size="small"
                              onClick={() => handleDeleteExisting(doc.id)}
                              disabled={isSaving || isLoading}
                            >
                              {isLoading ? <CircularProgress size={16} /> : <DeleteIcon fontSize="small" />}
                            </IconButton>
                          </Box>
                          {allowDocumentDescription && (
                            <TextField
                              label="Document description (optional)"
                              fullWidth
                              size="small"
                              value={doc.description || ""}
                              onChange={(e) => handleDescriptionChange(doc.id, e.target.value)}
                              multiline
                              rows={2}
                              sx={{ mt: 1.5 }}
                              disabled={isSaving}
                            />
                          )}
                        </Box>
                      );
                    })}
                  </Stack>
                </Box>
              )}

              {tempFiles.length > 0 && (
                <Box>
                  <Typography variant="subtitle2">New documents:</Typography>
                  <Stack spacing={1.5}>
                    {tempFiles.map((file) => (
                      <Box
                        key={file.name}
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
                          <Typography variant="body2" fontWeight={500} noWrap>
                            {file.name}
                          </Typography>
                          <IconButton
                            size="small"
                            onClick={() =>
                              setTempFiles((prev) => prev.filter((f) => f.name !== file.name))
                            }
                            disabled={isSaving}
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Box>

                        {allowDocumentDescription && (
                          <TextField
                            label="Document description (optional)"
                            fullWidth
                            size="small"
                            value={tempFileDescriptions[file.name] || ""}
                            onChange={(e) =>
                              setTempFileDescriptions((prev) => ({
                                ...prev,
                                [file.name]: e.target.value,
                              }))
                            }
                            multiline
                            rows={2}
                            sx={{ mt: 1.5 }}
                            disabled={isSaving}
                          />
                        )}
                      </Box>

                    ))}
                  </Stack>
                </Box>
              )}
            </>
          )}
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={isSaving}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={!title.trim() || isSaving}
        >
          {isSaving ? <CircularProgress size={20} /> : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
