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

import { Box, Button, Card, CardContent, CardHeader, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { TopBar } from "../common/TopBar";
import { useToast } from "../components/ToastProvider";
import {
  AgentTaskProgressResponse,
  RunAgentTaskResponse,
  useGetAgentTaskProgressAgenticV1SchedulerAgentTasksProgressPostMutation,
  useRunAgentTaskAgenticV1SchedulerAgentTasksPostMutation,
} from "../slices/agentic/agenticOpenApi";

const AGENT_OPTIONS = [
  { value: "Georges", label: "Georges (Generalist Expert)" },
  { value: "Temporal Test Agent", label: "Temporal Test Agent" },
  { value: "Rico Senior", label: "Rico Senior" },
];

export const AppsScheduler = () => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const [runTask, { isLoading }] = useRunAgentTaskAgenticV1SchedulerAgentTasksPostMutation();
  const [fetchProgress, { isLoading: isChecking }] = useGetAgentTaskProgressAgenticV1SchedulerAgentTasksProgressPostMutation();
  const [agent, setAgent] = useState(AGENT_OPTIONS[0].value);
  const [question, setQuestion] = useState("");
  const [lastRun, setLastRun] = useState<RunAgentTaskResponse | null>(null);
  const [lastProgress, setLastProgress] = useState<AgentTaskProgressResponse | null>(null);
  const [submittedTasks, setSubmittedTasks] = useState<RunAgentTaskResponse[]>([]);

  const handleSubmit = async () => {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      showError({
        summary: t("apps.scheduler.toasts.error.title", "Scheduler error"),
        detail: t("apps.scheduler.toasts.error.questionRequired", "Please enter a question before submitting."),
      });
      return;
    }
    try {
      const response = await runTask({
        runAgentTaskRequest: {
          target_agent: agent,
          payload: {
            question: trimmedQuestion,
          },
        },
      }).unwrap();
      setLastRun(response);
      setLastProgress({
        task_id: response.task_id,
        workflow_id: response.workflow_id,
        run_id: response.run_id ?? null,
        progress: {
          state: "queued",
          percent: 0,
          message: t("apps.scheduler.progress.queued", "Waiting for worker to pick up the task."),
        },
      });
      setSubmittedTasks((prev) => {
        const next = [response, ...prev];
        return next.slice(0, 5); // keep recent few
      });
      showSuccess({
        summary: t("apps.scheduler.toasts.submitted.title", "Task scheduled"),
        detail: t("apps.scheduler.toasts.submitted.simple", "Your question was submitted to the scheduler."),
      });
      setQuestion("");
    } catch (error: any) {
      const detail = error?.data?.detail || error?.message || t("apps.scheduler.toasts.error.default", "Request failed.");
      showError({
        summary: t("apps.scheduler.toasts.error.title", "Scheduler error"),
        detail,
      });
    }
  };

  const handleCheck = async () => {
    if (!lastRun?.task_id) return;
    try {
      const progress = await fetchProgress({
        agentTaskProgressRequest: {
          task_id: lastRun.task_id,
          workflow_id: lastRun.workflow_id,
          run_id: lastRun.run_id || null,
        },
      }).unwrap();
      setLastProgress(progress);
    } catch (error: any) {
      const detail = error?.data?.detail || error?.message || t("apps.scheduler.toasts.error.default", "Request failed.");
      showError({
        summary: t("apps.scheduler.toasts.error.title", "Scheduler error"),
        detail,
      });
    }
  };

  return (
    <Box sx={{ px: 3, py: 2 }}>
      <TopBar title={t("apps.scheduler.title", "Apps / Scheduler")} description={t("apps.scheduler.subtitle", "Fire a single agent task via Temporal.")} />
      <Card variant="outlined" sx={{ mt: 1, maxWidth: 800, mx: "auto" }}>
        <CardHeader title={t("apps.scheduler.submit.title", "Schedule an agent task")} subheader={t("apps.scheduler.subtitle", "Fire a single agent task via Temporal.").toLowerCase()} />
        <CardContent>
          <Stack spacing={2}>
            <TextField
              select
              label={t("apps.scheduler.fields.targetAgent", "Target agent")}
              value={agent}
              onChange={(event) => setAgent(event.target.value)}
              fullWidth
            >
              {AGENT_OPTIONS.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label={t("apps.scheduler.fields.question", "User question")}
              placeholder={t("apps.scheduler.placeholders.question", "Describe what you want the agent to do…")}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              fullWidth
              multiline
              minRows={4}
            />
            <Typography variant="body2" color="text.secondary">
              {t(
                "apps.scheduler.tip",
                "We persist nothing here for now. Submit the question and inspect the Temporal worker logs downstream."
              )}
            </Typography>
            <Button variant="contained" onClick={handleSubmit} disabled={isLoading || !question.trim()}>
              {isLoading
                ? t("apps.scheduler.submit.loading", "Submitting...")
                : t("apps.scheduler.submit.action", "Submit question")}
            </Button>
            {lastRun && (
              <Button variant="text" onClick={handleCheck} disabled={isChecking}>
                {isChecking ? t("apps.scheduler.progress.loading", "Refreshing...") : t("apps.scheduler.progress.action", "Refresh progress")}
              </Button>
            )}
            {lastProgress && (
              <Stack spacing={0.5} sx={{ border: (theme) => `1px solid ${theme.palette.divider}`, borderRadius: 1, p: 1.5 }}>
                <Typography variant="subtitle2">{t("apps.scheduler.progress.title", "Progress lookup")}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {t("apps.scheduler.progress.state", "State")}: {lastProgress.progress.state}
                </Typography>
                {typeof lastProgress.progress.percent === "number" && (
                  <Typography variant="body2" color="text.secondary">
                    {t("apps.scheduler.progress.percent", "Percent")}: {lastProgress.progress.percent}%
                  </Typography>
                )}
                <Typography variant="body2" color="text.secondary">
                  {t("apps.scheduler.progress.message", "Message")}: {lastProgress.progress.message ?? t("apps.scheduler.progress.none", "No message")}
                </Typography>
              </Stack>
            )}
            <Stack spacing={0.5} sx={{ border: (theme) => `1px dashed ${theme.palette.divider}`, borderRadius: 1, p: 1.25 }}>
              <Typography variant="subtitle2">{t("apps.scheduler.pending.title", "Pending tasks")}</Typography>
              {submittedTasks.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  {t("apps.scheduler.pending.empty", "No pending tasks")}
                </Typography>
              )}
              {submittedTasks.map((task) => (
                <Typography key={task.task_id} variant="body2" color="text.secondary" sx={{ fontSize: "0.85rem" }}>
                  {task.task_id} · {task.workflow_id || t("apps.scheduler.pending.noWorkflow", "no workflow id")}
                </Typography>
              ))}
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
};
