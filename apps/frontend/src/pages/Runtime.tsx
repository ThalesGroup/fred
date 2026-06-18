import { Box, Chip, Divider, Paper, Stack, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useGetRuntimeSummaryQuery } from "../slices/agentic/agenticRuntimeApi";

export default function Runtime() {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch } = useGetRuntimeSummaryQuery();

  return (
    <Box p={2} sx={{ display: "flex", justifyContent: "center" }}>
      <Paper sx={{ p: 2, width: "min(900px, 100%)" }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">{t("runtime.title")}</Typography>
        </Stack>
        <Divider sx={{ my: 1.5 }} />
        {isLoading && <Typography>{t("common.loading")}</Typography>}
        {isError && (
          <Stack direction="row" gap={1} alignItems="center">
            <Typography color="error">{t("runtime.error")}</Typography>
            <Chip label={t("common.retry")} onClick={() => refetch()} size="small" />
          </Stack>
        )}
        {data && (
          <Stack direction={{ xs: "column", sm: "row" }} gap={2} flexWrap="wrap">
            <Metric label={t("runtime.sessions")} value={data.sessions_total} />
            <Metric label={t("runtime.activeAgents")} value={data.agents_active_total} />
            <Metric label={t("runtime.attachments")} value={data.attachments_total} />
            <Metric label={t("runtime.sessionsWithAttachments")} value={data.attachments_sessions} />
            <Metric label={t("runtime.maxAttachmentsPerSession")} value={data.max_attachments_per_session} />
          </Stack>
        )}
      </Paper>
    </Box>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <Paper sx={{ p: 2, minWidth: 180 }} variant="outlined">
      <Typography variant="subtitle2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h5">{value}</Typography>
    </Paper>
  );
}
