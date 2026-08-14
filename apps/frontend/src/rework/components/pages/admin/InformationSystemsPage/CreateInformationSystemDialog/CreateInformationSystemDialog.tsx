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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import { useListAllTagsKnowledgeFlowV1TagsGetQuery } from "../../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import {
  useCreateInformationSystemRagsServicesV1InformationSystemPostMutation,
  type InformationSystemSummary,
} from "../../../../../../slices/rags/ragsOpenApi.ts";
import styles from "./CreateInformationSystemDialog.module.css";

interface CreateInformationSystemDialogProps {
  open: boolean;
  /** Current SI list — drives the "already has a system" exclusion below. */
  existingSystems: InformationSystemSummary[];
  onClose: () => void;
  onCreated: () => void;
}

/**
 * Create an Information System from an existing top-level document library
 * (a knowledge-flow tag). The SI's `information_system` name is ALWAYS set
 * to the chosen tag's name — never independently typed — because
 * `rags_agents/assessment/graph_steps.py`'s `identify_technical_documents_step`
 * re-resolves the target SI by exact string match against the library name;
 * any drift between the two makes Eva fail with "Système d'information
 * introuvable dans le résumé pour la librairie « X »" (found the hard way
 * setting this up manually — see #2307). Libraries that already back an SI
 * are excluded from the picker for the same reason the legacy modal did:
 * a second SI on the same library would silently create a second string that
 * must also match, doubling the failure surface for no benefit.
 */
export default function CreateInformationSystemDialog({
  open,
  existingSystems,
  onClose,
  onCreated,
}: CreateInformationSystemDialogProps) {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();

  const [selectedTagId, setSelectedTagId] = useState<string | undefined>(undefined);

  const { data: tags, isFetching: isLoadingTags } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: "document", limit: 200, offset: 0 },
    { skip: !open },
  );

  const [createInformationSystem, { isLoading: isCreating }] =
    useCreateInformationSystemRagsServicesV1InformationSystemPostMutation();

  const usedNames = new Set(existingSystems.map((system) => system.information_system.trim().toLowerCase()));

  // Top-level libraries only (no `path`, matching the legacy picker) that
  // aren't already the backing library of another SI.
  const availableTags = (tags ?? []).filter((tag) => !tag.path && !usedNames.has(tag.name.trim().toLowerCase()));

  useEffect(() => {
    if (!open) setSelectedTagId(undefined);
  }, [open]);

  const selectedTag = availableTags.find((tag) => tag.id === selectedTagId);

  const handleClose = () => {
    setSelectedTagId(undefined);
    onClose();
  };

  const handleConfirm = async () => {
    if (!selectedTag) return;
    await runMutationAction({
      action: () =>
        createInformationSystem({
          informationSystemWithoutUid: {
            information_system: selectedTag.name,
            library_tag_id: selectedTag.id,
          },
        }).unwrap(),
      onSuccess: () => {
        showSuccess({ summary: t("rework.informationSystems.create.success", { name: selectedTag.name }) });
        setSelectedTagId(undefined);
        onCreated();
      },
      onError: (error) =>
        notifyApiError(error, {
          summary: t("rework.informationSystems.create.errorSummary"),
          fallbackDetail: t("rework.informationSystems.create.errorFallback"),
          conflictDetail: t("rework.informationSystems.create.errorConflict"),
        }),
    });
  };

  const placeholder = isLoadingTags
    ? t("common.loading")
    : availableTags.length === 0
      ? t("rework.informationSystems.create.noLibraries")
      : t("rework.informationSystems.create.libraryPlaceholder");

  return (
    <Dialog
      open={open}
      title={t("rework.informationSystems.create.title")}
      confirmLabel={t("rework.informationSystems.create.submit")}
      onConfirm={handleConfirm}
      onCancel={handleClose}
      confirmDisabled={!selectedTag || isCreating}
    >
      <div className={styles.body}>
        <p className={styles.helperText}>{t("rework.informationSystems.create.helperText")}</p>
        <Select<string>
          label={t("rework.informationSystems.create.libraryLabel")}
          size="medium"
          value={selectedTagId}
          onChange={setSelectedTagId}
          placeholder={placeholder}
          disabled={isLoadingTags || availableTags.length === 0}
          options={availableTags.map((tag) => ({ value: tag.id, label: tag.name, key: tag.id }))}
        />
      </div>
    </Dialog>
  );
}
