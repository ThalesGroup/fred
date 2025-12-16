// ReBAC backfill maintenance page
import ShieldIcon from "@mui/icons-material/Shield";
import { Alert, Box, Button, Card, CardContent, CardHeader, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/ToastProvider";
import {
  RebacBackfillResponse,
  useBackfillRebacRelationsKnowledgeFlowV1TagsRebacBackfillPostMutation,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

const RebacBackfill = () => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const [trigger, { isLoading }] = useBackfillRebacRelationsKnowledgeFlowV1TagsRebacBackfillPostMutation();
  const [result, setResult] = useState<RebacBackfillResponse | null>(null);

  const handleRun = async () => {
    try {
      const res = await trigger().unwrap();
      setResult(res);
      if (res.rebac_enabled) {
        showSuccess({
          summary: t("rebac.backfill.success.title", "ReBAC relations rebuilt"),
          detail: t("rebac.backfill.success.detail", {
            owners: res.tag_owner_relations_created,
            parents: res.tag_parent_relations_created,
          }),
        });
      } else {
        showError({
          summary: t("rebac.backfill.disabled.title", "ReBAC disabled"),
          detail: t("rebac.backfill.disabled.detail", "ReBAC is turned off; nothing to backfill."),
        });
      }
    } catch (err: any) {
      const detail = err?.data?.detail || err?.error || err?.message || String(err);
      showError({
        summary: t("rebac.backfill.error.title", "Backfill failed"),
        detail,
      });
    }
  };

  const Stat = ({ label, value }: { label: string; value: number | string | boolean }) => (
    <Stack spacing={0.25}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h6">{String(value)}</Typography>
    </Stack>
  );

  return (
    <Box p={3} display="flex" justifyContent="center">
      <Card sx={{ maxWidth: 720, width: "100%" }}>
        <CardHeader
          avatar={<ShieldIcon color="primary" />}
          title={t("rebac.backfill.title", "ReBAC Backfill")}
          subheader={t(
            "rebac.backfill.subtitle",
            "Rebuild owner and tag-to-document relations after enabling ReBAC.",
          )}
        />
        <CardContent>
          <Stack spacing={3}>
            <Typography variant="body2" color="text.secondary">
              {t(
                "rebac.backfill.description",
                "Use this once after turning on ReBAC in an existing deployment to restore access to libraries and their documents.",
              )}
            </Typography>

            <Button
              variant="contained"
              color="primary"
              onClick={handleRun}
              disabled={isLoading}
              startIcon={<ShieldIcon />}
            >
              {isLoading ? t("rebac.backfill.running", "Running...") : t("rebac.backfill.run", "Run backfill")}
            </Button>

            {result && (
              <Card variant="outlined">
                <CardContent>
                  <Stack spacing={2}>
                    {!result.rebac_enabled && (
                      <Alert severity="warning">
                        {t("rebac.backfill.disabled.detail", "ReBAC is turned off; nothing to backfill.")}
                      </Alert>
                    )}
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={3}>
                      <Stat label={t("rebac.backfill.stats.tags", "Tags processed")} value={result.tags_seen} />
                      <Stat
                        label={t("rebac.backfill.stats.docs", "Documents scanned")}
                        value={result.documents_seen}
                      />
                      <Stat
                        label={t("rebac.backfill.stats.ownerRelations", "Owner relations created")}
                        value={result.tag_owner_relations_created}
                      />
                      <Stat
                        label={t("rebac.backfill.stats.parentRelations", "Tag→doc relations created")}
                        value={result.tag_parent_relations_created}
                      />
                    </Stack>
                  </Stack>
                </CardContent>
              </Card>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
};

export default RebacBackfill;
