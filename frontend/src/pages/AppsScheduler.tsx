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

import { Box, Button, Card, CardContent, CardHeader, Stack, TextField, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { TopBar } from "../common/TopBar";
import { useToast } from "../components/ToastProvider";
import {
  SubmitAgentTaskResponse,
  useSubmitAgentTaskAgenticV1V1AgentTasksPostMutation,
} from "../slices/agentic/agenticOpenApi";

const TARGET_AGENT = "Researcher";

export const AppsScheduler = () => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const [submitTask, { isLoading }] = useSubmitAgentTaskAgenticV1V1AgentTasksPostMutation();
  const [question, setQuestion] = useState("");
  const [lastRun, setLastRun] = useState<SubmitAgentTaskResponse | null>(null);

  const helperText = useMemo(
    () =>
      t(
        "apps.scheduler.tip",
        "Submit a quick research question to the Temporal worker. The backend will route it to the Researcher agent."
      ),
    [t]
  );

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
      const response = await submitTask({
        submitAgentTaskRequest: {
          target_agent: TARGET_AGENT,
          request_text: trimmedQuestion,
          parameters: {},
        },
      }).unwrap();
      setLastRun(response);
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

  return (
    <Box sx={{ px: 3, py: 2 }}>
      <TopBar title={t("apps.scheduler.title", "Apps / Scheduler")} description={t("apps.scheduler.subtitle", "Fire a single agent task via Temporal.")} />
      <Card variant="outlined" sx={{ mt: 1, maxWidth: 800, mx: "auto" }}>
        <CardHeader title={t("apps.scheduler.submit.title", "Schedule an agent task")} subheader={t("apps.scheduler.subtitle", "Fire a single agent task via Temporal.").toLowerCase()} />
        <CardContent>
          <Stack spacing={2}>
            <TextField label={t("apps.scheduler.fields.targetAgent", "Target agent")} value={TARGET_AGENT} fullWidth disabled />
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
              {helperText}
            </Typography>
            <Button variant="contained" onClick={handleSubmit} disabled={isLoading || !question.trim()}>
              {isLoading
                ? t("apps.scheduler.submit.loading", "Submitting...")
                : t("apps.scheduler.submit.action", "Submit question")}
            </Button>
            {lastRun && (
              <Stack spacing={0.5} sx={{ border: (theme) => `1px solid ${theme.palette.divider}`, borderRadius: 1, p: 1.25 }}>
                <Typography variant="subtitle2">{t("apps.scheduler.progress.title", "Progress lookup")}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {t("apps.scheduler.pending.lastTaskId", "Task id")}: {lastRun.task_id}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t("apps.scheduler.progress.state", "State")}: {lastRun.status}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t("apps.scheduler.progress.message", "Message")}:{" "}
                  {t("apps.scheduler.progress.hitTemporal", "Inspect Temporal UI or worker logs for live status.")}
                </Typography>
              </Stack>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
};
