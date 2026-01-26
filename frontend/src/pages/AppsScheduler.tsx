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

import { Box, Button, Card, CardContent, CardHeader, Divider, LinearProgress, Stack, TextField, Typography } from "@mui/material";
import Grid2 from "@mui/material/Grid2";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { TopBar } from "../common/TopBar";
import { useToast } from "../components/ToastProvider";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import {
  AgentTaskProgressResponse,
  RunAgentTaskResponse,
  useGetAgentTaskProgressAgenticV1SchedulerAgentTasksProgressPostMutation,
  useRunAgentTaskAgenticV1SchedulerAgentTasksPostMutation,
} from "../slices/agentic/agenticOpenApi";

type StoredTask = {
  taskId?: string;
  workflowId?: string;
  runId?: string;
  targetAgent?: string;
};

const storageKey = "apps.agentScheduler.lastTask";

const parseOptionalJsonObject = (raw: string, label: string) => {
  const trimmed = raw.trim();
  if (!trimmed) {
    return {};
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (error) {
    throw new Error(`${label} is not valid JSON.`);
  }
  if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
};

export const AppsScheduler = () => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const [runTask, { isLoading: isRunning }] = useRunAgentTaskAgenticV1SchedulerAgentTasksPostMutation();
  const [fetchProgress, { isLoading: isFetching }] = useGetAgentTaskProgressAgenticV1SchedulerAgentTasksProgressPostMutation();

  const [storedTask, setStoredTask] = useLocalStorageState<StoredTask>(storageKey, {});
  const [lastRun, setLastRun] = useState<RunAgentTaskResponse | null>(null);
  const [lastProgress, setLastProgress] = useState<AgentTaskProgressResponse | null>(null);

  const [taskId, setTaskId] = useState(storedTask.taskId || "");
  const [workflowType, setWorkflowType] = useState("AgentWorkflow");
  const [taskQueue, setTaskQueue] = useState("agents");
  const [targetAgent, setTargetAgent] = useState(storedTask.targetAgent || "Rico Senior");
  const [sessionId, setSessionId] = useState("");
  const [requestId, setRequestId] = useState("");
  const [payloadText, setPayloadText] = useState('{\n  "input": "Hi Rico Senior, can you review the attached query and summarize the key points?"\n}');
  const [contextText, setContextText] = useState('{\n  "caller_actor": "alice"\n}');

  const [progressTaskId, setProgressTaskId] = useState(storedTask.taskId || "");
  const [progressWorkflowId, setProgressWorkflowId] = useState(storedTask.workflowId || "");
  const [progressRunId, setProgressRunId] = useState(storedTask.runId || "");

  const handleSubmit = async () => {
    try {
      const payload = parseOptionalJsonObject(payloadText, "Payload");
      const context = parseOptionalJsonObject(contextText, "Context");

      const response = await runTask({
        runAgentTaskRequest: {
          task_id: taskId || null,
          workflow_type: workflowType,
          task_queue: taskQueue || null,
          target_agent: targetAgent.trim(),
          session_id: sessionId || null,
          request_id: requestId || null,
          payload,
          context,
        },
      }).unwrap();

      setLastRun(response);
      setLastProgress(null);
      setStoredTask({
        taskId: response.task_id,
        workflowId: response.workflow_id,
        runId: response.run_id ?? undefined,
        targetAgent: targetAgent.trim(),
      });
      setProgressTaskId(response.task_id);
      setProgressWorkflowId(response.workflow_id);
      setProgressRunId(response.run_id ?? "");
      showSuccess({
        summary: t("apps.scheduler.toasts.submitted.title", "Task scheduled"),
        detail: t("apps.scheduler.toasts.submitted.detail", "Your agent task was submitted to the scheduler."),
      });
    } catch (error: any) {
      const detail = error?.data?.detail || error?.message || "Request failed.";
      showError({
        summary: t("apps.scheduler.toasts.error.title", "Scheduler error"),
        detail,
      });
    }
  };

  const handleFetchProgress = async () => {
    try {
      const response = await fetchProgress({
        agentTaskProgressRequest: {
          task_id: progressTaskId || null,
          workflow_id: progressWorkflowId || null,
          run_id: progressRunId || null,
        },
      }).unwrap();
      setLastProgress(response);
    } catch (error: any) {
      const detail = error?.data?.detail || error?.message || "Unable to fetch progress.";
      showError({
        summary: t("apps.scheduler.toasts.progressError.title", "Progress error"),
        detail,
      });
    }
  };

  const progressValue = lastProgress?.progress?.percent;
  const progressState = lastProgress?.progress?.state || "unknown";
  const progressMessage = lastProgress?.progress?.message || "No progress reported yet.";

  return (
    <Box sx={{ px: 3, py: 2 }}>
      <TopBar title={t("apps.scheduler.title", "Apps / Scheduler")} description={t("apps.scheduler.subtitle", "Submit and inspect agent tasks queued via Temporal.")} />
      <Grid2 container spacing={3} sx={{ mt: 1 }}>
        <Grid2 size={{ xs: 12, lg: 7 }}>
          <Card variant="outlined">
            <CardHeader title={t("apps.scheduler.submit.title", "Schedule an agent task")} />
            <CardContent>
              <Stack spacing={2}>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                  <TextField label={t("apps.scheduler.fields.targetAgent", "Target agent")} value={targetAgent} onChange={(event) => setTargetAgent(event.target.value)} fullWidth />
                  <TextField label={t("apps.scheduler.fields.taskId", "Task ID (optional)")} value={taskId} onChange={(event) => setTaskId(event.target.value)} fullWidth />
                </Stack>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                  <TextField label={t("apps.scheduler.fields.workflowType", "Workflow type")} value={workflowType} onChange={(event) => setWorkflowType(event.target.value)} fullWidth />
                  <TextField label={t("apps.scheduler.fields.taskQueue", "Task queue (optional)")} value={taskQueue} onChange={(event) => setTaskQueue(event.target.value)} fullWidth />
                </Stack>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                  <TextField label={t("apps.scheduler.fields.sessionId", "Session ID (optional)")} value={sessionId} onChange={(event) => setSessionId(event.target.value)} fullWidth />
                  <TextField label={t("apps.scheduler.fields.requestId", "Request ID (optional)")} value={requestId} onChange={(event) => setRequestId(event.target.value)} fullWidth />
                </Stack>
                <TextField label={t("apps.scheduler.fields.payload", "Payload (JSON object)")} value={payloadText} onChange={(event) => setPayloadText(event.target.value)} fullWidth multiline minRows={6} />
                <TextField label={t("apps.scheduler.fields.context", "Context (JSON object)")} value={contextText} onChange={(event) => setContextText(event.target.value)} fullWidth multiline minRows={4} />
                <Button variant="contained" onClick={handleSubmit} disabled={isRunning || !targetAgent.trim()}>
                  {isRunning ? t("apps.scheduler.submit.loading", "Submitting...") : t("apps.scheduler.submit.action", "Submit task")}
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid2>
        <Grid2 size={{ xs: 12, lg: 5 }}>
          <Stack spacing={3}>
            <Card variant="outlined">
              <CardHeader title={t("apps.scheduler.status.title", "Latest submission")} />
              <CardContent>
                {lastRun ? (
                  <Stack spacing={1}>
                    <Typography variant="body2">
                      <strong>Task ID:</strong> {lastRun.task_id}
                    </Typography>
                    <Typography variant="body2">
                      <strong>Workflow ID:</strong> {lastRun.workflow_id}
                    </Typography>
                    <Typography variant="body2">
                      <strong>Run ID:</strong> {lastRun.run_id || "n/a"}
                    </Typography>
                    <Typography variant="body2">
                      <strong>Status:</strong> {lastRun.status}
                    </Typography>
                  </Stack>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {t("apps.scheduler.status.empty", "No tasks submitted yet.")}
                  </Typography>
                )}
              </CardContent>
            </Card>
            <Card variant="outlined">
              <CardHeader title={t("apps.scheduler.progress.title", "Progress lookup")} />
              <CardContent>
                <Stack spacing={2}>
                  <TextField label={t("apps.scheduler.fields.progressTaskId", "Task ID")} value={progressTaskId} onChange={(event) => setProgressTaskId(event.target.value)} fullWidth />
                  <TextField label={t("apps.scheduler.fields.progressWorkflowId", "Workflow ID")} value={progressWorkflowId} onChange={(event) => setProgressWorkflowId(event.target.value)} fullWidth />
                  <TextField label={t("apps.scheduler.fields.progressRunId", "Run ID (optional)")} value={progressRunId} onChange={(event) => setProgressRunId(event.target.value)} fullWidth />
                  <Button variant="outlined" onClick={handleFetchProgress} disabled={isFetching}>
                    {isFetching ? t("apps.scheduler.progress.loading", "Refreshing...") : t("apps.scheduler.progress.action", "Refresh progress")}
                  </Button>
                  <Divider />
                  <Stack spacing={1}>
                    <Typography variant="subtitle2">{t("apps.scheduler.progress.state", "State")}</Typography>
                    <Typography variant="body2">{progressState}</Typography>
                    <LinearProgress variant={typeof progressValue === "number" ? "determinate" : "indeterminate"} value={typeof progressValue === "number" ? progressValue : 0} />
                    <Typography variant="body2" color="text.secondary">
                      {typeof progressValue === "number" ? `${progressValue}%` : t("apps.scheduler.progress.unknown", "No percent reported")}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {progressMessage}
                    </Typography>
                  </Stack>
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        </Grid2>
      </Grid2>
    </Box>
  );
};
