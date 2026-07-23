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

import { useTranslation } from "react-i18next";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { useLocalizedUploadWarning } from "../../../../core/hooks/useLocalizedUploadWarning";

interface UploadWarningAckDialogProps {
  open: boolean;
  /** Called after the user accepted the notice — proceed with the pending files. */
  onConfirm: () => void;
  /** Called when the user dismissed the notice — drop the pending files. */
  onCancel: () => void;
}

/**
 * Blocking one-time acknowledgement of the deployer-configured upload warning.
 *
 * Why this component exists:
 * - chat attachments have no persistent surface where a passive banner would
 *   reliably be seen *before* the first file is attached, so the notice is
 *   shown as a dialog the user must accept once
 *   (`useUploadWarningAcknowledgement` persists the acceptance)
 * - reuses `ConfirmationDialog` so it looks like every other confirmation
 *
 * How to use it:
 * - open it when a file add is pending and `requiresAcknowledgement` is true;
 *   on confirm, call `acknowledge()` and proceed with the held files
 *
 * Example:
 * - `<UploadWarningAckDialog open={pending !== null} onConfirm={...} onCancel={...} />`
 */
export function UploadWarningAckDialog({ open, onConfirm, onCancel }: UploadWarningAckDialogProps) {
  const { t } = useTranslation();
  const { uploadWarningMessage } = useLocalizedUploadWarning();

  if (!uploadWarningMessage) return null;

  return (
    <ConfirmationDialog
      open={open}
      title={t("chatbot.attachments.uploadWarningTitle")}
      message={uploadWarningMessage}
      confirmLabel={t("chatbot.attachments.uploadWarningConfirm")}
      cancelLabel={t("common.cancel")}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
