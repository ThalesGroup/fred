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

import Icon from "@shared/atoms/Icon/Icon";
import type { IconType } from "@shared/utils/Type";
import { useLocalizedUploadWarning } from "../../../../core/hooks/useLocalizedUploadWarning";
import styles from "./UploadWarningBanner.module.css";

const severityIcons: Record<string, IconType> = {
  info: "info",
  warning: "warning",
  error: "error",
  success: "check_circle",
};

interface UploadWarningBannerProps {
  className?: string;
}

/**
 * Render the deployer-configured upload warning banner when one is available.
 *
 * Why this component exists:
 * - upload-related surfaces (document upload drawer, chat attachments) must
 *   share one banner so the notice stays visually consistent while locale
 *   resolution remains centralized in `useLocalizedUploadWarning`
 * - renders nothing when the deployment configures no warning — callers can
 *   place it unconditionally
 * - ported from the main-branch `UploadWarningAlert` (MIGR-01.01), restyled
 *   for the rework design system (no MUI)
 *
 * How to use it:
 * - place it where an upload warning should appear; pass `className` for
 *   local layout adjustments
 *
 * Example:
 * - `<UploadWarningBanner />`
 */
export default function UploadWarningBanner({ className }: UploadWarningBannerProps) {
  const { uploadWarning, uploadWarningMessage } = useLocalizedUploadWarning();

  if (!uploadWarning || !uploadWarningMessage) {
    return null;
  }

  const severity = uploadWarning.severity ?? "info";

  return (
    <div className={className ? `${styles.banner} ${className}` : styles.banner} data-severity={severity} role="alert">
      <span className={styles.icon} aria-hidden>
        <Icon category="outlined" type={severityIcons[severity] ?? "info"} />
      </span>
      <span className={styles.message}>{uploadWarningMessage}</span>
    </div>
  );
}
