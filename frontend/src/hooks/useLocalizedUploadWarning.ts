import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { UploadWarning } from "../slices/agentic/agenticOpenApi";
import { useFrontendProperties } from "./useFrontendProperties";

type LocalizedUploadWarning = {
  uploadWarning?: UploadWarning | null;
  uploadWarningMessage: string | null;
};

/**
 * Resolve the optional upload warning configured by the platform for the current locale.
 *
 * Document uploads and chat attachments both need to display the same
 * platform-managed banner without duplicating locale fallback logic.
 *
 * We can call this hook inside a React component, then render the alert
 * only when both `uploadWarning` and `uploadWarningMessage` are present.
 *
 */
export function useLocalizedUploadWarning(): LocalizedUploadWarning {
  const { i18n } = useTranslation();
  const { uploadWarning } = useFrontendProperties();

  return useMemo(
    () => ({
      uploadWarning,
      uploadWarningMessage: uploadWarning?.messages
        ? (uploadWarning.messages[i18n.language?.split("-")[0] ?? "en"] ?? uploadWarning.messages["en"] ?? null)
        : null,
    }),
    [i18n.language, uploadWarning],
  );
}
