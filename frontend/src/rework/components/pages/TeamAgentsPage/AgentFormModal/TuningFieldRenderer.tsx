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

import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import type { ManagedAgentFieldSpec } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { SwitchRow } from "../AgentCreateEditModal/SwitchRow/SwitchRow.tsx";
import styles from "./TuningFieldRenderer.module.css";

type TuningFieldRendererProps = {
  field: ManagedAgentFieldSpec;
  value: unknown;
  onChange: (key: string, value: unknown) => void;
  disabled: boolean;
  error?: string;
};

export function TuningFieldRenderer({ field, value, onChange, disabled, error }: TuningFieldRendererProps) {
  if (field.ui?.hide) return null;

  const fieldValue = value ?? field.default ?? "";
  const label = `${field.title}${field.required ? " *" : ""}`;

  if (field.enum && field.enum.length > 0) {
    return (
      <div className={styles.field}>
        <label className={styles.label} htmlFor={`tuning-${field.key}`}>
          {label}
        </label>
        <select
          id={`tuning-${field.key}`}
          className={`${styles.select} ${error ? styles.selectError : ""}`}
          value={String(fieldValue)}
          onChange={(e) => onChange(field.key, e.target.value)}
          disabled={disabled}
        >
          {field.enum.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
        {field.description && <p className={styles.hint}>{field.description}</p>}
        {error && <p className={styles.error}>{error}</p>}
      </div>
    );
  }

  if (field.type === "boolean") {
    return (
      <div className={styles.field}>
        <SwitchRow
          label={field.title}
          description={field.description ?? ""}
          checked={Boolean(fieldValue)}
          onChange={(checked) => onChange(field.key, checked)}
        />
        {error && <p className={styles.error}>{error}</p>}
      </div>
    );
  }

  const isMultiline =
    field.ui?.multiline || field.ui?.textarea || field.type === "prompt" || field.type === "text-multiline";

  if (isMultiline) {
    return (
      <TextArea
        label={label}
        value={String(fieldValue)}
        rows={field.ui?.max_lines ?? 4}
        onChange={(e) => onChange(field.key, e.target.value)}
        disabled={disabled}
        error={error}
      />
    );
  }

  const inputType =
    field.type === "secret"
      ? "password"
      : field.type === "url"
        ? "url"
        : field.type === "number" || field.type === "integer"
          ? "number"
          : "text";

  return (
    <TextInput
      label={label}
      value={String(fieldValue)}
      type={inputType}
      min={field.min ?? undefined}
      max={field.max ?? undefined}
      onChange={(e) => onChange(field.key, inputType === "number" ? Number(e.target.value) : e.target.value)}
      disabled={disabled}
      required={field.required}
      error={error}
      explanation={field.description ?? undefined}
    />
  );
}
