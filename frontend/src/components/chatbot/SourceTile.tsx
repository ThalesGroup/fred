import ShieldIcon from "@mui/icons-material/Shield";
import { Box, Card, Chip, SvgIcon, Tooltip, Typography } from "@mui/material";
import { VectorSearchHit } from "../../slices/agentic/agenticOpenApi";
import { mimeMeta } from "../../common/mimeUtils";

export function SourceTile({
  documentId,
  hits,
  onOpenDetails,
}: {
  documentId: string;
  hits: VectorSearchHit[];
  onOpenDetails: () => void;
}) {
  if (!hits?.length) return null;

  const sorted = hits.slice().sort((a, b) => {
    const ra = a.rank ?? Number.MAX_SAFE_INTEGER;
    const rb = b.rank ?? Number.MAX_SAFE_INTEGER;
    if (ra !== rb) return ra - rb;
    return (b.score ?? 0) - (a.score ?? 0);
  });

  const title =
    (sorted.find((h) => h.title)?.title || sorted[0]?.title)?.trim() || sorted[0]?.file_name?.trim() || documentId;

  const bestScore = Math.max(...sorted.map((h) => h.score ?? 0));
  const language = sorted.find((h) => h.language)?.language;
  const confidential = !!sorted.find((h) => h.confidential)?.confidential;
  const partsCount = sorted.length;

  const { Icon, label } = mimeMeta(sorted[0]?.mime_type);
  return (
    <Card
      variant="outlined"
      onClick={onOpenDetails}
      sx={(theme) => ({
        height: "100%",
        display: "flex",
        flexDirection: "column",
        cursor: "pointer",
        borderRadius: 2,
        p: 1,
        gap: 0.5,
        minHeight: 132,
        boxShadow: "none",
        backgroundColor: "transparent",
        borderColor: theme.palette.divider,
        transition: "background 0.2s, border-color 0.2s",
        "&:hover": {
          borderColor: theme.palette.divider,
        },
      })}
    >
      {/* HEADER LINE WITH ICON + TITLE */}
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
        <Tooltip title={label}>
          <SvgIcon component={Icon} inheritViewBox sx={{ fontSize: 20, color: "text.secondary", mt: "2px" }} />
        </Tooltip>

        <Tooltip title={title}>
          <Typography
            variant="subtitle2"
            sx={{
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              lineHeight: 1.25,
            }}
          >
            {title}
          </Typography>
        </Tooltip>
      </Box>

      {/* METADATA CHIPS */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 0.5,
          flexWrap: "nowrap",
          overflow: "hidden",
        }}
      >
        <Chip size="small" label={`${partsCount} parts`} />
        <ScorePill score={bestScore} />
        {language && <Chip size="small" label={language} variant="outlined" sx={{ flexShrink: 0 }} />}

        {confidential && (
          <Chip
            size="small"
            color="warning"
            label={
              <Box display="flex" alignItems="center" gap={0.5}>
                <ShieldIcon fontSize="small" /> Confidential
              </Box>
            }
            sx={{ flexShrink: 0 }}
          />
        )}
      </Box>

      <Box sx={{ flex: 1 }} />
    </Card>
  );
}

function ScorePill({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score ?? 0)) * 100;
  return <Chip size="small" label={`${Math.round(pct)}%`} variant="outlined" sx={{ flexShrink: 0 }} />;
}
