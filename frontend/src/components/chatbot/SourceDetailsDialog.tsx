import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Link as MUILink,
  Tooltip,
  Typography,
} from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { VectorSearchHit } from "../../slices/agentic/agenticOpenApi";
import { useDocumentViewer } from "../../common/useDocumentViewer";

export function SourceDetailsDialog({
  open,
  onClose,
  documentId,
  hits,
}: {
  open: boolean;
  onClose: () => void;
  documentId: string;
  hits: VectorSearchHit[];
}) {
  const { openDocument } = useDocumentViewer();
  if (!open) return null;
  if (!hits?.length) return null;

  // sort & dedupe
  const sorted = hits.slice().sort((a, b) => {
    const ra = a.rank ?? Number.MAX_SAFE_INTEGER;
    const rb = b.rank ?? Number.MAX_SAFE_INTEGER;
    if (ra !== rb) return ra - rb;
    return (b.score ?? 0) - (a.score ?? 0);
  });
  const deduped = dedupe(sorted);

  const title =
    (deduped.find(h => h.title)?.title || deduped[0]?.title)?.trim() ||
    deduped[0]?.file_name?.trim() ||
    documentId;

  const bestScore = Math.max(...deduped.map(h => h.score ?? 0));
  const author = deduped.find(h => h.author)?.author || undefined;
  const created = firstDate(deduped.map(h => h.created).filter(Boolean) as string[]);
  const modified = firstDate(deduped.map(h => h.modified).filter(Boolean) as string[]);
  const language = deduped.find(h => h.language)?.language || undefined;
  const license = deduped.find(h => h.license)?.license || undefined;
  const fileName = deduped.find(h => h.file_name)?.file_name || undefined;
  const filePath = deduped.find(h => h.file_path)?.file_path || undefined;
  const repo = deduped.find(h => h.repository)?.repository || undefined;
  const pull = deduped.find(h => h.pull_location)?.pull_location || undefined;
  const tags = Array.from(new Set(deduped.flatMap(h => h.tag_names || [])));
  const confidential = !!deduped.find(h => h.confidential)?.confidential;

  const highlightAll = () => {
    const chunks = deduped
      .map(h => h.viewer_fragment || h.content)
      .filter((s): s is string => !!(s && s.trim()));
    openDocument({ document_uid: documentId }, { chunksToHighlight: chunks });
    onClose();
  };

  const openSingle = (h: VectorSearchHit) => {
    const chunk = h.viewer_fragment || h.content || "";
    openDocument({ document_uid: documentId }, { chunksToHighlight: [chunk] });
    onClose();
  };

  const externalUrl = pickFirstUrl([pull, repo, filePath]);
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ pr: 3 }}>
        <Typography variant="h6" sx={{ mb: 0.5 }}>
          {title}
        </Typography>
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
          <Chip size="small" label={`best ${(bestScore * 100).toFixed(0)}%`} />
          {language && <Chip size="small" label={language} variant="outlined" />}
          {license && <Chip size="small" label={`license: ${license}`} variant="outlined" />}
          {confidential && <Chip size="small" color="warning" label="Confidential" />}
          {tags.slice(0, 6).map(t => <Chip key={t} size="small" label={t} />)}
          {tags.length > 6 && <Chip size="small" label={`+${tags.length - 6}`} />}
        </Box>
      </DialogTitle>

      <DialogContent dividers>
        {/* Doc meta */}
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, mb: 1 }}>
          {fileName && <Meta label="File" value={fileName} />}
          {filePath && <Meta label="Path" value={filePath} />}
          {author && <Meta label="Author" value={author} />}
          {created && <Meta label="Created" value={created} />}
          {modified && <Meta label="Modified" value={modified} />}
        </Box>

        {/* External link(s) */}
        {externalUrl && (
          <Box sx={{ mb: 1 }}>
            <Button
              component={MUILink}
              href={externalUrl}
              target="_blank"
              rel="noopener noreferrer"
              endIcon={<OpenInNewIcon />}
            >
              Open source document
            </Button>
          </Box>
        )}

        <Divider sx={{ my: 1 }} />

        {/* Passages list */}
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Cited passages ({deduped.length})
        </Typography>

        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {deduped.map((h, i) => (
            <Box
              key={`${documentId}-${i}`}
              sx={{
                border: theme => `1px solid ${theme.palette.divider}`,
                borderRadius: 1,
                p: 1,
              }}
            >
              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                {h.content?.trim() || h.viewer_fragment?.trim() || "<empty>"}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                {[
                  h.page != null ? `p.${h.page}` : null,
                  h.section || null,
                  h.modified ? `edited ${new Date(h.modified).toLocaleDateString()}` : null,
                  typeof h.score === "number" ? `${Math.round(h.score * 100)}%` : null,
                ]
                  .filter(Boolean)
                  .join(" • ")}
              </Typography>

              <Box sx={{ display: "flex", gap: 1, mt: 0.75 }}>
                <Button size="small" variant="text" onClick={() => openSingle(h)}>
                  Open in preview
                </Button>
                {externalUrl && (
                  <Button
                    size="small"
                    variant="text"
                    component={MUILink}
                    href={externalUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    endIcon={<OpenInNewIcon />}
                  >
                    Open source
                  </Button>
                )}
              </Box>
            </Box>
          ))}
        </Box>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 1 }}>
        <Button onClick={highlightAll}>Open all in preview</Button>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Tooltip title={value}>
        <Typography variant="body2" noWrap>{value}</Typography>
      </Tooltip>
    </Box>
  );
}

function pickFirstUrl(parts: Array<string | undefined>) {
  for (const p of parts) {
    if (!p) continue;
    try {
      const u = new URL(p);
      return u.toString();
    } catch {
      // not a URL (e.g., a local path) — skip
    }
  }
  return undefined;
}

function dedupe(arr: VectorSearchHit[]) {
  return arr.filter((h, i, a) => {
    const key = `${h.page ?? ""}|${h.section ?? ""}|${h.viewer_fragment ?? ""}|${(h.content || "").slice(0, 80)}`;
    return a.findIndex(x => `${x.page ?? ""}|${x.section ?? ""}|${x.viewer_fragment ?? ""}|${(x.content || "").slice(0, 80)}` === key) === i;
  });
}

function firstDate(values: string[]) {
  return values.length ? new Date(values[0]).toLocaleString() : undefined;
}
