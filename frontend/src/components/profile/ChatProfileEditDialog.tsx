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
import { useDeleteChatProfileDocumentMutation } from '../../slices/chatProfileApi';
import { useToast } from '../ToastProvider';

interface ChatProfileDocument {
    id: string;
    document_name: string;
    document_type: string;
    size?: string;
}

export interface ChatProfile {
    id: string;
    title: string;
    description?: string;
    documents: ChatProfileDocument[];
}

interface EditChatProfileDialogProps {
    open: boolean;
    onClose: () => void;
    onReloadProfile: () => void;
    onSave: (params: {
        title: string;
        description: string;
        files: File[];
        documents: ChatProfileDocument[];
    }) => Promise<void>;
    chatProfile: ChatProfile;
}

export const ChatProfileEditDialog = ({
    open,
    onClose,
    onSave,
    chatProfile
}: EditChatProfileDialogProps) => {
    const theme = useTheme();
    const [title, setTitle] = useState("");
    const [description, setDescription] = useState("");
    const [tempFiles, setTempFiles] = useState<File[]>([]);
    const [documents, setDocuments] = useState<ChatProfileDocument[]>([]);
    const [loadingDocumentIds, setLoadingDocumentIds] = useState<string[]>([]);
    const [isSaving, setIsSaving] = useState(false);
    const [, setError] = useState<string | null>(null);
    const { showError } = useToast();

    const [deleteDocument] = useDeleteChatProfileDocumentMutation();

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop: (accepted) => setTempFiles((prev) => [...prev, ...accepted]),
        accept: [".pdf", ".docx", ".xlsx", ".pptx"]
    });

    useEffect(() => {
        if (chatProfile) {
            setTitle(chatProfile.title || "");
            setDescription(chatProfile.description || "");
            setTempFiles([]);
            setDocuments(chatProfile.documents || []);
            setLoadingDocumentIds([]);
            setIsSaving(false);
        }
    }, [chatProfile]);

    const handleDeleteExisting = async (docId: string) => {
        try {
            setLoadingDocumentIds((prev) => [...prev, docId]);
            await deleteDocument({
                chatProfile_id: chatProfile.id,
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

    const handleSave = async () => {
        if (!title.trim()) return;
        setIsSaving(true);
        setError(null);

        try {
            await onSave({
                title,
                description,
                files: tempFiles,
                documents
            });

            onClose();
        } catch (err: any) {
            showError({
                summary: "Update failed",
                detail: `Could not update profile: ${err?.data?.detail || err.message}`,
            });
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Dialog open={open} onClose={isSaving ? undefined : onClose} fullWidth maxWidth="sm">
            <DialogTitle>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="h6">Edit Profile</Typography>
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

                    {tempFiles.length > 0 && (
                        <Box>
                            <Typography variant="subtitle2">New files:</Typography>
                            <Stack spacing={0.5}>
                                {tempFiles.map((file, i) => (
                                    <Box
                                        key={i}
                                        sx={{
                                            display: "flex",
                                            alignItems: "center",
                                            "&:hover .delete-icon": { opacity: 1 }
                                        }}
                                    >
                                        <DocumentScannerIcon />
                                        <Typography variant="caption" noWrap sx={{ flex: 1 }}>
                                            {file.name} ({(file.size / 1024).toFixed(1)} KB)
                                        </Typography>
                                        <IconButton
                                            className="delete-icon"
                                            sx={{ opacity: 0, transition: "opacity 0.2s ease" }}
                                            onClick={() =>
                                                setTempFiles((prev) => prev.filter((_, index) => index !== i))
                                            }
                                            disabled={isSaving}
                                        >
                                            <DeleteIcon fontSize="small" />
                                        </IconButton>
                                    </Box>
                                ))}
                            </Stack>
                        </Box>
                    )}

                    {documents.length > 0 && (
                        <Box>
                            <Typography variant="subtitle2">Existing documents:</Typography>
                            <Stack spacing={0.5}>
                                {documents.map((doc) => {
                                    const isLoading = loadingDocumentIds.includes(doc.id);
                                    return (
                                        <Box
                                            key={doc.id}
                                            sx={{
                                                display: "flex",
                                                alignItems: "center",
                                                "&:hover .delete-icon": { opacity: 1 }
                                            }}
                                        >
                                            <DocumentScannerIcon />
                                            <Typography variant="caption" noWrap sx={{ flex: 1 }}>
                                                {doc.document_name}
                                            </Typography>
                                            <IconButton
                                                size="small"
                                                className="delete-icon"
                                                sx={{ opacity: 0, transition: "opacity 0.2s ease" }}
                                                onClick={() => handleDeleteExisting(doc.id)}
                                                disabled={isSaving || isLoading}
                                            >
                                                {isLoading ? (
                                                    <CircularProgress size={16} />
                                                ) : (
                                                    <DeleteIcon fontSize="small" />
                                                )}
                                            </IconButton>
                                        </Box>
                                    );
                                })}
                            </Stack>
                        </Box>
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
