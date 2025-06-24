// components/profile/Workspaces.tsx
import { useEffect, useState } from "react";
import {
    Box,
    Typography,
    Container,
    TextField,
    Paper,
    InputAdornment,
    Grid2,
    Fab,
    Drawer,
    IconButton
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import CloseIcon from "@mui/icons-material/Close"
import { TopBar } from "../common/TopBar";
import { useToast } from "../components/ToastProvider";
import { useGetKnowledgeContextsMutation, useDeleteKnowledgeContextMutation, useUpdateKnowledgeContextMutation } from "../slices/knowledgeContextApi";
import { PageBodyWrapper } from "../common/PageBodyWrapper";
import { KnowledgeContext, KnowledgeContextEditDialog } from "../components/knowledgeContext/KnowledgeContextEditDialog";
import { KnowledgeContextItem } from "../components/knowledgeContext/KnowledgeContextItem";
import { KnowledgeContextCreateDialog } from "../components/knowledgeContext/KnowledgeContextCreateDialog";


const mockWorkspaces: KnowledgeContext[] = [{
    id: "1",
    title: "Client – Vinci Construction",
    description: "Ce workspace contient tous les documents relatifs au projet A22.",
    tokens: 9800,
    documents: [
        {
            id: "doc-1",
            document_name: "contrat_final.pdf",
            document_type: "pdf",
            description: "Version finale du contrat signée avec le client.fgeyfdlveyzfvudzqp bf evozge ziu tgra_ègrègoz_èargtoèa ent.fgeyfdlveyzfvudzqp bf evozge ziu tgraent.fgeyfdlveyzfvudzqp bf evozge ziu tgraent.fgeyfdlveyzfvudzqp bf evozge ziu tgraent.fgeyfdlveyzfvudzqp bf evozge ziu tgraent.fgeyfdlveyzfvudzqp bf evozge ziu tgraent.fgeyfdlveyzfvudzqp bf evozge ziu tgra gy agio rphgh_a çpay _çtapy",
        },
        {
            id: "doc-2",
            document_name: "plan_technique_v2.docx",
            document_type: "docx",
            description: "Plans techniques mis à jour suite aux remarques du bureau d'études.",
        },
        {
            id: "doc-3",
            document_name: "budget.xlsx",
            document_type: "xlsx",
            description: "Projection budgétaire validée pour le T3.",
        },
        {
            id: "doc-4",
            document_name: "meeting_notes_mars.pptx",
            document_type: "pptx",
            description: "Présentation récapitulative du comité de pilotage de mars.",
        },
        {
            id: "doc-5",
            document_name: "annexes.pdf",
            document_type: "pdf",
            description: "Documents annexes et références réglementaires.",
        }
    ]
}];


export const WorkspacePage = () => {
    const [workspaces, setWorkspaces] = useState([]);
    const [search, setSearch] = useState("");
    const [getWorkspaces] = useGetKnowledgeContextsMutation();
    const [deleteWorkspace] = useDeleteKnowledgeContextMutation();
    const [updateWorkspace] = useUpdateKnowledgeContextMutation();
    const [openDescription, setOpenDescription] = useState<KnowledgeContext | null>(null);

    const [openDialog, setOpenDialog] = useState(false);
    const [openEditDialog, setOpenEditDialog] = useState(false);
    const [currentWorkspace, setCurrentWorkspace] = useState<KnowledgeContext>()
    const { showError } = useToast();

    useEffect(() => {
        fetchWorkspaces();
    }, []);

    const fetchWorkspaces = async () => {
        try {
            const response = await getWorkspaces().unwrap();
            setWorkspaces(response);
        } catch (e) {
            console.error("Failed to fetch workspaces", e);
        }
    };

    // Edit workspace
    const handleOpenEditDialog = (workspace: any) => {
        setCurrentWorkspace(workspace);
        setOpenEditDialog(true);
    };


    const handleSaveWorkspace = async ({
        title,
        description,
        files,
    }: {
        title: string;
        description: string;
        files: File[];
    }) => {
        try {
            await updateWorkspace({
                knowledgeContext_id: currentWorkspace.id,
                title,
                description,
                files
            }).unwrap();

            setOpenEditDialog(false);
            setCurrentWorkspace(null);

            await fetchWorkspaces();
        } catch (error: any) {
            showError({
                summary: "Update failed",
                detail: `Could not update workspace: ${error?.data?.detail || error.message}`,
            });

            await handleReloadProfile();
        }
    };


    const handleDelete = async (id: string) => {
        try {
            await deleteWorkspace({ knowledgeContext_id: id }).unwrap();
            setWorkspaces((prev) => prev.filter((p) => p.id !== id));
        } catch (e) {
            showError({
                summary: "Delete failed",
                detail: `Could not delete workspace: ${e?.data?.detail || e.message}`,
            });
        }
    };

    const filteredWorkspaces = workspaces.filter((workspace) =>
        workspace.title.toLowerCase().includes(search.toLowerCase())
    );

    const handleReloadProfile = async () => {
        try {
            const response = await getWorkspaces().unwrap();
            setWorkspaces(response);

            if (currentWorkspace) {
                const updated = response.find((p) => p.id === currentWorkspace.id);
                if (updated) {
                    setCurrentWorkspace(updated);
                }
            }
        } catch (e) {
            showError({
                summary: "Reload failed",
                detail: `Could not reload workdpace: ${e?.data?.detail || e.message}`,
            });
        }
    };

    return (
        <PageBodyWrapper>
            <TopBar
                title="Workspaces"
                description="Access your workspaces"
            >
                <Grid2
                    sx={{
                        display: "flex",
                        justifyContent: "flex-end",
                        mt: { xs: 1, md: 0 },
                    }}
                >
                </Grid2>
            </TopBar>
            <Container maxWidth="xl" sx={{ pb: 10, justifyContent: "center" }}>
                <Box mb={3}>
                    <TextField
                        fullWidth
                        placeholder="Search workspaces..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        slotProps={{
                            input: {
                                startAdornment: (
                                    <InputAdornment position="start">
                                        <SearchIcon color="action" />
                                    </InputAdornment>
                                ),
                            },
                        }}
                    />
                </Box>

                <Grid2 container spacing={3} alignItems="stretch">
                    {mockWorkspaces.map((w) => (
                        <Grid2 size={{ xs: 12 }} key={w.id} display="flex">
                            <KnowledgeContextItem
                                onEdit={handleOpenEditDialog}
                                onDelete={handleDelete}
                                onViewDescription={setOpenDescription}
                                allowDocuments
                                allowDocumentDescription
                                id={w.id}
                                title={w.title}
                                description={w.description}
                                documents={w.documents} 
                                />
                        </Grid2>
                    ))}
                </Grid2>

                {filteredWorkspaces.length === 0 && (
                    <Paper elevation={2} sx={{ p: 4, mt: 3, borderRadius: 2, textAlign: "center" }}>
                        <Typography variant="body1">No workspaces found.</Typography>
                    </Paper>
                )}

                <Fab
                    color="primary"
                    aria-label="add"
                    sx={{ position: "fixed", bottom: 32, right: 32, zIndex: 10 }}
                    onClick={() => setOpenDialog(true)}
                >
                    <AddIcon />
                </Fab>

                <KnowledgeContextCreateDialog
                    open={openDialog}
                    onClose={() => setOpenDialog(false)}
                    onCreated={fetchWorkspaces}
                />

                <KnowledgeContextEditDialog
                    open={openEditDialog}
                    onClose={() => setOpenEditDialog(false)}
                    onSave={handleSaveWorkspace}
                    context={currentWorkspace}
                    onReloadContext={handleReloadProfile}
                />
                <Drawer
                    anchor="right"
                    open={Boolean(openDescription)}
                    onClose={() => setOpenDescription(null)}
                    PaperProps={{
                        sx: { width: { xs: "100%", sm: 500 }, p: 3 },
                    }}
                >
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                        <Typography variant="h6">
                            {openDescription?.title || "Profile description"}
                        </Typography>
                        <IconButton onClick={() => setOpenDescription(null)}>
                            <CloseIcon />
                        </IconButton>
                    </Box>

                    <Box
                        sx={{
                            fontFamily: "monospace",
                            whiteSpace: "pre-wrap",
                            lineHeight: 1.6,
                            overflowY: "auto",
                            color: "text.primary",
                        }}
                    >
                        {openDescription?.description || "No description provided."}
                    </Box>
                </Drawer>
            </Container>
        </PageBodyWrapper>

    );
};
