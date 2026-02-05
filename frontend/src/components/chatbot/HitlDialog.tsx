import React, { useEffect, useMemo, useState } from "react";
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Stack,
  Typography,
  TextField,
  useMediaQuery,
  useTheme,
  Paper,
  Radio,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import CancelIcon from "@mui/icons-material/Cancel";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import { AwaitingHumanEvent, HitlChoice } from "../../slices/agentic/agenticOpenApi";

type HitlDialogProps = {
  open: boolean;
  event: AwaitingHumanEvent;
  onSubmit: (choiceId: string, freeText?: string) => void;
  onCancel: () => void;
};

const fallbackChoices: HitlChoice[] = [
  { id: "yes", label: "Yes", default: true },
  { id: "no", label: "No" },
];

export const HitlDialog: React.FC<HitlDialogProps> = ({ open, event, onSubmit, onCancel }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  const choices = useMemo<HitlChoice[]>(() => {
    const incoming = event?.payload?.choices;
    if (incoming && incoming.length) {
      return incoming;
    }
    // Legacy boolean path
    return fallbackChoices;
  }, [event]);

  const defaultChoiceId = useMemo(() => {
    const preferred = choices.find((c) => c.default) || choices[0];
    return preferred?.id ?? "";
  }, [choices]);

  const [selectedId, setSelectedId] = useState<string>(defaultChoiceId);
  const [freeText, setFreeText] = useState<string>("");

  useEffect(() => {
    setSelectedId(defaultChoiceId);
    setFreeText("");
  }, [defaultChoiceId, event]);

  const question =
    event?.payload?.question ||
    event?.payload?.title ||
    (event?.payload as any)?.prompt ||
    (event?.payload as any)?.message ||
    "Please review and choose an option.";

  const showFreeText = Boolean(event?.payload?.free_text);

  const handleSubmit = () => {
    if (!selectedId) return;
    onSubmit(selectedId, showFreeText ? freeText.trim() || undefined : undefined);
  };

  return (
    <Dialog
      open={open}
      onClose={onCancel}
      fullWidth
      maxWidth="sm"
      PaperProps={{
        sx: {
          borderRadius: 3,
          boxShadow: "0 18px 60px rgba(15, 23, 42, 0.25)",
        },
      }}
    >
      <DialogTitle sx={{ pb: 1, display: "flex", alignItems: "center", gap: 1 }}>
        <InfoOutlinedIcon fontSize="small" color="primary" />
        {event?.payload?.title || "Action required"}
      </DialogTitle>
      <DialogContent sx={{ pt: 0, display: "flex", flexDirection: "column", gap: 2 }}>
        <Typography variant="body1" sx={{ color: "text.primary" }}>
          {question}
        </Typography>

        <Stack spacing={1.5}>
          {choices.map((choice) => (
            <Paper
              key={choice.id}
              variant="outlined"
              sx={{
                borderColor: selectedId === choice.id ? theme.palette.primary.main : "divider",
                px: 2,
                py: 1.5,
                display: "flex",
                alignItems: "flex-start",
                gap: 1,
                cursor: "pointer",
              }}
              onClick={() => setSelectedId(choice.id)}
              role="button"
              aria-pressed={selectedId === choice.id}
            >
              <Radio
                checked={selectedId === choice.id}
                onChange={() => setSelectedId(choice.id)}
                color="primary"
                sx={{ mt: 0.2 }}
              />
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  {choice.label}
                </Typography>
                {choice.description ? (
                  <Typography variant="body2" sx={{ color: "text.secondary" }}>
                    {choice.description}
                  </Typography>
                ) : null}
              </Box>
            </Paper>
          ))}
        </Stack>

        {showFreeText ? (
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              Additional notes (optional)
            </Typography>
            <TextField
              multiline
              minRows={3}
              fullWidth
              placeholder="Add context or clarifications..."
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
            />
          </Box>
        ) : null}

        {event?.payload?.metadata ? (
          <Box sx={{ mt: 1 }}>
            <Divider sx={{ mb: 1 }} />
            <Typography variant="caption" sx={{ textTransform: "uppercase", color: "text.secondary" }}>
              Context
            </Typography>
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", color: "text.secondary" }}>
              {JSON.stringify(event.payload.metadata, null, 2)}
            </Typography>
          </Box>
        ) : null}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2, gap: 1, flexWrap: isMobile ? "wrap" : "nowrap" }}>
        <Button
          startIcon={<CancelIcon />}
          color="inherit"
          variant="text"
          onClick={onCancel}
          fullWidth={isMobile}
        >
          Cancel
        </Button>
        <Button
          startIcon={<CheckCircleIcon />}
          variant="contained"
          onClick={handleSubmit}
          disabled={!selectedId}
          fullWidth={isMobile}
        >
          Confirm
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default HitlDialog;
