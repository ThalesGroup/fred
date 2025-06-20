// components/profile/CreateChatProfileDialog.tsx
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
import { useCreateChatProfileMutation } from "../../slices/chatProfileApi";

interface CreateChatProfileDialogProps {
    open: boolean;
    onClose: () => void;
    onCreated: () => void;
}

export const CreateChatProfileDialog = ({ open, onClose, onCreated }: CreateChatProfileDialogProps) => {
    const theme = useTheme();
    const [title, setTitle] = useState("");
    const [description, setDescription] = useState("");
    const [files, setFiles] = useState<File[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [createChatProfile] = useCreateChatProfileMutation();

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop: (accepted) => setFiles((prev) => [...prev, ...accepted]),
        accept: [
            ".pdf",
            ".docx",
            ".xlsx",
            ".pptx"
        ]
    });

    const handleCreate = async () => {
        if (!title.trim()) return;
        setIsLoading(true);
        try {
            await createChatProfile({
                title,
                description,
                files,
            }).unwrap();
            setTitle("");
            setDescription("");
            setFiles([]);
            onCreated();
            onClose();
        } catch (e) {
            console.error("Failed to create profile", e);
        } finally {
            setIsLoading(false);
        }
    };



    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="h6">New Profile</Typography>
                    <IconButton onClick={onClose} disabled={isLoading}>
                        <CloseIcon />
                    </IconButton>
                </Stack>
            </DialogTitle>

            <DialogContent>
                <Stack spacing={2.5} mt={1}>
                    <TextField
                        label="Title"
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
                        <Stack spacing={0.5}>
                            {files.map((file, i) => (
                                <Typography key={i} variant="caption" noWrap>
                                    {file.name} ({(file.size / 1024).toFixed(1)} KB)
                                </Typography>
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
