import React, { useState } from 'react';
import { 
  Button, 
  Dialog, 
  DialogActions, 
  DialogContent, 
  DialogTitle, 
  TextField, 
  Rating 
} from '@mui/material';

interface FeedbackDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (rating: number, reason: string) => void;
  feedbackType: 'up' | 'down';
}

export const FeedbackDialog: React.FC<FeedbackDialogProps> = ({ open, onClose, onSubmit, feedbackType }) => {
  const [rating, setRating] = useState<number | null>(null);
  const [reason, setReason] = useState('');

  const handleSubmit = () => {
    if (rating !== null) {
      onSubmit(rating, reason);
      // Reset local state after submission if needed
      setRating(null);
      setReason('');
    }
  };

  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>
        {feedbackType === 'up' ? 'Positive Feedback' : 'Negative Feedback'}
      </DialogTitle>
      <DialogContent>
        <Rating
          name="feedback-rating"
          value={rating}
          onChange={(_, newValue) => setRating(newValue)}
          max={5}
        />
        <TextField
          autoFocus
          margin="dense"
          label="Reason"
          type="text"
          fullWidth
          variant="standard"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Tell us why..."
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleSubmit} disabled={rating === null}>
          Submit
        </Button>
      </DialogActions>
    </Dialog>
  );
};
