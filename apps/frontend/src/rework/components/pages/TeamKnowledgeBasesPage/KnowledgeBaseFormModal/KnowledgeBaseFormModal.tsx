// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Select from "@shared/molecules/Select/Select";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import SettingsModal from "@shared/organisms/SettingsModal/SettingsModal";
import ScheduleField, { type IntervalScheduleValue } from "@shared/molecules/ScheduleField/ScheduleField";
import Switch from "@shared/atoms/Switch/Switch";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useCreateKnowledgeBaseMutation,
  useUpdateKnowledgeBaseMutation,
  useAvailableKnowledgeBaseDefinitionsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  CreateInstance,
  KnowledgeBaseInstance,
  FieldSpec,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TuningFieldRenderer } from "../../TeamAgentsPage/AgentFormModal/TuningFieldRenderer";
import styles from "./KnowledgeBaseFormModal.module.css";
const prefix = "rework.knowledgeBases.form";

// Public configuration and provisioned secret references have separate API fields.
export function buildCreatePayload(input: {
  definitionId: string;
  folderName: string;
  fields: FieldSpec[];
  values: Record<string, unknown>;
  schedule: IntervalScheduleValue;
  suspended: boolean;
  profile: string;
}): CreateInstance {
  const config: Record<string, unknown> = {};
  const credential_refs: Record<string, string> = {};
  for (const field of input.fields) {
    const value = input.values[field.key];
    if (value === undefined || value === "") continue;
    if (field.type === "secret") {
      if (typeof value === "string") credential_refs[field.key] = value;
    } else config[field.key] = value;
  }
  return {
    definition_id: input.definitionId,
    name: input.folderName,
    config,
    credential_refs,
    interval_seconds: input.schedule.every_seconds,
    paused: input.suspended,
    profile: input.profile,
  };
}
export function readInstanceValues(instance: KnowledgeBaseInstance): Record<string, unknown> {
  return Object.fromEntries(
    instance.config_schema.fields
      .map((field) => [
        field.key,
        field.type === "secret"
          ? Reflect.get(instance.credential_refs, field.key)
          : Reflect.get(instance.config, field.key),
      ])
      .filter(([, value]) => value !== undefined),
  );
}
export interface KnowledgeBaseFormModalProps {
  open: boolean;
  teamId: string;
  instance?: KnowledgeBaseInstance;
  onClose: () => void;
}
export default function KnowledgeBaseFormModal({ open, teamId, instance, onClose }: KnowledgeBaseFormModalProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const definitions = useAvailableKnowledgeBaseDefinitionsQuery(
    { spaceId: teamId },
    { skip: !open || !!instance, refetchOnMountOrArgChange: true },
  );
  const [create, creating] = useCreateKnowledgeBaseMutation();
  const [update, updating] = useUpdateKnowledgeBaseMutation();
  const [name, setName] = useState("");
  const [definitionId, setDefinitionId] = useState("");
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [schedule, setSchedule] = useState<IntervalScheduleValue>({ type: "interval", every_seconds: 86400 });
  const [suspended, setSuspended] = useState(false);
  const [profile, setProfile] = useState("medium");
  const saving = useRef(false);
  const busy = creating.isLoading || updating.isLoading;
  const selected = definitions.currentData?.find((row) => row.definition.id === definitionId);
  const schema = instance?.config_schema ?? selected?.definition.config_schema;
  useEffect(() => {
    if (!open) return;
    setName(instance?.name ?? "");
    setDefinitionId(instance?.definition_id ?? "");
    setSchedule({ type: "interval", every_seconds: instance?.interval_seconds ?? 86400 });
    setSuspended(instance?.paused ?? false);
    setProfile(instance?.profile ?? "medium");
  }, [open, instance]);
  useEffect(() => {
    if (!open) return;
    setValues(
      instance
        ? readInstanceValues(instance)
        : Object.fromEntries(
            (schema?.fields ?? [])
              .filter((field) => field.type !== "secret" && field.default != null)
              .map((field) => [field.key, field.default]),
          ),
    );
  }, [open, instance, schema]);
  const fields = schema?.fields ?? [];
  const blocked =
    !name.trim() ||
    !definitionId ||
    (!instance &&
      (!selected ||
        fields.some(
          (field) =>
            field.key !== "profile" && field.required && (values[field.key] == null || values[field.key] === ""),
        )));
  const save = async () => {
    if (saving.current || blocked) return;
    saving.current = true;
    try {
      if (instance)
        await update({
          id: instance.id,
          updateInstance: { paused: suspended, interval_seconds: schedule.every_seconds },
        }).unwrap();
      else
        await create({
          spaceId: teamId,
          createInstance: buildCreatePayload({
            definitionId,
            folderName: name.trim(),
            fields,
            values: { ...values, profile },
            schedule,
            suspended,
            profile,
          }),
        }).unwrap();
      showSuccess({ summary: t(`${prefix}.${instance ? "saved" : "created"}`, { name: name.trim() }) });
      onClose();
    } catch {
      showError({ summary: t(`${prefix}.saveFailed`, { name: name.trim() }) });
    } finally {
      saving.current = false;
    }
  };
  if (!open) return null;
  const identityFields = (
    <>
      <TextInput
        label={t(`${prefix}.name`)}
        value={name}
        onChange={(event) => setName(event.target.value)}
        disabled={!!instance || busy}
      />
      <Select<string>
        size="medium"
        label={t(`${prefix}.synchronizedBy`)}
        value={definitionId}
        onChange={setDefinitionId}
        disabled={!!instance || busy || definitions.isError}
        options={
          instance
            ? [{ key: instance.definition_id, value: instance.definition_id, label: instance.definition_name }]
            : [
                {
                  key: "",
                  value: "",
                  label: t(
                    `${prefix}.${definitions.isError ? "definitionsFailed" : definitions.isLoading ? "definitionsLoading" : !definitions.currentData?.length ? "noDefinitions" : "pickOne"}`,
                  ),
                },
                ...(definitions.currentData ?? []).map(({ definition, runtime_id }) => ({
                  key: definition.id,
                  value: definition.id,
                  label: `${definition.name} (${runtime_id})`,
                })),
              ]
        }
      />
    </>
  );
  if (!instance && !definitionId)
    return (
      <Dialog
        open
        title={t(`${prefix}.title`)}
        confirmLabel={t(`${prefix}.submit`)}
        confirmDisabled={blocked}
        onConfirm={save}
        onCancel={onClose}
      >
        <div className={styles.form}>{identityFields}</div>
      </Dialog>
    );
  return (
    <SettingsModal
      isOpen
      onClose={onClose}
      id="knowledge-base-form-modal"
      title={t(`${prefix}.${instance ? "titleEdit" : "title"}`, { name: instance?.name })}
      subtitle={instance ? t(`${prefix}.sourceImmutable`) : undefined}
      actions={
        <>
          <Button color="primary" variant="text" size="medium" onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button color="primary" variant="filled" size="medium" onClick={save} disabled={blocked || busy}>
            {t(instance ? "common.save" : `${prefix}.submit`)}
          </Button>
        </>
      }
    >
      <div className={styles.form}>
        {identityFields}
        {definitionId && (
          <>
            <fieldset className={styles.zone}>
              <legend className={styles.zoneLegend}>{t(`${prefix}.zoneFred`)}</legend>
              <ScheduleField
                value={schedule}
                onChange={setSchedule}
                disabled={busy}
                explanation={t(`${prefix}.scheduleExplanation`)}
              />
              <label className={styles.suspended}>
                <Switch checked={suspended} onChange={(event) => setSuspended(event.target.checked)} disabled={busy} />
                {t(`${prefix}.suspended`)}
              </label>
              <Select<string>
                size="medium"
                label={t(`${prefix}.profile`)}
                value={profile}
                onChange={setProfile}
                disabled={!!instance || busy}
                options={["fast", "medium", "rich"].map((value) => ({
                  key: value,
                  value,
                  label: t(`${prefix}.profiles.${value}`),
                }))}
              />
            </fieldset>
            <fieldset className={styles.zone}>
              <legend className={styles.zoneLegend}>{t(`${prefix}.zoneSource`)}</legend>
              {fields
                .filter((field) => field.key !== "profile")
                .map((field) =>
                  field.type === "secret" ? (
                    <Select<string>
                      size="medium"
                      key={field.key}
                      label={field.title || field.key}
                      value={String(values[field.key] ?? "")}
                      onChange={(value) => setValues((current) => ({ ...current, [field.key]: value }))}
                      disabled={!!instance || busy}
                      options={[
                        { key: "", value: "", label: t(`${prefix}.credentialReference`) },
                        ...(instance
                          ? [String(values[field.key] ?? "")].filter(Boolean)
                          : (selected?.credential_bindings ?? [])
                        ).map((value) => ({ key: value, value, label: value })),
                      ]}
                    />
                  ) : (
                    <TuningFieldRenderer
                      key={field.key}
                      field={field}
                      value={values[field.key]}
                      onChange={(key, value) => setValues((current) => ({ ...current, [key]: value }))}
                      disabled={!!instance || busy}
                      teamId={teamId}
                      allValues={values}
                    />
                  ),
                )}
            </fieldset>
          </>
        )}
      </div>
    </SettingsModal>
  );
}
