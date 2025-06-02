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

import React, { useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Rating,
  Box,
  Typography,
  useTheme,
} from "@mui/material";

interface FeedbackDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (rating: number, comment?: string) => void;
}

export const FeedbackDialog: React.FC<FeedbackDialogProps> = ({ open, onClose, onSubmit }) => {
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const theme = useTheme();

  const handleSubmit = () => {
    if (rating !== null) {
      onSubmit(rating, comment?.trim() || undefined);
      setRating(null);
      setComment("");
      onClose();
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: {
          borderRadius: 3,
          p: 2,
          backgroundColor: theme.palette.background.default,
          width: "600px", // Forcera une largeur confortable
        },
      }}
    >
      <DialogTitle sx={{ pb: 1 }}>How was this response?</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
          <Typography sx={{ mr: 2 }}>Your rating</Typography>
          <Rating name="feedback-rating" value={rating} onChange={(_, newValue) => setRating(newValue)} size="large" />
        </Box>
        <TextField
          label="Leave a comment (optional)"
          multiline
          rows={4}
          fullWidth
          variant="outlined"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Tell us what you liked or what could be improved..."
        />
      </DialogContent>
      <DialogActions sx={{ justifyContent: "space-between", px: 3 }}>
        <Button onClick={onClose} color="secondary" variant="text">
          Cancel
        </Button>
        <Button onClick={handleSubmit} disabled={rating === null} variant="contained">
          Submit
        </Button>
      </DialogActions>
    </Dialog>
  );
};
