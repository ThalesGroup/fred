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

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendBootstrap } from "../../../hooks/useFrontendBootstrap";
import type { UploadWarning } from "../../../slices/controlPlane/controlPlaneOpenApi";

type LocalizedUploadWarning = {
  uploadWarning: UploadWarning | null;
  uploadWarningMessage: string | null;
};

/**
 * Resolve the warning message for an i18next language tag ("fr-FR" → "fr"),
 * falling back to "en", then to nothing (banner hidden).
 *
 * Exported separately so the fallback contract is unit-testable without
 * mocking the bootstrap query or i18next.
 */
export function resolveUploadWarningMessage(
  uploadWarning: UploadWarning | null,
  language: string | undefined,
): string | null {
  if (!uploadWarning?.messages) return null;
  return uploadWarning.messages[language?.split("-")[0] ?? "en"] ?? uploadWarning.messages["en"] ?? null;
}

/**
 * Resolve the deployer-configured upload warning for the current locale.
 *
 * Why this hook exists:
 * - document uploads and chat attachments both display the same
 *   platform-managed banner (`platform.frontend.upload_warning`, served on
 *   `/frontend/bootstrap`) and must not duplicate locale fallback logic
 * - ported from the main-branch `useLocalizedUploadWarning` (MIGR-01.01),
 *   re-sourced from the control-plane bootstrap instead of agentic-backend
 *   properties
 *
 * How to use it:
 * - call inside a component, render the banner only when both `uploadWarning`
 *   and `uploadWarningMessage` are non-null — `UploadWarningBanner` does this
 *
 * Example:
 * - `const { uploadWarning, uploadWarningMessage } = useLocalizedUploadWarning();`
 */
export function useLocalizedUploadWarning(): LocalizedUploadWarning {
  const { i18n } = useTranslation();
  const { bootstrap } = useFrontendBootstrap();
  const uploadWarning = bootstrap?.upload_warning ?? null;

  return useMemo(
    () => ({
      uploadWarning,
      uploadWarningMessage: resolveUploadWarningMessage(uploadWarning, i18n.language),
    }),
    [i18n.language, uploadWarning],
  );
}
