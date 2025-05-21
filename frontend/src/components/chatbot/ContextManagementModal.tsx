import {
  Box,
  Typography,
  Modal,
  Button,
  IconButton,
  Alert,
  CircularProgress
} from "@mui/material";
import Grid2 from "@mui/material/Grid2";
import CloseIcon from '@mui/icons-material/Close';
import AddCircleIcon from '@mui/icons-material/AddCircle';
import DescriptionIcon from '@mui/icons-material/Description';
import { useTheme } from "@mui/material";
import ContextCard from "./ContexteCard";
import { useState, useEffect } from "react";
import ContextCardDialog from "./ContexteCardDialog";
import DeleteConfirmationDialog from "../DeleteConfirmationDialog";
import { useDeleteAgentContextMutation, useGetAgentContextsMutation, useSaveAgentContextMutation } from "../../slices/agentContextApi";


/**
 * Modal component for managing context cards of an agent using Minio backend
 */
const ContextManagementModal = ({
  open,
  onClose,
  agent,
  getAgentBadge
}) => {
  const theme = useTheme();
  const isDarkTheme = theme.palette.mode === "dark";

  const [contexts, setContexts] = useState([]);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
  const [cardDialogOpen, setCardDialogOpen] = useState(false);
  const [editingCard, setEditingCard] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [cardToDelete, setCardToDelete] = useState(null);

  // RTK Query hooks
  const [getAgentContexts, { isLoading: isLoadingGet }] = useGetAgentContextsMutation();
  const [saveAgentContext, { isLoading: isLoadingSave }] = useSaveAgentContextMutation();
  const [deleteAgentContext, { isLoading: isLoadingDelete }] = useDeleteAgentContextMutation();

  // Combine all loading states
  const isLoading = isLoadingGet || isLoadingSave || isLoadingDelete;

  useEffect(() => {
    if (open && agent) {
      loadContexts();
    }
  }, [open, agent]);

  const loadContexts = async () => {
    if (!agent) return;

    try {
      const response = await getAgentContexts(agent.name).unwrap();

      // Transform { id: { title, content } } in [{ id, title, content }]
      const entries = Object.entries(response.context || {}).map(
        ([id, data]) => ({ id, ...(data as { title?: string; content?: string }) })
      );

      setContexts(entries);
      setError(null);
    } catch (err) {
      console.error('Error loading contexts:', err);
      setError('Failed to load context. Please try again.');
    }
  };

  // Handle adding a new card
  const handleAddCard = () => {
    setEditingCard(null);
    setCardDialogOpen(true);
  };

  // Handle editing a card
  const handleEditCard = (card) => {
    setEditingCard(card);
    setCardDialogOpen(true);
  };

  // Handle deleting a card
  const handleDeleteCard = (card) => {
    setCardToDelete(card);
    setDeleteDialogOpen(true);
  };

  // Save context to backend
  const saveContext = async (cardData) => {
    if (!agent) return;

    try {
      const { title, content } = cardData;

      const response = await saveAgentContext({
        agentName: agent.name,
        context: { title, content }
      }).unwrap();

      setContexts([...contexts, response]);
      setSuccessMessage("New context card added successfully");

      setTimeout(() => setSuccessMessage(null), 3000);
      setCardDialogOpen(false);
    } catch (err) {
      console.error('Error saving context:', err);
      setError('Failed to save context card. Please try again.');
      setTimeout(() => setError(null), 5000);
    }
  };

  // Delete context from backend
  const deleteContext = async () => {
    if (!agent || !cardToDelete) return;

    try {
      await deleteAgentContext({
        agentName: agent.name,
        contextId: cardToDelete.id
      }).unwrap();

      // Update local state for immediate feedback
      setContexts(contexts.filter(c => c.id !== cardToDelete.id));
      setSuccessMessage("Context card deleted successfully");

      // Clear success message after 3 seconds
      setTimeout(() => setSuccessMessage(null), 3000);
      setDeleteDialogOpen(false);
      setCardToDelete(null);
    } catch (err) {
      console.error('Error deleting context:', err);
      setError('Failed to delete context card. Please try again.');
      setTimeout(() => setError(null), 5000);
    }
  };

  if (!agent) return null;

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        aria-labelledby="agent-context-modal"
        aria-describedby="manage-agent-context"
      >
        <Box sx={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: { xs: '95%', sm: '85%', md: '75%', lg: '65%' },
          maxHeight: '90vh',
          bgcolor: 'background.paper',
          boxShadow: 24,
          p: 4,
          borderRadius: 2,
          overflow: 'auto'
        }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <Box sx={{ mr: 1.5 }}>
                {getAgentBadge(agent.nickname)}
              </Box>
              <Box>
                <Typography variant="h5" component="h2">
                  {agent.nickname} Context
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Add context information to enhance this agent's knowledge and capabilities
                </Typography>
              </Box>
            </Box>

            <IconButton
              aria-label="close"
              onClick={onClose}
              sx={{ color: 'text.secondary' }}
            >
              <CloseIcon />
            </IconButton>
          </Box>

          {error && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          {successMessage && (
            <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccessMessage(null)}>
              {successMessage}
            </Alert>
          )}

          <Box sx={{ mb: 3 }}>
            <Button
              variant="contained"
              color="primary"
              startIcon={<AddCircleIcon />}
              onClick={handleAddCard}
              sx={{ borderRadius: 2 }}
              disabled={isLoading}
            >
              Add Context
            </Button>
          </Box>

          {isLoading && contexts.length === 0 ? (
            <Box sx={{
              py: 6,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: '200px'
            }}>
              <CircularProgress sx={{ mb: 2 }} />
              <Typography variant="body2" color="text.secondary">
                Loading context...
              </Typography>
            </Box>
          ) : (
            <Grid2 container spacing={2}>
              {contexts.length > 0 ? (
                contexts.map(card => (
                  <Grid2 size={{ xs: 12, sm: 6, md: 4 }} key={card.id}>
                    <ContextCard
                      card={card}
                      onEdit={() => handleEditCard(card)}
                      onDelete={() => handleDeleteCard(card)}
                    />
                  </Grid2>
                ))
              ) : (
                <Grid2 size={{ xs: 12 }}>
                  <Box sx={{
                    py: 6,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    backgroundColor: isDarkTheme ? theme.palette.chart.alterningBgColor1 : theme.palette.chart.alterningBgColor2,
                    borderRadius: 2
                  }}>
                    <DescriptionIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="h6" color="text.secondary">
                      No context cards yet
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      Add context information to enhance this agent's knowledge
                    </Typography>
                    <Button
                      variant="outlined"
                      startIcon={<AddCircleIcon />}
                      onClick={handleAddCard}
                      disabled={isLoading}
                    >
                      Add First Card
                    </Button>
                  </Box>
                </Grid2>
              )}
            </Grid2>
          )}
        </Box>
      </Modal>

      {/* Add/Edit Context Card Dialog */}
      <ContextCardDialog
        open={cardDialogOpen}
        onClose={() => setCardDialogOpen(false)}
        card={editingCard}
        onSave={saveContext}
      />

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        card={cardToDelete}
        onConfirm={deleteContext}
      />
    </>
  );
};

export default ContextManagementModal;