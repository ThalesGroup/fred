import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  TextField,
  Button,
  InputAdornment,
  CircularProgress
} from "@mui/material";
import DescriptionIcon from '@mui/icons-material/Description';
import { useState, useEffect } from "react";

/**
 * Dialog component for adding or editing context
 *
 * @param {Object} props - Component props
 * @param {boolean} props.open - Whether the dialog is open
 * @param {Function} props.onClose - Function to call to close the dialog
 * @param {Object|null} props.card - Card to edit, or null for adding a new card
 * @param {Function} props.onSave - Callback for successful save
 */
const ContextCardDialog = ({ open, onClose, card, onSave }) => {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  
  // Set form values when card changes (for editing)
  useEffect(() => {
    if (card) {
      setTitle(card.title);
      setContent(card.content);
    } else {
      setTitle("");
      setContent("");
    }
  }, [card, open]);
  
  const handleSave = async () => {
    if (!title.trim() || !content.trim()) return;
    
    setIsLoading(true);
    
    try {
      const cardData = {
        id: card?.id,
        title: title.trim(),
        content: content.trim()
      };
      
      await onSave(cardData);
      
      // Reset form
      setTitle("");
      setContent("");
      onClose();
    } catch (error) {
      console.error('Error saving context card:', error);
      // Error handling could be improved here
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleClose = () => {
    // Reset form
    setTitle("");
    setContent("");
    onClose();
  };
  
  return (
    <Dialog
      open={open}
      onClose={handleClose}
      fullWidth
      maxWidth="sm"
    >
      <DialogTitle>
        {card ? "Edit Context" : "Add New Context"}
      </DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          Context help the agent understand specific domain knowledge for better responses.
        </DialogContentText>
        <TextField
          autoFocus
          margin="dense"
          id="card-title"
          label="Title"
          fullWidth
          variant="outlined"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          sx={{ mb: 2 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <DescriptionIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
          disabled={isLoading}
        />
        <TextField
          margin="dense"
          id="card-content"
          label="Content"
          fullWidth
          multiline
          rows={6}
          variant="outlined"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Enter the context information that will be provided to the agent..."
          disabled={isLoading}
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3 }}>
        <Button
          onClick={handleClose}
          color="inherit"
          disabled={isLoading}
        >
          Cancel
        </Button>
        <Button
          onClick={handleSave}
          variant="contained"
          disabled={isLoading || !title.trim() || !content.trim()}
          startIcon={isLoading ? <CircularProgress size={20} /> : null}
        >
          {isLoading ? 'Saving...' : card ? "Update" : "Add"}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ContextCardDialog;