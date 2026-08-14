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
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import DataTable, { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { Portal } from "@shared/utils/Portal.tsx";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useMutationAction } from "@core/hooks/useMutationAction.ts";
import {
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation,
  type DocumentMetadata,
} from "../../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import {
  useAddInformationSystemDocumentsMutation,
  useRemoveInformationSystemDocumentsMutation,
  type InformationSystemDocument,
  type InformationSystemSummary,
} from "../../../../../../slices/rags/ragsOpenApi.ts";
import styles from "./DocumentAssignmentModal.module.css";

/** The three roles `rags-services` recognises — kept as a local literal union
 *  since the wire format itself is a free-form `Record<string, ...>` (no
 *  generated enum to reuse; see rags-services' `DocumentRole` OpenAPI enum). */
export type DocumentRole = "DAT" | "MEX" | "CMDB";
const ROLES: DocumentRole[] = ["DAT", "MEX", "CMDB"];
/** Sentinel for "not assigned to this SI" — the Select needs a real option
 *  value distinct from every `DocumentRole`, since removing a row isn't a
 *  concept the "browse the whole library" table exposes directly. */
type RoleSelection = DocumentRole | "none";

interface DocumentAssignmentModalProps {
  open: boolean;
  system: InformationSystemSummary;
  onClose: () => void;
  onUpdated: () => void;
}

function flattenAssignedRoles(system: InformationSystemSummary): Map<string, DocumentRole> {
  const assigned = new Map<string, DocumentRole>();
  const docsByRole = system.documents ?? {};
  for (const role of ROLES) {
    for (const doc of docsByRole[role] ?? []) {
      assigned.set(doc.document_uid, role);
    }
  }
  return assigned;
}

/**
 * Browse the SI's backing library and assign each document a role
 * (DAT/MEX/CMDB, or none). `rags-services` has no per-document PATCH, only
 * "add these role assignments" / "remove these role assignments" — so saving
 * an edit means diffing the working selection against the assignment the SI
 * had when the modal opened (mirrors the legacy
 * `EditInformationSystemDocumentsModal`'s remove-then-add, but as a genuine
 * diff rather than blindly removing and re-adding every document):
 *
 * - a document whose role didn't change is left out of BOTH calls entirely.
 * - a document that gained/changed/lost a role contributes to `add` (its new
 *   role, if any) and/or `remove` (its old role, if any) — never the same
 *   role in both, so the two calls can never race each other.
 *
 * That makes it safe to call ADD before REMOVE: if the network drops after
 * add succeeds but before remove runs, the worst case is a document that
 * temporarily keeps an old role alongside its new one (recoverable by
 * reopening and saving again) instead of the reverse ordering's failure mode
 * — remove succeeds, add then fails, and the document silently loses a role
 * assignment the user never intended to remove.
 */
export default function DocumentAssignmentModal({ open, system, onClose, onUpdated }: DocumentAssignmentModalProps) {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { runMutationAction } = useMutationAction();

  const [browseDocumentsByTag, { data: browseResult, isLoading: isLoadingDocuments }] =
    useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation();
  const [addInformationSystemDocuments, { isLoading: isAdding }] = useAddInformationSystemDocumentsMutation();
  const [removeInformationSystemDocuments, { isLoading: isRemoving }] = useRemoveInformationSystemDocumentsMutation();

  // The assignment this SI actually had when the modal opened — the baseline
  // the "remove" half of save must undo. Recomputed only when a fresh
  // `system` is opened, not on every render, so in-flight edits below aren't
  // clobbered by the summary list's own refetches while the modal is open.
  const initialAssignment = useMemo(() => flattenAssignedRoles(system), [system.information_system_uid]); // eslint-disable-line react-hooks/exhaustive-deps
  const [roleByDocUid, setRoleByDocUid] = useState<Map<string, RoleSelection>>(initialAssignment);

  useEffect(() => {
    if (!open) return;
    setRoleByDocUid(new Map(initialAssignment));
    void browseDocumentsByTag({
      browseDocumentsByTagRequest: { tag_id: system.library_tag_id, offset: 0, limit: 200 },
    });
    // Re-run whenever a different SI is opened, or the modal reopens for the same one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, system.information_system_uid]);

  // Matches every other dialog in the app (Dialog.tsx, ConfirmationDialog.tsx,
  // CreateInformationSystemDialog's shared Dialog) — this one hand-rolls its
  // chrome instead of reusing that molecule (needs a wide, scrollable
  // DataTable body Dialog's fixed 400px shell can't fit), so it must still
  // pick up Escape-to-close by hand to stay consistent for the user.
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const documents: DocumentMetadata[] = browseResult?.documents ?? [];

  const roleOptions: { value: RoleSelection; label: string; key: string }[] = [
    { value: "none", label: t("rework.informationSystems.assignDocuments.roleNone"), key: "none" },
    ...ROLES.map((role) => ({ value: role, label: role, key: role })),
  ];

  const setRole = (documentUid: string, role: RoleSelection) => {
    setRoleByDocUid((prev) => {
      const next = new Map(prev);
      next.set(documentUid, role);
      return next;
    });
  };

  const columns: DataTableColumn<DocumentMetadata>[] = [
    {
      label: t("rework.informationSystems.assignDocuments.document"),
      size: "2fr",
      cellRenderer: (doc) => (
        <span className={styles.documentName} title={doc.identity.document_name}>
          {doc.identity.document_name}
        </span>
      ),
    },
    {
      label: t("rework.informationSystems.assignDocuments.role"),
      size: "10rem",
      cellRenderer: (doc) => (
        <Select<RoleSelection>
          size="small"
          compact
          value={roleByDocUid.get(doc.identity.document_uid) ?? "none"}
          onChange={(role) => setRole(doc.identity.document_uid, role)}
          options={roleOptions}
        />
      ),
    },
  ];

  const handleClose = () => {
    onClose();
  };

  const handleSave = async () => {
    // Diff against the assignment the SI had when the modal opened — a
    // document whose role is unchanged contributes to neither call (see the
    // component doc comment for why that's what makes add-before-remove safe).
    const touchedDocUids = new Set([...initialAssignment.keys(), ...roleByDocUid.keys()]);
    const removeByRole: Record<string, string[]> = {};
    const addByRole: Record<string, InformationSystemDocument[]> = {};
    for (const documentUid of touchedDocUids) {
      const oldRole = initialAssignment.get(documentUid);
      const newRole = roleByDocUid.get(documentUid) ?? "none";
      if (oldRole === newRole) continue;
      if (oldRole !== undefined) {
        (removeByRole[oldRole] ??= []).push(documentUid);
      }
      if (newRole !== "none") {
        const name = documents.find((doc) => doc.identity.document_uid === documentUid)?.identity.document_name;
        (addByRole[newRole] ??= []).push({ document_uid: documentUid, document_name: name ?? null });
      }
    }

    await runMutationAction({
      action: async () => {
        if (Object.keys(addByRole).length > 0) {
          await addInformationSystemDocuments({
            informationSystemUid: system.information_system_uid,
            informationSystemDocumentsAdd: { documents: addByRole },
          }).unwrap();
        }
        if (Object.keys(removeByRole).length > 0) {
          await removeInformationSystemDocuments({
            informationSystemUid: system.information_system_uid,
            informationSystemDocumentsRemove: { documents: removeByRole },
          }).unwrap();
        }
      },
      onSuccess: () => {
        showSuccess({ summary: t("rework.informationSystems.assignDocuments.success") });
        onUpdated();
      },
      onError: (error) =>
        notifyApiError(error, {
          summary: t("rework.informationSystems.assignDocuments.errorSummary"),
          fallbackDetail: t("rework.informationSystems.assignDocuments.errorFallback"),
        }),
    });
  };

  const isSaving = isAdding || isRemoving;

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={handleClose}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby="document-assignment-modal-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.header}>
            <div>
              <p id="document-assignment-modal-title" className={styles.title}>
                {t("rework.informationSystems.assignDocuments.title", { name: system.information_system })}
              </p>
              <p className={styles.subtitle}>{t("rework.informationSystems.assignDocuments.subtitle")}</p>
            </div>
            <IconButton
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "close" }}
              aria-label={t("common.cancel")}
              onClick={handleClose}
            />
          </div>
          <div className={styles.body}>
            {isLoadingDocuments ? (
              <div className={styles.loadingState}>
                <Spinner size={20} />
                {t("common.loading")}
              </div>
            ) : documents.length === 0 ? (
              <div className={styles.emptyState}>{t("rework.informationSystems.assignDocuments.empty")}</div>
            ) : (
              <DataTable columns={columns} data={documents} rowKey={(doc) => doc.identity.document_uid} pageSize={20} />
            )}
          </div>
          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="medium" onClick={handleClose}>
              {t("common.cancel")}
            </Button>
            <Button color="primary" variant="filled" size="medium" disabled={isSaving} onClick={handleSave}>
              {t("common.save")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
