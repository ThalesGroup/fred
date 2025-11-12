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

import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ViewColumnIcon from "@mui/icons-material/ViewColumn";
import ViewStreamIcon from "@mui/icons-material/ViewStream";
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Checkbox,
  Chip,
  Container,
  FormControlLabel,
  IconButton,
  MenuItem,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import MarkdownRenderer from "../components/markdown/MarkdownRenderer";
import { useGetBenchRunQuery } from "../slices/knowledgeFlow/benchPersistApi";

export default function ProcessorRunDetail() {
  const { t } = useTranslation();
  const { runId } = useParams();
  const { data: resp } = useGetBenchRunQuery({ runId: runId! }, { skip: !runId });

  const allIds = useMemo(() => new Set((resp?.results || []).map((r) => r.processor_id)), [resp]);
  const [sideBySide, setSideBySide] = useState(true);
  const [visible, setVisible] = useState<Set<string>>(allIds);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  React.useEffect(() => {
    setVisible(allIds);
  }, [allIds.size]);

  const toggleAll = (open: boolean) => {
    const next: Record<string, boolean> = {};
    for (const id of allIds) next[id] = !open;
    setCollapsed(next);
  };

  const results = (resp?.results || []).filter((r) => visible.has(r.processor_id));

  return (
    <>
      <TopBar
        title={t("procbench.detail.title", "Run Detail")}
        description={resp?.input_filename || ""}
        backTo="/monitoring/processors"
      />
      <Container maxWidth="xl" sx={{ pb: 2 }}>
        {/* Controls */}
        <Card variant="outlined" sx={{ mb: 1.5 }}>
          <CardContent sx={{ py: 1, px: 1.5 }}>
            <Stack direction={{ xs: "column", md: "row" }} alignItems="center" justifyContent="space-between" gap={1}>
              <Box>
                <Typography variant="subtitle2">{resp?.input_filename}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {resp?.results?.length || 0} processors • {resp?.file_type}
                </Typography>
              </Box>
              <Stack direction="row" alignItems="center" gap={2}>
                <FormControlLabel
                  control={<Switch checked={sideBySide} onChange={(_, v) => setSideBySide(v)} />}
                  label={sideBySide ? t("procbench.view.sideBySide") : t("procbench.view.stacked")}
                />
                <Select
                  multiple
                  size="small"
                  value={Array.from(visible)}
                  onChange={(e) => setVisible(new Set(e.target.value as string[]))}
                  renderValue={(selected) => (
                    <Stack direction="row" gap={0.5} flexWrap="wrap">
                      {(selected as string[]).map((id) => (
                        <Chip
                          key={id}
                          label={resp?.results?.find((r) => r.processor_id === id)?.display_name || id}
                          size="small"
                        />
                      ))}
                    </Stack>
                  )}
                >
                  {resp?.results?.map((r) => (
                    <MenuItem key={r.processor_id} value={r.processor_id}>
                      <Checkbox checked={visible.has(r.processor_id)} />
                      <Typography variant="body2">{r.display_name}</Typography>
                    </MenuItem>
                  ))}
                </Select>
                <Stack direction="row" gap={1}>
                  <IconButton
                    size="small"
                    onClick={() => toggleAll(true)}
                    title={t("procbench.detail.expandAll", "Expand all")!}
                  >
                    <ExpandMoreIcon fontSize="small" />
                  </IconButton>
                  <IconButton
                    size="small"
                    onClick={() => toggleAll(false)}
                    title={t("procbench.detail.collapseAll", "Collapse all")!}
                  >
                    <ExpandLessIcon fontSize="small" />
                  </IconButton>
                  {sideBySide ? <ViewColumnIcon fontSize="small" /> : <ViewStreamIcon fontSize="small" />}
                </Stack>
              </Stack>
            </Stack>
          </CardContent>
        </Card>

        {/* Metrics */}
        <Card variant="outlined" sx={{ mb: 1.5 }}>
          <CardHeader title={t("procbench.metricsTitle")} titleTypographyProps={{ variant: "subtitle2" }} />
          <CardContent sx={{ py: 0.5 }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ "& th": { py: 0.5 } }}>
                  <TableCell>{t("procbench.col.processor")}</TableCell>
                  <TableCell>{t("procbench.col.status")}</TableCell>
                  <TableCell align="right">{t("procbench.col.duration")}</TableCell>
                  <TableCell align="right">{t("procbench.col.tokens")}</TableCell>
                  <TableCell align="right">{t("procbench.col.words")}</TableCell>
                  <TableCell align="right">{t("procbench.col.headings")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {results.map((r) => (
                  <TableRow key={r.processor_id} sx={{ "& td": { py: 0.5 } }}>
                    <TableCell>{r.display_name}</TableCell>
                    <TableCell>
                      <Chip size="small" label={r.status} color={r.status === "ok" ? "success" : "error"} />
                    </TableCell>
                    <TableCell align="right">{r.duration_ms.toLocaleString()} ms</TableCell>
                    <TableCell align="right">{r.metrics?.tokens_est ?? "-"}</TableCell>
                    <TableCell align="right">{r.metrics?.words ?? "-"}</TableCell>
                    <TableCell align="right">{r.metrics?.headings ?? "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Markdown grid */}
        <Box sx={{ display: "grid", gridTemplateColumns: sideBySide ? { xs: "1fr", md: "1fr 1fr" } : "1fr", gap: 1.5 }}>
          {results.map((r) => {
            const isCollapsed = !!collapsed[r.processor_id];
            return (
              <Card key={r.processor_id} variant="outlined" sx={{ overflow: "hidden" }}>
                <CardHeader
                  title={r.display_name}
                  action={
                    <IconButton
                      size="small"
                      onClick={() => setCollapsed((c) => ({ ...c, [r.processor_id]: !isCollapsed }))}
                    >
                      {isCollapsed ? <ExpandMoreIcon fontSize="small" /> : <ExpandLessIcon fontSize="small" />}
                    </IconButton>
                  }
                  subheader={
                    <Typography component="span" variant="caption" color="text.secondary">
                      {r.duration_ms.toLocaleString()} ms
                    </Typography>
                  }
                />
                {!isCollapsed && (
                  <CardContent sx={{ pt: 0.5, pb: 1, px: 1 }}>
                    {r.status === "ok" && r.markdown ? (
                      <Box sx={{ maxHeight: { xs: 360, md: 520 }, overflowY: "auto", pr: 1 }}>
                        <MarkdownRenderer content={r.markdown} size="small" />
                      </Box>
                    ) : (
                      <Typography variant="body2" color="error">
                        {r.error_message || t("procbench.noMarkdown")}
                      </Typography>
                    )}
                  </CardContent>
                )}
              </Card>
            );
          })}
        </Box>
      </Container>
    </>
  );
}
