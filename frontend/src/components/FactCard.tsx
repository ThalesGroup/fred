import { useState } from "react";
import { Card, CardContent, CardHeader, Typography, Button, Drawer, IconButton, Paper, Box, Modal } from "@mui/material";
import CloseIcon from '@mui/icons-material/Close';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import { Fact } from "../slices/factsStructures";
import { getUserAvatar } from "../utils/avatar";
import { FactInputForm } from "../common/FactInputForm";

interface FactCardProps {
    fact: Fact;
    maxContentLength?: number;
    onEdit: (title: string, newContent: string) => void; // Updated type
    onDeleted?: (newTitle: string) => void;
}

export const FactCard: React.FC<FactCardProps> = ({ fact, maxContentLength = 200, onEdit, onDeleted }) => {
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [editModalOpen, setEditModalOpen] = useState(false); // State for Edit Modal
    const formattedDate = (() => {
        const date = new Date(fact.date);
        const day = date.getDate().toString().padStart(2, '0');
        const month = (date.getMonth() + 1).toString().padStart(2, '0'); // Months are 0-indexed
        const year = date.getFullYear();
        return `${day}.${month}.${year}`;
    })();

    // Truncate content for initial display
    const displayedContent = `${fact.content.slice(0, maxContentLength)}${fact.content.length > maxContentLength ? '...' : ''}`;

    const handleEditSubmit = (updatedFact: Fact) => {
        if (onEdit) {
            onEdit(updatedFact.title, updatedFact.content); // Pass updated fact back to the parent
        }
        setEditModalOpen(false); // Close the edit form
    };

    return (
        <>
            <Box
                sx={{
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                }}
            >
                <Card sx={{ maxWidth: 800, width: '100%', display: 'flex', flexDirection: 'column' }}>
                    <CardHeader
                        avatar={getUserAvatar(fact.title)}
                        title={fact.title}
                        subheader={
                            <>
                                <Typography variant="subtitle2" color="text.secondary">
                                    Submitted by: {fact.user}
                                </Typography>
                                <Typography variant="subtitle2" color="text.secondary">
                                    On: {formattedDate}
                                </Typography>
                            </>
                        }
                        action={
                            <Box>
                                <IconButton onClick={() => setEditModalOpen(true)} aria-label="edit">
                                    <EditIcon />
                                </IconButton>
                                <IconButton onClick={() => onDeleted && onDeleted(fact.title)} aria-label="delete">
                                    <DeleteIcon />
                                </IconButton>
                            </Box>
                        }
                    />
                    <CardContent sx={{ flexGrow: 1, pb: 2 }}>
                        <Typography p={2} variant="body1" color="text.primary" sx={{ fontStyle: 'italic' }}>
                            &quot;{displayedContent}&quot;
                        </Typography>
                        {fact.content.length > maxContentLength && (
                            <Button size="small" onClick={() => setDrawerOpen(true)}>
                                Show More
                            </Button>
                        )}
                    </CardContent>
                </Card>

                {/* Drawer for full content */}
                <Drawer anchor="right" open={drawerOpen} onClose={() => setDrawerOpen(false)}>
                    <Box sx={{ width: '50vw', p: 2 }}>
                        <Paper sx={{ p: 1, px: 2, width: "100%" }}>
                            <IconButton onClick={() => setDrawerOpen(false)} style={{ float: 'right' }}>
                                <CloseIcon />
                            </IconButton>
                            <Typography variant="h5" gutterBottom>
                                {fact.title}
                            </Typography>
                            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                                {formattedDate}
                            </Typography>
                            <Typography variant="body1" color="text.primary">
                                {fact.content}
                            </Typography>
                        </Paper>
                    </Box>
                </Drawer>

                {/* Modal for Edit Form */}
                <Modal open={editModalOpen} onClose={() => setEditModalOpen(false)}>
                    <Box
                        sx={{
                            position: 'absolute',
                            top: '50%',
                            left: '50%',
                            transform: 'translate(-50%, -50%)',
                            width: { xs: '90%', sm: 600 },
                            bgcolor: 'background.paper',
                            boxShadow: 24,
                            p: 4,
                            borderRadius: 2,
                        }}
                    >
                        <FactInputForm
                            isOpen={editModalOpen}
                            onClose={() => setEditModalOpen(false)}
                            onSubmit={handleEditSubmit}
                            initialValues={fact}
                        />
                    </Box>
                </Modal>
            </Box>
        </>
    );
};
