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

import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DescriptionIcon from "@mui/icons-material/Description";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CircularProgress,
  Container,
  FormControlLabel,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
  useTheme,
} from "@mui/material";
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import { useToast } from "../components/ToastProvider";
import { useDeleteBenchRunMutation, useListBenchRunsQuery } from "../slices/knowledgeFlow/benchPersistApi";
import {
  useListProcessorsKnowledgeFlowV1DevBenchProcessorsGetQuery,
  useRunKnowledgeFlowV1DevBenchRunPostMutation,
  type BenchmarkResponse as ApiBenchmarkResponse,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

type BenchmarkResponse = ApiBenchmarkResponse;

export default function ProcessorBench() {
  const theme = useTheme();
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();

  const [file, setFile] = useState<File | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [resp, setResp] = useState<BenchmarkResponse | null>(null);
  const [runBench, { isLoading: isMutating }] = useRunKnowledgeFlowV1DevBenchRunPostMutation();
  useListProcessorsKnowledgeFlowV1DevBenchProcessorsGetQuery(); // warm cache; optional for future selector
  const { data: savedRuns, refetch: refetchRuns } = useListBenchRunsQuery();
  const [deleteRun] = useDeleteBenchRunMutation();
  const navigate = useNavigate();
  const getErrorMessage = (e: any): string => {
    try {
      if (!e) return "Unknown error";
      if (typeof e === "string") return e;
      const data = (e as any).data;
      if (data) {
        if (typeof data === "string") return data;
        if (typeof (data as any).detail === "string") return (data as any).detail;
        // fallback stringify
        return JSON.stringify(data);
      }
      if ((e as any).error) return String((e as any).error);
      if ((e as any).message) return String((e as any).message);
      return JSON.stringify(e);
    } catch {
      return "Unknown error";
    }
  };
  const [persist, setPersist] = useState(true);

  const onSelectFile: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.target.files && e.target.files[0];
    setFile(f || null);
  };

  const onRun = async () => {
    if (!file) return;
    setIsRunning(true);
    setResp(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("persist", persist ? "true" : "false");
      // processors omitted → backend selects by file extension
      console.log("Submitting procbench run", { file, persist });
      const data = await runBench({ bodyRunKnowledgeFlowV1DevBenchRunPost: form as any }).unwrap();
      setResp(data as BenchmarkResponse);
      // If persisted, refresh list so user can open latest quickly
      if (persist) await refetchRuns();
      showSuccess?.({ summary: t("procbench.runSuccess"), detail: t("procbench.runSuccessDetail") });
    } catch (err: any) {
      console.error("procbench run failed", err);
      showError?.({ summary: t("procbench.runFailed"), detail: getErrorMessage(err) });
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <>
      <TopBar title={t("procbench.title")} description={t("procbench.description")} />
      <Container maxWidth="xl" sx={{ pb: 2, mt: 3 }}>
        {/* Upload Panel */}
        <Card variant="outlined" sx={{ mb: 1.5, borderColor: theme.palette.divider }}>
          <CardHeader
            avatar={<DescriptionIcon color="primary" />}
            title={t("procbench.uploadTitle")}
            subheader={t("procbench.uploadSubtitle")}
          />
          <CardContent sx={{ py: 1, px: 1.5 }}>
            <Stack direction={{ xs: "column", sm: "row" }} gap={1.5} alignItems={{ xs: "stretch", sm: "center" }}>
              <input
                id="procbench-input"
                type="file"
                onChange={onSelectFile}
                accept=".pdf,.docx,.pptx,.md,.txt"
                style={{ display: "none" }}
              />
              <label htmlFor="procbench-input">
                <Button size="small" variant="outlined" component="span">
                  {t("procbench.browse")}
                </Button>
              </label>
              <Typography variant="body2" color="text.secondary" sx={{ flex: 1, minHeight: 24 }}>
                {file ? file.name : t("procbench.noFile")}
              </Typography>
              <FormControlLabel
                control={<Switch checked={persist} onChange={(_, v) => setPersist(v)} />}
                label={t("procbench.persistLabel")}
              />
              <Button
                size="small"
                startIcon={<PlayArrowIcon />}
                variant="contained"
                onClick={onRun}
                disabled={!file || isRunning || isMutating}
              >
                {isRunning ? (
                  <>
                    <CircularProgress size={16} sx={{ mr: 1 }} /> {t("procbench.running")}
                  </>
                ) : (
                  t("procbench.run")
                )}
              </Button>
              <Button
                size="small"
                startIcon={<DeleteOutlineIcon />}
                variant="text"
                onClick={() => {
                  setResp(null);
                  setFile(null);
                }}
                disabled={isRunning || (!file && !resp)}
              >
                {t("procbench.clear")}
              </Button>
            </Stack>
          </CardContent>
        </Card>

        {/* Saved Runs */}
        <Card variant="outlined" sx={{ mb: 1.5 }}>
          <CardHeader
            title={t("procbench.saved.title")}
            slotProps={{
              title: {
                variant: "h6",
                color: "primary",
              },
            }}
          />
          <CardContent sx={{ pt: 0.5, pb: 1 }}>
            {savedRuns && savedRuns.length > 0 ? (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ py: 0.5 }}>{t("procbench.saved.modified")}</TableCell>
                    <TableCell sx={{ py: 0.5 }}>{t("procbench.saved.file")}</TableCell>
                    <TableCell sx={{ py: 0.5 }}>{t("procbench.saved.count")}</TableCell>
                    <TableCell align="right" sx={{ py: 0.5 }}>
                      {t("procbench.saved.actions")}
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {savedRuns.map((r) => (
                    <TableRow key={r.id} hover sx={{ "& td": { py: 0.5 } }}>
                      <TableCell>
                        <Typography variant="body2">
                          {r.modified ? new Date(r.modified).toLocaleString() : "—"}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{r.input_filename}</Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{r.processors_count}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Stack direction="row" justifyContent="flex-end" gap={1}>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => navigate(`/monitoring/processors/runs/${encodeURIComponent(r.id)}`)}
                          >
                            {t("procbench.saved.open")}
                          </Button>
                          <Button
                            size="small"
                            color="error"
                            variant="text"
                            onClick={async () => {
                              try {
                                await deleteRun({ runId: r.id }).unwrap();
                              } catch (e: any) {
                                showError?.({ summary: t("procbench.saved.deleteFailed"), detail: getErrorMessage(e) });
                              }
                            }}
                          >
                            {t("procbench.saved.delete")}
                          </Button>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <Typography variant="body2" color="text.secondary">
                {t("procbench.saved.empty")}
              </Typography>
            )}
          </CardContent>
        </Card>

        {/* Post-run hint to open the detail page */}
        {resp && (
          <Card variant="outlined" sx={{ mb: 1.5 }}>
            <CardContent sx={{ py: 1, px: 1.5 }}>
              <Stack direction={{ xs: "column", md: "row" }} alignItems="center" justifyContent="space-between" gap={1}>
                <Typography variant="body2">
                  {t("procbench.summaryFor", { name: resp.input_filename })} •{" "}
                  {t("procbench.processorsCount", { count: resp.results.length })}
                </Typography>
                <Button
                  size="small"
                  variant="contained"
                  onClick={() => {
                    if (savedRuns && savedRuns.length > 0) {
                      navigate(`/monitoring/processors/runs/${encodeURIComponent(savedRuns[0].id)}`);
                    }
                  }}
                >
                  {t("procbench.openLatest")}
                </Button>
              </Stack>
            </CardContent>
          </Card>
        )}
      </Container>
    </>
  );
}
