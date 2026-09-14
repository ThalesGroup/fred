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

import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { Portal } from "@shared/utils/Portal.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useCreateKnowledgeBaseMutation,
  useKnowledgeBaseDefinitionsQuery,
  useKnowledgeBaseFieldsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import type {
  KnowledgeBaseInstanceCreate,
  ManagedAgentFieldSpec,
  RunCadence,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { TuningFieldRenderer } from "../../TeamAgentsPage/AgentFormModal/TuningFieldRenderer";
import styles from "./KnowledgeBaseFormModal.module.css";

/** Keys of the zone Fred declares itself; everything else is the author's. */
const CADENCE_KEY = "fred.cadence";
const SUSPENDED_KEY = "fred.suspended";

/** What one form submission asks the Control Plane for.
 *
 * Pure, and exported for its own test: the split between what Fred acts on and
 * what it merely carries is the whole contract here, and getting it wrong sends
 * a cadence to a source that has no idea what to do with it.
 */
export function buildCreatePayload(input: {
  definitionId: string;
  teamId: string;
  folderName: string;
  declaredConfigurationKeys: string[];
  values: Record<string, unknown>;
}): KnowledgeBaseInstanceCreate {
  const configuration = Object.fromEntries(
    input.declaredConfigurationKeys
      .map((key) => [key, input.values[key]] as const)
      .filter(([, value]) => value !== undefined && value !== ""),
  );
  return {
    definition_id: input.definitionId,
    team_id: input.teamId,
    folder_name: input.folderName,
    cadence: input.values[CADENCE_KEY] as RunCadence | undefined,
    suspended: Boolean(input.values[SUSPENDED_KEY]),
    configuration,
  };
}

export interface KnowledgeBaseFormModalProps {
  open: boolean;
  teamId: string;
  onClose: () => void;
}

export default function KnowledgeBaseFormModal({ open, teamId, onClose }: KnowledgeBaseFormModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();

  const [name, setName] = useState("");
  const [definitionId, setDefinitionId] = useState("");
  const [values, setValues] = useState<Record<string, unknown>>({});

  const {
    data: definitions,
    isError: definitionsFailed,
    isLoading: definitionsLoading,
  } = useKnowledgeBaseDefinitionsQuery({ teamId }, { skip: !open });
  const { data: fields } = useKnowledgeBaseFieldsQuery({ definitionId, teamId }, { skip: !open || !definitionId });
  const [createKnowledgeBase, { isLoading: isCreating }] = useCreateKnowledgeBaseMutation();

  useEffect(() => {
    if (open) {
      setName("");
      setDefinitionId("");
      setValues({});
    }
  }, [open]);

  // The empty option carries the state of the list itself, so "no Knowledge
  // Base is enabled" never looks like "the list could not be loaded".
  const definitionOptions = useMemo<OptionModel<string>[]>(() => {
    const emptyLabel = definitionsLoading
      ? "rework.knowledgeBases.form.definitionsLoading"
      : definitionsFailed
        ? "rework.knowledgeBases.form.definitionsFailed"
        : (definitions?.length ?? 0) === 0
          ? "rework.knowledgeBases.form.noDefinitions"
          : "rework.knowledgeBases.form.pickOne";
    return [
      { key: "", value: "", label: t(emptyLabel) },
      ...(definitions ?? []).map((definition) => ({
        key: definition.definition_id,
        value: definition.definition_id,
        label: definition.name,
      })),
    ];
  }, [definitions, definitionsFailed, definitionsLoading, t]);

  // A definition's declared defaults are what the form starts from, so a user
  // who changes nothing still submits what the author intended.
  useEffect(() => {
    if (!fields) return;
    const defaults: Record<string, unknown> = {};
    for (const field of [...(fields.platform_fields ?? []), ...(fields.configuration_fields ?? [])]) {
      if (field.default !== undefined && field.default !== null) defaults[field.key] = field.default;
    }
    setValues(defaults);
  }, [fields]);

  const trimmed = name.trim();
  const blocked = !trimmed || !definitionId;

  const handleCreate = async () => {
    if (blocked || isCreating) return;
    // One call, not two: creating the library, the instance, the pod's grant
    // over that library and its cadence is one transaction on the Control
    // Plane's side, or none of them happens.
    try {
      await createKnowledgeBase({
        knowledgeBaseInstanceCreate: buildCreatePayload({
          definitionId,
          teamId,
          folderName: trimmed,
          declaredConfigurationKeys: (fields?.configuration_fields ?? []).map((field) => field.key),
          values,
        }),
      }).unwrap();
      showSuccess({ summary: t("rework.knowledgeBases.form.created", { name: trimmed }) });
      onClose();
    } catch {
      showError({ summary: t("rework.knowledgeBases.form.createFailed", { name: trimmed }) });
    }
  };

  if (!open) return null;

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onClose}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-knowledge-base-title"
          onClick={(event) => event.stopPropagation()}
        >
          <div className={styles.body}>
            <div className={styles.header}>
              <p id="create-knowledge-base-title" className={styles.title}>
                {t("rework.knowledgeBases.form.title")}
              </p>
              <IconButton
                variant="icon"
                size="small"
                icon={{ category: "outlined", type: "close" }}
                aria-label={t("common.close")}
                onClick={onClose}
              />
            </div>

            <TextInput
              autoFocus
              label={t("rework.knowledgeBases.form.name")}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t("rework.knowledgeBases.form.namePlaceholder")}
              disabled={isCreating}
            />

            <Select<string>
              label={t("rework.knowledgeBases.form.synchronizedBy")}
              options={definitionOptions}
              value={definitionId}
              onChange={setDefinitionId}
              size="medium"
              disabled={isCreating || definitionsLoading || definitionsFailed || (definitions?.length ?? 0) === 0}
            />

            {/* Two zones, kept apart: what Fred declares and acts on, and what
                the author declared, which Fred only carries. */}
            {fields &&
              [
                { legend: t("rework.knowledgeBases.form.zoneFred"), specs: fields.platform_fields ?? [] },
                { legend: t("rework.knowledgeBases.form.zoneSource"), specs: fields.configuration_fields ?? [] },
              ].map(({ legend, specs }) =>
                specs.length === 0 ? null : (
                  <fieldset key={legend} className={styles.zone}>
                    <legend className={styles.zoneLegend}>{legend}</legend>
                    {specs.map((field) => (
                      <TuningFieldRenderer
                        key={field.key}
                        // The renderer is typed on the agent form's looser
                        // generated twin. Promoting it to a shared strict
                        // component is a convergence of its own, still owed.
                        field={field as unknown as ManagedAgentFieldSpec}
                        value={values[field.key]}
                        onChange={(key, value) => setValues((v) => ({ ...v, [key]: value }))}
                        disabled={isCreating}
                        teamId={teamId}
                        allValues={values}
                      />
                    ))}
                  </fieldset>
                ),
              )}
          </div>

          <div className={styles.actions}>
            <Button color="primary" variant="text" size="medium" onClick={onClose} disabled={isCreating}>
              {t("common.cancel")}
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              onClick={handleCreate}
              disabled={blocked || isCreating}
            >
              {t("rework.knowledgeBases.form.submit")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
