import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Button
} from '@mui/material';

/**
 * DeleteConfirmationDialog component for confirming deletion of context cards
 * 
 * @param {Object} props - Component props
 * @param {boolean} props.open - Whether the dialog is open
 * @param {Function} props.onClose - Function to call to close the dialog
 * @param {Object|null} props.card - Card to delete
 * @param {Object} props.agent - Agent that owns the card
 * @param {Function} props.onSuccess - Callback for successful deletion
 */
const DeleteConfirmationDialog = ({ open, onClose, card, onConfirm }) => {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      aria-labelledby="delete-dialog-title"
      aria-describedby="delete-dialog-description"
    >
      <DialogTitle id="delete-dialog-title">
        Delete Context Card
      </DialogTitle>
      <DialogContent>
        <DialogContentText id="delete-dialog-description">
          Are you sure you want to delete the context card "{card?.title}"?
          This action cannot be undone.
        </DialogContentText>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3 }}>
        <Button
          onClick={onClose}
          color="inherit"
        >
          Cancel
        </Button>
        <Button
          onClick={() => onConfirm()}
          variant="contained"
          color="error"
          autoFocus
        >
          Delete
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default DeleteConfirmationDialog;