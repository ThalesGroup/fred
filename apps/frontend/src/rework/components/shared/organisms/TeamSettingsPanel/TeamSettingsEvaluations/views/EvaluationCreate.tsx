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

// Create an Evaluation — a name and its cases, nothing else. Starting a Run is a
// separate, later action (RFC AGENT-EVALUATION §8.5: "201, no run created"), and
// re-using an existing Evaluation is not done here at all: pick it from the list
// and start a run on it.
//
// Two exclusive ways to supply the cases: import a JSON file, or type them in.
// Re-using an existing name is not an error — the backend versions it (v1 → v2)
// and the new version becomes current (RFC §8.5, lines 396 and 528).

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextInput from "@shared/atoms/TextInput/TextInput";
import TextArea from "@shared/atoms/TextArea/TextArea";
import FileDropzone from "@shared/molecules/FileDropzone/FileDropzone";
import SelectableCard from "@shared/molecules/SelectableCard/SelectableCard";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  useCreateEvaluationEvaluationV1EvaluationsPostMutation,
  type EvaluationCase,
} from "../../../../../../../slices/evaluation/evaluationOpenApi";
import styles from "./EvaluationForms.module.css";

type SourceMode = "import" | "manual";

interface CaseRow {
  id: string;
  input: string;
  expected_output: string;
  external_id: string;
}

function newRow(): CaseRow {
  return { id: crypto.randomUUID(), input: "", expected_output: "", external_id: "" };
}

interface EvaluationCreateProps {
  teamId: string;
  onCancel: () => void;
  onCreated: (evaluationId: string, name: string) => void;
}

export default function EvaluationCreate({ teamId, onCancel, onCreated }: EvaluationCreateProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();

  const [mode, setMode] = useState<SourceMode>("import");
  const [name, setName] = useState("");
  const [importedCases, setImportedCases] = useState<CaseRow[]>([]);
  const [importError, setImportError] = useState<string | undefined>();
  const [manualCases, setManualCases] = useState<CaseRow[]>([newRow()]);

  const [createEvaluation, { isLoading }] = useCreateEvaluationEvaluationV1EvaluationsPostMutation();

  // The two modes are exclusive: only the active one contributes cases, so
  // switching back and forth never silently mixes a stale import into a typed set.
  const activeCases = (mode === "import" ? importedCases : manualCases).filter((c) => c.input.trim());
  const canSubmit = !!name.trim() && activeCases.length > 0;

  const addRow = () => setManualCases((p) => [...p, newRow()]);
  const removeRow = (id: string) => setManualCases((p) => p.filter((r) => r.id !== id));
  const updateRow = (id: string, field: keyof CaseRow, value: string) =>
    setManualCases((p) => p.map((r) => (r.id === id ? { ...r, [field]: value } : r)));

  const parseJsonFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) ?? "";
      setImportError(undefined);
      try {
        const data = JSON.parse(text);
        const arr = Array.isArray(data) ? data : (data.cases ?? []);
        const rows: CaseRow[] = arr.map((item: Record<string, unknown>) => ({
          id: crypto.randomUUID(),
          input: String(item.input ?? ""),
          expected_output: String(item.expected_output ?? ""),
          external_id: String(item.external_id ?? ""),
        }));
        if (rows.length > 200) {
          setImportError(t("rework.evaluation.create.import.tooMany"));
          return;
        }
        if (rows.length === 0) {
          setImportError(t("rework.evaluation.create.import.empty"));
          return;
        }
        setImportedCases(rows);
        // A file named usage-arxivai.json is almost always meant to be the
        // evaluation's name — offer it, but never overwrite what was typed.
        if (!name.trim()) setName(file.name.replace(/\.json$/i, ""));
      } catch {
        setImportError(t("rework.evaluation.create.import.error"));
      }
    };
    reader.readAsText(file);
  };

  const handleSubmit = async () => {
    const caseInputs: EvaluationCase[] = activeCases.map((c) => ({
      input: c.input,
      expected_output: c.expected_output || null,
      external_id: c.external_id || null,
    }));
    try {
      const evaluation = await createEvaluation({
        createEvaluationRequest: {
          team_id: teamId,
          name: name.trim(),
          origin: mode === "import" ? "upload" : "manual",
          cases: caseInputs,
        },
      }).unwrap();
      showSuccess({
        summary: t("rework.evaluation.evaluationCreate.success", {
          name: evaluation.name,
          version: evaluation.version,
        }),
      });
      onCreated(evaluation.evaluation_id, evaluation.name);
    } catch (e) {
      const detail = (e as { data?: { detail?: unknown } })?.data?.detail;
      showError({
        summary: typeof detail === "string" ? detail : t("rework.evaluation.evaluationCreate.error"),
      });
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{t("rework.evaluation.evaluationCreate.title")}</h1>
          <p className={styles.subtitle}>{t("rework.evaluation.evaluationCreate.description")}</p>
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
        <div className={styles.field}>
          <span className={styles.fieldLabel}>{t("rework.evaluation.evaluationCreate.mode.label")}</span>
          <div className={styles.cardRow}>
            <SelectableCard
              selected={mode === "import"}
              title={t("rework.evaluation.evaluationCreate.mode.import.title")}
              description={t("rework.evaluation.evaluationCreate.mode.import.desc")}
              onSelect={() => setMode("import")}
            />
            <SelectableCard
              selected={mode === "manual"}
              title={t("rework.evaluation.evaluationCreate.mode.manual.title")}
              description={t("rework.evaluation.evaluationCreate.mode.manual.desc")}
              onSelect={() => setMode("manual")}
            />
          </div>
        </div>

        <div className={styles.row}>
          <TextInput
            label={t("rework.evaluation.evaluationCreate.name.label")}
            value={name}
            required
            placeholder={t("rework.evaluation.evaluationCreate.name.placeholder")}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <p className={styles.note}>{t("rework.evaluation.evaluationCreate.versionNote")}</p>

        {mode === "import" && (
          <div className={styles.field}>
            <span className={styles.fieldLabel}>{t("rework.evaluation.create.import.json")}</span>
            <FileDropzone
              accept=".json"
              hint={t("rework.evaluation.create.import.dropHint", { mode: "JSON" })}
              subHint={t("rework.evaluation.create.import.dropSub")}
              error={importError}
              onFile={parseJsonFile}
            />
            {importedCases.length > 0 && (
              <span className={styles.success}>
                {t("rework.evaluation.create.import.jsonImported", { count: importedCases.length })}
              </span>
            )}
          </div>
        )}

        {mode === "manual" && (
          <div className={styles.field}>
            <span className={styles.fieldLabel}>{t("rework.evaluation.create.manual.label")}</span>
            <div className={styles.caseList}>
              {manualCases.map((row, idx) => (
                <div key={row.id} className={styles.caseCard}>
                  <div className={styles.caseCardHead}>
                    <span className={styles.muted}>{t("rework.evaluation.create.case.n", { n: idx + 1 })}</span>
                    <IconButton
                      color="error"
                      variant="icon"
                      size="small"
                      icon={{ category: "outlined", type: "delete" }}
                      aria-label={t("rework.evaluation.create.case.remove")}
                      disabled={manualCases.length === 1}
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

        {activeCases.length > 0 && (
          <span className={styles.muted}>
            {t("rework.evaluation.create.import.total", { count: activeCases.length })}
          </span>
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
          {isLoading ? t("rework.evaluation.evaluationCreate.saving") : t("rework.evaluation.evaluationCreate.submit")}
        </Button>
      </div>
    </div>
  );
}
