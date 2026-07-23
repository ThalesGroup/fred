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

import { useCallback } from "react";
import { useLocalStorageState } from "../../../hooks/useLocalStorageState";
import type { UploadWarning } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { useLocalizedUploadWarning } from "./useLocalizedUploadWarning";

type UploadWarningAcknowledgement = {
  /** True when a warning is configured and this browser has not acknowledged it yet. */
  requiresAcknowledgement: boolean;
  /** Persist the acknowledgement so the dialog is not shown again. */
  acknowledge: () => void;
};

/**
 * Stable signature of the configured warning, locale-independent.
 *
 * Exported separately so the re-prompt contract is unit-testable: an
 * acknowledgement is stored against this signature, so editing the warning in
 * deployment config (message or severity) re-prompts every user, while a mere
 * UI locale switch does not.
 */
export function uploadWarningSignature(uploadWarning: UploadWarning): string {
  return JSON.stringify({ severity: uploadWarning.severity ?? "info", messages: uploadWarning.messages ?? {} });
}

/**
 * One-time acknowledgement of the deployer-configured upload warning.
 *
 * Why this hook exists:
 * - chat attachments show the warning as a blocking dialog on the first file
 *   add (unlike the passive banner on the document upload drawer), and that
 *   dialog must not re-appear once acknowledged
 * - the acknowledgement is per-browser (localStorage), keyed on the warning
 *   content — a deployer changing the notice re-prompts everyone
 *
 * How to use it:
 * - when `requiresAcknowledgement` is true, hold the pending files and open
 *   `UploadWarningAckDialog`; call `acknowledge()` on confirm, then proceed
 *
 * Example:
 * - `const { requiresAcknowledgement, acknowledge } = useUploadWarningAcknowledgement();`
 */
export function useUploadWarningAcknowledgement(): UploadWarningAcknowledgement {
  const { uploadWarning, uploadWarningMessage } = useLocalizedUploadWarning();
  const [acknowledgedSignature, setAcknowledgedSignature] = useLocalStorageState<string | null>(
    "uploadWarningAck",
    null,
  );

  const signature = uploadWarning ? uploadWarningSignature(uploadWarning) : null;
  const acknowledge = useCallback(() => setAcknowledgedSignature(signature), [setAcknowledgedSignature, signature]);

  return {
    requiresAcknowledgement: uploadWarningMessage !== null && signature !== acknowledgedSignature,
    acknowledge,
  };
}
