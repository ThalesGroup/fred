import { PageBodyWrapper } from "../common/PageBodyWrapper";
import {
    Box, Typography, useTheme, TextField, Button, IconButton,
    Container, Paper, Fade, Snackbar, Alert,
    Dialog, DialogTitle, DialogContent, DialogActions,
    Stack, alpha, InputAdornment,
    Grid2
} from "@mui/material";
import { useState, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import { LoadingSpinner } from "../utils/loadingSpinner";
import AddIcon from "@mui/icons-material/Add";
import UploadIcon from '@mui/icons-material/Upload';
import DeleteIcon from '@mui/icons-material/Delete';
import CloseIcon from '@mui/icons-material/Close';
import SearchIcon from '@mui/icons-material/Search';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import DocumentScannerIcon from '@mui/icons-material/DocumentScanner';
import DescriptionIcon from '@mui/icons-material/Description';
import TableChartIcon from '@mui/icons-material/TableChart';
import SlideshowIcon from '@mui/icons-material/Slideshow';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import FolderIcon from '@mui/icons-material/Folder';

// API imports
import {
    useCreateChatProfileMutation,
    useGetChatProfilesMutation,
    useUpdateChatProfileMutation,
    useDeleteChatProfileMutation,
    useUploadChatProfileDocumentsMutation,
    useDeleteChatProfileDocumentMutation
} from "../slices/chatProfileApi"

// Components
import { CustomProfile } from "../components/CustomProfile";

export interface ChatProfileDocument {
    id: string;
    document_name: string;
    document_type: string;
    size?: number;
}

export interface ChatProfile {
    id: string;
    title: string;
    description: string;
    created_at: string;
    updated_at: string;
    documents: ChatProfileDocument[];
    user_id: string;
    tokens: number;
}

export const ChatProfiles = () => {
    const theme = useTheme();
    const isDarkTheme = theme.palette.mode === "dark";

    // États
    const [chatProfiles, setChatProfiles] = useState<ChatProfile[]>([]);
    const [filteredChatProfiles, setFilteredChatProfiles] = useState<ChatProfile[]>([]);
    const [searchQuery, setSearchQuery] = useState("");
    const [showElements, setShowElements] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    // Dialog states
    const [openCreateDialog, setOpenCreateDialog] = useState(false);
    const [openEditDialog, setOpenEditDialog] = useState(false);
    const [openDeleteDialog, setOpenDeleteDialog] = useState(false);

    // Form states
    const [currentChatProfile, setCurrentChatProfile] = useState<ChatProfile | null>(null);
    const [newChatProfileTitle, setNewChatProfileTitle] = useState("");
    const [newChatProfileDescription, setNewChatProfileDescription] = useState("");
    const [tempFiles, setTempFiles] = useState<File[]>([]);

    // Snackbar states
    const [snackbarOpen, setSnackbarOpen] = useState(false);
    const [snackbarMessage, setSnackbarMessage] = useState("");
    const [snackbarSeverity, setSnackbarSeverity] = useState<"success" | "error" | "info" | "warning">("success");

    // API hooks
    const [getChatProfiles] = useGetChatProfilesMutation();
    const [createChatProfile] = useCreateChatProfileMutation();
    const [updateChatProfile] = useUpdateChatProfileMutation();
    const [deleteChatProfile] = useDeleteChatProfileMutation();
    const [uploadChatProfileDocuments] = useUploadChatProfileDocumentsMutation();
    const [deleteChatProfileDocument] = useDeleteChatProfileDocumentMutation();

    // Dropzone configuration
    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop: (acceptedFiles) => {
            setTempFiles((prevFiles) => [...prevFiles, ...acceptedFiles]);
        },
        accept: '.pdf,.docx,.xlsx,.pptx'
    });

    // Animation effect on load
    useEffect(() => {
        setShowElements(true);
        fetchChatProfiles();
    }, []);

    // Search effect
    useEffect(() => {
        handleSearch();
    }, [chatProfiles, searchQuery]);

    // Fetch chatProfiles from API with mock data
    const fetchChatProfiles = async () => {
        setIsLoading(true);
        try {
            const response = await getChatProfiles().unwrap();
            setChatProfiles(response);
        } catch (error) {
            console.error("Error fetching chatProfiles:", error);
            showSnackbar("Erreur lors du chargement des chatProfiles", "error");
        } finally {
            setIsLoading(false);
        }
    };

    // Handle search
    const handleSearch = () => {
        const filtered = chatProfiles.filter((chatProfile) =>
            chatProfile.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
            chatProfile.description.toLowerCase().includes(searchQuery.toLowerCase())
        );
        setFilteredChatProfiles(filtered);
    };

    // Delete temporary file 
    const handleDeleteTempFile = (index: number) => {
        setTempFiles(tempFiles.filter((_, i) => i !== index));
    };

    // Get file icon based on type
    const getFileIcon = (fileType: string) => {
        switch (fileType.toLowerCase()) {
            case 'pdf':
                return <PictureAsPdfIcon sx={{ color: '#f44336' }} />;
            case 'xlsx':
            case 'xls':
                return <TableChartIcon sx={{ color: '#4caf50' }} />;
            case 'docx':
            case 'doc':
                return <DescriptionIcon sx={{ color: '#2196f3' }} />;
            case 'pptx':
            case 'ppt':
                return <SlideshowIcon sx={{ color: '#ff9800' }} />;
            default:
                return <FolderIcon sx={{ color: '#9e9e9e' }} />;
        }
    };

    // Format file size
    const formatFileSize = (bytes: number) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    };

    const handleCreateChatProfile = async () => {
        setIsLoading(true);
        try {
            if (!newChatProfileTitle.trim()) {
                showSnackbar("Le titre est requis", "error");
                return;
            }

            const newChatProfile = await createChatProfile({
                title: newChatProfileTitle,
                description: newChatProfileDescription,
                files: tempFiles,
            }).unwrap();

            setNewChatProfileTitle("");
            setNewChatProfileDescription("");
            setTempFiles([]);
            setOpenCreateDialog(false);

            fetchChatProfiles();
            showSnackbar("ChatProfile créé avec succès", "success");
        } catch (error) {
            console.error("Error creating chatProfile:", error);
            showSnackbar("Erreur lors de la création du chatProfile", "error");
        } finally {
            setIsLoading(false);
        }
    };


    // Edit chatProfile
    const handleOpenEditDialog = (chatProfile: ChatProfile) => {
        setCurrentChatProfile(chatProfile);
        setNewChatProfileTitle(chatProfile.title);
        setNewChatProfileDescription(chatProfile.description);
        setOpenEditDialog(true);
    };

    const handleUpdateChatProfile = async () => {
        if (!currentChatProfile) return;

        setIsLoading(true);
        try {
            if (!newChatProfileTitle.trim()) {
                showSnackbar("Le titre est requis", "error");
                return;
            }

            await updateChatProfile({
                chatProfile_id: currentChatProfile.id,
                title: newChatProfileTitle,
                description: newChatProfileDescription
            }).unwrap();

            if (tempFiles.length > 0) {
                await uploadChatProfileDocuments({
                    chatProfile_id: currentChatProfile.id,
                    files: tempFiles
                }).unwrap();
            }

            setNewChatProfileTitle("");
            setNewChatProfileDescription("");
            setTempFiles([]);
            setCurrentChatProfile(null);
            setOpenEditDialog(false);

            fetchChatProfiles();
            showSnackbar("ChatProfile modifié avec succès", "success");
        } catch (error) {
            console.error("Error updating chatProfile:", error);
            showSnackbar("Erreur lors de la modification du chatProfile", "error");
        } finally {
            setIsLoading(false);
        }
    };

    // Delete chatProfile
    const handleOpenDeleteDialog = (chatProfile: ChatProfile) => {
        setCurrentChatProfile(chatProfile);
        setOpenDeleteDialog(true);
    };

    const handleDeleteChatProfile = async () => {
        if (!currentChatProfile) return;

        setIsLoading(true);
        try {
            await deleteChatProfile({ chatProfile_id: currentChatProfile.id }).unwrap();

            setCurrentChatProfile(null);
            setOpenDeleteDialog(false);

            fetchChatProfiles();
            showSnackbar("ChatProfile supprimé avec succès", "success");
        } catch (error) {
            console.error("Error deleting chatProfile:", error);
            showSnackbar("Erreur lors de la suppression du chatProfile", "error");
        } finally {
            setIsLoading(false);
        }
    };

    const handleDeleteExistingDocument = async (documentId: string) => {
        if (!currentChatProfile) return;
        try {
            await deleteChatProfileDocument({
                chatProfile_id: currentChatProfile.id,
                document_id: documentId
            }).unwrap();

            // Mettre à jour le profil en local sans re-fetch global
            const updatedDocuments = currentChatProfile.documents.filter(doc => doc.id !== documentId);
            setCurrentChatProfile({
                ...currentChatProfile,
                documents: updatedDocuments
            });

            showSnackbar("Document supprimé avec succès", "success");
        } catch (error) {
            console.error("Erreur lors de la suppression du document :", error);
            showSnackbar("Échec de la suppression du document", "error");
        }
    };

    // Snackbar handlers
    const showSnackbar = (message: string, severity: "success" | "error" | "info" | "warning" = "success") => {
        setSnackbarMessage(message);
        setSnackbarSeverity(severity);
        setSnackbarOpen(true);
    };

    const handleSnackbarClose = (_event?: React.SyntheticEvent | Event, reason?: string) => {
        if (reason === 'clickaway') {
            return;
        }
        setSnackbarOpen(false);
    };

    return (
        <PageBodyWrapper>
            {/*  Header Section */}
            <Fade in={showElements} timeout={1000}>
                <Box
                    sx={{
                        position: "relative",
                        backgroundSize: "cover",
                        backgroundPosition: "center",
                        py: { xs: 3, md: 4 },
                        mb: 3,
                        borderRadius: 2,
                        boxShadow: theme.shadows[4],
                    }}
                >
                    <Container maxWidth="xl">
                        <Grid2 container alignItems="center" spacing={2}>
                            <Grid2 size={{ xs: 12, md: 8 }}>
                                <Box>
                                    <Typography variant="h4" fontWeight="bold" gutterBottom>
                                        Chat Profiles
                                    </Typography>
                                    <Typography variant="body2" color="textSecondary" sx={{ maxWidth: "700px" }}>
                                        Create and enhance profiles to guide your agents
                                    </Typography>
                                </Box>
                            </Grid2>
                            <Grid2 size={{ xs: 12, md: 4 }} sx={{ textAlign: { xs: "left", md: "right" } }}>
                                <Button
                                    variant="contained"
                                    startIcon={<AddIcon />}
                                    onClick={() => setOpenCreateDialog(true)}
                                    size="medium"
                                    sx={{
                                        borderRadius: "8px",
                                        mt: { xs: 1, md: 0 },
                                    }}
                                >
                                    Create profile
                                </Button>
                            </Grid2>
                        </Grid2>
                    </Container>
                </Box>
            </Fade>

            {/*  Search Section */}
            <Container maxWidth="xl" sx={{ mb: 4 }}>
                <Fade in={showElements} timeout={1200}>
                    <Paper
                        elevation={0}
                        sx={{
                            p: 3,
                            borderRadius: 4,
                            border: `1px solid ${alpha(theme.palette.divider, 0.1)}`,
                            backgroundColor: alpha(theme.palette.background.paper, 0.7),
                            backdropFilter: 'blur(10px)',
                            boxShadow: `0 8px 32px ${alpha(theme.palette.common.black, 0.1)}`,
                        }}
                    >
                        <TextField
                            fullWidth
                            placeholder="Rechercher un chatProfile..."
                            variant="outlined"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            InputProps={{
                                startAdornment: (
                                    <InputAdornment position="start">
                                        <SearchIcon color="action" />
                                    </InputAdornment>
                                ),
                            }}
                            sx={{
                                '& .MuiOutlinedInput-root': {
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.background.paper, 0.8),
                                    '&:hover': {
                                        '& .MuiOutlinedInput-notchedOutline': {
                                            borderColor: theme.palette.primary.main,
                                        },
                                    },
                                },
                            }}
                        />
                    </Paper>
                </Fade>
            </Container>

            {/*  ChatProfiles Grid */}
            <Container maxWidth="xl">
                <Fade in={showElements} timeout={1400}>
                    <Box>
                        {isLoading ? (
                            <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
                                <LoadingSpinner />
                            </Box>
                        ) : filteredChatProfiles.length > 0 ? (
                            <Grid2 container spacing={3}>
                                {filteredChatProfiles.map((chatProfile, index) => (
                                    <Grid2 size={{ xs: 12, sm: 6, lg: 4 }} key={chatProfile.id}>
                                        <CustomProfile
                                            chatProfile={chatProfile}
                                            index={index}
                                            onEdit={handleOpenEditDialog}
                                            onDelete={handleOpenDeleteDialog}
                                            getFileIcon={getFileIcon}
                                            formatFileSize={formatFileSize}
                                        />
                                    </Grid2>
                                ))}
                            </Grid2>
                        ) : (
                            <Paper
                                sx={{
                                    p: 6,
                                    textAlign: 'center',
                                    borderRadius: 4,
                                    border: `1px solid ${alpha(theme.palette.divider, 0.1)}`,
                                    backgroundColor: alpha(theme.palette.background.paper, 0.7),
                                    backdropFilter: 'blur(10px)',
                                }}
                            >
                                <DocumentScannerIcon
                                    sx={{
                                        fontSize: 80,
                                        color: alpha(theme.palette.text.secondary, 0.3),
                                        mb: 3
                                    }}
                                />
                                <Typography variant="body1" color="text.secondary" sx={{ mb: 3, maxWidth: 400, mx: 'auto' }}>
                                    {searchQuery
                                        ? "No profile found"
                                        : "Create your first chat profile to enhance your agents efficiency"
                                    }
                                </Typography>
                                <Button
                                    variant="contained"
                                    startIcon={<AddIcon />}
                                    onClick={() => setOpenCreateDialog(true)}
                                    size="large"
                                    sx={{
                                        borderRadius: 3,
                                        px: 4,
                                        py: 1.5,
                                    }}
                                >
                                    Create profile
                                </Button>
                            </Paper>
                        )}
                    </Box>
                </Fade>
            </Container>

            {/* Minimalist Create ChatProfile Dialog */}
            <Dialog
                open={openCreateDialog}
                onClose={() => !isLoading && setOpenCreateDialog(false)}
                fullWidth
                maxWidth="sm"
                PaperProps={{
                    sx: {
                        borderRadius: 3,
                        boxShadow: `0 10px 30px ${alpha(theme.palette.common.black, 0.15)}`,
                    }
                }}
            >
                <DialogTitle sx={{ pt: 3, pb: 1 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Typography variant="h6" fontWeight={600}>
                            New Profile
                        </Typography>
                        <IconButton
                            onClick={() => !isLoading && setOpenCreateDialog(false)}
                            disabled={isLoading}
                            size="small"
                        >
                            <CloseIcon />
                        </IconButton>
                    </Stack>
                </DialogTitle>

                <DialogContent sx={{ py: 2, pt: 2.5 }}>
                    <Stack spacing={2.5}>
                        <TextField
                            autoFocus
                            label="Title"
                            fullWidth
                            value={newChatProfileTitle}
                            onChange={(e) => setNewChatProfileTitle(e.target.value)}
                            required
                            variant="outlined"
                            size="small"
                            sx={{
                                '& .MuiOutlinedInput-root': {
                                    borderRadius: 2,
                                }
                            }}
                        />

                        <TextField
                            label="Description"
                            fullWidth
                            multiline
                            rows={3}
                            value={newChatProfileDescription}
                            onChange={(e) => setNewChatProfileDescription(e.target.value)}
                            variant="outlined"
                            size="small"
                            sx={{
                                '& .MuiOutlinedInput-root': {
                                    borderRadius: 2,
                                }
                            }}
                        />

                        <Box>
                            <Typography variant="body2" fontWeight={500} gutterBottom sx={{ color: 'text.secondary' }}>
                                Documents (optional)
                            </Typography>
                            <Box
                                {...getRootProps()}
                                sx={{
                                    p: 3,
                                    border: `2px dashed ${isDragActive ? theme.palette.primary.main : alpha(theme.palette.divider, 0.4)}`,
                                    borderRadius: 2,
                                    backgroundColor: isDragActive
                                        ? alpha(theme.palette.primary.main, 0.03)
                                        : alpha(theme.palette.background.default, 0.3),
                                    cursor: 'pointer',
                                    transition: 'all 0.2s ease',
                                    textAlign: 'center',
                                    '&:hover': {
                                        borderColor: theme.palette.primary.main,
                                        backgroundColor: alpha(theme.palette.primary.main, 0.02),
                                    }
                                }}
                            >
                                <input {...getInputProps()} />
                                <Typography variant="body2" color="text.secondary">
                                    {isDragActive ? "Drop files here" : "Click or drag files here"}
                                </Typography>
                            </Box>

                            {tempFiles.length > 0 && (
                                <Stack spacing={0.8} sx={{ mt: 2 }}>
                                    {tempFiles.map((file, index) => (
                                        <Box
                                            key={index}
                                            sx={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: 1,
                                                p: 1,
                                                borderRadius: 2,
                                                backgroundColor: alpha(theme.palette.background.default, 0.5),
                                                border: `1px solid ${alpha(theme.palette.divider, 0.1)}`,
                                                transition: 'all 0.2s ease',
                                                '&:hover': {
                                                    backgroundColor: alpha(theme.palette.background.default, 0.7),
                                                }
                                            }}
                                        >
                                            {getFileIcon(file.name.split('.').pop() || '')}
                                            <Typography
                                                variant="caption"
                                                fontWeight={500}
                                                sx={{
                                                    flex: 1,
                                                    overflow: 'hidden',
                                                    textOverflow: 'ellipsis',
                                                    whiteSpace: 'nowrap',
                                                    fontSize: '0.8rem',
                                                }}
                                            >
                                                {file.name}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                                                {formatFileSize(file.size)}
                                            </Typography>
                                            <IconButton
                                                size="small"
                                                onClick={() => handleDeleteTempFile(index)}
                                                disabled={isLoading}
                                                sx={{ ml: 0.5 }}
                                            >
                                                <DeleteIcon fontSize="small" />
                                            </IconButton>
                                        </Box>
                                    ))}
                                </Stack>
                            )}
                        </Box>
                    </Stack>
                </DialogContent>

                <DialogActions sx={{ px: 3, pb: 3, pt: 1 }}>
                    <Button
                        onClick={() => !isLoading && setOpenCreateDialog(false)}
                        disabled={isLoading}
                        sx={{ borderRadius: 2 }}
                    >
                        Cancel
                    </Button>
                    <Button
                        variant="contained"
                        onClick={handleCreateChatProfile}
                        disabled={isLoading || !newChatProfileTitle.trim()}
                        sx={{
                            borderRadius: 2,
                            px: 3,
                        }}
                    >
                        {isLoading ? 'Creating...' : 'Create'}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Minimalist Edit ChatProfile Dialog */}
            <Dialog
                open={openEditDialog}
                onClose={() => !isLoading && setOpenEditDialog(false)}
                fullWidth
                maxWidth="sm"
                PaperProps={{
                    sx: {
                        borderRadius: 3,
                        boxShadow: `0 10px 30px ${alpha(theme.palette.common.black, 0.15)}`,
                    }
                }}
            >
                <DialogTitle sx={{ pt: 3, pb: 1 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Typography variant="h6" fontWeight={600}>
                            Edit Profile
                        </Typography>
                        <IconButton
                            onClick={() => !isLoading && setOpenEditDialog(false)}
                            disabled={isLoading}
                            size="small"
                        >
                            <CloseIcon />
                        </IconButton>
                    </Stack>
                </DialogTitle>

                <DialogContent sx={{ py: 2, pt: 2.5 }}>
                    <Stack spacing={2.5}>
                        <TextField
                            autoFocus
                            label="Title"
                            fullWidth
                            value={newChatProfileTitle}
                            onChange={(e) => setNewChatProfileTitle(e.target.value)}
                            required
                            variant="outlined"
                            size="small"
                            sx={{
                                '& .MuiOutlinedInput-root': {
                                    borderRadius: 2,
                                }
                            }}
                        />

                        <TextField
                            label="Description"
                            fullWidth
                            multiline
                            rows={3}
                            value={newChatProfileDescription}
                            onChange={(e) => setNewChatProfileDescription(e.target.value)}
                            variant="outlined"
                            size="small"
                            sx={{
                                '& .MuiOutlinedInput-root': {
                                    borderRadius: 2,
                                }
                            }}
                        />

                        {currentChatProfile?.documents && currentChatProfile.documents.length > 0 && (
                            <Box>
                                <Typography variant="body2" fontWeight={500} gutterBottom sx={{ color: 'text.secondary' }}>
                                    Current documents
                                </Typography>
                                <Box
                                    sx={{
                                        maxHeight: 200,
                                        overflowY: 'auto',
                                        backgroundColor: alpha(theme.palette.background.default, 0.2),
                                        px: 1,
                                        py: 1,
                                    }}
                                >
                                    <Stack spacing={0.8}>
                                        {currentChatProfile.documents.map((doc) => (
                                            <Box
                                                key={doc.id}
                                                sx={{
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: 1,
                                                    p: 1,
                                                    borderRadius: 2,
                                                    backgroundColor: alpha(theme.palette.background.default, 0.3),
                                                    border: `1px solid ${alpha(theme.palette.divider, 0.1)}`,
                                                    transition: 'all 0.2s ease',
                                                    '&:hover': {
                                                        backgroundColor: alpha(theme.palette.background.default, 0.5),
                                                    }
                                                }}
                                            >
                                                {getFileIcon(doc.document_type)}
                                                <Typography
                                                    variant="caption"
                                                    fontWeight={500}
                                                    sx={{
                                                        flex: 1,
                                                        overflow: 'hidden',
                                                        textOverflow: 'ellipsis',
                                                        whiteSpace: 'nowrap',
                                                        fontSize: '0.8rem',
                                                    }}
                                                >
                                                    {doc.document_name}
                                                </Typography>
                                                <IconButton size="small" sx={{ ml: 'auto' }} onClick={() => handleDeleteExistingDocument(doc.id)}>
                                                    <DeleteIcon fontSize="small" />
                                                </IconButton>
                                            </Box>
                                        ))}
                                    </Stack>
                                </Box>
                                {currentChatProfile.documents.length > 3 && (
                                    <Typography
                                        variant="caption"
                                        color="text.secondary"
                                        sx={{
                                            pt: 0.5,
                                            fontSize: '0.75rem',
                                            fontStyle: 'italic',
                                            textAlign: 'right'
                                        }}
                                    >
                                        Showing all {currentChatProfile.documents.length} documents
                                    </Typography>
                                )}
                            </Box>
                        )}


                        {/* Add Documents - Simplified */}
                        <Box>
                            <Typography variant="body2" fontWeight={500} gutterBottom sx={{ color: 'text.secondary' }}>
                                Add documents
                            </Typography>
                            <Box
                                {...getRootProps()}
                                sx={{
                                    p: 3,
                                    border: `2px dashed ${isDragActive ? theme.palette.primary.main : alpha(theme.palette.divider, 0.4)}`,
                                    borderRadius: 2,
                                    backgroundColor: isDragActive
                                        ? alpha(theme.palette.primary.main, 0.03)
                                        : alpha(theme.palette.background.default, 0.3),
                                    cursor: 'pointer',
                                    transition: 'all 0.2s ease',
                                    textAlign: 'center',
                                    '&:hover': {
                                        borderColor: theme.palette.primary.main,
                                        backgroundColor: alpha(theme.palette.primary.main, 0.02),
                                    }
                                }}
                            >
                                <input {...getInputProps()} />
                                <Typography variant="body2" color="text.secondary">
                                    {isDragActive ? "Drop files here" : "Click or drag files here"}
                                </Typography>
                            </Box>

                            {tempFiles.length > 0 && (
                                <Stack spacing={0.8} sx={{ mt: 2 }}>
                                    {tempFiles.map((file, index) => (
                                        <Box
                                            key={index}
                                            sx={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: 1,
                                                p: 1,
                                                borderRadius: 2,
                                                backgroundColor: alpha(theme.palette.success.main, 0.05),
                                                border: `1px solid ${alpha(theme.palette.success.main, 0.2)}`,
                                                transition: 'all 0.2s ease',
                                                '&:hover': {
                                                    backgroundColor: alpha(theme.palette.success.main, 0.1),
                                                }
                                            }}
                                        >
                                            {getFileIcon(file.name.split('.').pop() || '')}
                                            <Typography
                                                variant="caption"
                                                fontWeight={500}
                                                sx={{
                                                    flex: 1,
                                                    overflow: 'hidden',
                                                    textOverflow: 'ellipsis',
                                                    whiteSpace: 'nowrap',
                                                    fontSize: '0.8rem',
                                                }}
                                            >
                                                {file.name}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                                                {formatFileSize(file.size)}
                                            </Typography>
                                            <IconButton
                                                size="small"
                                                onClick={() => handleDeleteTempFile(index)}
                                                disabled={isLoading}
                                                sx={{ ml: 0.5 }}
                                            >
                                                <DeleteIcon fontSize="small" />
                                            </IconButton>
                                        </Box>
                                    ))}
                                </Stack>
                            )}
                        </Box>
                    </Stack>
                </DialogContent>

                <DialogActions sx={{ px: 3, pb: 3, pt: 1 }}>
                    <Button
                        onClick={() => !isLoading && setOpenEditDialog(false)}
                        disabled={isLoading}
                        sx={{ borderRadius: 2 }}
                    >
                        Cancel
                    </Button>
                    <Button
                        variant="contained"
                        onClick={handleUpdateChatProfile}
                        disabled={isLoading || !newChatProfileTitle.trim()}
                        sx={{
                            borderRadius: 2,
                            px: 3,
                        }}
                    >
                        {isLoading ? 'Saving...' : 'Save'}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Clean Delete Confirmation Dialog */}
            <Dialog
                open={openDeleteDialog}
                onClose={() => !isLoading && setOpenDeleteDialog(false)}
                maxWidth="xs"
                fullWidth
                PaperProps={{
                    sx: {
                        borderRadius: 3,
                        boxShadow: `0 10px 30px ${alpha(theme.palette.common.black, 0.15)}`,
                    }
                }}
            >
                <DialogTitle sx={{ pt: 3, pb: 1 }}>
                    <Typography variant="h6" fontWeight={600} color="error.main">
                        Delete Profile
                    </Typography>
                </DialogTitle>
                <DialogContent sx={{ py: 2, pt: 2.5 }}>
                    <Typography variant="body2" gutterBottom>
                        Are you sure you want to delete{' '}
                        <Typography component="span" fontWeight={600}>
                            "{currentChatProfile?.title}"
                        </Typography>
                        ?
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                        This action cannot be undone and will delete all associated documents.
                    </Typography>
                </DialogContent>
                <DialogActions sx={{ px: 3, pb: 3, pt: 1 }}>
                    <Button
                        onClick={() => !isLoading && setOpenDeleteDialog(false)}
                        disabled={isLoading}
                        sx={{ borderRadius: 2 }}
                    >
                        Cancel
                    </Button>
                    <Button
                        color="error"
                        variant="contained"
                        onClick={handleDeleteChatProfile}
                        disabled={isLoading}
                        sx={{
                            borderRadius: 2,
                            px: 3,
                        }}
                    >
                        {isLoading ? 'Deleting...' : 'Delete'}
                    </Button>
                </DialogActions>
            </Dialog>

            {/*  Snackbar */}
            <Snackbar
                open={snackbarOpen}
                autoHideDuration={6000}
                onClose={handleSnackbarClose}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
            >
                <Alert
                    onClose={handleSnackbarClose}
                    severity={snackbarSeverity}
                    variant="filled"
                    icon={snackbarSeverity === "success" ? <CheckCircleOutlineIcon /> : undefined}
                    sx={{
                        width: '100%',
                        borderRadius: 3,
                        boxShadow: `0 8px 32px ${alpha(theme.palette.common.black, 0.2)}`,
                    }}
                >
                    {snackbarMessage}
                </Alert>
            </Snackbar>
        </PageBodyWrapper>
    );
};