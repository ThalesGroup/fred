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

import React from "react";
import { Button, Box, Modal, Typography, Grid2 } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import { FactInputForm } from "../../common/FactInputForm";
import { Fact, FactList } from "../slices/factsStructures";
import { FactCard } from "./FactCard";

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
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
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
          backgroundColor: "background.paper",
          color: "text.primary",
          borderRadius: "50%",
          minWidth: "40px",
          width: "40px",
          height: "40px",
          "&:hover": { backgroundColor: "primary.light" },
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
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          bgcolor: "background.paper",
          boxShadow: 24,
          p: 4,
          width: { xs: "90%", sm: 600 },
          borderRadius: 2,
        }}
      >
        <FactInputForm
          isOpen={showForm}
          onClose={toggleForm}
          onSubmit={onSubmit}
          existingTitles={factList.facts.map((fact) => fact.title)}
        />
      </Box>
    </Modal>
  </Box>
);
