import { useState } from "react";
import { useTheme } from "@mui/material/styles";
import {
    Button,
    Card,
    CardContent,
    Collapse,
    Tooltip,
    Typography,
    Modal,
    Box,
    IconButton,
    Divider,
    Drawer,
    Backdrop,
    Chip,
    Paper
} from "@mui/material";
import Grid2 from "@mui/material/Grid2";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import CloseIcon from "@mui/icons-material/Close";
import VisibilityIcon from "@mui/icons-material/Visibility";
import LibraryBooksIcon from '@mui/icons-material/LibraryBooks';
import PersonOutlineIcon from '@mui/icons-material/PersonOutline';
import HistoryIcon from '@mui/icons-material/History';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { ExcelIcon, PdfIcon, WordIcon } from "../../utils/icons.tsx";
import DocumentIcon from '@mui/icons-material/Description';
import dayjs from "dayjs";
import DocumentViewer from "./DocumentViewer";
import { useGetFullDocumentMutation } from "../../slices/documentApi.tsx";
import { ChatSource } from "../../slices/chatApiStructures.ts";
import MarkdownRenderer from "../../common/MarkdownRenderer.tsx";

const getIcon = (fileName) => {
    if (!fileName) return <DocumentIcon />;
    const fileType = fileName.split('.').pop()?.toLowerCase();
    switch (fileType) {
        case 'pdf':
            return <PdfIcon />;
        case 'docx':
        case 'doc':
            return <WordIcon />;
        case 'xlsx':
        case 'xls':
            return <ExcelIcon />;
        default:
            return <DocumentIcon />;
    }
};

// Card component for displaying source information
const SourceCard = ({ source, onCardClick, onViewDocument, loading }) => {
    const theme = useTheme();

    const formatDate = (dateString) => {
        return dateString ? dayjs(dateString).format('DD/MM/YYYY') : 'N/A';
    };

    console.log("Source", source);
    return (
        <Card
            sx={{
                width: 220,
                height: 180,
                cursor: "pointer",
                transition: "transform 0.2s, box-shadow 0.2s",
                "&:hover": {
                    transform: "translateY(-4px)",
                    boxShadow: 3
                },
                display: 'flex',
                flexDirection: 'column',
                position: 'relative',
                overflow: 'visible'
            }}
            onClick={onCardClick}
        >
            {/* Icon on top left corner */}
            <Box
                sx={{
                    position: 'absolute',
                    top: -10,
                    left: 10,
                    bgcolor: theme.palette.background.paper,
                    borderRadius: '50%',
                    p: 1,
                    boxShadow: 1,
                    display: 'flex',
                    zIndex: 1
                }}
            >
                {getIcon(source.file_name)}
            </Box>

            <CardContent sx={{ p: 2, pt: 3, flex: 1, display: 'flex', flexDirection: 'column' }}>
                {/* Document name */}
                <Typography
                    variant="subtitle1"
                    sx={{
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        fontWeight: 'medium',
                        mb: 1,
                        mt: 1
                    }}
                >
                    {source.file_name}
                </Typography>

                <Divider sx={{ my: 1 }} />

                {/* Informations sous le titre */}
                <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                    {/* Titre du document */}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <InfoOutlinedIcon fontSize="small" color="action" sx={{ fontSize: '0.9rem' }} />
                        <Typography
                            variant="body2"
                            sx={{
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                display: '-webkit-box',
                                WebkitLineClamp: 1,
                                WebkitBoxOrient: 'vertical'
                            }}
                        >
                            {source.title ?? "Title unavailable"}
                        </Typography>
                    </Box>

                    {/* Date de modification */}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <HistoryIcon fontSize="small" color="action" sx={{ fontSize: '0.9rem' }} />
                        <Typography variant="body2" color="text.secondary">
                            {formatDate(source.modified)}
                        </Typography>
                    </Box>

                    {/* Nom de l'agent */}
                    {source.agent_name && (
                        <Chip
                            icon={<PersonOutlineIcon sx={{ fontSize: '0.9rem' }} />}
                            label={source.agent_name}
                            size="small"
                            sx={{
                                height: 24,
                                '& .MuiChip-label': { px: 1, fontSize: '0.75rem' },
                                alignSelf: 'flex-start',
                                mt: 0.5
                            }}
                        />
                    )}
                </Box>

                <Tooltip title="Preview the document">
                    <IconButton
                        onClick={onViewDocument}
                        sx={{
                            position: 'absolute',
                            bottom: 8,
                            right: 8,
                            padding: '8px',
                            bgcolor: theme.palette.background.paper,
                            boxShadow: 1,
                            '&:hover': {
                                bgcolor: theme.palette.primary.light,
                                color: theme.palette.primary.contrastText
                            },
                            transition: 'all 0.2s'
                        }}
                        disabled={loading}
                        size="small"
                    >
                        <VisibilityIcon fontSize="small" />
                    </IconButton>
                </Tooltip>
            </CardContent>
        </Card>
    );
};

export default function Sources({
    sources,
    expandSources = false,
    enableSources = false,
}: {
    sources: ChatSource[],
    expandSources: boolean,
    enableSources: boolean
}) {
    const theme = useTheme();
    const [openSources, setOpenSources] = useState<boolean>(expandSources);
    const [selectedSource, setSelectedSource] = useState<ChatSource | null>(null);
    const [drawerOpen, setDrawerOpen] = useState<boolean>(false);
    const [documentViewerOpen, setDocumentViewerOpen] = useState<boolean>(false);
    const [fullDocument, setFullDocument] = useState<any>(null);
    const [loading, setLoading] = useState<boolean>(false);
    const [getDocument] = useGetFullDocumentMutation();

    const handleOpenModal = (source: ChatSource) => {
        setSelectedSource(source);
    };

    const handleCloseModal = () => {
        setSelectedSource(null);
    };

    const handleOpenDrawer = () => {
        setDrawerOpen(true);
    };

    const handleCloseDrawer = () => {
        setDrawerOpen(false);
    };

    const handleCloseDocumentViewer = () => {
        setDocumentViewerOpen(false);
        setFullDocument(null);
    };

    // Fetch the full document when the user clicks on "View Full Document"
    // and open the DocumentViewer component
    const handleViewFullDocument = async (source: ChatSource, event: React.MouseEvent) => {
        event.stopPropagation();
        setLoading(true);
        setSelectedSource(null); // ❗ Close the modal before drawer opens

        try {
            const response = await getDocument({ document_uid: source.document_uid }).unwrap();

            if (response.documents && response.documents[0]) {
                const doc = response.documents[0];
                setFullDocument(doc); setTimeout(() => {
                    setDocumentViewerOpen(true);
                }, 100);

            } else {
                console.error("Document not found in response:", response);
            }
        } catch (error) {
            console.error("Error fetching document:", error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <>
            <Grid2 container marginBottom={1}>
                {enableSources && sources.length > 0 &&
                    <Grid2 paddingTop={2}>
                        <Button
                            onClick={() => setOpenSources(!openSources)}
                            sx={{
                                textTransform: 'none',
                                display: 'flex',
                                alignItems: 'center',
                                padding: '4px 8px',
                                borderRadius: '20px',
                                bgcolor: openSources ? theme.palette.action.hover : 'transparent',
                                '&:hover': {
                                    bgcolor: theme.palette.action.selected
                                }
                            }}
                        >
                            <LibraryBooksIcon sx={{ mr: 1, color: theme.palette.primary.main }} />
                            <Typography variant="body2" fontWeight="medium">
                                Sources ({sources.length})
                            </Typography>
                            <ExpandMoreIcon
                                sx={{
                                    ml: 0.5,
                                    transform: openSources ? 'rotate(180deg)' : 'rotate(0deg)',
                                    transition: 'transform 0.3s',
                                    color: theme.palette.text.secondary,
                                }}
                                fontSize="small"
                            />
                        </Button>

                        <Collapse in={openSources} timeout={300} unmountOnExit>
                            <Paper
                                elevation={0}
                                sx={{
                                    mt: 1.5,
                                    p: 2,
                                    bgcolor: theme.palette.sidebar.background,
                                    borderRadius: 2
                                }}
                            >
                                <Grid2 container spacing={2}>
                                    {sources.slice(0, 3).map((source, index) => (
                                        <Grid2 key={index}>
                                            <SourceCard
                                                source={source}
                                                onCardClick={() => handleOpenModal(source)}
                                                onViewDocument={(e) => handleViewFullDocument(source, e)}
                                                loading={loading}
                                            />
                                        </Grid2>
                                    ))}

                                    {sources.length > 3 && (
                                        <Grid2>
                                            <Card
                                                sx={{
                                                    width: 80,
                                                    height: 180,
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    justifyContent: 'center',
                                                    cursor: "pointer",
                                                    transition: "transform 0.2s, box-shadow 0.2s",
                                                    "&:hover": {
                                                        transform: "translateY(-4px)",
                                                        boxShadow: 3
                                                    }
                                                }}
                                                onClick={handleOpenDrawer}
                                            >
                                                <Box sx={{ textAlign: 'center' }}>
                                                    <Typography variant="h4" color="primary.main">+</Typography>
                                                    <Typography variant="caption" sx={{ display: 'block', mt: 1 }}>
                                                        {sources.length - 3} more
                                                    </Typography>
                                                </Box>
                                            </Card>
                                        </Grid2>
                                    )}
                                </Grid2>
                            </Paper>
                        </Collapse>
                    </Grid2>
                }
            </Grid2>

            {/* Modal pour l'aperçu du document */}
            <Modal
                open={!!selectedSource}
                onClose={handleCloseModal}
                aria-labelledby="modal-title"
                aria-describedby="modal-description"
            >
                <Box sx={{
                    position: 'absolute',
                    top: '50%',
                    left: '50%',
                    transform: 'translate(-50%, -50%)',
                    width: '50%',
                    maxHeight: '80vh',
                    bgcolor: theme.palette.background.paper,
                    boxShadow: 24,
                    p: 3,
                    borderRadius: 2,
                    overflow: 'auto',
                }}>
                    <IconButton
                        aria-label="close"
                        onClick={handleCloseModal}
                        sx={{
                            position: 'absolute',
                            right: 8,
                            top: 8,
                            color: theme.palette.grey[500],
                        }}
                    >
                        <CloseIcon />
                    </IconButton>

                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <Box sx={{ mr: 2, p: 1, bgcolor: theme.palette.background.default, borderRadius: '50%' }}>
                            {selectedSource && getIcon(selectedSource.file_name)}
                        </Box>
                        <Box>
                            <Typography id="modal-title" variant="h6" component="h2">
                                {selectedSource?.file_name}
                            </Typography>
                            {selectedSource?.agent_name && (
                                <Chip
                                    size="small"
                                    icon={<PersonOutlineIcon />}
                                    label={selectedSource.agent_name}
                                    sx={{ mt: 0.5 }}
                                />
                            )}
                        </Box>
                    </Box>

                    <Divider sx={{ my: 2 }} />

                    {selectedSource?.title && (
                        <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                            <InfoOutlinedIcon color="action" />
                            <Typography variant="subtitle1" fontWeight="medium">
                                {selectedSource.title}
                            </Typography>
                        </Box>
                    )}

                    <Box sx={{ maxHeight: '60vh', overflowY: 'auto', pr: 1 }}>
                        <MarkdownRenderer content={selectedSource?.content} />
                        {/* <Typography variant="body1" component="div">
                            {selectedSource?.content.split('\n\n').map((paragraph, index) => (
                                <p key={index}>{paragraph}</p>
                            ))}
                        </Typography> */}
                    </Box>

                    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 3 }}>
                        <Button
                            onClick={(e) => selectedSource && handleViewFullDocument(selectedSource, e)}
                            variant="contained"
                            startIcon={<VisibilityIcon />}
                        >
                            View Full Document
                        </Button>
                    </Box>
                </Box>
            </Modal>

            {/* Drawer pour tous les documents */}
            <Drawer
                anchor="right"
                open={drawerOpen}
                onClose={handleCloseDrawer}
                ModalProps={{
                    BackdropComponent: Backdrop,
                    BackdropProps: {
                        open: drawerOpen,
                        onClick: handleCloseDrawer,
                    }
                }}
            >
                <Box sx={{ width: 760, p: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <LibraryBooksIcon color="primary" />
                            <Typography variant="h6">
                                All Sources ({sources.length})
                            </Typography>
                        </Box>

                        <IconButton
                            onClick={handleCloseDrawer}
                            aria-label="close"
                        >
                            <CloseIcon />
                        </IconButton>
                    </Box>

                    <Divider sx={{ mb: 3 }} />

                    <Box sx={{ flex: 1, overflow: 'auto' }}>
                        <Grid2 container spacing={2}>
                            {sources.map((source, index) => (
                                <Grid2 key={index}>
                                    <SourceCard
                                        source={source}
                                        onCardClick={() => handleOpenModal(source)}
                                        onViewDocument={(e) => handleViewFullDocument(source, e)}
                                        loading={loading}
                                    />
                                </Grid2>
                            ))}
                        </Grid2>
                    </Box>
                </Box>
            </Drawer>

            {/* Utilisation du nouveau composant DocumentViewer */}
            <DocumentViewer
                document={fullDocument}
                open={documentViewerOpen}
                onClose={handleCloseDocumentViewer}
                loading={loading}
            />
        </>
    );
}