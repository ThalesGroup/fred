import React, { useState } from 'react';
import { Typography, Paper, Button, TextField, Box, Select, MenuItem, FormControl, InputLabel } from "@mui/material";
import { Fact, FactType } from '../slices/factsStructures';

interface FactInputFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (fact: Fact) => void;
  initialValues?: Fact;
  existingTitles?: string[];
}

export const FactInputForm: React.FC<FactInputFormProps> = ({ isOpen, onClose, onSubmit, initialValues, existingTitles }) => {
  const [content, setContent] = useState(initialValues?.content || '');
  const [title, setTitle] = useState(initialValues?.title || '');
  const [type, setType] = useState<FactType>(initialValues?.type || FactType.DOMAIN);
  const currentUser = initialValues?.user || 'current_user';
  const initialDate = initialValues?.date || new Date().toISOString();

  // Validation states
  const [titleError, setTitleError] = useState(false);
  const [titleErrorMessage, setTitleErrorMessage] = useState('');

  const handleTitleChange = (value: string) => {
    setTitle(value);

    // Check for duplicate title
    if (existingTitles?.includes(value.trim()) && !initialValues) {
      setTitleError(true);
      setTitleErrorMessage('A fact with this title already exists.');
    } else {
      setTitleError(false);
      setTitleErrorMessage('');
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();

    // Final validation before submission
    if (!title.trim() || titleError) {
      setTitleError(true);
      setTitleErrorMessage(titleError ? titleErrorMessage : 'Title is required.');
      return;
    }

    if (!content.trim()) {
      return; // Content validation can be expanded similarly
    }

    const newFact: Fact = {
      user: currentUser,
      date: initialDate,
      content: content,
      title: title,
      type: type as FactType,
    };

    onSubmit(newFact);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <Paper elevation={3} sx={{ p: 3, mt: 2 }}>
      <form onSubmit={handleSubmit}>
        <Typography variant="h6" gutterBottom>
          {initialValues ? 'Edit Fact' : 'New Fact'}
        </Typography>

        <TextField
          label="Title"
          variant="outlined"
          fullWidth
          value={title}
          onChange={(e) => handleTitleChange(e.target.value)}
          sx={{ mt: 2 }}
          error={titleError}
          helperText={titleErrorMessage || (titleError ? 'Title is required.' : '')}
          disabled={!!initialValues} // Disable title in edit mode
        />

        <FormControl fullWidth sx={{ mt: 2 }}>
          <InputLabel>Type</InputLabel>
          <Select
            value={type}
            onChange={(e) => setType(e.target.value as FactType)}
            label="Type"
          >
            <MenuItem value={FactType.DOMAIN}>Domain</MenuItem>
            <MenuItem value={FactType.REQUIREMENT}>Requirement</MenuItem>
            <MenuItem value={FactType.COST}>Cost</MenuItem>
            <MenuItem value={FactType.COMPLIANCE}>Compliance</MenuItem>
            <MenuItem value={FactType.SECURITY}>Security</MenuItem>
          </Select>
        </FormControl>

        <TextField
          label="Content"
          variant="outlined"
          fullWidth
          multiline
          rows={4}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          sx={{ mt: 2 }}
        />

        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
          <Button type="submit" variant="contained" color="primary">
            Save
          </Button>
          <Button onClick={onClose} variant="outlined" color="secondary" sx={{ ml: 2 }}>
            Cancel
          </Button>
        </Box>
      </form>
    </Paper>
  );
};
