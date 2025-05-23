// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useState } from "react";
import { useTheme } from "@mui/material/styles";
import {
    Button,
    Card,
    Collapse,
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
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import DocumentViewer from "../documents/DocumentViewer.tsx";
import { ChatSource } from "../../slices/chatApiStructures.ts";
import MarkdownRenderer from "../markdown/MarkdownRenderer.tsx";
import { SourceCard } from "./SourceCard.tsx";
import { getDocumentIcon } from "../documents/DocumentIcon.tsx";

/**
 * Sources Component
 *
 * This component displays a section for document sources related to a chat interaction.
 *
 * Features:
 * - Collapsible source panel with preview of top 3 sources
 * - Modal popup to quickly preview a document summary
 * - Drawer panel to list and open all sources
 * - DocumentViewer integration to render full content of a selected markdown document
 *
 * Props:
 * - sources: List of ChatSource objects
 * - expandSources: Whether to start with sources expanded
 * - enableSources: Whether to display the sources section at all
 */
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

    // Local UI state
    const [openSources, setOpenSources] = useState<boolean>(expandSources);
    const [selectedSource, setSelectedSource] = useState<ChatSource | null>(null);
    const [drawerOpen, setDrawerOpen] = useState<boolean>(false);
    const [documentViewerOpen, setDocumentViewerOpen] = useState<boolean>(false);
    const [fullDocument, setFullDocument] = useState<any>(null);

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

    /**
     * When the user clicks on "Preview Full Document",
     * extract the basic metadata and open the full DocumentViewer.
     * The DocumentViewer will handle the rest (fetching, decoding, etc.)
     * @param source The source object containing document metadata
     * @param event The click event
     */
    const handleViewFullDocument = (source: ChatSource, event: React.MouseEvent) => {
        event.stopPropagation();
        setSelectedSource(null); // Close the Modal first
        setFullDocument({
            document_uid: source.document_uid,
            file_name: source.file_name,
            file_url: source.file_url,
            content: null,
        });
        setDocumentViewerOpen(true);
    };

    return (
        <>
            {/* Top-level button to expand/collapse source view */}
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
                                                loading={false}
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

            {/* Modal preview (quick summary) */}
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
                    height: '80vh',
                    display: 'flex',
                    flexDirection: 'column',
                    bgcolor: theme.palette.background.paper,
                    boxShadow: 24,
                    borderRadius: 2,
                    padding: 3,
                    boxSizing: 'border-box',
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
                            {selectedSource && getDocumentIcon(selectedSource.file_name)}
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

                    <Box sx={{
                        flexGrow: 1,
                        overflowY: 'auto',
                        minHeight: 0,
                        pr: 1,
                    }}>
                        <MarkdownRenderer
                            content={selectedSource?.content}
                            size="large"
                            enableEmojiSubstitution={true}
                        />
                    </Box>

                    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 3 }}>
                        <Button
                            onClick={(e) => selectedSource && handleViewFullDocument(selectedSource, e)}
                            variant="contained"
                            startIcon={<VisibilityIcon />}
                        >
                            Preview Full Document
                        </Button>
                    </Box>
                </Box>
            </Modal>

            {/* Drawer to list all sources */}
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
                        <IconButton onClick={handleCloseDrawer} aria-label="close">
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
                                        loading={false}
                                    />
                                </Grid2>
                            ))}
                        </Grid2>
                    </Box>
                </Box>
            </Drawer>

            {/* Drawer-based full markdown viewer */}
            <DocumentViewer
                document={fullDocument}
                open={documentViewerOpen}
                onClose={handleCloseDocumentViewer}
            />
        </>
    );
}
