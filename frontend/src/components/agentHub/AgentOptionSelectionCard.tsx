import { Paper, Stack, Switch, Typography } from "@mui/material";
export interface AgentOptionSelectionCardProps {
  name: string;
  description?: string;
  selected: boolean;
  onSelectedChange: (selected: boolean) => void;
}

export function AgentOptionSelectionCard({
  name,
  description,
  selected,
  onSelectedChange,
}: AgentOptionSelectionCardProps) {
  return (
    <Paper
      elevation={60}
      onClick={() => onSelectedChange(!selected)}
      sx={[
        {
          boxShadow: "none",
          border: "1px solid transparent",
          borderRadius: 2,
          cursor: "pointer",
        },
        !selected && {
          "&:hover": {
            borderColor: "text.secondary",
          },
        },
        selected && { borderColor: "primary.main" },
      ]}
    >
      <Stack spacing={1} sx={{ p: 1.25 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Switch
            size="small"
            checked={selected}
            onChange={(event) => {
              event.stopPropagation();
              onSelectedChange(event.target.checked);
            }}
            sx={{ mt: -0.25, ml: -0.5 }}
          />
          <Stack gap={0.5} flex={1} sx={{ minWidth: 0 }}>
            <Typography fontWeight={selected ? 500 : 400} variant="body2" sx={{ lineHeight: 1.2, userSelect: "none" }}>
              {name}
            </Typography>

            {/* Description */}
            {description && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  userSelect: "none",
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  lineHeight: 1.25,
                }}
              >
                {description}
              </Typography>
            )}
          </Stack>
        </Stack>
      </Stack>
    </Paper>
  );
}
