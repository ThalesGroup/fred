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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDispatch } from "react-redux";
import { taskRegistered } from "@rework/features/tasks/taskSlice";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextInput from "@shared/atoms/TextInput/TextInput";
import TextArea from "@shared/atoms/TextArea/TextArea";
import Select from "@shared/molecules/Select/Select";
import Stepper from "@shared/molecules/Stepper/Stepper";
import SelectableCard from "@shared/molecules/SelectableCard/SelectableCard";
import FileDropzone from "@shared/molecules/FileDropzone/FileDropzone";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { OptionModel } from "@models/Option.model.ts";
import { useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery } from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useCreateCampaignEvaluationV1CampaignsPostMutation,
  type EvaluationCaseInput,
} from "../../../../../../../slices/evaluation/evaluationOpenApi";
import styles from "./EvaluationCampaignCreate.module.css";

type TargetKind = "managed_instance" | "runtime_agent";

interface CaseRow {
  id: string;
  input: string;
  expected_output: string;
  external_id: string;
}

function newRow(): CaseRow {
  return { id: crypto.randomUUID(), input: "", expected_output: "", external_id: "" };
}

interface EvaluationCampaignCreateProps {
  teamId: string;
  onCancel: () => void;
  onCreated: (campaignId: string) => void;
}

export default function EvaluationCampaignCreate({ teamId, onCancel, onCreated }: EvaluationCampaignCreateProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const dispatch = useDispatch();

  const STEPS = [
    t("rework.evaluation.create.steps.target"),
    t("rework.evaluation.create.steps.dataset"),
    t("rework.evaluation.create.steps.policy"),
  ];

  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [targetKind, setTargetKind] = useState<TargetKind>("managed_instance");
  const [agentInstanceId, setAgentInstanceId] = useState("");
  const [runtimeId, setRuntimeId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [datasetName, setDatasetName] = useState("");
  const [datasetVersion, setDatasetVersion] = useState("");
  const [jsonCases, setJsonCases] = useState<CaseRow[]>([]);
  const [csvCases, setCsvCases] = useState<CaseRow[]>([]);
  const [jsonError, setJsonError] = useState<string | undefined>();
  const [csvError, setCsvError] = useState<string | undefined>();
  const [cases, setCases] = useState<CaseRow[]>([newRow()]);
  const [judgeProfileId, setJudgeProfileId] = useState("mistral-small");
  const [maxConcurrency, setMaxConcurrency] = useState(3);
  const [caseTimeout, setCaseTimeout] = useState(120);

  const { data: instances, isLoading: instancesLoading } =
    useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery({ teamId }, { skip: !teamId });

  const [createCampaign, { isLoading: isCreating }] = useCreateCampaignEvaluationV1CampaignsPostMutation();

  const instanceOptions: OptionModel<string>[] = (instances ?? []).map((inst) => ({
    value: inst.agent_instance_id,
    label: inst.display_name,
    key: inst.agent_instance_id,
  }));

  const canNext0 = !!name.trim() && (targetKind === "managed_instance" ? !!agentInstanceId : !!runtimeId && !!agentId);
  const allCases = [...cases, ...jsonCases, ...csvCases].filter((c) => c.input.trim());
  const canNext1 = !!datasetName.trim() && allCases.length > 0;

  const addRow = () => setCases((p) => [...p, newRow()]);
  const removeRow = (id: string) => setCases((p) => p.filter((r) => r.id !== id));
  const updateRow = (id: string, field: keyof CaseRow, value: string) =>
    setCases((p) => p.map((r) => (r.id === id ? { ...r, [field]: value } : r)));

  const parseFile = (file: File, setRows: (r: CaseRow[]) => void, setErr: (e?: string) => void) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) ?? "";
      setErr(undefined);
      try {
        let rows: CaseRow[];
        if (file.name.endsWith(".json")) {
          const data = JSON.parse(text);
          const arr = Array.isArray(data) ? data : (data.cases ?? []);
          rows = arr.map((item: Record<string, unknown>) => ({
            id: crypto.randomUUID(),
            input: String(item.input ?? ""),
            expected_output: String(item.expected_output ?? ""),
            external_id: String(item.external_id ?? ""),
          }));
        } else {
          rows = text
            .split("\n")
            .filter(Boolean)
            .slice(1)
            .map((line) => {
              const parts = line.split(",");
              return {
                id: crypto.randomUUID(),
                input: parts[0] ?? "",
                expected_output: parts[1] ?? "",
                external_id: parts[2] ?? "",
              };
            });
        }
        if (rows.length > 200) {
          setErr(t("rework.evaluation.create.import.tooMany"));
          return;
        }
        setRows(rows);
      } catch {
        setErr(t("rework.evaluation.create.import.error"));
      }
    };
    reader.readAsText(file);
  };

  const handleSubmit = async () => {
    const caseInputs: EvaluationCaseInput[] = allCases.map((c) => ({
      input: c.input,
      expected_output: c.expected_output || null,
      external_id: c.external_id || null,
    }));
    const target =
      targetKind === "managed_instance"
        ? { kind: "managed_instance" as const, agent_instance_id: agentInstanceId }
        : { kind: "runtime_agent" as const, runtime_id: runtimeId, agent_id: agentId };
    try {
      const result = await createCampaign({
        createEvaluationCampaignRequest: {
          name,
          team_id: teamId,
          target,
          dataset: { name: datasetName, version: datasetVersion || null, cases: caseInputs },
          profile: "auto",
          judge_profile_id: judgeProfileId,
          execution: { max_concurrency: maxConcurrency, case_timeout_seconds: caseTimeout },
        },
      }).unwrap();
      // Register the launched run into the shared task store so it streams via
      // useTaskSseManager and surfaces in the global TaskTray immediately.
      if (result.task_id) {
        dispatch(
          taskRegistered({
            taskId: result.task_id,
            kind: "evaluation",
            target: { type: "evaluation_campaign", id: result.campaign_id, label: name },
          }),
        );
      }
      showSuccess({ summary: t("rework.evaluation.create.success") });
      onCreated(result.campaign_id);
    } catch (e) {
      const detail = (e as { data?: { detail?: unknown } })?.data?.detail;
      showError({
        summary: typeof detail === "string" ? detail : t("rework.evaluation.create.error"),
      });
    }
  };

  const recapRows: { label: string; value: string }[] = [
    { label: t("rework.evaluation.create.recap.campaign"), value: name || "—" },
    {
      label: t("rework.evaluation.create.recap.targetType"),
      value:
        targetKind === "managed_instance"
          ? t("rework.evaluation.create.recap.managed")
          : t("rework.evaluation.create.recap.runtime"),
    },
    ...(targetKind === "managed_instance"
      ? [{ label: t("rework.evaluation.create.recap.instance"), value: agentInstanceId || "—" }]
      : [
          { label: t("rework.evaluation.create.recap.runtimeId"), value: runtimeId || "—" },
          { label: t("rework.evaluation.create.recap.agent"), value: agentId || "—" },
        ]),
    {
      label: t("rework.evaluation.create.recap.dataset"),
      value: `${datasetName}${datasetVersion ? ` v${datasetVersion}` : ""}` || "—",
    },
    { label: t("rework.evaluation.create.recap.cases"), value: `${allCases.length}` },
    { label: t("rework.evaluation.create.recap.judge"), value: judgeProfileId },
    { label: t("rework.evaluation.create.recap.concurrency"), value: `${maxConcurrency}` },
    { label: t("rework.evaluation.create.recap.timeout"), value: `${caseTimeout}s` },
    { label: t("rework.evaluation.create.recap.profile"), value: t("rework.evaluation.create.recap.profileAuto") },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{t("rework.evaluation.create.title")}</h1>
          <p className={styles.subtitle}>{t("rework.evaluation.create.description")}</p>
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

      <Stepper steps={STEPS} active={step} />

      {/* Step 0 — Target */}
      {step === 0 && (
        <div className={styles.section}>
          <TextInput
            label={t("rework.evaluation.create.name.label")}
            value={name}
            required
            placeholder={t("rework.evaluation.create.name.placeholder")}
            onChange={(e) => setName(e.target.value)}
          />

          <div className={styles.field}>
            <span className={styles.fieldLabel}>{t("rework.evaluation.create.targetKind.label")}</span>
            <div className={styles.cardRow}>
              <SelectableCard
                selected={targetKind === "managed_instance"}
                title={t("rework.evaluation.create.target.managed.title")}
                description={t("rework.evaluation.create.target.managed.desc")}
                onSelect={() => setTargetKind("managed_instance")}
              />
              <SelectableCard
                selected={targetKind === "runtime_agent"}
                title={t("rework.evaluation.create.target.runtime.title")}
                description={t("rework.evaluation.create.target.runtime.desc")}
                onSelect={() => setTargetKind("runtime_agent")}
              />
            </div>
          </div>

          {targetKind === "managed_instance" ? (
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
          ) : (
            <>
              <TextInput
                label={t("rework.evaluation.create.runtime.label")}
                value={runtimeId}
                required
                placeholder={t("rework.evaluation.create.runtime.placeholder")}
                onChange={(e) => setRuntimeId(e.target.value)}
              />
              <TextInput
                label={t("rework.evaluation.create.agent.label")}
                value={agentId}
                required
                placeholder={t("rework.evaluation.create.agent.placeholder")}
                onChange={(e) => setAgentId(e.target.value)}
              />
            </>
          )}

          <p className={styles.note}>{t("rework.evaluation.create.securityNote")}</p>
        </div>
      )}

      {/* Step 1 — Dataset */}
      {step === 1 && (
        <div className={styles.section}>
          <div className={styles.row}>
            <TextInput
              label={t("rework.evaluation.create.dataset.name")}
              value={datasetName}
              required
              onChange={(e) => setDatasetName(e.target.value)}
            />
            <TextInput
              label={t("rework.evaluation.create.dataset.version")}
              value={datasetVersion}
              onChange={(e) => setDatasetVersion(e.target.value)}
            />
          </div>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>{t("rework.evaluation.create.manual.label")}</span>
            <div className={styles.caseList}>
              {cases.map((row, idx) => (
                <div key={row.id} className={styles.caseCard}>
                  <div className={styles.caseCardHead}>
                    <span className={styles.muted}>{t("rework.evaluation.create.case.n", { n: idx + 1 })}</span>
                    <IconButton
                      color="error"
                      variant="icon"
                      size="small"
                      icon={{ category: "outlined", type: "delete" }}
                      aria-label={t("rework.evaluation.create.case.remove")}
                      disabled={cases.length === 1}
                      onClick={() => removeRow(row.id)}
                    />
                  </div>
                  <TextInput
                    label={t("rework.evaluation.create.case.input")}
                    value={row.input}
                    required
                    onChange={(e) => updateRow(row.id, "input", e.target.value)}
                  />
                  <TextArea
                    label={t("rework.evaluation.create.case.expected")}
                    value={row.expected_output}
                    rows={2}
                    onChange={(e) => updateRow(row.id, "expected_output", e.target.value)}
                  />
                </div>
              ))}
              <div>
                <Button
                  color="on-surface"
                  variant="outlined"
                  size="small"
                  icon={{ category: "outlined", type: "add" }}
                  onClick={addRow}
                >
                  {t("rework.evaluation.create.case.add")}
                </Button>
              </div>
            </div>
          </div>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>{t("rework.evaluation.create.import.json")}</span>
            <FileDropzone
              accept=".json"
              hint={t("rework.evaluation.create.import.dropHint", { mode: "JSON" })}
              subHint={t("rework.evaluation.create.import.dropSub")}
              error={jsonError}
              onFile={(f) => parseFile(f, setJsonCases, setJsonError)}
            />
            {jsonCases.length > 0 && (
              <span className={styles.success}>
                {t("rework.evaluation.create.import.jsonImported", { count: jsonCases.length })}
              </span>
            )}
          </div>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>{t("rework.evaluation.create.import.csv")}</span>
            <FileDropzone
              accept=".csv"
              hint={t("rework.evaluation.create.import.dropHint", { mode: "CSV" })}
              subHint={t("rework.evaluation.create.import.dropSub")}
              error={csvError}
              onFile={(f) => parseFile(f, setCsvCases, setCsvError)}
            />
            {csvCases.length > 0 && (
              <span className={styles.success}>
                {t("rework.evaluation.create.import.csvImported", { count: csvCases.length })}
              </span>
            )}
          </div>

          {allCases.length > 0 && (
            <span className={styles.muted}>
              {t("rework.evaluation.create.import.total", { count: allCases.length })}
            </span>
          )}
        </div>
      )}

      {/* Step 2 — Policy */}
      {step === 2 && (
        <div className={styles.section}>
          <TextInput
            label={t("rework.evaluation.create.judge.label")}
            value={judgeProfileId}
            explanation={t("rework.evaluation.create.judge.help")}
            onChange={(e) => setJudgeProfileId(e.target.value)}
          />
          <div className={styles.row}>
            <TextInput
              label={t("rework.evaluation.create.concurrency.label")}
              type="number"
              min={1}
              max={20}
              value={String(maxConcurrency)}
              onChange={(e) => setMaxConcurrency(Number(e.target.value))}
            />
            <TextInput
              label={t("rework.evaluation.create.timeout.label")}
              type="number"
              min={30}
              max={600}
              value={String(caseTimeout)}
              onChange={(e) => setCaseTimeout(Number(e.target.value))}
            />
          </div>

          <div className={styles.recap}>
            <span className={styles.recapTitle}>{t("rework.evaluation.create.recap.title")}</span>
            {recapRows.map((r) => (
              <div key={r.label} className={styles.recapRow}>
                <span className={styles.muted}>{r.label}</span>
                <span className={styles.recapValue}>{r.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Navigation */}
      <div className={styles.nav}>
        <Button
          color="on-surface"
          variant="text"
          size="medium"
          disabled={step === 0}
          onClick={() => setStep((s) => s - 1)}
        >
          {t("rework.evaluation.create.nav.prev")}
        </Button>
        {step < STEPS.length - 1 ? (
          <Button
            color="primary"
            variant="filled"
            size="medium"
            disabled={step === 0 ? !canNext0 : !canNext1}
            onClick={() => setStep((s) => s + 1)}
          >
            {t("rework.evaluation.create.nav.next")}
          </Button>
        ) : (
          <Button color="primary" variant="filled" size="medium" disabled={isCreating} onClick={handleSubmit}>
            {isCreating ? t("rework.evaluation.create.launching") : t("rework.evaluation.create.nav.launch")}
          </Button>
        )}
      </div>
    </div>
  );
}
