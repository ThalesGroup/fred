import {
  Card,
  CardContent,
  Typography,
  Box,
  IconButton,
  Divider
} from "@mui/material";
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
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
    <Card sx={{
      height: '100%',
      borderRadius: 2,
      boxShadow: theme.shadows[2],
      transition: 'transform 0.2s',
      '&:hover': {
        transform: 'translateY(-4px)',
        boxShadow: theme.shadows[4],
      },
      display: 'flex',
      flexDirection: 'column'
    }}>
      <CardContent sx={{ flexGrow: 1 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 600 }}>
            {card.title || "Untitled background information"}
          </Typography>
          <Box>
            <IconButton size="small" onClick={() => onEdit(card)} sx={{ color: 'primary.main' }}>
              <EditIcon fontSize="small" />
            </IconButton>
            <IconButton size="small" onClick={() => onDelete(card)} sx={{ color: 'error.main' }}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Box>
        </Box>
        <Divider sx={{ mb: 2 }} />
        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
          {card.content || "(empty background)"}
        </Typography>
      </CardContent>
    </Card>
  );
};

export default ContextCard;
