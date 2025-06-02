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

import { Card, CardContent, Typography, Box, IconButton, Divider } from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import { useTheme } from "@mui/material";

/**
 * AgentContextItem displays a single knowledge entry added to an agent.
 *
 * @param {Object} props
 * @param {Object} props.card - Object containing title and content.
 * @param {Function} props.onEdit - Called when edit button is clicked.
 * @param {Function} props.onDelete - Called when delete button is clicked.
 */
const ContextCard = ({ card, onEdit, onDelete }) => {
  const theme = useTheme();

  return (
    <Card
      sx={{
        height: "100%",
        borderRadius: 2,
        boxShadow: theme.shadows[2],
        transition: "transform 0.2s",
        "&:hover": {
          transform: "translateY(-4px)",
          boxShadow: theme.shadows[4],
        },
        display: "flex",
        flexDirection: "column",
      }}
    >
      <CardContent sx={{ flexGrow: 1 }}>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 1,
            mb: 1,
          }}
        >
          <Typography
            variant="subtitle1"
            component="h3"
            sx={{
              fontWeight: 600,
              flexGrow: 1,
              overflow: "hidden",
              textOverflow: "ellipsis",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
            }}
          >
            {card.title || "Untitled background information"}
          </Typography>
          <Box sx={{ display: "flex", flexShrink: 0 }}>
            <IconButton size="small" onClick={() => onEdit(card)} sx={{ color: "primary.main" }}>
              <EditIcon fontSize="small" />
            </IconButton>
            <IconButton size="small" onClick={() => onDelete(card)} sx={{ color: "error.main" }}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Box>
        </Box>

        <Divider sx={{ mb: 2 }} />

        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
          {card.content || "(empty background)"}
        </Typography>
      </CardContent>
    </Card>
  );
};

export default ContextCard;
