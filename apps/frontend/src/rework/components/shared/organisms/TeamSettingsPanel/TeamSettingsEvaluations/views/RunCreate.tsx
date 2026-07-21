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
import IconButton from "@shared/atoms/IconButton/IconButton";
import Switch from "@shared/atoms/Switch/Switch";
import TextArea from "@shared/atoms/TextArea/TextArea";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Select from "@shared/molecules/Select/Select";
import SelectableCard from "@shared/molecules/SelectableCard/SelectableCard";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { OptionModel } from "@models/Option.model.ts";
import {
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
} from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useStartRunEvaluationV1EvaluationsEvaluationIdRunsPostMutation } from "../../../../../../../slices/evaluation/evaluationOpenApi";
import styles from "./EvaluationForms.module.css";

// Built-in DeepEval metrics selectable for a run — the user picks explicitly, there is
// no automatic profile detection anymore (EVAL-CUSTOM-METRIC, manual metric selection).
const BUILTIN_METRICS = [
  { id: "answer_relevancy", key: "answerRelevancy" },
  { id: "faithfulness", key: "faithfulness" },
  { id: "contextual_relevancy", key: "contextualRelevancy" },
  { id: "contextual_precision", key: "contextualPrecision" },
  { id: "contextual_recall", key: "contextualRecall" },
] as const;

// Curated subset of DeepEval's LLMTestCaseParams: the only ones the evaluator actually
// populates from a case's trace (see fred-deepeval-cli core/scorer.py::_trace_to_test_case).
// Exposing the rest (TOOLS_CALLED, MCP_*, ...) would let a user pick a field that is
// always empty for this evaluator.
const CUSTOM_METRIC_PARAMETERS = [
  { value: "INPUT", key: "input" },
  { value: "ACTUAL_OUTPUT", key: "actualOutput" },
  { value: "EXPECTED_OUTPUT", key: "expectedOutput" },
  { value: "RETRIEVAL_CONTEXT", key: "retrievalContext" },
] as const;

interface CustomMetricRow {
  id: string;
  name: string;
  criteria: string;
  parameters: string[];
  threshold: string;
}

function newCustomMetricRow(): CustomMetricRow {
  return { id: crypto.randomUUID(), name: "", criteria: "", parameters: [], threshold: "0.5" };
}

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
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>(["answer_relevancy"]);
  const [customMetrics, setCustomMetrics] = useState<CustomMetricRow[]>([]);

  const {
    data: instances,
    isLoading: instancesLoading,
    refetch: refetchInstances,
  } = useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery({ teamId }, { skip: !teamId });
  const { data: templates } = useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery(
    { teamId },
    { skip: !teamId },
  );

  const [startRun, { isLoading }] = useStartRunEvaluationV1EvaluationsEvaluationIdRunsPostMutation();

  const instanceOptions: OptionModel<string>[] = (instances ?? []).map((inst) => ({
    value: inst.agent_instance_id,
    label: inst.display_name,
    key: inst.agent_instance_id,
  }));

  // Tool access on an instance can be changed by any teammate at any time — refetch
  // right when it's picked for an eval, so the tool list below reflects the live
  // configuration instead of whatever was cached when this screen happened to open.
  const handleSelectInstance = (instanceId: string) => {
    setAgentInstanceId(instanceId);
    void refetchInstances();
  };

  const selectedInstance = instances?.find((inst) => inst.agent_instance_id === agentInstanceId);
  const selectedTemplate = templates?.find((tpl) => tpl.template_id === selectedInstance?.template_id);
  const capabilityById = new Map((selectedTemplate?.available_capabilities ?? []).map((cap) => [cap.id, cap]));
  // null means "inherits the template's default selection" (no explicit per-instance
  // override) — distinct from an empty array, which means the instance has no tools.
  const activeCapabilityIds = selectedInstance?.selected_capability_ids ?? null;
  const activeCapabilities = (activeCapabilityIds ?? [])
    .map((id) => capabilityById.get(id))
    .filter((cap): cap is NonNullable<typeof cap> => !!cap);

  const toggleMetric = (metricId: string) =>
    setSelectedMetrics((prev) => (prev.includes(metricId) ? prev.filter((m) => m !== metricId) : [...prev, metricId]));

  const addCustomMetric = () => setCustomMetrics((prev) => [...prev, newCustomMetricRow()]);
  const removeCustomMetric = (id: string) => setCustomMetrics((prev) => prev.filter((r) => r.id !== id));
  const updateCustomMetric = (id: string, field: "name" | "criteria" | "threshold", value: string) =>
    setCustomMetrics((prev) => prev.map((r) => (r.id === id ? { ...r, [field]: value } : r)));
  const toggleCustomMetricParam = (id: string, param: string) =>
    setCustomMetrics((prev) =>
      prev.map((r) =>
        r.id === id
          ? {
              ...r,
              parameters: r.parameters.includes(param)
                ? r.parameters.filter((p) => p !== param)
                : [...r.parameters, param],
            }
          : r,
      ),
    );

  // Only rows with a name, a criterion, and at least one field are sent — a row left
  // half-filled while editing is silently dropped rather than rejected at submit time.
  const validCustomMetrics = customMetrics.filter((r) => r.name.trim() && r.criteria.trim() && r.parameters.length > 0);
  const canSubmit = !!agentInstanceId && selectedMetrics.length > 0;

  const handleSubmit = async () => {
    try {
      const result = await startRun({
        evaluationId,
        startRunRequest: {
          team_id: teamId,
          target: { kind: "managed_instance", agent_instance_id: agentInstanceId },
          metrics: selectedMetrics,
          custom_metrics: validCustomMetrics.map((r) => ({
            name: r.name.trim(),
            criteria: r.criteria.trim(),
            parameters: r.parameters,
            threshold: Number(r.threshold) || 0.5,
          })),
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
          onChange={handleSelectInstance}
        />

        {agentInstanceId && (
          <div className={styles.field}>
            <span className={styles.fieldLabel}>{t("rework.evaluation.create.instanceTools.label")}</span>
            {activeCapabilityIds === null ? (
              <p className={styles.note}>{t("rework.evaluation.create.instanceTools.inherited")}</p>
            ) : activeCapabilities.length === 0 ? (
              <p className={styles.note}>{t("rework.evaluation.create.instanceTools.none")}</p>
            ) : (
              <div className={styles.toolChips}>
                {activeCapabilities.map((cap) => (
                  <span key={cap.id} className={styles.toolChip}>
                    {t(cap.name)}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        <p className={styles.note}>{t("rework.evaluation.create.securityNote")}</p>
      </div>

      <div className={styles.field}>
        <span className={styles.fieldLabel}>{t("rework.evaluation.create.builtinMetrics.label")}</span>
        <p className={styles.note}>{t("rework.evaluation.create.builtinMetrics.help")}</p>
        <ul className={styles.metricList}>
          {BUILTIN_METRICS.map((metric) => {
            const checked = selectedMetrics.includes(metric.id);
            return (
              <li key={metric.id} className={styles.metricRow}>
                <Switch
                  checked={checked}
                  onChange={() => toggleMetric(metric.id)}
                  aria-label={t(`rework.evaluation.create.builtinMetrics.${metric.key}`)}
                />
                <span className={styles.metricMeta}>
                  <span className={styles.metricName}>
                    {t(`rework.evaluation.create.builtinMetrics.${metric.key}`)}
                  </span>
                  <span className={styles.metricDesc}>
                    {t(`rework.evaluation.create.builtinMetrics.${metric.key}Desc`)}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
        {selectedMetrics.length === 0 && (
          <p className={styles.note}>{t("rework.evaluation.create.builtinMetrics.none")}</p>
        )}
      </div>

      <div className={styles.field}>
        <span className={styles.fieldLabel}>{t("rework.evaluation.create.metrics.label")}</span>
        <p className={styles.note}>{t("rework.evaluation.create.metrics.help")}</p>
        <div className={styles.caseList}>
          {customMetrics.map((row, idx) => (
            <div key={row.id} className={styles.caseCard}>
              <div className={styles.caseCardHead}>
                <span className={styles.muted}>{t("rework.evaluation.create.metrics.n", { n: idx + 1 })}</span>
                <IconButton
                  color="error"
                  variant="icon"
                  size="small"
                  icon={{ category: "outlined", type: "delete" }}
                  aria-label={t("rework.evaluation.create.metrics.remove")}
                  onClick={() => removeCustomMetric(row.id)}
                />
              </div>
              <TextInput
                label={t("rework.evaluation.create.metrics.name")}
                value={row.name}
                placeholder={t("rework.evaluation.create.metrics.namePlaceholder")}
                onChange={(e) => updateCustomMetric(row.id, "name", e.target.value)}
              />
              <TextArea
                label={t("rework.evaluation.create.metrics.criteria")}
                value={row.criteria}
                rows={2}
                placeholder={t("rework.evaluation.create.metrics.criteriaPlaceholder")}
                onChange={(e) => updateCustomMetric(row.id, "criteria", e.target.value)}
              />
              <div className={styles.field}>
                <span className={styles.fieldLabel}>{t("rework.evaluation.create.metrics.parameters")}</span>
                <div className={styles.paramRow}>
                  {CUSTOM_METRIC_PARAMETERS.map((param) => (
                    <label key={param.value} className={styles.paramOption}>
                      <Switch
                        checked={row.parameters.includes(param.value)}
                        onChange={() => toggleCustomMetricParam(row.id, param.value)}
                      />
                      {t(`rework.evaluation.create.metrics.parameterOptions.${param.key}`)}
                    </label>
                  ))}
                </div>
              </div>
              <TextInput
                type="number"
                min={0}
                max={1}
                step={0.1}
                label={t("rework.evaluation.create.metrics.threshold")}
                value={row.threshold}
                onChange={(e) => updateCustomMetric(row.id, "threshold", e.target.value)}
              />
            </div>
          ))}
          <div>
            <Button
              color="on-surface"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "add" }}
              onClick={addCustomMetric}
            >
              {t("rework.evaluation.create.metrics.add")}
            </Button>
          </div>
        </div>
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
        <div className={styles.recapRow}>
          <span className={styles.muted}>{t("rework.evaluation.create.recap.metrics")}</span>
          <span className={styles.recapValue}>{selectedMetrics.length}</span>
        </div>
        {validCustomMetrics.length > 0 && (
          <div className={styles.recapRow}>
            <span className={styles.muted}>{t("rework.evaluation.create.recap.customMetrics")}</span>
            <span className={styles.recapValue}>{validCustomMetrics.length}</span>
          </div>
        )}
      </div>

      <div className={styles.nav}>
        <Button color="on-surface" variant="text" size="medium" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          disabled={!canSubmit || isLoading}
          onClick={handleSubmit}
        >
          {isLoading ? t("rework.evaluation.runCreate.starting") : t("rework.evaluation.runCreate.submit")}
        </Button>
      </div>
    </div>
  );
}
