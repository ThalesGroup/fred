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

import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  Link as MUILink,
  Tooltip,
  Typography,
} from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { VectorSearchHit } from "../../slices/agentic/agenticOpenApi";
import { useMarkdownDocumentViewer } from "../../common/useMarkdownDocumentViewer";
import { usePdfDocumentViewer } from "../../common/usePdfDocumentViewer";
import { useTranslation } from "react-i18next";
import MarkdownRenderer from "../markdown/MarkdownRenderer";

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
  const { openMarkdownDocument } = useMarkdownDocumentViewer();
  const { openPdfDocument } = usePdfDocumentViewer();
  const { t } = useTranslation();
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
    (deduped.find((h) => h.title)?.title || deduped[0]?.title)?.trim() || deduped[0]?.file_name?.trim() || documentId;

  const bestScore = Math.max(...deduped.map((h) => h.score ?? 0));
  const author = deduped.find((h) => h.author)?.author || undefined;
  const created = firstDate(deduped.map((h) => h.created).filter(Boolean) as string[]);
  const modified = firstDate(deduped.map((h) => h.modified).filter(Boolean) as string[]);
  const language = deduped.find((h) => h.language)?.language || undefined;
  const license = deduped.find((h) => h.license)?.license || undefined;
  const fileName = deduped.find((h) => h.file_name)?.file_name || undefined;
  const filePath = deduped.find((h) => h.file_path)?.file_path || undefined;
  const repo = deduped.find((h) => h.repository)?.repository || undefined;
  const pull = deduped.find((h) => h.pull_location)?.pull_location || undefined;
  const tags = Array.from(new Set(deduped.flatMap((h) => h.tag_names || [])));
  const confidential = !!deduped.find((h) => h.confidential)?.confidential;

  const openSingle = (h: VectorSearchHit) => {
    const chunk = h.viewer_fragment || h.content || "";
    if (h.file_name?.toLowerCase().endsWith(".pdf")) {
      openPdfDocument({ document_uid: documentId, file_name: h.file_name });
      onClose();
      return;
    }
    openMarkdownDocument({ document_uid: documentId }, { chunksToHighlight: [chunk] });
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
          <Chip size="small" label={t("sourceDetails.bestScore", { score: (bestScore * 100).toFixed(0) })} />
          {language && <Chip size="small" label={t("sourceDetails.language", { language })} variant="outlined" />}
          {license && <Chip size="small" label={t("sourceDetails.license", { license })} variant="outlined" />}
          {confidential && <Chip size="small" color="warning" label={t("sourceDetails.confidential")} />}
          {tags.slice(0, 6).map((t) => (
            <Chip key={t} size="small" label={t} />
          ))}
          {tags.length > 6 && <Chip size="small" label={`+${tags.length - 6}`} />}
        </Box>
      </DialogTitle>

      <DialogContent dividers>
        {/* Doc meta */}
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, mb: 1 }}>
          {fileName && <Meta label={t("sourceDetails.file")} value={fileName} />}
          {filePath && <Meta label={t("sourceDetails.path")} value={filePath} />}
          {author && <Meta label={t("sourceDetails.author")} value={author} />}
          {created && <Meta label={t("sourceDetails.created")} value={created} />}
          {modified && <Meta label={t("sourceDetails.modified")} value={modified} />}
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
              {t("sourceDetails.openSourceDocument")}
            </Button>
          </Box>
        )}

        <Divider sx={{ my: 1 }} />

        {/* Passages list */}
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          {t("sourceDetails.citedPassagesTitle", { count: deduped.length })}
        </Typography>

        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {deduped.map((h, i) => (
            <Box
              key={`${documentId}-${i}`}
              sx={{
                border: (theme) => `1px solid ${theme.palette.divider}`,
                borderRadius: 1,
                p: 1,
              }}
            >
              <Box sx={{ "& p": { margin: 0 } }}>
                {" "}
                {/* Optional styling to remove default paragraph margins */}
                <MarkdownRenderer
                  content={h.content?.trim() || h.viewer_fragment?.trim() || "No content available."}
                  size="small" // Use "small" to keep the passage compact in the dialog
                  remarkPlugins={[]} // Add any remark plugins if needed
                  enableEmojiSubstitution={false} // Disable emoji substitution for formal source display
                />
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                {[
                  h.page != null ? t("sourceDetails.pageAbbreviation", { page: h.page }) : null,
                  h.section || null,
                  h.modified
                    ? t("sourceDetails.editedAbbreviation", { date: new Date(h.modified).toLocaleDateString() })
                    : null,
                  typeof h.score === "number" ? `${Math.round(h.score * 100)}%` : null,
                ]
                  .filter(Boolean)
                  .join(" • ")}
              </Typography>

              <Box sx={{ display: "flex", gap: 1, mt: 0.75 }}>
                <Button size="small" variant="text" onClick={() => openSingle(h)}>
                  {t("sourceDetails.openInPreview")}
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
                    {t("sourceDetails.openSource")}
                  </Button>
                )}
              </Box>
            </Box>
          ))}
        </Box>
      </DialogContent>
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
        <Typography variant="body2" noWrap>
          {value}
        </Typography>
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
    return (
      a.findIndex(
        (x) =>
          `${x.page ?? ""}|${x.section ?? ""}|${x.viewer_fragment ?? ""}|${(x.content || "").slice(0, 80)}` === key,
      ) === i
    );
  });
}

function firstDate(values: string[]) {
  return values.length ? new Date(values[0]).toLocaleString() : undefined;
}
