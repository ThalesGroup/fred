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
