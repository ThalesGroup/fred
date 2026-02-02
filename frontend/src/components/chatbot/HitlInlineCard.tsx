import CloseIcon from "@mui/icons-material/Close";
import TaskAltIcon from "@mui/icons-material/TaskAlt";
import { Box, Button, Chip, Paper, Stack, TextField, Typography, useMediaQuery, useTheme } from "@mui/material";
import { useMemo, useState } from "react";
import { AwaitingHumanEvent, HitlChoice } from "../../slices/agentic/agenticOpenApi";
import MarkdownRenderer from "../markdown/MarkdownRenderer";

type Props = {
  event: AwaitingHumanEvent;
  onSubmit?: (choiceId: string, freeText?: string) => void;
  onCancel?: () => void;
};

const fallbackChoices: HitlChoice[] = [
  { id: "yes", label: "Yes", default: true },
  { id: "no", label: "No" },
];

export default function HitlInlineCard({ event, onSubmit, onCancel }: Props) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  const choices = useMemo<HitlChoice[]>(() => {
    const incoming = event?.payload?.choices;
    if (incoming && incoming.length) return incoming;
    return fallbackChoices;
  }, [event]);

  const defaultChoice = useMemo(() => choices.find((c) => c.default) || choices[0], [choices]);
  const [selected, setSelected] = useState<string>(defaultChoice?.id || "");
  const [freeText, setFreeText] = useState("");

  const handleSubmit = (choiceId: string) => {
    if (!choiceId || !onSubmit) return;
    onSubmit(choiceId, event?.payload?.free_text ? freeText.trim() || undefined : undefined);
  };

  const questionMd =
    event?.payload?.question ||
    event?.payload?.title ||
    (event?.payload as any)?.prompt ||
    "Please review and choose an option.";

  const stage = event?.payload?.stage;

  return (
    <Paper
      variant="outlined"
      sx={{
        borderColor: theme.palette.divider,
        background: theme.palette.background.default,
        px: 2,
        py: 2,
        mb: 1,
        borderRadius: 2,
        boxShadow: "0 6px 18px rgba(15,23,42,0.06)",
      }}
    >
      <Stack spacing={1.25}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <TaskAltIcon fontSize="small" color="primary" />
          <Typography variant="subtitle1" fontWeight={700}>
            {event?.payload?.title || "Action required"}
          </Typography>
          {stage ? (
            <Chip label={stage} size="small" variant="outlined" sx={{ ml: "auto", textTransform: "uppercase" }} />
          ) : null}
        </Stack>

        <Box sx={{ color: "text.primary" }}>
          <MarkdownRenderer content={questionMd} />
        </Box>

        <Stack spacing={1}>
          {choices.map((choice) => (
            <Button
              key={choice.id}
              onClick={() => {
                setSelected(choice.id);
                handleSubmit(choice.id);
              }}
              variant={selected === choice.id ? "contained" : "outlined"}
              color={selected === choice.id ? "primary" : "inherit"}
              fullWidth={isMobile}
              sx={{ justifyContent: "flex-start", textAlign: "left", gap: 1 }}
            >
              <Box>
                <Typography variant="subtitle2" fontWeight={700}>
                  {choice.label}
                </Typography>
                {choice.description ? (
                  <Typography variant="body2" color="text.secondary">
                    {choice.description}
                  </Typography>
                ) : null}
              </Box>
            </Button>
          ))}
        </Stack>

        {event?.payload?.free_text ? (
          <TextField
            label="Notes (optional)"
            multiline
            minRows={3}
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
            placeholder="Add guidance or corrections..."
          />
        ) : null}

        <Stack direction="row" justifyContent="flex-end" spacing={1}>
          {onCancel ? (
            <Button variant="text" startIcon={<CloseIcon />} onClick={onCancel} color="inherit" fullWidth={isMobile}>
              Dismiss
            </Button>
          ) : null}
          <Button
            variant="contained"
            startIcon={<TaskAltIcon />}
            disabled={!selected}
            onClick={() => handleSubmit(selected)}
            fullWidth={isMobile}
          >
            Send choice
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}
