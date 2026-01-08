// UserAssetsList.tsx
// Simplified view for user-generated assets (tagged "User Assets").

import { InfoOutlined } from "@mui/icons-material";
import CloudDownloadIcon from "@mui/icons-material/CloudDownload";
import VisibilityIcon from "@mui/icons-material/Visibility";
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import dayjs from "dayjs";
import React from "react";
import { useTranslation } from "react-i18next";
import { useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useDocumentCommands } from "../common/useDocumentCommands";

const formatSize = (bytes?: number | null) => {
  if (!bytes || bytes <= 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

type Props = {
  tagId?: string | null;
};

export const UserAssetsList: React.FC<Props> = ({ tagId }) => {
  const { t } = useTranslation();
  const [docs, setDocs] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [browseByTag] = useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation();
  const { preview, previewPdf, download } = useDocumentCommands();

  React.useEffect(() => {
    const run = async () => {
      if (!tagId) {
        setDocs([]);
        return;
      }
      setLoading(true);
      try {
        const res = await browseByTag({
          browseDocumentsByTagRequest: { tag_id: tagId, offset: 0, limit: 100 },
        }).unwrap();
        setDocs(res.documents || []);
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, [tagId, browseByTag]);

  return (
    <Card sx={{ mb: 2 }}>
      <CardHeader
        title={
          <Box display="flex" alignItems="center" gap={1}>
            <Typography variant="h6">{t("knowledge.userAssets.title")}</Typography>
            <Tooltip title={t("knowledge.userAssets.subtitle")}>
              <Box aria-label={t("knowledge.userAssets.subtitle") || "Info"} sx={{ display: "inline-flex" }}>
                <InfoOutlined fontSize="small" color="action" />
              </Box>
            </Tooltip>
          </Box>
        }
      />
      <CardContent>
        {loading && (
          <Box display="flex" alignItems="center" gap={1} mb={1}>
            <CircularProgress size={18} />
            <Typography variant="body2">Loading user assets…</Typography>
          </Box>
        )}
        {!loading && (!docs || docs.length === 0) && (
          <Typography variant="body2" color="text.secondary">
            No user assets yet. Generate content with an agent to see it here.
          </Typography>
        )}
        <Stack spacing={1}>
          {docs.map((doc) => {
            const name = doc.identity?.document_name || doc.identity?.document_uid;
            const added = doc.source?.date_added_to_kb
              ? dayjs(doc.source.date_added_to_kb).format("YYYY-MM-DD HH:mm")
              : "—";
            const size = formatSize(doc.file?.file_size_bytes);
            const isPdf = (name || "").toLowerCase().endsWith(".pdf");
            return (
              <Box
                key={doc.identity.document_uid}
                sx={{
                  display: "grid",
                  gridTemplateColumns: "minmax(0,2fr) auto auto auto",
                  alignItems: "center",
                  gap: 1,
                  px: 1,
                  py: 1,
                  border: "1px solid",
                  borderColor: "divider",
                  borderRadius: 1,
                }}
              >
                <Box minWidth={0}>
                  <Typography variant="body2" noWrap title={name}>
                    {name}
                  </Typography>
                  <Box display="flex" gap={1} alignItems="center" mt={0.5}>
                    <Chip size="small" label={size} />
                    <Typography variant="caption" color="text.secondary">
                      {added}
                    </Typography>
                  </Box>
                </Box>
                <Box display="flex" gap={1} justifyContent="flex-end">
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<VisibilityIcon />}
                    onClick={() => (isPdf ? previewPdf(doc) : preview(doc))}
                  >
                    View
                  </Button>
                  <Button
                    size="small"
                    variant="contained"
                    startIcon={<CloudDownloadIcon />}
                    onClick={() => download(doc)}
                  >
                    Download
                  </Button>
                </Box>
              </Box>
            );
          })}
        </Stack>
      </CardContent>
    </Card>
  );
};
