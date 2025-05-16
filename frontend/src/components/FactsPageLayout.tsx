import React from 'react';
import { Button, Box, Modal, Typography, Grid2 } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import { FactCard } from '../components/FactCard';
import { FactInputForm } from '../common/FactInputForm';
import { Fact, FactList } from '../slices/factsStructures';

interface FactsPagesLayoutProps {
  title: string;
  factList: FactList;
  onSubmit: (newFact: Fact) => void;
  onEdit: (title: string, newContent: string) => void;
  onDelete: (title: string) => void;
  showForm: boolean;
  toggleForm: () => void;
}

export const FactsPageLayout: React.FC<FactsPagesLayoutProps> = ({
  title,
  factList,
  onSubmit,
  onEdit,
  onDelete,
  showForm,
  toggleForm,
}) => (
  <Box p={6}>
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        mb: 2,
      }}
    >
      <Typography variant="h5" align="center" gutterBottom>
        {title}
      </Typography>
      <Button
        variant="outlined"
        onClick={toggleForm}
        sx={{
          backgroundColor: 'background.paper',
          color: 'text.primary',
          borderRadius: '50%',
          minWidth: '40px',
          width: '40px',
          height: '40px',
          '&:hover': { backgroundColor: 'primary.light' },
        }}
      >
        {showForm ? <CloseIcon /> : <AddIcon />}
      </Button>
    </Box>

    <Grid2 p={6} container spacing={2} justifyContent="center" alignItems="center">
      {factList.facts.map((fact, index) => (
        <Grid2 size={{ xs: 12, sm: 12, md: 12 }} key={index}>
          <FactCard
            fact={fact}
            onDeleted={(title) => onDelete(title)}
            onEdit={(title, newContent) => onEdit(title, newContent)}
          />
        </Grid2>
      ))}
    </Grid2>

    <Modal
      open={showForm}
      onClose={toggleForm}
      aria-labelledby="fact-input-form"
      aria-describedby="form-to-add-new-fact"
    >
      <Box
        sx={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          bgcolor: 'background.paper',
          boxShadow: 24,
          p: 4,
          width: { xs: '90%', sm: 600 },
          borderRadius: 2,
        }}
      >
        <FactInputForm
          isOpen={showForm}
          onClose={toggleForm}
          onSubmit={onSubmit}
          existingTitles={factList.facts.map(fact => fact.title)}
        />
      </Box>
    </Modal>
  </Box>
);
