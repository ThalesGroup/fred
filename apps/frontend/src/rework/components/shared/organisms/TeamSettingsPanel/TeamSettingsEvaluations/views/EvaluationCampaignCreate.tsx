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
import SelectableCard from "@shared/molecules/SelectableCard/SelectableCard";
import FileDropzone from "@shared/molecules/FileDropzone/FileDropzone";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { OptionModel } from "@models/Option.model.ts";
import { useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery } from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useCreateCampaignEvaluationV1CampaignsPostMutation,
  useCreateDatasetEvaluationV1DatasetsPostMutation,
  useListDatasetsEvaluationV1DatasetsGetQuery,
  type DatasetCase,
} from "../../../../../../../slices/evaluation/evaluationOpenApi";
import styles from "./EvaluationCampaignCreate.module.css";

type DatasetChoice = "existing" | "new";
type NewDatasetSource = "json" | "manual";

interface CaseRow {
  id: string;
  input: string;
  expected_output: string;
}

function newRow(): CaseRow {
  return { id: crypto.randomUUID(), input: "", expected_output: "" };
}

interface EvaluationCampaignCreateProps {
  teamId: string;
  onCancel: () => void;
  onCreated: (campaignId: string) => void;
}

function extractErrorMessage(error: unknown, fallback: string): string {
  const data = (error as { data?: unknown } | undefined)?.data;
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail?: unknown }).detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
    }
  }
  return fallback;
}

export default function EvaluationCampaignCreate({ teamId, onCancel, onCreated }: EvaluationCampaignCreateProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const dispatch = useDispatch();

  const [agentInstanceId, setAgentInstanceId] = useState("");
  const [datasetChoice, setDatasetChoice] = useState<DatasetChoice>("existing");
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [newDatasetSource, setNewDatasetSource] = useState<NewDatasetSource>("json");
  const [jsonCases, setJsonCases] = useState<DatasetCase[]>([]);
  const [jsonFileName, setJsonFileName] = useState<string | undefined>();
  const [jsonError, setJsonError] = useState<string | undefined>();
  const [manualRows, setManualRows] = useState<CaseRow[]>([newRow()]);

  const { data: instances, isLoading: instancesLoading } =
    useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery({ teamId }, { skip: !teamId });
  const { data: datasetList, isLoading: datasetsLoading } = useListDatasetsEvaluationV1DatasetsGetQuery(
    { teamId },
    { skip: !teamId },
  );

  const [createDataset, { isLoading: isCreatingDataset }] = useCreateDatasetEvaluationV1DatasetsPostMutation();
  const [createCampaign, { isLoading: isCreatingCampaign }] = useCreateCampaignEvaluationV1CampaignsPostMutation();
  const isSubmitting = isCreatingDataset || isCreatingCampaign;

  const instanceOptions: OptionModel<string>[] = (instances ?? []).map((inst) => ({
    value: inst.agent_instance_id,
    label: inst.display_name,
    key: inst.agent_instance_id,
  }));

  const datasetOptions: OptionModel<string>[] = (datasetList?.datasets ?? []).map((ds) => ({
    value: ds.dataset_id,
    label: `${ds.name} (${ds.version}) — ${ds.case_count} cases`,
    key: ds.dataset_id,
  }));

  const manualCases: DatasetCase[] = manualRows
    .filter((r) => r.input.trim())
    .map((r) => ({ input: r.input, expected_output: r.expected_output.trim() || null }));

  const newCases = newDatasetSource === "json" ? jsonCases : manualCases;
  const newDatasetValid = newCases.length > 0;

  const canStart = !!agentInstanceId && (datasetChoice === "existing" ? !!selectedDatasetId : newDatasetValid);

  const addRow = () => setManualRows((p) => [...p, newRow()]);
  const removeRow = (id: string) => setManualRows((p) => p.filter((r) => r.id !== id));
  const updateRow = (id: string, field: keyof CaseRow, value: string) =>
    setManualRows((p) => p.map((r) => (r.id === id ? { ...r, [field]: value } : r)));

  const parseJsonFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) ?? "";
      setJsonError(undefined);
      setJsonCases([]);
      let data: unknown;
      try {
        data = JSON.parse(text);
      } catch {
        setJsonError(t("rework.evaluation.create.import.invalidJson"));
        return;
      }
      if (!Array.isArray(data)) {
        setJsonError(t("rework.evaluation.create.import.mustBeArray"));
        return;
      }
      if (data.length === 0) {
        setJsonError(t("rework.evaluation.create.import.empty"));
        return;
      }
      if (data.length > 200) {
        setJsonError(t("rework.evaluation.create.import.tooMany"));
        return;
      }
      const cases: DatasetCase[] = [];
      for (const item of data as unknown[]) {
        const input = (item as Record<string, unknown> | null)?.input;
        if (typeof input !== "string" || !input.trim()) {
          setJsonError(t("rework.evaluation.create.import.missingInput"));
          return;
        }
        const expected = (item as Record<string, unknown>).expected_output;
        cases.push({ input, expected_output: typeof expected === "string" ? expected : null });
      }
      setJsonCases(cases);
      setJsonFileName(file.name);
    };
    reader.readAsText(file);
  };

  const handleSubmit = async () => {
    let datasetId = selectedDatasetId;
    let justCreatedDataset = false;

    if (datasetChoice === "new") {
      try {
        const created = await createDataset({
          createDatasetRequest: {
            team_id: teamId,
            origin: newDatasetSource === "json" ? "upload" : "manual",
            source_filename: newDatasetSource === "json" ? (jsonFileName ?? null) : null,
            cases: newCases,
          },
        }).unwrap();
        datasetId = created.dataset_id;
        justCreatedDataset = true;
      } catch (e) {
        showError({
          summary: extractErrorMessage(e, t("rework.evaluation.create.datasetError")),
        });
        return;
      }
    }

    try {
      const result = await createCampaign({
        createEvaluationCampaignRequest: {
          team_id: teamId,
          target: { kind: "managed_instance", agent_instance_id: agentInstanceId },
          dataset_id: datasetId,
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
            target: { type: "evaluation_campaign", id: result.campaign_id, label: result.campaign_id },
          }),
        );
      }
      showSuccess({ summary: t("rework.evaluation.create.success") });
      onCreated(result.campaign_id);
    } catch (e) {
      const message = extractErrorMessage(e, t("rework.evaluation.create.campaignError"));
      showError({
        summary: justCreatedDataset ? t("rework.evaluation.create.campaignErrorDatasetSaved", { message }) : message,
      });
    }
  };

  const withExpected = newCases.filter((c) => c.expected_output).length;
  const previewLabel =
    newCases.length === 0
      ? undefined
      : withExpected === newCases.length
        ? t("rework.evaluation.create.dataset.preview.withExpected")
        : withExpected === 0
          ? t("rework.evaluation.create.dataset.preview.withoutExpected")
          : t("rework.evaluation.create.dataset.preview.partialExpected", {
              count: withExpected,
              total: newCases.length,
            });

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

      {/* Managed agent */}
      <div className={styles.section}>
        <Select<string>
          label={t("rework.evaluation.create.agent.label")}
          size="medium"
          options={instanceOptions}
          value={agentInstanceId}
          placeholder={
            instancesLoading
              ? t("rework.evaluation.create.agent.loading")
              : t("rework.evaluation.create.agent.placeholder")
          }
          onChange={setAgentInstanceId}
        />
      </div>

      {/* Dataset */}
      <div className={styles.section}>
        <div className={styles.field}>
          <span className={styles.fieldLabel}>{t("rework.evaluation.create.dataset.sectionLabel")}</span>
          <div className={styles.cardRow}>
            <SelectableCard
              selected={datasetChoice === "existing"}
              title={t("rework.evaluation.create.dataset.useExisting")}
              description={t("rework.evaluation.create.dataset.useExistingDesc")}
              onSelect={() => setDatasetChoice("existing")}
            />
            <SelectableCard
              selected={datasetChoice === "new"}
              title={t("rework.evaluation.create.dataset.createNew")}
              description={t("rework.evaluation.create.dataset.createNewDesc")}
              onSelect={() => setDatasetChoice("new")}
            />
          </div>
        </div>

        {datasetChoice === "existing" ? (
          <Select<string>
            label={t("rework.evaluation.create.dataset.select.label")}
            size="medium"
            options={datasetOptions}
            value={selectedDatasetId}
            placeholder={
              datasetsLoading
                ? t("rework.evaluation.create.dataset.select.loading")
                : datasetOptions.length === 0
                  ? t("rework.evaluation.create.dataset.select.empty")
                  : t("rework.evaluation.create.dataset.select.placeholder")
            }
            onChange={setSelectedDatasetId}
          />
        ) : (
          <>
            <div className={styles.cardRow}>
              <SelectableCard
                selected={newDatasetSource === "json"}
                title={t("rework.evaluation.create.dataset.sourceJson")}
                description=""
                onSelect={() => setNewDatasetSource("json")}
              />
              <SelectableCard
                selected={newDatasetSource === "manual"}
                title={t("rework.evaluation.create.dataset.sourceManual")}
                description=""
                onSelect={() => setNewDatasetSource("manual")}
              />
            </div>

            {newDatasetSource === "json" ? (
              <div className={styles.field}>
                <FileDropzone
                  accept=".json"
                  hint={t("rework.evaluation.create.import.dropHint")}
                  subHint={t("rework.evaluation.create.import.dropSub")}
                  error={jsonError}
                  onFile={parseJsonFile}
                />
                {jsonCases.length > 0 && (
                  <span className={styles.success}>
                    {t("rework.evaluation.create.import.imported", { count: jsonCases.length })}
                  </span>
                )}
              </div>
            ) : (
              <div className={styles.field}>
                <div className={styles.caseList}>
                  {manualRows.map((row, idx) => (
                    <div key={row.id} className={styles.caseCard}>
                      <div className={styles.caseCardHead}>
                        <span className={styles.muted}>{t("rework.evaluation.create.case.n", { n: idx + 1 })}</span>
                        <IconButton
                          color="error"
                          variant="icon"
                          size="small"
                          icon={{ category: "outlined", type: "delete" }}
                          aria-label={t("rework.evaluation.create.case.remove")}
                          disabled={manualRows.length === 1}
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
            )}

            {previewLabel && (
              <span className={styles.muted}>
                {t("rework.evaluation.create.dataset.preview.cases", { count: newCases.length })} — {previewLabel}
              </span>
            )}
          </>
        )}
      </div>

      {/* Start */}
      <div className={styles.nav}>
        <div />
        <Button
          color="primary"
          variant="filled"
          size="medium"
          disabled={!canStart || isSubmitting}
          onClick={handleSubmit}
        >
          {isSubmitting ? t("rework.evaluation.create.launching") : t("rework.evaluation.create.nav.start")}
        </Button>
      </div>
    </div>
  );
}
