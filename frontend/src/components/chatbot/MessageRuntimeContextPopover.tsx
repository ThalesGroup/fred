// MessageRuntimeContextPopover.tsx
// Popover content (Overview + Tokens + Latency/Search/Temp + Libraries/Chat Contexts)

import { Popper, Paper, Stack, Typography, Divider, Box } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useTranslation } from "react-i18next";

type Props = {
  anchorEl: HTMLElement | null;
  onMouseEnter: () => void;
  onMouseLeave: () => void;

  // Overview values
  task?: string;
  node?: string;
  modelName?: string;

  tokens?: { in?: number; out?: number };
  latencyMs?: number;
  searchPolicy?: string;
  temperature?: number;

  libsLabeled: string[];
  ctxLabeled: string[];
};

export default function MessageRuntimeContextPopover({
  anchorEl,
  onMouseEnter,
  onMouseLeave,
  task,
  node,
  modelName,
  tokens,
  latencyMs,
  searchPolicy,
  temperature,
  libsLabeled,
  ctxLabeled,
}: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const open = Boolean(anchorEl);

  const fmt = (n?: number) => (n == null ? undefined : Number(n).toLocaleString());

  const inTok = Math.max(0, Number(tokens?.in ?? 0));
  const outTok = Math.max(0, Number(tokens?.out ?? 0));
  const totalTok = inTok + outTok;

  const SectionRow = ({ label, value }: { label: string; value?: string | number }) =>
    value === undefined || value === null || value === "" ? null : (
      <Box display="flex" justifyContent="space-between" gap={1}>
        <Typography variant="caption" sx={{ opacity: 0.7 }}>
          {label}
        </Typography>
        <Typography variant="caption" fontWeight={500} textAlign="right">
          {String(value)}
        </Typography>
      </Box>
    );

  return (
    <Popper
      open={open}
      anchorEl={anchorEl}
      placement="bottom-end"
      modifiers={[{ name: "offset", options: { offset: [0, 8] } }]}
      sx={{ zIndex: (t) => t.zIndex.tooltip + 1 }}
    >
      <Paper
        elevation={6}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        sx={{
          p: 1.25,
          minWidth: 260,
          maxWidth: 360,
          borderRadius: 2,
          bgcolor: theme.palette.background.paper, // unified light/dark
          border: `1px solid ${theme.palette.divider}`,
        }}
        role="dialog"
        aria-label={t("popover.aria")}
      >
        <Stack spacing={1}>
          <Typography variant="overline" sx={{ opacity: 0.7, letterSpacing: 0.6 }}>
            {t("popover.title")}
          </Typography>

          <SectionRow label={t("popover.task")} value={task} />
          <SectionRow label={t("popover.node")} value={node} />
          <SectionRow label={t("popover.model")} value={modelName} />

          {/* Tokens */}
          <Stack spacing={0}>
            <SectionRow label={t("popover.tokensTotal")} value={fmt(totalTok)} />
            <Stack spacing={0.25} sx={{ pl: 1.5 }}>
              <SectionRow label={t("popover.tokensIn")} value={fmt(inTok)} />
              <SectionRow label={t("popover.tokensOut")} value={fmt(outTok)} />
            </Stack>
          </Stack>

          <SectionRow
            label={t("popover.latency")}
            value={latencyMs != null ? `${latencyMs.toLocaleString()} ms` : undefined}
          />
          <SectionRow label={t("popover.search")} value={searchPolicy} />
          <SectionRow label={t("popover.temp")} value={typeof temperature === "number" ? temperature : undefined} />

          {libsLabeled.length || ctxLabeled.length ? <Divider flexItem /> : null}

          {libsLabeled.length ? (
            <>
              <Typography variant="overline" sx={{ opacity: 0.7 }}>
                {libsLabeled.length > 1 ? t("popover.sectionLibrariesPlural") : t("popover.sectionLibrarySingular")}
              </Typography>
              <Typography variant="caption" fontWeight={500} sx={{ display: "block" }}>
                {libsLabeled.join(", ")}
              </Typography>
            </>
          ) : null}

          {ctxLabeled.length ? (
            <>
              <Typography variant="overline" sx={{ opacity: 0.7 }}>
                {ctxLabeled.length > 1
                  ? t("popover.sectionChatContextsPlural")
                  : t("popover.sectionChatContextSingular")}
              </Typography>
              <Typography variant="caption" fontWeight={500} sx={{ display: "block" }}>
                {ctxLabeled.join(", ")}
              </Typography>
            </>
          ) : null}

          <Divider flexItem />
          <Typography variant="caption" sx={{ opacity: 0.7 }}>
            {t("popover.disclaimer")}
          </Typography>
        </Stack>
      </Paper>
    </Popper>
  );
}
