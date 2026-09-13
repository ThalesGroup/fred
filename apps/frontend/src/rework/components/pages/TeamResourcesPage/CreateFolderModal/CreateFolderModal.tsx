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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import { Portal } from "@shared/utils/Portal.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useCreateTagKnowledgeFlowV1TagsPostMutation } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import {
  useListKnowledgeBaseDefinitionsControlPlaneV1KnowledgeBasesDefinitionsGetQuery,
  useGetDefinitionFieldsControlPlaneV1KnowledgeBasesDefinitionsDefinitionIdFieldsGetQuery,
  useCreateKnowledgeBaseInstanceControlPlaneV1KnowledgeBasesInstancesPostMutation,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TuningFieldRenderer } from "../../TeamAgentsPage/AgentFormModal/TuningFieldRenderer";
import type { ManagedAgentFieldSpec } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { MAX_FOLDER_DEPTH, folderPathDepth } from "@shared/organisms/DocumentUploadDrawer/droppedPaths";
import styles from "./CreateFolderModal.module.css";

/** Keys of the zone Fred declares itself; everything else is the author's. */
const CADENCE_KEY = "fred.cadence";
const SUSPENDED_KEY = "fred.suspended";

interface CreateFolderModalProps {
  open: boolean;
  onClose: () => void;
  /** Parent folder full path, e.g. "CIR" or "CIR/Sub". `undefined` => top level. */
  parentPath?: string;
  /** Team id for a collaborative team; omit/undefined for the personal space. */
  teamId?: string;
  /**
   * Optional custom create handler. When provided it is used instead of creating a corpus
   * library (e.g. a team-rooted /fs `mkdir`); the corpus behaviour is the default.
   */
  onSubmit?: (name: string) => Promise<void>;
  onCreated: () => void;
}

/**
 * Small centred modal for the single "folder name" field. Replaces the old MUI
 * `LibraryCreateDrawer`. The header makes the destination explicit ("In CIR /"
 * or "At the top level") so top-level vs subfolder is never ambiguous.
 */
export default function CreateFolderModal({
  open,
  onClose,
  parentPath,
  teamId,
  onSubmit,
  onCreated,
}: CreateFolderModalProps) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [createTag, { isLoading }] = useCreateTagKnowledgeFlowV1TagsPostMutation();
  const [createInstance, { isLoading: isCreatingInstance }] =
    useCreateKnowledgeBaseInstanceControlPlaneV1KnowledgeBasesInstancesPostMutation();
  const [name, setName] = useState("");
  const [definitionId, setDefinitionId] = useState("");
  const [values, setValues] = useState<Record<string, unknown>>({});

  // A synchronized folder lives at the top level and owns its whole subtree, so
  // the choice is offered only there — and only for a team, since the pod is
  // granted against the team's library.
  const canSynchronize = !onSubmit && !!teamId && !parentPath;
  const {
    data: definitions,
    isError: definitionsFailed,
    isLoading: definitionsLoading,
  } = useListKnowledgeBaseDefinitionsControlPlaneV1KnowledgeBasesDefinitionsGetQuery(
    { teamId: teamId ?? "" },
    { skip: !canSynchronize },
  );
  const { data: fields } = useGetDefinitionFieldsControlPlaneV1KnowledgeBasesDefinitionsDefinitionIdFieldsGetQuery(
    { definitionId, teamId: teamId ?? "" },
    { skip: !definitionId || !canSynchronize },
  );

  // Reset the field each time the modal opens (it mounts fresh, so the input's
  // autoFocus handles focus).
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
      ? "rework.resources.folderModal.definitionsLoading"
      : definitionsFailed
        ? "rework.resources.folderModal.definitionsFailed"
        : (definitions?.length ?? 0) === 0
          ? "rework.resources.folderModal.noDefinitions"
          : "rework.resources.folderModal.notSynchronized";
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
    for (const field of [...fields.platform_fields, ...fields.configuration_fields]) {
      if (field.default !== undefined && field.default !== null) defaults[field.key] = field.default;
    }
    setValues(defaults);
  }, [fields]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const trimmed = name.trim();
  const parentLeaf = parentPath?.split("/").filter(Boolean).pop();

  // Mirror the backend's TagCreate guards (#2355) so the user learns BEFORE
  // clicking Create, not from a 422 toast: a folder name is a single level
  // (no slashes — a slashed name would smuggle several levels past the depth
  // cap), and corpus folders stop nesting at MAX_FOLDER_DEPTH. The fs `mkdir`
  // variant (custom onSubmit) is not tag-backed, so the depth cap — a
  // ReBAC-chain constraint — doesn't apply there; the slash rule does.
  const nameHasSlash = trimmed.includes("/") || trimmed.includes("\\");
  const tooDeep = !onSubmit && folderPathDepth(parentPath) + 1 > MAX_FOLDER_DEPTH;
  const blocked = !trimmed || nameHasSlash || tooDeep;
  const inlineError = tooDeep
    ? t("rework.resources.folderModal.tooDeep", { max: MAX_FOLDER_DEPTH })
    : nameHasSlash
      ? t("rework.resources.folderModal.nameNoSlash")
      : undefined;

  const submit = async () => {
    if (blocked || isLoading || isCreatingInstance) return;
    try {
      if (definitionId) {
        // One call, not two: creating the library, the instance, the pod's
        // grant over that library and its cadence is one transaction on the
        // Control Plane's side, or none of them happens.
        const configuration = Object.fromEntries(
          (fields?.configuration_fields ?? [])
            .map((field) => [field.key, values[field.key]] as const)
            .filter(([, value]) => value !== undefined && value !== ""),
        );
        await createInstance({
          knowledgeBaseInstanceCreate: {
            definition_id: definitionId,
            team_id: teamId as string,
            folder_name: trimmed,
            cadence: values[CADENCE_KEY] as never,
            suspended: Boolean(values[SUSPENDED_KEY]),
            configuration,
          },
        }).unwrap();
      } else if (onSubmit) {
        await onSubmit(trimmed);
      } else {
        await createTag({
          tagCreate: {
            name: trimmed,
            path: parentPath ?? null,
            type: "document",
            team_id: teamId ?? null,
          },
        }).unwrap();
      }
      onCreated();
      onClose();
    } catch (e: unknown) {
      showError?.({
        summary: t("validation.error"),
        detail: (e as { data?: { detail?: string } })?.data?.detail ?? t("rework.resources.folderModal.error"),
      });
    }
  };

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onClose}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-folder-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.body}>
            <div className={styles.header}>
              <div>
                <p id="create-folder-title" className={styles.title}>
                  {t("rework.resources.folderModal.title")}
                </p>
                <p className={styles.context}>
                  {parentLeaf ? (
                    <>
                      {t("rework.resources.folderModal.inFolder")} <code className={styles.path}>{parentLeaf}</code> /
                    </>
                  ) : (
                    t("rework.resources.folderModal.atRoot")
                  )}
                </p>
              </div>
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
              label={t("rework.resources.folderModal.nameLabel")}
              placeholder={t("rework.resources.folderModal.namePlaceholder")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void submit();
              }}
            />
            {inlineError && (
              <p className={styles.inlineError} role="alert">
                {inlineError}
              </p>
            )}

            {/* Always shown where a synchronized folder is possible, even with
                nothing to offer: hiding it made "no Knowledge Base is enabled"
                and "the list could not be loaded" look identical — which cost a
                test run to tell apart. */}
            {canSynchronize && (
              <>
                <Select<string>
                  label={t("rework.resources.folderModal.synchronizedBy")}
                  options={definitionOptions}
                  value={definitionId}
                  onChange={setDefinitionId}
                  size="medium"
                  disabled={definitionsLoading || definitionsFailed || (definitions?.length ?? 0) === 0}
                />

                {/* Two zones, kept apart: what Fred declares and acts on, and
                    what the author declared, which Fred only carries. */}
                {fields &&
                  [
                    { legend: t("rework.resources.folderModal.zoneFred"), specs: fields.platform_fields },
                    { legend: t("rework.resources.folderModal.zoneSource"), specs: fields.configuration_fields },
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
                            disabled={isCreatingInstance}
                            teamId={teamId}
                            allValues={values}
                          />
                        ))}
                      </fieldset>
                    ),
                  )}
              </>
            )}
          </div>

          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="medium" onClick={onClose}>
              {t("rework.resources.folderModal.cancel")}
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={blocked || isLoading || isCreatingInstance}
              onClick={() => void submit()}
            >
              {t("rework.resources.folderModal.create")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
