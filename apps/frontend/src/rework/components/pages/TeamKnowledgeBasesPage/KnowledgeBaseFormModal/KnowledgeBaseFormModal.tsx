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
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import SettingsModal from "@shared/organisms/SettingsModal/SettingsModal.tsx";
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
  KnowledgeBaseInstanceFields,
  KnowledgeBaseInstanceSummary,
  ManagedAgentFieldSpec,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import ScheduleField, { type IntervalScheduleValue } from "@shared/molecules/ScheduleField/ScheduleField.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { TuningFieldRenderer } from "../../TeamAgentsPage/AgentFormModal/TuningFieldRenderer";
import styles from "./KnowledgeBaseFormModal.module.css";

/** What a blank form starts from. Daily, because most sources change slowly
 *  and a user who wants otherwise says so. */
const DEFAULT_SCHEDULE: IntervalScheduleValue = { type: "interval", every_seconds: 86400 };

/** What one form submission asks the Control Plane for.
 *
 * Pure, and exported for its own test: the split between what Fred acts on and
 * what it merely carries is the whole contract here. What Fred acts on is typed
 * — the schedule and whether it is suspended — and only the author's declared
 * fields travel as an untyped configuration.
 */
export function buildCreatePayload(input: {
  definitionId: string;
  teamId: string;
  folderName: string;
  declaredConfigurationKeys: string[];
  values: Record<string, unknown>;
  schedule: IntervalScheduleValue;
  suspended: boolean;
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
    schedule: input.schedule,
    suspended: input.suspended,
    configuration,
  };
}

/** What an existing base's settings show, in the same shape the form edits.
 *
 * Built from the declaration rather than filtered against it: a value is
 * carried only if a non-secret field asks for it, so a secret cannot reach the
 * screen even for the frame before the declaration lands. The Control Plane
 * strips those values anyway — one arriving here is a Fred that stopped.
 *
 * Only the author's fields: the schedule and the suspended flag are typed on
 * the instance itself, so they are read straight from it.
 */
export function readInstanceValues(
  instance: KnowledgeBaseInstanceSummary,
  fields?: KnowledgeBaseInstanceFields,
): Record<string, unknown> {
  const configuration = instance.configuration ?? {};
  const shown = (fields?.configuration_fields ?? [])
    .filter((field) => field.type !== "secret" && field.key in configuration)
    .map((field) => [field.key, configuration[field.key]] as const);
  return Object.fromEntries(shown);
}

/** What a blank form starts from, so a user who changes nothing still submits
 *  what the definition's author intended. */
function declaredDefaults(fields?: KnowledgeBaseInstanceFields): Record<string, unknown> {
  const defaults: Record<string, unknown> = {};
  for (const field of fields?.configuration_fields ?? []) {
    if (field.default !== undefined && field.default !== null) defaults[field.key] = field.default;
  }
  return defaults;
}

export interface KnowledgeBaseFormModalProps {
  open: boolean;
  teamId: string;
  /** Present to show that base's settings instead of a blank creation form.
   *  Read-only: the Control Plane has no route that updates an instance. */
  instance?: KnowledgeBaseInstanceSummary;
  onClose: () => void;
}

export default function KnowledgeBaseFormModal({ open, teamId, instance, onClose }: KnowledgeBaseFormModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();

  const [name, setName] = useState("");
  const [definitionId, setDefinitionId] = useState("");
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [schedule, setSchedule] = useState<IntervalScheduleValue>(DEFAULT_SCHEDULE);
  const [suspended, setSuspended] = useState(false);

  const viewing = instance !== undefined;

  const {
    data: definitions,
    isError: definitionsFailed,
    isLoading: definitionsLoading,
  } = useKnowledgeBaseDefinitionsQuery({ teamId }, { skip: !open || viewing });
  const { data: fields } = useKnowledgeBaseFieldsQuery({ definitionId, teamId }, { skip: !open || !definitionId });
  const [createKnowledgeBase, { isLoading: isCreating }] = useCreateKnowledgeBaseMutation();

  // Opening is what seeds the form: either the base being shown, or nothing.
  useEffect(() => {
    if (!open) return;
    setName(instance?.library_name ?? "");
    setDefinitionId(instance?.definition_id ?? "");
  }, [open, instance]);

  // The values follow the declaration, which arrives after the form is on
  // screen: an existing base shows its own, a new one the author's defaults.
  useEffect(() => {
    if (!open) return;
    setValues(instance ? readInstanceValues(instance, fields) : declaredDefaults(fields));
  }, [open, instance, fields]);

  // The empty option carries the state of the list itself, so "no Knowledge
  // Base is enabled" never looks like "the list could not be loaded".
  const definitionOptions = useMemo<OptionModel<string>[]>(() => {
    if (instance) {
      return [{ key: instance.definition_id, value: instance.definition_id, label: instance.definition_name }];
    }
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
  }, [definitions, definitionsFailed, definitionsLoading, instance, t]);

  const trimmed = name.trim();
  const blocked = !trimmed || !definitionId;
  const frozen = viewing || isCreating;
  // Until a source is chosen there is no form to show, only the question of
  // which one — and a full-page takeover to ask it is a screen of empty space.
  const chosen = viewing || definitionId !== "";

  const handleCreate = async () => {
    if (blocked || isCreating) return;
    // One call, not two: creating the library, the instance, the pod's grant
    // over that library and its cadence is one transaction on the Control
    // Plane's side, or none of them happens.
    try {
      await createKnowledgeBase({
        knowledgeBaseInstanceCreate: buildCreatePayload({
          schedule,
          suspended,
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

  // Before a source is chosen there is no form, only two questions — which is
  // what the app's central Dialog is for. Choosing one turns the panel into the
  // settings page that renders what that source declared.
  if (!chosen) {
    return (
      <Dialog
        open
        title={t("rework.knowledgeBases.form.title")}
        confirmLabel={t("rework.knowledgeBases.form.submit")}
        confirmDisabled={blocked}
        onConfirm={handleCreate}
        onCancel={onClose}
      >
        <div className={styles.form}>
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
        </div>
      </Dialog>
    );
  }

  return (
    <SettingsModal
      isOpen={open}
      onClose={onClose}
      id="knowledge-base-form-modal"
      title={
        instance
          ? t("rework.knowledgeBases.form.titleEdit", { name: instance.library_name })
          : t("rework.knowledgeBases.form.title")
      }
      subtitle={viewing ? t("rework.knowledgeBases.form.subtitleReadOnly") : undefined}
      actions={
        <>
          <Button color="primary" variant="text" size="medium" onClick={onClose} disabled={isCreating}>
            {viewing ? t("common.close") : t("common.cancel")}
          </Button>
          {!viewing && (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              onClick={handleCreate}
              disabled={blocked || isCreating}
            >
              {t("rework.knowledgeBases.form.submit")}
            </Button>
          )}
        </>
      }
    >
      <div className={styles.form}>
        <TextInput
          autoFocus={!viewing}
          label={t("rework.knowledgeBases.form.name")}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("rework.knowledgeBases.form.namePlaceholder")}
          disabled={frozen}
        />

        <Select<string>
          label={t("rework.knowledgeBases.form.synchronizedBy")}
          options={definitionOptions}
          value={definitionId}
          onChange={setDefinitionId}
          size="medium"
          disabled={frozen || definitionsLoading || definitionsFailed || (!viewing && (definitions?.length ?? 0) === 0)}
        />

        {/* What Fred acts on is typed, so it is edited by its own component
            rather than rendered generically and fished back out by key. */}
        <fieldset className={styles.zone}>
          <legend className={styles.zoneLegend}>{t("rework.knowledgeBases.form.zoneFred")}</legend>
          <ScheduleField
            value={schedule}
            onChange={setSchedule}
            disabled={frozen}
            explanation={t("rework.knowledgeBases.form.scheduleExplanation")}
          />
          <label className={styles.suspended}>
            <Switch checked={suspended} onChange={(event) => setSuspended(event.target.checked)} disabled={frozen} />
            {t("rework.knowledgeBases.form.suspended")}
          </label>
        </fieldset>

        {/* The author's own fields, which Fred stores and never reads. */}
        {fields &&
          [{ legend: t("rework.knowledgeBases.form.zoneSource"), specs: fields.configuration_fields ?? [] }].map(
            ({ legend, specs }) =>
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
                      disabled={frozen}
                      teamId={teamId}
                      allValues={values}
                    />
                  ))}
                </fieldset>
              ),
          )}
      </div>
    </SettingsModal>
  );
}
