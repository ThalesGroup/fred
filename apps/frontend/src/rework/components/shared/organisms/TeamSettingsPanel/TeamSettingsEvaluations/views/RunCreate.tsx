// Copyright Thales 2026
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

// Start one Run of an existing Evaluation. The case set is already fixed by the
// Evaluation; what this screen chooses is what to evaluate it against (RFC
// AGENT-EVALUATION §8.5: "each Run of it independently picks what to evaluate
// against"). Several Runs of the same Evaluation are the point — that is what
// makes them comparable.

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDispatch } from "react-redux";
import { taskRegistered } from "@rework/features/tasks/taskSlice";
import Button from "@shared/atoms/Button/Button";
import Select from "@shared/molecules/Select/Select";
import SelectableCard from "@shared/molecules/SelectableCard/SelectableCard";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { OptionModel } from "@models/Option.model.ts";
import { useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery } from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useStartRunEvaluationV1EvaluationsEvaluationIdRunsPostMutation } from "../../../../../../../slices/evaluation/evaluationOpenApi";
import styles from "./EvaluationForms.module.css";

interface RunCreateProps {
  teamId: string;
  evaluationId: string;
  evaluationName: string;
  onCancel: () => void;
  onStarted: (runId: string) => void;
}

export default function RunCreate({ teamId, evaluationId, evaluationName, onCancel, onStarted }: RunCreateProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const dispatch = useDispatch();

  const [agentInstanceId, setAgentInstanceId] = useState("");

  const { data: instances, isLoading: instancesLoading } =
    useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery({ teamId }, { skip: !teamId });

  const [startRun, { isLoading }] = useStartRunEvaluationV1EvaluationsEvaluationIdRunsPostMutation();

  const instanceOptions: OptionModel<string>[] = (instances ?? []).map((inst) => ({
    value: inst.agent_instance_id,
    label: inst.display_name,
    key: inst.agent_instance_id,
  }));

  const handleSubmit = async () => {
    try {
      const result = await startRun({
        evaluationId,
        startRunRequest: {
          team_id: teamId,
          target: { kind: "managed_instance", agent_instance_id: agentInstanceId },
        },
      }).unwrap();
      // Register the launched run into the shared task store so it streams via
      // useTaskSseManager. (TaskTray is currently unmounted from Sidebar.tsx, see
      // BACKLOG.md P4 — this store registration is otherwise unaffected.)
      if (result.task_id) {
        dispatch(
          taskRegistered({
            taskId: result.task_id,
            kind: "evaluation",
            target: { type: "evaluation_run", id: result.run_id, label: evaluationName },
          }),
        );
      }
      showSuccess({ summary: t("rework.evaluation.runCreate.success") });
      onStarted(result.run_id);
    } catch (e) {
      const detail = (e as { data?: { detail?: unknown } })?.data?.detail;
      showError({
        summary: typeof detail === "string" ? detail : t("rework.evaluation.runCreate.error"),
      });
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{t("rework.evaluation.runCreate.title")}</h1>
          <p className={styles.subtitle}>{t("rework.evaluation.runCreate.description", { name: evaluationName })}</p>
        </div>
        <Button
          color="on-surface"
          variant="text"
          size="medium"
          icon={{ category: "outlined", type: "arrow_back" }}
          onClick={onCancel}
        >
          {t("rework.evaluation.create.back")}
        </Button>
      </div>

      <div className={styles.section}>
        <SelectableCard
          selected
          title={t("rework.evaluation.create.target.managed.title")}
          description={t("rework.evaluation.create.target.managed.desc")}
          onSelect={() => undefined}
        />

        <Select<string>
          label={t("rework.evaluation.create.instance.label")}
          size="medium"
          options={instanceOptions}
          value={agentInstanceId}
          placeholder={
            instancesLoading
              ? t("rework.evaluation.create.instance.loading")
              : t("rework.evaluation.create.instance.placeholder")
          }
          onChange={setAgentInstanceId}
        />

        <p className={styles.note}>{t("rework.evaluation.create.securityNote")}</p>
      </div>

      <div className={styles.recap}>
        <span className={styles.recapTitle}>{t("rework.evaluation.create.recap.title")}</span>
        <div className={styles.recapRow}>
          <span className={styles.muted}>{t("rework.evaluation.runCreate.recap.evaluation")}</span>
          <span className={styles.recapValue}>{evaluationName}</span>
        </div>
        <div className={styles.recapRow}>
          <span className={styles.muted}>{t("rework.evaluation.create.recap.instance")}</span>
          <span className={styles.recapValue}>{agentInstanceId || "—"}</span>
        </div>
      </div>

      <div className={styles.nav}>
        <Button color="on-surface" variant="text" size="medium" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          disabled={!agentInstanceId || isLoading}
          onClick={handleSubmit}
        >
          {isLoading ? t("rework.evaluation.runCreate.starting") : t("rework.evaluation.runCreate.submit")}
        </Button>
      </div>
    </div>
  );
}
